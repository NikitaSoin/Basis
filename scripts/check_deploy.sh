#!/usr/bin/env bash
# =============================================================================
# ПРОВЕРКА ДЕПЛОЯ НА БОЮ — единственный правильный способ.
#
# Зачем скрипт, а не «curl + grep руками». За один день проверка деплоя соврала
# ТРИЖДЫ, каждый раз по-новому:
#   1) греп бандла по СЛОВУ дал «доехало», хотя слово было там от прошлого
#      выката (2026-07-30, Decision-rail; повтор 2026-08-02 с чужой правкой);
#   2) `asset-manifest.json` без cache-buster отдавался ИЗ КЭША — я больше часа
#      докладывал «деплой не доехал», хотя он доехал (2026-08-02);
#   3) 404 на новом эндпоинте принимался за «бэк не пересобрался», хотя мог
#      означать сменившийся адрес API или отсутствие данных в боевой БД.
# Каждая из ошибок выглядела как достоверный результат. Поэтому проверка должна
# быть одной командой с фиксированным протоколом, а не импровизацией.
#
# ИСПОЛЬЗОВАНИЕ:
#   scripts/check_deploy.sh "маркер1" "маркер2" ...          # ждать появления
#   scripts/check_deploy.sh --once "маркер1"                 # один замер
#   scripts/check_deploy.sh --gone "старое" --new "новое"    # смена поведения
#
# Маркер — СТРОКА, КОТОРУЮ ДОБАВИЛ ТЫ САМ в этой правке (класс, текст кнопки).
# Не бери слово, которое могло быть в бандле раньше: имя вкладки, общий термин,
# label из константы, которая осталась в коде. Если правка меняет ЛОГИКУ, а не
# текст, — маркер бесполезен, нужен прогон Playwright по бою.
# =============================================================================
set -uo pipefail

SITE="${BASIS_SITE:-https://inbasis.ru}"
API="${BASIS_API:-https://nikitasoin-basis-a772.twc1.net}"
INTERVAL="${INTERVAL:-60}"
MAX_TRIES="${MAX_TRIES:-15}"

ONCE=0; GONE=""; MARKERS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1; shift;;
    --gone) GONE="$2"; shift 2;;
    --new)  MARKERS+=("$2"); shift 2;;
    *)      MARKERS+=("$1"); shift;;
  esac
done

if [ ${#MARKERS[@]} -eq 0 ]; then
  echo "Укажи хотя бы один маркер (строку, которую ты сам добавил)." >&2
  exit 2
fi

# Бандл берём из index.html, а НЕ из asset-manifest.json: манифест кэшируется
# отдельно и способен отставать от реально подключённого бандла. Cache-buster
# обязателен обоим — именно из-за кэша проверка врала час.
live_bundle() {
  cb=$(date +%s%N)
  curl -s --max-time 25 -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' \
       "$SITE/?cb=$cb" 2>/dev/null | grep -o 'main\.[a-z0-9]*\.js' | head -1
}

check_once() {
  bundle=$(live_bundle)
  if [ -z "$bundle" ]; then
    echo "  ✕ не удалось прочитать index.html — сайт недоступен?"
    return 1
  fi
  cb=$(date +%s%N)
  tmp=$(mktemp)
  curl -s --max-time 90 -H 'Cache-Control: no-cache' \
       "$SITE/static/js/$bundle?cb=$cb" 2>/dev/null > "$tmp"
  size=$(wc -c < "$tmp")
  if [ "$size" -lt 100000 ]; then
    echo "  ✕ бандл $bundle скачался обрезанным ($size байт) — не верить результату"
    rm -f "$tmp"; return 1
  fi

  # Две ловушки bash 3.2 (штатный на macOS), обе воспроизведены здесь:
  #  • повторный `local n` в теле for рушит имя переменной;
  #  • `«$m»` разбирается как $m» — байты типографской кавычки считаются
  #    продолжением имени переменной, отсюда «unbound variable». Нужны ${...}.
  all_ok=1
  line="  бандл $bundle ($((size/1024)) КБ):"
  for m in "${MARKERS[@]}"; do
    n=$(grep -c -- "$m" "$tmp")
    if [ "$n" -gt 0 ]; then line="$line  ✓ «${m}»"; else line="$line  ✕ «${m}»"; all_ok=0; fi
  done
  if [ -n "$GONE" ]; then
    n=$(grep -c -- "$GONE" "$tmp")
    # Контроль: старая строка ОБЯЗАНА исчезнуть. Без него нельзя отличить
    # «доехало» от «эти слова и так были в бандле».
    if [ "$n" -eq 0 ]; then line="$line  ✓ старое ушло"; else line="$line  ✕ старое «${GONE}» ещё на месте"; all_ok=0; fi
  fi
  echo "$line"
  rm -f "$tmp"
  return $((1 - all_ok))
}

echo "Сайт: $SITE"
echo "Маркеры: ${MARKERS[*]}${GONE:+  | должно исчезнуть: $GONE}"

if [ "$ONCE" -eq 1 ]; then
  check_once; exit $?
fi

for i in $(seq 1 "$MAX_TRIES"); do
  echo "[$i/$MAX_TRIES]"
  if check_once; then
    echo "ДОЕХАЛО."
    exit 0
  fi
  [ "$i" -lt "$MAX_TRIES" ] && sleep "$INTERVAL"
done

echo "НЕ ДОЕХАЛО за $((MAX_TRIES * INTERVAL / 60)) мин."
echo "Прежде чем говорить «деплой сломан», проверь:"
echo "  • адрес API не сменился (CLAUDE.md: меняется при пересоздании приложения)"
echo "     curl -s -o /dev/null -w '%{http_code}' $API/api/market/geo-barometer"
echo "  • билд вообще стартовал (Timeweb уже переставал их стартовать при частых пушах)"
echo "  • маркер действительно НОВЫЙ — не строка, которая была в бандле раньше"
exit 1
