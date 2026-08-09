#!/usr/bin/env python3
"""Извлечение текста из отчётности в PDF, с распознаванием сканов.

🔴 ЗАЧЕМ. Раз за разом добытчики упирались в одно и то же: отчёт найден и скачан, но
`pdftotext` возвращает пустоту — и это записывалось как «данных нет». На деле у части
эмитентов отчётность выложена КАРТИНКОЙ (ЭЛ5-Энерго, НОВАТЭК, Юнипро — проверено), и
пустой текстовый слой означает лишь «нужно распознать», а не «источник недоступен».

Логика: сначала обычный текстовый слой (быстро и точно). Если страница пустая —
рендерим её и распознаём. Распознавание медленное, поэтому по умолчанию оно включается
ТОЛЬКО для страниц, которые прошли фильтр --grep: искать баланс постранично дешевле,
чем распознавать двести страниц целиком.

Примеры:
  # где в отчёте баланс — по оглавлению текстового слоя
  python3 backend/scripts/pdf_extract.py отчёт.pdf --grep "Итого активы"
  # распознать конкретные страницы (нумерация с 1)
  python3 backend/scripts/pdf_extract.py отчёт.pdf --pages 8-10 --ocr
  # найти страницу с балансом даже в скане: распознаём по одной, пока не совпадёт
  python3 backend/scripts/pdf_extract.py отчёт.pdf --find "Итого внеоборотные" --ocr --max-pages 20
  # таблица, где подписи слева, а числа у правого края — собирать строки по координатам
  python3 backend/scripts/pdf_extract.py отчёт.pdf --pages 6 --ocr --table

🔴 Числа, снятые распознаванием, ОБЯЗАТЕЛЬНО проверяй арифметикой (разделы = итог,
активы = обязательства + капитал). Распознавание путает 0/О, 3/8 и теряет пробелы в
разрядах; арифметика ловит это мгновенно, а глаз — нет.
"""
import argparse
import io
import sys


def parse_pages(spec, total):
    if not spec:
        return list(range(total))
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a) - 1, int(b)))
        else:
            out.append(int(part) - 1)
    return [p for p in out if 0 <= p < total]


def ocr_page(page, lang="rus", dpi=200, table=False):
    """table=True — собирать строку из слов по их координатам.

    🔴 Зачем отдельный режим. В отчётности подпись строки стоит у левого края, а числа —
    у правого, и обычное распознавание выдаёт их РАЗНЫМИ строками: получается столбик
    подписей, а следом столбик чисел, и сопоставить их уже нельзя. На балансе ЧМК это
    выглядело как «Итого капитал» без единой цифры рядом. Сборка по вертикальной
    координате возвращает строку целиком: «Итого капитал 61 744 363 55 939 180».
    """
    import pytesseract
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    if not table:
        return pytesseract.image_to_string(img, lang=lang)
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    rows = {}
    for i, word in enumerate(data["text"]):
        if not word.strip() or int(data["conf"][i]) < 30:
            continue
        rows.setdefault(round(data["top"][i] / 12), []).append((data["left"][i], word))
    return "\n".join(" ".join(w for _, w in sorted(v)) for _, v in sorted(rows.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", help="страницы, напр. 8-10 или 3,7,9 (с 1)")
    ap.add_argument("--grep", help="печатать только страницы, где текстовый слой содержит эту строку")
    ap.add_argument("--find", help="искать строку, распознавая страницы по одной, и остановиться на первой найденной")
    ap.add_argument("--ocr", action="store_true", help="распознавать страницы без текстового слоя")
    ap.add_argument("--max-pages", type=int, default=25, help="предел числа распознаваемых страниц")
    ap.add_argument("--table", action="store_true", help="собирать строки по координатам слов — для таблиц, где подписи слева, а числа справа")
    ap.add_argument("--lang", default="rus")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    try:
        import fitz
    except ImportError:
        sys.exit("нужен pymupdf: pip install pymupdf")

    doc = fitz.open(args.pdf)
    pages = parse_pages(args.pages, len(doc))
    layer = sum(len(doc[i].get_text().strip()) for i in pages)
    print(f"# {args.pdf}: страниц {len(doc)}, текстового слоя на выбранных {layer} символов", file=sys.stderr)
    if layer == 0 and not args.ocr:
        print("# текстового слоя нет — это скан. Повтори с --ocr", file=sys.stderr)

    ocr_used = 0
    for i in pages:
        text = doc[i].get_text()
        if not text.strip() and args.ocr and ocr_used < args.max_pages:
            text = ocr_page(doc[i], args.lang, args.dpi, args.table)
            ocr_used += 1
        if args.find:
            if args.find.lower() in text.lower():
                print(f"===== страница {i+1} (найдено «{args.find}»)")
                print(text)
                return
            continue
        if args.grep and args.grep.lower() not in text.lower():
            continue
        if text.strip():
            print(f"===== страница {i+1}")
            print(text)
    if args.find:
        print(f"# «{args.find}» не найдено на {len(pages)} страницах"
              + (f" (распознано {ocr_used})" if ocr_used else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
