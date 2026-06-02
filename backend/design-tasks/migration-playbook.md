# Плейбук: перевод страницы на примитивы (Фаза 3)

Отлажено на эталоне — странице **Тарифы** (`PricingView` в `src/App.js`).
Рецепт повторяемый: по нему идут Лендинг, Рынок, Обозреватель и т.д.

## 0. Принцип
Меняем ТОЛЬКО визуальный слой одного компонента на примитивы из
`src/design/primitives.jsx` + токены/`tw-`-классы. Контент, данные, обработчики,
гейтинг (premium/free) сохраняем 1:1. Примитивы и токены НЕ трогаем (заморожены).
`styles.css`-классы НЕ удаляем (на них держатся другие страницы — чистка в конце фазы).

## 1. Как найти рукописные классы / инлайн-стили в компоненте
1. Найди границы компонента: `grep -n "const NameView\|function NameView" src/App.js`,
   далее читай до следующего компонента.
2. Внутри ищи, что переводить:
   - рукописные классы: `pricing-card`, `btn btn-primary`, `badge badge-accent`, `w-full` …
   - инлайн-стили: `style={{ ... }}` с цветами/отступами/размерами.
   - захардкоженный hex/rgb: `grep -nE "#[0-9A-Fa-f]{3,6}"` в диапазоне строк компонента.
3. Проверь, что под-классы используются ТОЛЬКО этой страницей, прежде чем считать
   их «своими»: `grep -rn "pricing-" src/ | grep -v App.js`. Если 0 совпадений —
   класс осиротеет после перевода (удалять не сейчас, а в финале фазы).

## 2. Таблица соответствия (эталон Тарифов)

| Было (рукописное) | Стало (примитив / tw / токен) |
|---|---|
| `<div className="pricing-card …">` | `<Card>` (примитив; поверхность + рамка + тень, обе темы) |
| `pricing-card.active-plan` (рамка-акцент) | `className="tw-ring-1 tw-ring-accent"` на `Card` |
| `<div className="pricing-card-badge">PREMIUM</div>` | `<Badge tone="accent">Premium</Badge>` |
| `<span className="badge badge-accent">Текущий план</span>` | `<Badge tone="accent">Текущий план</Badge>` |
| `<span className="badge badge-gold">Активен</span>` | `<Badge tone="accent">Активен</Badge>` (gold=warning зарезервирован под риск-каллауты, не под статус → accent) |
| `<button className="btn btn-primary w-full">` | `<Button variant="primary" className="tw-w-full">` |
| `<button className="btn btn-gold w-full">` (Premium CTA) | `<Button variant="primary" …>` на кобальт-акценте (gold-кнопок не делаем по конституции) |
| `pricing-feature-dot` + инлайн `background:var(--gold)/var(--accent-text)` + точка 6×6 | единый `FeatureItem`: глиф `<Check>` цвета `tw-text-success` + текст `tw-text-text-secondary` |
| `pricing-card-price` "990 ₽ /мес" (текст) | `{formatMoney(990)}` (₽ через NBSP, tabular-nums) + `/мес` как `tw-text-text-tertiary` |
| `pricing-card-name/-desc` (рукописные) | `tw-text-[18px] tw-font-semibold tw-text-text-primary` / `tw-text-text-tertiary` |
| инлайн `color:"var(--gold)"` у строки про подписку | `tw-text-success` (позитивный статус) |
| инлайн `marginBottom/marginTop/padding` | сетка 8pt через `tw-` (`tw-gap-6`, `tw-mt-4`, `tw-mb-4`, `tw-gap-2.5`) |

Импорты добавлять рядом с lucide-импортом:
`import { Button, Card, Badge } from "./design/primitives";`
`import { formatMoney } from "./design/format";`
(`primitives.jsx` резолвится без расширения; CRA берёт `.jsx`.)

## 3. На что смотреть, чтобы не было регресса
- **Паритет контента**: те же планы, цены, списки фич, CTA-действия (`onShowAuth`),
  гейтинг (`isPremium`/`isFree`), дата окончания подписки — слово в слово.
- **Обе темы**: цвета только через токены (`tw-text-text-*`, `tw-text-accent`,
  `tw-text-success`, `tw-ring-accent`). Никакого hex — проверь грепом, должно быть NONE.
  `Card`/`Badge`/`Button` уже корректны в light/dark by design.
- **Hover/focus**: CTA через `Button` → focus-ring и hover уже встроены. Не навешивай
  свои.
- **Числа через format.js**: денежные суммы — `formatMoney`, проценты — `formatPercent`,
  мультипликаторы — `formatMultiple`. tabular-nums для крупных значений.
- **Семантика цвета**: success(зелёный)/danger(красный) только по смыслу; warning(gold)
  НЕ для кнопок/статусов, только риск-каллауты; accent(кобальт) для интерактива.
- **Новые видимые элементы — помечать явно**: если при переводе появляется элемент,
  которого в старой вёрстке не было (пример Тарифов: бейдж «Premium» теперь рендерится
  и не-премиум юзерам как замена углового бейджа), это НЕ строгий 1:1 — отметь в отчёте
  и убедись, что владелец увидит и подтвердит на живом. Не вводи новые элементы молча.
- **Сетка 8pt строго**: выбирай `tw-gap-*`/`tw-p-*`/`tw-m-*` из ряда 8pt с под-сеткой
  4pt (2/4/6/8/12/16…). Избегай дробных вне сетки вроде `tw-gap-2.5` (10px) — бери
  `tw-gap-2` (8px) или `tw-gap-3` (12px).

## 4. Что НЕ трогать
- `src/styles/tokens.css`, `tailwind.config.js`, сами примитивы — заморожены.
- `styles.css`-классы — НЕ удаляем (другие страницы на них держатся; осиротевшие
  чистим единым заходом в конце Фазы 3, грепом подтвердив 0 потребителей).
- Другие страницы/компоненты, общие render-функции, данные/эндпоинты.
- Поведение и тексты переводимой страницы.

## 5. Как проверять
1. `cd frontend/Basis && CI=false npm run build` → «Compiled successfully», без новых
   eslint-варнингов. Зафиксируй хеши бандлов.
2. Греп самопроверки в диапазоне компонента:
   - используются примитивы: `<Card`/`<Badge`/`<Button`;
   - hex отсутствует: `grep -nE "#[0-9A-Fa-f]{3,6}"` → NONE.
3. `git diff --stat` → изменён только `src/App.js` (нужный компонент + импорты);
   `git diff -U0 src/App.js | grep '^@@'` — хунки только в пределах компонента и блока импортов.
4. На ЖИВОМ (Definition of Done): push → дождаться смены хеша бандла main.<hash>.js
   на inbasis.ru → открыть ИМЕННО эту страницу в светлой и тёмной теме → паритет +
   аккуратнее. Только потом следующая страница.

## Заметки эталона (Тарифы)
- Сетка карточек: `pricing-grid` → `tw-grid tw-gap-6 md:tw-grid-cols-2 tw-max-w-3xl`.
- Списки фич у обоих планов теперь ЕДИНЫЕ (раньше free=точка-accent, premium=точка-gold)
  → один `FeatureItem` с зелёным `Check`. Консистентность вместо двух разных стилей.
- Эмодзи-галочки («✓ Подписка…», «→» в CTA) убраны: статус — через цвет токена,
  стрелки в кнопках не нужны.
