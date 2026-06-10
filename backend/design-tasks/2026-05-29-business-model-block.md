# Дизайн-ревью: Блок «Бизнес-модель»

Дата: 2026-05-29  
Источник: inbasis.ru/company/SBER (вкладка «Бизнес-модель»)  
Компонент: `renderBusinessProfile()` в `frontend/Basis/src/App.js` (строки ~2207-2513)

---

## Что я увидел

Блок рендерит markdown-документ через `ReactMarkdown` с кастомными компонентами (`mdComponents`). Контент структурирован хорошо (заголовки H2/H3, таблицы, списки), но визуально выглядит **монотонно**: весь текст одинакового веса, таблицы сливаются с текстом, нет визуальной иерархии между секциями. Пользователь справедливо жалуется — глаз не за что зацепиться.

Текущий markdown-рендерер уже имеет базовую стилизацию (таблицы с hover, первый параграф с акцентной рамкой), но этого недостаточно для восприятия плотного финансового контента.

---

## Что не работает (приоритизировано)

### 1. [КРИТИЧНО] Монотонность секций — нет визуального разделения

**Почему плохо:** Все H2-заголовки выглядят одинаково. После «Первого экрана» идет «Экономика и детали» — и глаз не понимает, что это разные логические блоки. Пользователь теряется в «простыне».

**Где в коде:** `mdComponents.h2` (строка ~2223) — просто текст с border-bottom, без иконок и фона.

---

### 2. [КРИТИЧНО] Таблицы не читаются как финансовые данные

**Почему плохо:**
- Числовые колонки выровнены влево (должны вправо для сравнения разрядов)
- Дельты ("+18,5%", "-1,1%") не окрашены по знаку — невозможно быстро сканировать
- Нет zebra-striping для длинных таблиц
- Заголовки колонок того же размера, что и данные

**Где в коде:** `mdComponents.table`, `mdComponents.th`, `mdComponents.td` (строки ~2243-2276)

---

### 3. [ВАЖНО] Списки факторов и рисков — просто буллеты

**Почему плохо:** Пронумерованные факторы («1. Ключевая ставка ЦБ РФ», «2. Качество кредитного портфеля») — это ключевая информация, но визуально они ничем не отличаются от обычного текста. Нет карточек, нет иконок, нет акцентов.

**Где в коде:** `mdComponents.ol`, `mdComponents.li` (строки ~2283-2286)

---

### 4. [ВАЖНО] Блок с кодом (цепочка стоимости) — выглядит как код

**Почему плохо:** Цепочка стоимости отображается моноширинным шрифтом в сером блоке. Это не код — это бизнес-процесс. Должен быть визуальный flow-диаграмма или хотя бы стилизованная цепочка со стрелками.

**Где в коде:** `mdComponents.code` (строка ~2297) — базовый стиль для inline-кода, блок ``` обрабатывается так же.

---

### 5. [ВАЖНО] «Вывод из таблицы» не выделен

**Почему плохо:** После таблицы мини-P&L идет важный абзац «Вывод из таблицы: ...» — это ключевой insight, но он визуально неотличим от обычного текста.

**Где в коде:** Нет специальной обработки. Нужно парсить текст и выделять абзацы, начинающиеся с «Вывод».

---

### 6. [МИНОР] Нет прогрессивного раскрытия

**Почему плохо:** Весь контент показан сразу. Для «Первого экрана» это ок, но «Экономика и детали» можно сворачивать по умолчанию.

---

### 7. [МИНОР] Заголовок H1 (название компании) дублирует header карточки

**Почему плохо:** «СБЕРБАНК (SBER)» уже показан в header компании. В markdown это избыточно.

---

## Что предлагаю (конкретно)

### Правка 1: Секции с иконками и разделителями [P0]

**Что менять:** `mdComponents.h2`

**Как менять:**
- Добавить иконку слева от заголовка (из lucide-react)
- Добавить фоновую подложку для всей секции
- Увеличить отступ сверху

**Маппинг заголовков на иконки:**
```
"Первый экран" -> <Layout />
"Суть бизнеса" -> <Briefcase />
"Мини-P&L" -> <BarChart2 />
"Ключевые факторы и риски" -> <ShieldAlert />
"Экономика и детали" -> <Database />
"Сегменты" -> <Layers />
"Цепочка создания стоимости" -> <ArrowRightLeft />
"География" -> <Globe />
"Клиенты" -> <Users />
"Источники" -> <FileText />
```

---

### Правка 2: Финансовые таблицы с цветовым кодированием [P0]

**Что менять:** `mdComponents.table`, `mdComponents.th`, `mdComponents.td`, `mdComponents.tr`

**Как менять:**
1. Числовые ячейки выравнивать вправо
2. Детектировать дельты (строки вида `+X%`, `-X%`, `+X п.п.`, `-X п.п.`) и красить:
   - Положительные -> `var(--positive)`
   - Отрицательные -> `var(--negative)`
3. Zebra-striping для строк (`:nth-child(even)` -> `var(--bg-surface)`)
4. Заголовки колонок меньше и серее

---

### Правка 3: Карточки для факторов и рисков [P1]

**Что менять:** `mdComponents.ol`, `mdComponents.li`

**Как менять:** Для упорядоченных списков внутри секции «Ключевые факторы и риски» рендерить карточки вместо буллетов.

Визуал:
- Номер в круге слева
- Заголовок (до первого «—») жирным
- Остальной текст обычным
- border-left с цветом в зависимости от слова «Риск:» (красный) или обычный (серый)

---

### Правка 4: Визуальная цепочка стоимости [P1]

**Что менять:** `mdComponents.code` (для блоков ```)

**Как менять:** Детектировать паттерн цепочки (текст с `->` или стрелками) и рендерить как горизонтальный flow:

```
[Этап 1] --> [Этап 2] --> [Этап 3] --> ...
```

Каждый этап — pill с фоном, между ними стрелки.

---

### Правка 5: Выделение выводов [P1]

**Что менять:** `mdComponents.p`

**Как менять:** Детектировать абзацы, начинающиеся с «Вывод» / «Главный вывод» / «Итог», и стилизовать как callout:
- Фон `var(--accent-fade)`
- border-left `var(--accent)`
- Иконка `<Zap />` слева

---

### Правка 6: Скрытие H1 [P2]

**Что менять:** `mdComponents.h1`

**Как менять:** Возвращать `null` или рендерить только если это не дублирует название компании.

---

### Правка 7: Сворачиваемые секции [P2]

**Что менять:** `mdComponents.h2`

**Как менять:** Обернуть H2 и его контент в collapsible-компонент. Секция «Экономика и детали» свернута по умолчанию.

Требует рефакторинга: нужно парсить markdown и группировать контент по H2.

---

## Готовый JSX/CSS для критичных правок

### mdComponents с улучшениями (замена строк ~2219-2298)

```jsx
import {
  Layout, Briefcase, BarChart2, ShieldAlert, Database,
  Layers, ArrowRightLeft, Globe, Users, FileText, Zap
} from "lucide-react";

// Маппинг заголовков на иконки
const sectionIcons = {
  "первый экран": Layout,
  "суть бизнеса": Briefcase,
  "мини-p&l": BarChart2,
  "ключевые факторы и риски": ShieldAlert,
  "экономика и детали": Database,
  "сегменты": Layers,
  "цепочка создания стоимости": ArrowRightLeft,
  "география": Globe,
  "клиенты": Users,
  "источники": FileText,
};

const getIconForHeading = (text) => {
  const lower = String(text).toLowerCase();
  for (const [key, Icon] of Object.entries(sectionIcons)) {
    if (lower.includes(key)) return Icon;
  }
  return null;
};

// Детекция числовых значений и дельт
const isNumericCell = (text) => /^[+\-−]?[\d\s.,]+(%|п\.п\.|₽|руб|трлн|млрд|млн)?$/i.test(text.trim());
const isDeltaPositive = (text) => /^\+/.test(text.trim());
const isDeltaNegative = (text) => /^[−\-]/.test(text.trim()) && isNumericCell(text);

// Детекция выводов
const isConclusion = (text) => {
  const lower = String(text).toLowerCase();
  return lower.startsWith("вывод") || lower.startsWith("главный вывод") || lower.startsWith("итог");
};

// Детекция цепочки стоимости
const isValueChain = (text) => {
  return text.includes("→") || text.includes("->") || text.includes("-->");
};

let isFirstP = true;
let rowIndex = 0;

const mdComponents = {
  // H1 — скрываем, дублирует header
  h1: () => null,

  // H2 — секции с иконками
  h2: ({children}) => {
    const Icon = getIconForHeading(children);
    return (
      <div style={{
        marginTop: 32,
        marginBottom: 16,
        paddingBottom: 10,
        borderBottom: "1px solid var(--border-mid)",
      }}>
        <h2 style={{
          fontSize: 16,
          fontWeight: 700,
          color: "var(--text-1)",
          margin: 0,
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          {Icon && (
            <span style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: "var(--accent-fade)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}>
              <Icon size={16} style={{ color: "var(--accent-text)" }} />
            </span>
          )}
          {children}
        </h2>
      </div>
    );
  },

  // H3 — подзаголовки
  h3: ({children}) => (
    <h3 style={{
      fontSize: 14,
      fontWeight: 600,
      color: "var(--text-1)",
      margin: "20px 0 8px 0",
      display: "flex",
      alignItems: "center",
      gap: 6,
    }}>
      <span style={{
        width: 4,
        height: 14,
        background: "var(--accent)",
        borderRadius: 2,
      }} />
      {children}
    </h3>
  ),

  // Параграфы с детекцией выводов
  p: ({children}) => {
    const text = typeof children === "string" ? children : 
      (Array.isArray(children) ? children.map(c => typeof c === "string" ? c : "").join("") : "");
    
    // Первый параграф — акцентный
    if (isFirstP) {
      isFirstP = false;
      return (
        <p style={{
          fontSize: 14,
          lineHeight: 1.7,
          color: "var(--text-1)",
          background: "var(--bg-surface)",
          borderLeft: "3px solid var(--accent)",
          padding: "12px 16px",
          borderRadius: "0 8px 8px 0",
          margin: "12px 0 20px 0",
        }}>{children}</p>
      );
    }
    
    // Выводы — callout
    if (isConclusion(text)) {
      return (
        <div style={{
          display: "flex",
          gap: 12,
          background: "var(--accent-fade)",
          borderLeft: "3px solid var(--accent)",
          padding: "12px 16px",
          borderRadius: "0 8px 8px 0",
          margin: "16px 0",
        }}>
          <Zap size={18} style={{ color: "var(--accent-text)", flexShrink: 0, marginTop: 2 }} />
          <p style={{
            fontSize: 14,
            lineHeight: 1.7,
            color: "var(--text-1)",
            margin: 0,
          }}>{children}</p>
        </div>
      );
    }
    
    return (
      <p style={{
        fontSize: 14,
        lineHeight: 1.7,
        color: "var(--text-1)",
        margin: "0 0 12px 0",
      }}>{children}</p>
    );
  },

  // Таблицы — финансовый стиль
  table: ({children}) => {
    rowIndex = 0; // сброс для zebra
    return (
      <div style={{
        overflowX: "auto",
        margin: "12px 0 20px 0",
        borderRadius: 10,
        border: "1px solid var(--border-mid)",
      }}>
        <table style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 13,
        }}>{children}</table>
      </div>
    );
  },

  thead: ({children}) => (
    <thead style={{ background: "var(--bg-surface)" }}>{children}</thead>
  ),

  th: ({children}) => (
    <th style={{
      padding: "10px 14px",
      textAlign: "left",
      color: "var(--text-3)",
      fontWeight: 600,
      fontSize: 11,
      textTransform: "uppercase",
      letterSpacing: "0.05em",
      borderBottom: "1px solid var(--border-mid)",
      whiteSpace: "nowrap",
    }}>{children}</th>
  ),

  tr: ({children, ...props}) => {
    const isBody = !props.node?.parent?.tagName?.includes("head");
    const bgColor = isBody && rowIndex % 2 === 1 ? "var(--bg-surface)" : "transparent";
    if (isBody) rowIndex++;
    
    return (
      <tr
        style={{ background: bgColor }}
        onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"}
        onMouseLeave={e => e.currentTarget.style.background = bgColor}
      >{children}</tr>
    );
  },

  td: ({children}) => {
    const raw = typeof children === "string" ? children : 
      (Array.isArray(children) ? children.map(c => typeof c === "string" ? c : "").join("") : "");
    const trimmed = raw.trim();
    
    const isNum = isNumericCell(trimmed);
    const isPositive = isDeltaPositive(trimmed);
    const isNegative = isDeltaNegative(trimmed);
    
    let color = "var(--text-1)";
    let fontWeight = 400;
    
    if (isPositive) {
      color = "var(--positive)";
      fontWeight = 500;
    } else if (isNegative) {
      color = "var(--negative)";
      fontWeight = 500;
    }
    
    return (
      <td style={{
        padding: "9px 14px",
        color,
        fontWeight,
        fontSize: 13,
        borderBottom: "1px solid var(--border)",
        textAlign: isNum ? "right" : "left",
        fontVariantNumeric: isNum ? "tabular-nums" : "normal",
        whiteSpace: isNum ? "nowrap" : "normal",
      }}>{children}</td>
    );
  },

  // Упорядоченные списки — карточки для факторов/рисков
  ol: ({children}) => (
    <div style={{
      display: "flex",
      flexDirection: "column",
      gap: 12,
      margin: "12px 0 20px 0",
    }}>{children}</div>
  ),

  li: ({children, index, ordered}) => {
    if (!ordered) {
      // Неупорядоченный список — обычные буллеты
      return (
        <li style={{
          fontSize: 14,
          color: "var(--text-1)",
          marginBottom: 6,
          lineHeight: 1.6,
        }}>{children}</li>
      );
    }
    
    // Упорядоченный список — карточки
    const text = typeof children === "string" ? children :
      (Array.isArray(children) ? children.map(c => typeof c === "string" ? c : "").join("") : "");
    const hasRisk = text.toLowerCase().includes("риск:");
    
    return (
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${hasRisk ? "var(--negative)" : "var(--border-mid)"}`,
        borderRadius: "0 10px 10px 0",
        padding: "14px 16px",
        display: "flex",
        gap: 14,
      }}>
        <span style={{
          width: 26,
          height: 26,
          borderRadius: "50%",
          background: "var(--accent-fade)",
          color: "var(--accent-text)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          fontWeight: 700,
          flexShrink: 0,
        }}>{index + 1}</span>
        <div style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text-1)" }}>
          {children}
        </div>
      </div>
    );
  },

  ul: ({children}) => (
    <ul style={{ paddingLeft: 20, margin: "8px 0 16px 0" }}>{children}</ul>
  ),

  // Код — обработка цепочки стоимости
  code: ({children, inline}) => {
    const text = String(children);
    
    // Блок кода с цепочкой стоимости
    if (!inline && isValueChain(text)) {
      const steps = text.split(/\s*[→\->]+\s*/).filter(Boolean);
      return (
        <div style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 8,
          padding: "16px",
          background: "var(--bg-surface)",
          borderRadius: 10,
          margin: "12px 0 20px 0",
          overflowX: "auto",
        }}>
          {steps.map((step, i) => (
            <React.Fragment key={i}>
              <span style={{
                background: "var(--accent-fade)",
                border: "1px solid var(--accent-border)",
                color: "var(--text-1)",
                padding: "8px 14px",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 500,
                whiteSpace: "nowrap",
              }}>{step.trim()}</span>
              {i < steps.length - 1 && (
                <ChevronRight size={18} style={{ color: "var(--text-3)", flexShrink: 0 }} />
              )}
            </React.Fragment>
          ))}
        </div>
      );
    }
    
    // Inline код
    return (
      <code style={{
        background: "var(--bg-surface)",
        padding: "2px 6px",
        borderRadius: 4,
        fontSize: 12,
        color: "var(--text-2)",
        fontFamily: "monospace",
      }}>{children}</code>
    );
  },

  // pre — для блоков кода
  pre: ({children}) => children,

  strong: ({children}) => (
    <strong style={{ color: "var(--text-1)", fontWeight: 600 }}>{children}</strong>
  ),

  hr: () => (
    <hr style={{
      border: "none",
      borderTop: "1px solid var(--border-mid)",
      margin: "28px 0",
    }} />
  ),

  blockquote: ({children}) => (
    <blockquote style={{
      borderLeft: "3px solid var(--accent)",
      paddingLeft: 14,
      margin: "12px 0",
      color: "var(--text-2)",
      fontStyle: "italic",
    }}>{children}</blockquote>
  ),

  a: ({href, children}) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        color: "var(--accent-text)",
        textDecoration: "underline",
        textUnderlineOffset: 2,
      }}
    >{children}</a>
  ),
};
```

---

### CSS для таблиц (добавить в styles.css)

```css
/* =============================================
   BUSINESS MODEL MARKDOWN TABLES
   ============================================= */
.bm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.bm-table th {
  padding: 10px 14px;
  text-align: left;
  color: var(--text-3);
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-mid);
  background: var(--bg-surface);
}

.bm-table th.num { text-align: right; }

.bm-table td {
  padding: 9px 14px;
  color: var(--text-1);
  border-bottom: 1px solid var(--border);
}

.bm-table td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.bm-table td.delta-pos {
  color: var(--positive);
  font-weight: 500;
}

.bm-table td.delta-neg {
  color: var(--negative);
  font-weight: 500;
}

.bm-table tbody tr:nth-child(even) {
  background: var(--bg-surface);
}

.bm-table tbody tr:hover {
  background: var(--bg-hover);
}

/* Factor/Risk cards */
.factor-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border-mid);
  border-radius: 0 10px 10px 0;
  padding: 14px 16px;
  display: flex;
  gap: 14px;
  transition: border-color 0.15s;
}

.factor-card.has-risk {
  border-left-color: var(--negative);
}

.factor-card:hover {
  border-color: var(--border-mid);
}

.factor-number {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent-fade);
  color: var(--accent-text);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

/* Conclusion callout */
.conclusion-callout {
  display: flex;
  gap: 12px;
  background: var(--accent-fade);
  border-left: 3px solid var(--accent);
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  margin: 16px 0;
}

/* Value chain flow */
.value-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: var(--bg-surface);
  border-radius: 10px;
  margin: 12px 0 20px 0;
}

.value-chain-step {
  background: var(--accent-fade);
  border: 1px solid var(--accent-border);
  color: var(--text-1);
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}
```

---

## Чего НЕ менять (важно!)

1. **Общую структуру ReactMarkdown** — она работает, просто нужны лучшие компоненты
2. **Fallback на profile JSON** — он уже хорошо стилизован для структурированных данных
3. **CSS-переменные** — используем существующие `--positive`, `--negative`, `--accent` и т.д.
4. **Шрифты** — Inter для текста, monospace для чисел (уже так)
5. **Первый параграф с акцентом** — это хорошее решение, оставляем

---

## Оценка трудозатрат

| Правка | Приоритет | Оценка |
|--------|-----------|--------|
| Секции с иконками | P0 | S (1-2 часа) |
| Финансовые таблицы | P0 | M (3-4 часа) |
| Карточки факторов | P1 | S (1-2 часа) |
| Цепочка стоимости | P1 | S (1 час) |
| Выделение выводов | P1 | S (30 мин) |
| Скрытие H1 | P2 | XS (5 мин) |
| Сворачиваемые секции | P2 | L (требует рефакторинга) |

**Общая оценка: M (полдня)** для P0+P1 правок.

---

## Зависимости

1. Иконки уже импортированы в App.js (lucide-react)
2. CSS-переменные уже определены в styles.css
3. ReactMarkdown + remarkGfm уже подключены

---

## Тестирование

После внедрения проверить на:
- inbasis.ru/company/SBER — полный документ
- Другие компании с business_model.md (если есть)
- Светлая/темная тема
- Мобильные устройства (таблицы должны скроллиться)
