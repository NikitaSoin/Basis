---
name: tw-font-mono-not-neo-mono
description: tailwind-класс tw-font-mono рендерит JetBrains Mono (классика), НЕ IBM Plex Mono / --cc-mono NEO — для NEO-чисел используй .cc-num или явный font-family:var(--cc-mono)
metadata:
  type: project
---

`tailwind.config.js` → `theme.extend.fontFamily.mono` захардкожен как
`["JetBrains Mono", "ui-monospace", ...]` — НЕ читает CSS-переменную, поэтому класс
`tw-font-mono` всегда даёт JetBrains Mono (шрифт классической системы), даже внутри `.cc-root`.

NEO-канон для чисел — IBM Plex Mono через `--cc-mono` (см. `docs/design-system.md` §2). Она
подключена в `public/index.html` отдельным `<link>` (`IBM+Plex+Mono:wght@400;500;600;700`) и
уже доступна как готовый класс `.cc-root .cc-num` (`font-family:var(--cc-mono);
font-variant-numeric:tabular-nums lining-nums;`, объявлен в `tokens.css`).

**Why:** на новой NEO-странице легко машинально написать `tw-font-mono` (он есть в автокомплите,
выглядит подходящим по названию) и получить тихо неверную гарнитуру — визуально похоже
(оба моноширинные), поэтому в ревью можно не заметить.

**How to apply:** для чисел/цен/тикеров на NEO-экране — класс `.cc-num` ИЛИ свой CSS-класс с
`font-family:var(--cc-mono)` (как `.tar-price-num`/`.acct-avatar` в `styles/account.css`).
`tw-font-mono` использовать ТОЛЬКО в легаси-классике за `?classic=1`.
