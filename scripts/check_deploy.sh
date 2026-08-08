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
#      означать сменившийся адрес API или отсутствие данных в боевой БД;
#   4) греп ТОЛЬКО по main.js давал ✕ на правке экрана, вынесенного в ленивый
#      чанк (2026-08-08, стресс-тест: маркеры лежали в 699.<hash>.chunk.js, а
#      деплой был полностью доехавшим) — теперь скрипт при промахе идёт в чанки.
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

# Ленивые чанки. Экраны, вынесенные в отдельный bundle (React.lazy) — стресс-тест
# и другие тяжёлые разделы — в main.js НЕ попадают: там лежит только таблица
# хэшей вида {699:"02443a35"}. Греп по main.js на такой правке печатает
# убедительное ✕ при ПОЛНОСТЬЮ доехавшем деплое (обожглись 2026-08-08: маркеры
# нового блока стресс-теста «отсутствовали», хотя лежали в 699.<hash>.chunk.js).
# Поэтому: не нашли маркер в main.js — идём в чанки, собрав их имена из этой же
# таблицы. Скачиваем только по требованию: в обычном случае это лишние ~20 запросов.
CHUNK_DIR=""
fetch_chunks() {   # $1 — скачанный main.js; печатает пути скачанных чанков
  [ -n "$CHUNK_DIR" ] && { ls "$CHUNK_DIR"/* 2>/dev/null; return 0; }
  CHUNK_DIR=$(mktemp -d)
  grep -ao '[0-9]\{2,4\}:"[a-f0-9]\{6,10\}"' "$1" | sort -u | while IFS= read -r pair; do
    cid=${pair%%:*}; chash=${pair#*:\"}; chash=${chash%\"}
    for ext in js css; do
      f="$CHUNK_DIR/$cid.$chash.$ext"
      code=$(curl -s -o "$f" -w '%{http_code}' --max-time 30 \
             "$SITE/static/$ext/$cid.$chash.chunk.$ext" 2>/dev/null)
      # SPA отдаёт index.html с кодом 200 на ЛЮБОЙ несуществующий путь (у чанка
      # только одно расширение из двух) — такую «страницу» в корпус пускать нельзя,
      # иначе маркер найдётся в разметке оболочки и проверка соврёт в плюс.
      if [ "$code" = "200" ] && [ "$(wc -c < "$f")" -gt 500 ] \
         && ! head -c 20 "$f" | grep -qi '<!doctype\|<html'; then echo "$f"; else rm -f "$f"; fi
    done
  done
}

in_chunks() {      # $1 — маркер, $2 — main.js. 0 = нашли хотя бы в одном чанке
  files=$(fetch_chunks "$2")
  [ -z "$files" ] && return 1
  # 🔴 БЕЗ конвейера намеренно: `... | grep -q` при `set -o pipefail` возвращает
  # 141 (SIGPIPE левой части, которую grep обрывает по первому совпадению), и
  # найденный маркер читается как «не найден». Потеряно полчаса на ровном месте.
  _saved_ifs=$IFS; IFS='
'
  for f in $files; do
    if grep -qa -- "$1" "$f"; then IFS=$_saved_ifs; return 0; fi
  done
  IFS=$_saved_ifs
  return 1
}

check_once() {
  CHUNK_DIR=""
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
    n=$(grep -ca -- "$m" "$tmp")
    if [ "$n" -gt 0 ]; then
      line="$line  ✓ «${m}»"
    elif in_chunks "$m" "$tmp"; then
      line="$line  ✓ «${m}» (в чанке)"
    else
      line="$line  ✕ «${m}»"; all_ok=0
    fi
  done
  if [ -n "$GONE" ]; then
    # Контроль: старая строка ОБЯЗАНА исчезнуть. Без него нельзя отличить
    # «доехало» от «эти слова и так были в бандле». Чанки проверяем тоже —
    # иначе «ушло» соврёт ровно там же, где врал греп по main.js.
    n=$(grep -ca -- "$GONE" "$tmp")
    if [ "$n" -eq 0 ] && ! in_chunks "$GONE" "$tmp"; then
      line="$line  ✓ старое ушло"
    else
      line="$line  ✕ старое «${GONE}» ещё на месте"; all_ok=0
    fi
  fi
  echo "$line"
  rm -f "$tmp"
  [ -n "$CHUNK_DIR" ] && rm -rf "$CHUNK_DIR"
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
