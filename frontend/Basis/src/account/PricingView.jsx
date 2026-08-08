// =============================================================
// PricingView — NEO. Replaces the legacy inline PricingView that used to
// live in App.js (var(--text-1) inline styles, orbit decor, gradient
// sweep <h1>, binary isPremium, dead "Перейти на Premium" button with no
// onClick). Copy comes from tierCatalog.js so this page can never drift
// from ProfileView's own tariff summary.
//
// Real backend call: POST {apiUrl}/api/auth/me/subscription
// (Authorization: Bearer token, body {tier}) — see backend/app/api/auth.py.
// No confirm()/Modal on up- or downgrade — owner: "без препятствий".
// =============================================================
import React, { useRef, useState } from "react";
import { Check } from "lucide-react";
import { Button, Badge } from "../design/primitives";
import { AppearGroup } from "../design/motion";
import { formatNumber } from "../design/format";
import { TIERS, COMPARE_GROUPS, TIER_RANK, FREE_LIMITS_ENFORCED } from "./tierCatalog";
import "../styles/account.css";

const cx = (...parts) => parts.filter(Boolean).join(" ");

const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

async function postTier(tierId, token) {
  const r = await fetch(`${apiUrl}/api/auth/me/subscription`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ tier: tierId }),
  });
  if (!r.ok) throw new Error("Не удалось изменить тариф. Попробуйте ещё раз.");
  return r.json();
}

export default function PricingView({ user, token, onShowAuth, onUserUpdate }) {
  const appearGate = useRef(new Set());
  const [busyTier, setBusyTier] = useState(null);
  const [errorInfo, setErrorInfo] = useState(null); // { tierId, message }
  // Период оплаты Max (владелец, 2026-08-01: две стоимости — 390 ₽/мес и 1990 ₽/год).
  // Годовой выбран по умолчанию: он выгоднее, и это честнее показать сразу, а не
  // прятать за переключателем.
  const [billing, setBilling] = useState("year"); // "month" | "year"
  const currentTierId = user ? user.subscription_type || "free" : null;

  async function changeTier(tierId) {
    if (!token) { onShowAuth && onShowAuth(); return; }
    setErrorInfo(null);
    setBusyTier(tierId);
    try {
      const updated = await postTier(tierId, token);
      onUserUpdate && onUserUpdate(updated);
    } catch (e) {
      setErrorInfo({ tierId, message: e.message || "Не удалось изменить тариф. Попробуйте ещё раз." });
    } finally {
      setBusyTier(null);
    }
  }

  return (
    <div className="tar-screen">
      <div className="tar-page">
        <div className="acct-sec-head">
          <span className="acct-page-eyebrow">Аккаунт</span>
          <h1 className="acct-h1">Тарифы</h1>
        </div>
        <p className="acct-sec-sub">
          Работать с платформой можно бесплатно. Вся аналитика и все разборы — в тарифе Max.
        </p>

        {/* 🔴 Владелец, 2026-08-08: «пока всё открыто и бесплатно, платформа новая и
            тестируется» — и это должно быть видно СРАЗУ, а не мелкой строкой перед
            таблицей отличий. Плашка снимается вместе с включением границ
            (FREE_LIMITS_ENFORCED в tierCatalog.js + LIMITS_ROLLOUT на бэкенде). */}
        {!FREE_LIMITS_ENFORCED && (
          <div className="bs-callout tar-open-note">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" /></svg>
            <p>
              <b>Сейчас открыто всё и бесплатно.</b> Платформа новая, мы её обкатываем: тарифы
              ниже описывают, как доступ будет устроен позже, а пока ни одна возможность не
              закрыта — ни аналитика карточек, ни разборы отчётов, ни свои сценарии
              стресс-теста. Оплата картой тоже ещё не подключена.
            </p>
          </div>
        )}

        {user && (
          <div className="tar-status">
            Сейчас у вас тариф <b>{TIERS.find((t) => t.id === currentTierId)?.name || "Бесплатный"}</b>
          </div>
        )}

        {/* Период оплаты Max: 390 ₽/мес или 1990 ₽/год */}
        <div className="tar-billing-wrap">
        <div className="tar-billing" role="group" aria-label="Период оплаты">
          <button
            type="button"
            className={cx("tar-billing-opt", billing === "month" && "tar-billing-opt--on")}
            aria-pressed={billing === "month"}
            onClick={() => setBilling("month")}
          >
            Помесячно
          </button>
          <button
            type="button"
            className={cx("tar-billing-opt", billing === "year" && "tar-billing-opt--on")}
            aria-pressed={billing === "year"}
            onClick={() => setBilling("year")}
          >
            На год
            <span className="tar-billing-save">−57%</span>
          </button>
        </div>
        </div>

        <AppearGroup gate={appearGate.current} groupId="tar-grid" className="tar-grid">
          {TIERS.map((tier) => {
            const isPaid = tier.priceRub > 0;
            const isCurrent = currentTierId === tier.id;
            const rankDiff = currentTierId ? TIER_RANK[tier.id] - TIER_RANK[currentTierId] : null;
            const busy = busyTier === tier.id;
            const disabledByOther = busyTier !== null && busyTier !== tier.id;
            const err = errorInfo && errorInfo.tierId === tier.id ? errorInfo.message : null;

            return (
              <div key={tier.id} className={`tar-card${isPaid ? " tar-card--plus" : ""}`}>
                <div className="tar-eyebrow-slot">
                  {tier.eyebrow && <span className="tar-eyebrow">{tier.eyebrow}</span>}
                </div>
                <h3 className="tar-name">{tier.name}</h3>
                <div className="tar-price">
                  <span className="tar-price-num">
                    {!isPaid
                      ? "Бесплатно"
                      : formatNumber(billing === "year" ? tier.priceRubYear : tier.priceRub)}
                  </span>
                  {isPaid && (
                    <span className="tar-price-period">{billing === "year" ? "₽/год" : "₽/мес"}</span>
                  )}
                </div>
                {isPaid && billing === "year" && (
                  <div className="tar-price-sub">
                    {formatNumber(Math.round(tier.priceRubYear / 12))} ₽ в месяц при оплате за год
                  </div>
                )}
                {isPaid && billing === "month" && (
                  <div className="tar-price-sub">
                    или {formatNumber(tier.priceRubYear)} ₽ за год — выгоднее
                  </div>
                )}
                <p className="tar-desc">{tier.description}</p>
                <ul className="tar-bullets">
                  {tier.bullets.map((b, i) => (
                    <li key={i} className={`tar-bullet${b.accent ? " tar-bullet--accent" : ""}`}>
                      <Check size={15} aria-hidden="true" />
                      <span>
                        {b.text}
                        {b.soon && (
                          <Badge tone="neutral" className="tar-bullet-badge">Скоро</Badge>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="tar-cta-slot">
                  {!user ? (
                    <Button variant="primary" className="tw-w-full" onClick={onShowAuth}>
                      Войти / Регистрация
                    </Button>
                  ) : isCurrent ? (
                    <button type="button" className="tar-cta tar-cta--current" disabled>
                      Ваш текущий тариф
                    </button>
                  ) : (
                    <Button
                      variant={rankDiff > 0 ? "primary" : "secondary"}
                      className="tw-w-full"
                      loading={busy}
                      disabled={disabledByOther}
                      onClick={() => changeTier(tier.id)}
                    >
                      Перейти на {tier.name}
                    </Button>
                  )}
                </div>
                {err && <p className="tar-error">{err}</p>}
              </div>
            );
          })}
        </AppearGroup>

        <p className="tar-note">Тариф применяется сразу, без оплаты картой — она появится позже.</p>

        <p className="tar-compare-lead">
          Поиск, весь Скринер, лента новостей и карты Обозревателя, карточки всех бумаг —
          доступны на обоих тарифах. Ниже — только то, чем тарифы отличаются.
        </p>

        {/* Честная плашка: границы ниже описывают задуманный продукт, но код их
            ещё не применяет (см. FREE_LIMITS_ENFORCED в tierCatalog.js). Без неё
            страница обещала бы бесплатному пользователю ограничения, которых он
            не встретит, и продавала бы Max за то, что и так открыто. */}
        {!FREE_LIMITS_ENFORCED && (
          <p className="tar-note tar-note--soft">
            Пока идёт обкатка, всё перечисленное открыто и на бесплатном тарифе — ограничения
            ниже описывают, как тарифы будут различаться, и включатся позже.
          </p>
        )}

        <div className="tar-compare-scroll">
          <div className="tar-compare" role="table" aria-label="Отличия между тарифами">
            <div className="tar-compare-head" role="row">
              <div className="tar-compare-head-cell tar-compare-head-cell--label" role="columnheader">
                Что отличается
              </div>
              {TIERS.map((t) => {
                const isTierCol = t.priceRub > 0;
                // Max читается медным ВСЕГДА (владелец, 2026-07-12) — «текущий
                // тариф» подсвечивается тем же accent-soft только у Бесплатного,
                // иначе на Max наложились бы два одинаковых фона без смысла.
                const isCurrentCol = currentTierId === t.id && !isTierCol;
                return (
                  <div
                    key={t.id}
                    role="columnheader"
                    className={cx(
                      "tar-compare-head-cell",
                      isTierCol && "tar-compare-head-cell--tier",
                      isCurrentCol && "tar-compare-head-cell--current"
                    )}
                  >
                    {t.name}
                  </div>
                );
              })}
            </div>
            {COMPARE_GROUPS.map((group) => (
              <div className="tar-compare-group" key={group.title}>
                <div className="tar-compare-group-t">{group.title}</div>
                {group.rows.map((row) => (
                  <div className="tar-compare-row" role="row" key={row.key}>
                    <div className="tar-compare-row-label" role="rowheader">{row.label}</div>
                    {TIERS.map((t) => {
                      const val = t.compareCells[row.key];
                      const isTierCol = t.priceRub > 0;
                      const isCurrentCol = currentTierId === t.id && !isTierCol;
                      return (
                        <div
                          key={t.id}
                          role="cell"
                          className={cx(
                            "tar-compare-cell",
                            isTierCol && "tar-compare-cell--tier",
                            isCurrentCol && "tar-compare-cell--current",
                            !val && "tar-compare-cell--dash"
                          )}
                        >
                          {val === "Скоро" ? (
                            <Badge tone="neutral">Скоро</Badge>
                          ) : val ? (
                            <span>{val}</span>
                          ) : (
                            <span>—</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
