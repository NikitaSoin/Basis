"""Ловим «выплаты», которых не было: дивиденд без дивидендного гэпа.

🔴 ЗАЧЕМ. Проверка десяти расхождений (2026-08-09) вскрыла системный дефект
ИСТОЧНИКА, а не наш: `iss.moex.com/iss/securities/<T>/dividends.json` отдаёт в
одном ряду с состоявшимися выплатами РЕКОМЕНДАЦИИ совета директоров, которые
собрание акционеров не утвердило. Мы честно грузим ряд целиком — и получаем
выплаты-фантомы. Три подтверждённых случая на одну дату-другую: РусГидро
(0,0756 ₽, реестр 11.07.2025 — ГОСА решения не приняло), Мосэнерго (0,22606 ₽,
08.07.2025 — та же история), ТГК-1 (0,000829 ₽, 08.07.2025 — собрание решило не
объявлять). Опасность не в самой строке, а в том, что дальше она молча правит
карточку: сверка «рекомендация стала фактом» пометила бы год выплаченным.

🔴 КАК ЛОВИМ БЕЗ ВЕБА И БЕЗ LLM. Настоящая выплата оставляет след в цене: в день
отсечки бумага дешевеет примерно на размер дивиденда — деньги ушли из компании.
Фантом следа не оставляет. На живых данных разница видна невооружённым глазом:
у Сургутнефтегаза при ожидаемых 3,9% падение составило 5,2%, а у трёх фантомов
при ожидаемых 11-17% — от 0,9% до 1,7%, то есть обычный рыночный шум.

🔴 ГРАНИЦЫ МЕТОДА, О КОТОРЫХ НАДО ПОМНИТЬ.
1. Работает только на заметных выплатах. При ожидаемом гэпе меньше порога шум
   рынка перекрывает эффект — такие строки не судим вовсе, а не «признаём».
2. Гэп ищем как МАКСИМАЛЬНОЕ дневное падение в окне из ЧЕТЫРЁХ ТОРГОВЫХ дней,
   заканчивающемся сразу после отсечки. Окно именно торговое, а не календарное:
   до конца июля 2023 биржа рассчитывалась в режиме T+2, и экс-дата отстояла от
   отсечки на два торговых дня — через выходные это до четырёх календарных, и
   календарное окно её теряло. Так под подозрение попал Сбербанк с заведомо
   настоящей выплатой октября 2020 года.
3. Наблюдаемый гэп МЕНЬШЕ дивиденда — рынок частично отыгрывает отсечку заранее.
   На настоящих выплатах Сбербанка он составил 45-62% от размера дивиденда, у
   подтверждённых фантомов — 5-20%. Отсюда порог: подозрительно, если падение не
   дотянуло до трети ожидаемого.
3. Сильное падение рынка в тот же день может замаскировать отсутствие гэпа —
   поэтому это ДЕТЕКТОР ПОДОЗРЕНИЙ, а не приговор. Каждый флаг проверяется
   решением собрания акционеров, и только потом строка удаляется.
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# 🔴 Ниже этого ожидаемого гэпа НЕ СУДИМ ВОВСЕ. Порог поднят с 3% до 8% по факту
# проверки на живых данных, а не «на всякий случай»: в полосе 3-6% детектор ровно
# так же уверенно обвинял заведомо настоящие выплаты (Татнефть 27,71 ₽, Полюс
# 436,79 ₽, Сургутнефтегаз 0,85 ₽) — их гэп тонет в дневном шуме и в неточности
# даты отсечки на день-два. Все ЧЕТЫРЕ независимо подтверждённых фантома имеют
# ожидаемый гэп 10-18%, то есть настоящий сигнал живёт выше порога. Проверка,
# которая одинаково громко кричит на правду и на ложь, бесполезнее молчания.
MIN_EXPECTED_PCT = 8.0
# доля ожидаемого гэпа, ниже которой выплата подозрительна (см. п.3 выше)
GAP_RATIO_FLAG = 0.30


def _sql_all(q_tpl: str, page: int = 180) -> list[dict]:
    """Выбрать ВСЁ постранично.

    🔴 Отладочный эндпоинт молча режет выдачу: на запрос за 503 строки он отдал 200
    и выставил флаг «усечено», которого никто не читал. Проверка при этом печатала
    бы бодрое «строк всего: 200» — и две трети таблицы остались бы непроверенными
    без единого признака, что что-то пропущено. Поэтому листаем сами и на всякий
    случай кричим, если страница вернулась усечённой.
    """
    out: list[dict] = []
    offset = 0
    while True:
        chunk = _sql(q_tpl + f" LIMIT {page} OFFSET {offset}")
        out.extend(chunk)
        if len(chunk) < page:
            return out
        offset += page
        if offset > 100_000:  # предохранитель от бесконечного листания
            print("⚠️  листание прервано на 100 000 строк")
            return out


def _sql(q: str) -> list[dict]:
    base = "https://nikitasoin-basis-a772.twc1.net"
    tok = ""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEBUG_API_TOKEN="):
                tok = line.split("=", 1)[1].strip()
                break
    url = f"{base}/api/debug/sql?q={urllib.parse.quote(q)}"
    req = urllib.request.Request(url, headers={"X-Debug-Token": tok})
    with urllib.request.urlopen(req, timeout=180, context=_ctx) as r:
        data = json.loads(r.read())
    if data.get("усечено"):
        print(f"⚠️  выдача усечена на {len(data.get('строки') or [])} строках — "
              f"листаем дальше")
    return data.get("строки") or []


# 🔴 Гэп меряем ОТНОСИТЕЛЬНО РЫНКА, а не в абсолюте. Иначе всё зависит от того,
# какой был день: на растущем рынке настоящая отсечка выглядит слабее, чем есть, и
# честная выплата попадает в подозрительные. Вычитаем дневное движение IMOEX —
# остаётся то, что произошло ИМЕННО с бумагой.
QUERY = """
WITH mkt AS (
  SELECT date,
         (close / lag(close) OVER (ORDER BY date) - 1) * 100 AS pct
  FROM index_history WHERE ticker = 'IMOEX'
)
SELECT d.ticker, d.record_date::text AS record_date, d.amount::float8 AS amount,
  (SELECT q.close::float8 FROM quotes q JOIN companies c ON c.id = q.company_id
     WHERE c.ticker = d.ticker AND q.date < d.record_date
     ORDER BY q.date DESC LIMIT 1) AS prev_close,
  (SELECT min(w.change_pct)::float8 FROM (
     SELECT q.change_pct FROM quotes q JOIN companies c ON c.id = q.company_id
      WHERE c.ticker = d.ticker AND q.date <= d.record_date + 1
      ORDER BY q.date DESC LIMIT 4) w) AS worst_raw_pct,
  (SELECT min(w.rel)::float8 FROM (
     SELECT (q.change_pct - COALESCE(mkt.pct, 0)) AS rel
       FROM quotes q JOIN companies c ON c.id = q.company_id
       LEFT JOIN mkt ON mkt.date = q.date
      WHERE c.ticker = d.ticker AND q.date <= d.record_date + 1
      ORDER BY q.date DESC LIMIT 4) w) AS worst_rel_pct
FROM dividends d
WHERE d.record_date >= DATE '{since}'
ORDER BY d.record_date DESC
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2019-01-01")
    ap.add_argument("--json", help="куда записать находки")
    args = ap.parse_args()

    rows = _sql_all(QUERY.format(since=args.since))
    judged, flagged, skipped_small, no_price = 0, [], 0, 0
    for r in rows:
        prev, amt = r.get("prev_close"), r.get("amount")
        # 🔴 Берём ЛУЧШИЙ из двух замеров — сырой и очищенный от движения рынка.
        # Поправка на индекс задумана против ложных обвинений на растущем рынке, но
        # в день общего ОБВАЛА она работает наоборот: вычитая падение индекса, мы
        # стираем настоящий гэп и обвиняем честную выплату (так под подозрение попала
        # Северсталь: сырое падение 3,6% при ожидаемых 4,7% — гэп на месте, а после
        # вычитания рухнувшего индекса от него осталось 1,8%). Презумпция в пользу
        # «выплата была»: достаточно, чтобы гэп нашёлся ХОТЯ БЫ ОДНИМ способом.
        cands = [v for v in (r.get("worst_raw_pct"), r.get("worst_rel_pct")) if v is not None]
        worst = min(cands) if cands else None
        if not prev or not amt or worst is None:
            no_price += 1
            continue
        expected = amt / prev * 100.0
        if expected < MIN_EXPECTED_PCT:
            skipped_small += 1
            continue
        judged += 1
        drop = -float(worst)  # worst_day_pct отрицателен у падения
        if drop < expected * GAP_RATIO_FLAG:
            flagged.append({
                "ticker": r["ticker"], "record_date": r["record_date"],
                "amount": round(amt, 6), "price": round(prev, 4),
                "expected_gap_pct": round(expected, 2),
                "actual_worst_drop_pct": round(drop, 2),
            })

    print(f"строк всего: {len(rows)} | судимо: {judged} | "
          f"мелких (не судим): {skipped_small} | без цены: {no_price}")
    print(f"🔴 ПОДОЗРИТЕЛЬНЫХ (гэпа нет при заметном дивиденде): {len(flagged)}")
    for f in sorted(flagged, key=lambda x: x["record_date"], reverse=True):
        print(f"   {f['ticker']:8} {f['record_date']}  {f['amount']:>12.6f} ₽ "
              f"при цене {f['price']:>10.4f} — ждали −{f['expected_gap_pct']:.1f}%, "
              f"было −{f['actual_worst_drop_pct']:.1f}%")
    if args.json:
        Path(args.json).write_text(
            json.dumps({"flagged": flagged, "judged": judged}, ensure_ascii=False,
                       indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
