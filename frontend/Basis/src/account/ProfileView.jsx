// =============================================================
// ProfileView — вариант 1d прототипа docs/«Регистрация и профиль.dc.html»
// (раскатка 2026-07-17, заменяет одноколоночный стек от 2026-07-12):
// баннер-шапка (аватар + email + чип тарифа + «Выйти») с чипами-вкладками,
// две колонки контента (1.25fr/1fr), тёмная плита подписки (--bs-deep-*).
//
// Адаптация прототипа к реальному бэкенду (backend/app/api/auth.py):
//   - у пользователя есть ТОЛЬКО email/тариф/даты/статус — поля «Имя/
//     Фамилия/Телефон» и кнопку «Редактировать профиль» не рисуем
//     (сохранять некуда), заголовок баннера = email;
//   - вкладки «Уведомления» и «Активность» прототипа не раскатаны (нет
//     пайплайна), «Безопасность» показана честно — строки со «Скоро»;
//   - в тёмной плите вместо «VISA •••• 4242» — честная строка про то,
//     что оплаты ещё нет и тарифы переключаются свободно.
//
// Тарифная копия — из tierCatalog.js (единый источник с PricingView).
// Реальный вызов: POST /api/auth/me/subscription (даунгрейд в один клик,
// без confirm() — owner: отмена должна быть не сложнее подписки).
// =============================================================
import React, { useState } from "react";
import { User, LogOut, Check } from "lucide-react";
import { Button, Badge, Card } from "../design/primitives";
import { getTier } from "./tierCatalog";
import "../styles/account.css";

const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

function fmtDate(iso, opts) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", opts || { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return "—";
  }
}

// Вкладка «Безопасность» из прототипа НЕ раскатана отдельным чипом: за ней
// пока только две строки «Скоро» (ОТК-персона: отдельная почти пустая вкладка
// читается как недоделка) — карточка безопасности живёт в «Обзоре», отдельная
// вкладка появится вместе с реальной сменой пароля/2FA на бэке.
const TABS = [
  { id: "overview", label: "Обзор" },
  { id: "plan", label: "Подписка" },
];

export default function ProfileView({ user, token, onLogout, onNavigate, onShowAuth, onUserUpdate, tourLabel, onTourClick, tourCompleted, tourPaused }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("overview");
  // Повторная отправка письма подтверждения почты (ссылка, бессрочная)
  const [verifySending, setVerifySending] = useState(false);
  const [verifyNote, setVerifyNote] = useState(null);
  const resendVerification = async () => {
    setVerifySending(true); setVerifyNote(null);
    try {
      const r = await fetch(`${apiUrl}/api/auth/send-verification`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` },
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.status === "sent") setVerifyNote("Письмо отправлено — проверьте почту (и папку «Спам»).");
      else if (d.status === "already") setVerifyNote("Почта уже подтверждена — обновите страницу.");
      else if (d.status === "disabled") setVerifyNote("Отправка писем пока не настроена.");
      else setVerifyNote(d.detail || "Не получилось отправить, попробуйте позже.");
    } catch {
      setVerifyNote("Не получилось отправить, попробуйте позже.");
    } finally {
      setVerifySending(false);
    }
  };

  if (!user) {
    return (
      <div className="acct-screen">
        <div className="acct-page">
          <div className="tw-flex tw-items-center tw-justify-center tw-py-20">
            <Card className="tw-max-w-[420px] tw-w-full tw-text-center">
              <div className="tw-flex tw-flex-col tw-items-center tw-gap-4 tw-py-6">
                <span className="tw-w-14 tw-h-14 tw-rounded-xl tw-bg-accent-soft tw-flex tw-items-center tw-justify-center tw-shrink-0">
                  <User size={26} className="tw-text-accent" aria-hidden="true" />
                </span>
                <div>
                  <h2 className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-m-0 tw-mb-2">Войдите в аккаунт</h2>
                  <p className="tw-text-[14px] tw-text-text-secondary tw-leading-[1.6] tw-m-0">
                    Для доступа к профилю и тарифу необходимо авторизоваться.
                  </p>
                </div>
                <Button variant="primary" className="acct-pill tw-w-full" onClick={onShowAuth}>
                  Войти / Регистрация
                </Button>
                {onTourClick && (
                  <div className="acct-tour-guest">
                    <p className="acct-tour-note">
                      {tourPaused
                        ? "Экскурс по платформе на паузе — продолжим с того шага, где остановились."
                        : "Платформа работает и без аккаунта. Хотите посмотреть, что где лежит, — пройдите экскурс."}
                    </p>
                    <Button variant="secondary" className="acct-pill tw-w-full" onClick={onTourClick}>
                      {tourLabel || "Пройти экскурс"}
                    </Button>
                  </div>
                )}
              </div>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  const tier = getTier(user.subscription_type || "free");
  const isFree = tier.id === "free";
  const initials = (user.email || "").slice(0, 2).toUpperCase();

  async function changeTier(tierId) {
    setError(null);
    setBusy(true);
    try {
      const r = await fetch(`${apiUrl}/api/auth/me/subscription`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ tier: tierId }),
      });
      if (!r.ok) throw new Error();
      const updated = await r.json();
      onUserUpdate && onUserUpdate(updated);
    } catch {
      setError("Не удалось изменить тариф. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }


  // ЕДИНСТВЕННАЯ точка входа в живой экскурс по платформе (владелец 2026-08-05:
  // «верхний сайдбар, пройти экскурс — перенеси внутрь профиля, на сайдбаре не
  // оставляй»). Рисуется и ГОСТЮ тоже — иначе прерванный экскурс некуда было бы
  // вернуть без регистрации, а он работает без неё.
  const tourPanel = onTourClick ? (
    <section className="acct-panel">
      <h2 className="acct-panel-title">Экскурс по платформе</h2>
      <p className="acct-tour-note">
        {tourPaused
          ? "Экскурс на паузе — продолжим с того шага, где остановились."
          : tourCompleted
          ? "Экскурс пройден. Его можно запустить заново в любой момент."
          : "Шесть шагов по реальным экранам: рынок, разбор компании, скринер, обозреватель, портфель и стресс-тест. Занимает пару минут, прервать можно в любой момент."}
      </p>
      <Button variant={tourPaused ? "primary" : "secondary"} className="acct-pill" onClick={onTourClick}>
        {tourLabel || "Пройти экскурс"}
      </Button>
    </section>
  ) : null;

  const dataPanel = (
    <section className="acct-panel">
      <h2 className="acct-panel-title">Данные аккаунта</h2>
      <div className="acct-row">
        <span className="acct-row-label">Email</span>
        <span className="acct-row-value">{user.email}</span>
      </div>
      <div className="acct-row">
        <span className="acct-row-label">Подтверждение почты</span>
        <span className="acct-row-value">
          {user.email_verified ? (
            <span style={{ color: "var(--bs-up, #2E7D32)", fontWeight: 600 }}>✓ Подтверждена</span>
          ) : (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ color: "var(--cc-ink-3, #888)" }}>Не подтверждена</span>
              <button type="button" className="acct-pill" disabled={verifySending}
                onClick={resendVerification}
                style={{ font: "inherit", fontSize: 12.5, fontWeight: 600, cursor: "pointer", padding: "5px 12px", borderRadius: 999, border: "1px solid var(--cc-line-2, #ccc)", background: "transparent", color: "var(--cc-accent-2, #A85F35)" }}>
                {verifySending ? "Отправляем…" : "Отправить письмо"}
              </button>
              {verifyNote && <span style={{ fontSize: 12.5, color: "var(--cc-ink-3, #888)" }}>{verifyNote}</span>}
            </span>
          )}
        </span>
      </div>
      <div className="acct-row">
        <span className="acct-row-label">Дата регистрации</span>
        <span className="acct-row-value">{fmtDate(user.created_at)}</span>
      </div>
      <div className="acct-row">
        <span className="acct-row-label">Статус</span>
        <span className="acct-row-value">{user.is_active ? "Активен" : "Заблокирован"}</span>
      </div>
    </section>
  );

  const securityPanel = (
    <section className="acct-panel">
      <h2 className="acct-panel-title">Безопасность</h2>
      <div className="acct-setrow">
        <div className="acct-setrow-main">
          <span className="acct-setrow-title">Пароль</span>
          <span className="acct-setrow-sub">Смена пароля появится в ближайшем обновлении</span>
        </div>
        <Badge tone="neutral">Скоро</Badge>
      </div>
      <div className="acct-setrow">
        <div className="acct-setrow-main">
          <span className="acct-setrow-title">Двухфакторная аутентификация</span>
          <span className="acct-setrow-sub">Код-подтверждение при каждом входе</span>
        </div>
        <Badge tone="neutral">Скоро</Badge>
      </div>
    </section>
  );

  const planDeep = (
    <section className="acct-deep">
      <span className="acct-deep-eyebrow">Подписка · текущий план</span>
      <div className="acct-deep-head">
        <h2 className="acct-deep-name">{isFree ? "Бесплатный" : `Basis ${tier.name}`}</h2>
        <span className="acct-deep-price">
          {isFree ? "0 ₽" : `${tier.priceRub} ₽`}<span> / мес</span>
        </span>
      </div>
      <p className="acct-deep-note">
        {isFree
          ? "Рынок, скринер, карточки и портфель — бесплатно. Банковская карта не нужна."
          : `${user.subscription_expires_at ? `Активен до ${fmtDate(user.subscription_expires_at)}` : "Тариф активен"} · или ${tier.priceRubYear} ₽ за год. Оплата картой появится позже — сейчас тарифы переключаются свободно.`}
      </p>
      <div className="acct-deep-actions">
        <Button variant="primary" className="acct-pill" onClick={() => onNavigate("pricing")}>
          {isFree ? "Выбрать тариф" : "Изменить тариф"}
        </Button>
        {!isFree && (
          <Button
            variant="ghost"
            className="acct-pill acct-deep-ghost"
            loading={busy}
            disabled={busy}
            onClick={() => changeTier("free")}
          >
            Перейти на Бесплатный
          </Button>
        )}
      </div>
      {error && <p className="tar-error">{error}</p>}
    </section>
  );

  const capPanel = (
    <section className="acct-panel">
      <h2 className="acct-panel-title">Возможности тарифа «{tier.name}»</h2>
      <ul className="acct-cap-list">
        {tier.bullets.map((b, i) => (
          <li key={i} className="acct-cap-item">
            <Check size={15} aria-hidden="true" />
            <span>{b.text}</span>
            {b.soon && <span className="acct-cap-soon"><Badge tone="neutral">Скоро</Badge></span>}
          </li>
        ))}
      </ul>
      <button type="button" className="acct-cap-link" onClick={() => onNavigate("pricing")}>
        Сравнить все тарифы →
      </button>
    </section>
  );

  return (
    <div className="acct-screen">
      <div className="acct-page">
        <div className="acct-stack">
          <header className="acct-hero">
            <div className="acct-hero-top">
              <div className="acct-hero-id">
                <div className="acct-hero-avatar" aria-hidden="true">{initials}</div>
                <div className="acct-hero-main">
                  <h1 className="acct-hero-name">{user.email}</h1>
                  <div className="acct-hero-meta">
                    <span className="acct-hero-since">В Basis с {fmtDate(user.created_at)}</span>
                    <span className="acct-hero-plan">{tier.name}</span>
                    <span className="acct-status">
                      <span className={`acct-status-dot${user.is_active ? "" : " acct-status-dot--off"}`} aria-hidden="true" />
                      {user.is_active ? "Активен" : "Заблокирован"}
                    </span>
                  </div>
                </div>
              </div>
              <Button
                variant="secondary"
                className="acct-pill acct-logout-btn"
                iconLeft={<LogOut size={15} aria-hidden="true" />}
                onClick={onLogout}
              >
                Выйти
              </Button>
            </div>
            <div className="acct-tabs" role="tablist" aria-label="Разделы профиля">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  className={`acct-tab${tab === t.id ? " acct-tab--on" : ""}`}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </header>

          {tab === "overview" && (
            <div className="acct-cols">
              <div className="acct-col">
                {dataPanel}
                {tourPanel}
                {securityPanel}
              </div>
              <div className="acct-col">
                {planDeep}
                {capPanel}
              </div>
            </div>
          )}
          {tab === "plan" && (
            <div className="acct-cols">
              <div className="acct-col">{planDeep}</div>
              <div className="acct-col">{capPanel}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
