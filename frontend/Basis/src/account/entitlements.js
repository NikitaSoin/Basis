// =============================================================
// Границы тарифов — фронтовая половина. Бэкендная (и главная, потому что она
// реально закрывает данные) — backend/app/services/entitlements.py.
//
// Владелец (2026-08-01): «пропиши эти ограничения, просто оставь их не
// включёнными». Пока FREE_LIMITS_ENFORCED === false (tierCatalog.js), все
// функции ниже отвечают «можно» — интерфейс ведёт себя ровно как раньше.
//
// 🔴 ВКЛЮЧЕНИЕ — ДВА ФЛАГА, СНИМАТЬ ВМЕСТЕ:
//   1) бэкенд: env TIER_LIMITS_ENFORCED=1 (Timeweb → env приложения) — закрывает
//      данные, отдаёт 402 на закрытых эндпоинтах;
//   2) фронт: FREE_LIMITS_ENFORCED = true в tierCatalog.js — интерфейс перестаёт
//      обещать открытость (уходит плашка «пока всё открыто» со страницы тарифов)
//      и начинает показывать замки/предложение перейти на Max.
// Если включить только бэкенд — пользователь увидит ошибки вместо понятного
// «доступно на Max». Если только фронт — интерфейс запрёт то, что API отдаёт.
//
// Ключи фич совпадают со строковыми константами бэкенда (FEATURE_*), чтобы
// таблица тарифов, гейты API и замки в UI не разъезжались.
// =============================================================
import { FREE_LIMITS_ENFORCED } from "./tierCatalog";

export const FEATURE = {
  CARD_FULL_ANALYTICS: "card_full_analytics", // полный разбор вкладок карточки
  FAIR_PRICE: "fair_price",                   // справедливая цена и потенциал
  OBSERVER_DEEP: "observer_deep",             // разборы отчётов и аналитические разборы
  PORTFOLIO_FULL: "portfolio_full",           // полная аналитика портфеля
  STRESS_CUSTOM: "stress_custom",             // свои сценарии стресс-теста
};

export const ASSISTANT_DAILY_LIMIT_FREE = 2;

export function isPaid(user) {
  return Boolean(user) && (user.subscription_type || "free") !== "free";
}

/** Доступна ли фича. Пока лимиты не включены — всегда true. */
export function hasFeature(user, feature) {
  if (!FREE_LIMITS_ENFORCED) return true;
  if (!Object.values(FEATURE).includes(feature)) return true;
  return isPaid(user);
}

/** Суточный лимит запросов к ассистенту; null — без ограничения. */
export function assistantDailyLimit(user) {
  if (!FREE_LIMITS_ENFORCED || isPaid(user)) return null;
  return ASSISTANT_DAILY_LIMIT_FREE;
}

/** Бэкенд отвечает 402 (Payment Required) именно на «нужен платный тариф» —
 *  это НЕ 403 «нет прав», чтобы UI мог отличить одно от другого и показать
 *  предложение перейти на Max вместо ошибки доступа. */
export const PAYMENT_REQUIRED = 402;

export function isPaymentRequired(response) {
  return Boolean(response) && response.status === PAYMENT_REQUIRED;
}

/** Текст для замка/заглушки. detail с бэкенда уже человеческий — используем его,
 *  если пришёл, иначе даём общий. */
export function upgradeMessage(detail) {
  return detail || "Доступно на тарифе Max.";
}
