import React, { useCallback, useEffect, useState } from "react";
import { Check, RotateCcw, X, AlertCircle } from "lucide-react";
import "../styles/payment-banner.css";

// =========================================================================
// «ЧЕМ ЗАКОНЧИЛСЯ ПЛАТЁЖ» — встреча человека после оплаты (владелец 2026-08-28).
//
// Порядок теперь такой: результат сначала показывает БАНК на своей странице
// («Оплачено» / «Платёж не прошёл»), и только потом человек нажимает «В магазин».
// Кнопка ведёт на адрес сайта из настроек терминала — то есть на главную и БЕЗ
// номера заказа в ссылке. Поэтому платформа узнаёт исход сама: спрашивает свой
// последний платёж и говорит главное — подписка включена и до какого числа.
//
// Почему баннер, а не плашка внутри «Тарифов»: человек возвращается на главную,
// и всё, что нарисовано на других экранах, он не увидит. Ровно на этом
// спотыкался первый платёж владельца — деньги ушли, платформа промолчала.
// =========================================================================

const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
const SEEN_KEY = "basis_payment_seen";   // какой заказ уже показывали

function seen(orderId) {
  try {
    return (localStorage.getItem(SEEN_KEY) || "").split(",").includes(orderId);
  } catch {
    return false;
  }
}

function remember(orderId) {
  try {
    const prev = (localStorage.getItem(SEEN_KEY) || "").split(",").filter(Boolean);
    localStorage.setItem(SEEN_KEY, [...prev.slice(-4), orderId].join(","));
  } catch { /* приватный режим — покажем ещё раз, это не страшно */ }
}

export default function PaymentResultBanner({ token, onOpenPricing, onUserUpdate }) {
  const [info, setInfo] = useState(null);
  const hide = useCallback(() => setInfo(null), []);

  useEffect(() => {
    if (!token) return undefined;
    let alive = true;
    fetch(`${apiUrl}/api/payments/last`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!alive || !d || !d.found) return;
        // Показываем только свежий и уже завершившийся платёж, и только один раз.
        const finished = d.paid || d.refunded || ["REJECTED", "CANCELED",
          "DEADLINE_EXPIRED"].includes(d.status);
        if (!finished || !d.finished_recently || seen(d.order_id)) return;
        // Помечаем показанным СРАЗУ, а не по закрытию: иначе баннер всплывал бы
        // на каждой перезагрузке страницы ближайшие два часа. Продублировано
        // письмом и датой в профиле, так что один показ — достаточно.
        remember(d.order_id);
        setInfo(d);
        if (d.paid && onUserUpdate) {
          // Подписку начислил сервер — подтягиваем пользователя, чтобы тариф на
          // экране стал Max без перезагрузки страницы.
          fetch(`${apiUrl}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
            .then((r) => (r.ok ? r.json() : null))
            .then((u) => { if (u) onUserUpdate(u); })
            .catch(() => {});
        }
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [token, onUserUpdate]);

  if (!info) return null;

  const until = info.subscription_expires_at
    ? new Date(info.subscription_expires_at).toLocaleDateString("ru-RU")
    : null;
  const kind = info.paid ? "ok" : info.refunded ? "refund" : "fail";
  const icon = kind === "ok" ? <Check size={16} />
    : kind === "refund" ? <RotateCcw size={16} /> : <AlertCircle size={16} />;

  return (
    <aside className={`pbn pbn--${kind}`} role="status" aria-live="polite">
      <span className="pbn-ic" aria-hidden="true">{icon}</span>
      <div className="pbn-body">
        {kind === "ok" && (
          <>
            <b className="pbn-title">Оплата получена — тариф Max активен</b>
            <span className="pbn-text">
              {until ? `Действует до ${until}. ` : ""}Подтверждение отправили на почту.
              Заходить заново не нужно.
            </span>
          </>
        )}
        {kind === "refund" && (
          <>
            <b className="pbn-title">Платёж возвращён</b>
            <span className="pbn-text">
              Деньги вернутся на карту в срок банка — обычно до трёх рабочих дней.
              Тариф Max по этому платежу отключён.
            </span>
          </>
        )}
        {kind === "fail" && (
          <>
            <b className="pbn-title">Платёж не прошёл</b>
            <span className="pbn-text">
              Деньги не списаны. Можно попробовать ещё раз или другой картой.
            </span>
          </>
        )}
      </div>
      {kind !== "ok" && (
        <button type="button" className="pbn-cta"
                onClick={() => { hide(); onOpenPricing && onOpenPricing(); }}>
          К тарифам
        </button>
      )}
      <button type="button" className="pbn-x" onClick={hide} aria-label="Закрыть">
        <X size={14} />
      </button>
    </aside>
  );
}
