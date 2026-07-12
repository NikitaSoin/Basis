// =============================================================
// ProfileView — NEO. Replaces the legacy inline ProfileView that used to
// live in App.js (gradient avatar, badge-gold, hardcoded binary
// capabilities list). Tariff copy comes from tierCatalog.js — same
// source PricingView reads, so the two pages can never disagree.
//
// Real backend call for the "Перейти на Бесплатный" one-click downgrade:
// POST {apiUrl}/api/auth/me/subscription (see backend/app/api/auth.py).
// No confirm() — owner: cancelling must be as easy as subscribing.
// =============================================================
import React, { useState } from "react";
import { User, LogOut, CreditCard, Check } from "lucide-react";
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

export default function ProfileView({ user, token, onLogout, onNavigate, onShowAuth, onUserUpdate }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

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
                <Button variant="primary" className="tw-w-full" onClick={onShowAuth}>
                  Войти / Регистрация
                </Button>
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

  return (
    <div className="acct-screen">
      <div className="acct-page">
        <div className="acct-sec-head">
          <span className="acct-page-eyebrow">Аккаунт</span>
          <h1 className="acct-h1">Профиль</h1>
        </div>
        <p className="acct-sec-sub">Аккаунт и тарифный план</p>

        <div className="acct-stack">
          <div className="acct-identity">
            <div className="acct-avatar" aria-hidden="true">{initials}</div>
            <div className="acct-identity-main">
              <div className="acct-identity-email">{user.email}</div>
              <div className="acct-identity-sub">В Basis с {fmtDate(user.created_at)}</div>
            </div>
            <div className="acct-status">
              <span
                className={`acct-status-dot${user.is_active ? "" : " acct-status-dot--off"}`}
                aria-hidden="true"
              />
              {user.is_active ? "Активен" : "Заблокирован"}
            </div>
          </div>

          <div className="acct-plan-card">
            <div className="acct-plan-left">
              <span className="acct-plan-eyebrow">Тариф</span>
              <h2 className="acct-plan-name">{tier.name}</h2>
              <p className="acct-plan-desc">{tier.description}</p>
              {isFree && <p className="acct-plan-status tw-mt-3">Квота — 3 глубоких разбора в месяц.</p>}
            </div>
            <div className="acct-plan-right">
              {!isFree && (
                <>
                  <p className="acct-plan-status">
                    {user.subscription_expires_at ? `Активен до ${fmtDate(user.subscription_expires_at)}` : "Тариф активен"}
                  </p>
                  <p className="acct-plan-hint">Автопродление появится вместе с оплатой картой.</p>
                </>
              )}
              <div className="acct-plan-actions">
                <Button variant="secondary" onClick={() => onNavigate("pricing")}>
                  Изменить тариф
                </Button>
                {!isFree && (
                  <Button variant="ghost" loading={busy} disabled={busy} onClick={() => changeTier("free")}>
                    Перейти на Бесплатный
                  </Button>
                )}
              </div>
              {error && <p className="tar-error">{error}</p>}
            </div>
          </div>

          <div className="acct-grid2">
            <div className="acct-row-list">
              <div className="acct-row">
                <span className="acct-row-label">Email</span>
                <span className="acct-row-value">{user.email}</span>
              </div>
              <div className="acct-row">
                <span className="acct-row-label">Дата регистрации</span>
                <span className="acct-row-value">{fmtDate(user.created_at)}</span>
              </div>
              <div className="acct-row">
                <span className="acct-row-label">Статус</span>
                <span className="acct-row-value">{user.is_active ? "Активен" : "Заблокирован"}</span>
              </div>
            </div>

            <div className="acct-cap-card">
              <div className="acct-cap-title">Возможности тарифа «{tier.name}»</div>
              <ul className="acct-cap-list">
                {tier.bullets.map((b, i) => (
                  <li key={i} className="acct-cap-item">
                    <Check size={15} aria-hidden="true" />
                    <span>{b.text}</span>
                  </li>
                ))}
              </ul>
              <button type="button" className="acct-cap-link" onClick={() => onNavigate("pricing")}>
                Сравнить все тарифы →
              </button>
            </div>
          </div>

          <div className="acct-billing-card">
            <span className="acct-billing-icon">
              <CreditCard size={20} aria-hidden="true" />
            </span>
            <div className="acct-billing-body">
              <div className="acct-billing-title">
                Способ оплаты не подключён
                <Badge tone="neutral">Скоро</Badge>
              </div>
              <p className="acct-billing-note">
                История платежей и привязка карты появятся с запуском оплаты. Сейчас тариф переключается
                мгновенно и бесплатно.
              </p>
            </div>
          </div>

          <div className="acct-logout">
            <Button
              variant="ghost"
              className="acct-logout-btn"
              iconLeft={<LogOut size={15} aria-hidden="true" />}
              onClick={onLogout}
            >
              Выйти из аккаунта
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
