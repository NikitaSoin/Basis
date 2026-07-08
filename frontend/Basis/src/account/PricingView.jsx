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
import { StatInline } from "../design/textblocks";
import { formatNumber } from "../design/format";
import { TIERS, COMPARE_GROUPS, TIER_RANK } from "./tierCatalog";
import "../styles/account.css";

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
        <div className="view-header">
          <h1 className="view-title">Тарифы</h1>
          <p className="view-subtitle">
            Вердикт и вся ширина продукта — бесплатно. Глубина разбора и живой ИИ-слой — платно.
          </p>
        </div>

        {user && (
          <div className="tar-status">
            Сейчас у вас тариф <b>{TIERS.find((t) => t.id === currentTierId)?.name || "Бесплатный"}</b>
          </div>
        )}

        <AppearGroup gate={appearGate.current} groupId="tar-grid" className="tar-grid">
          {TIERS.map((tier) => {
            const isPlus = tier.id === "plus";
            const isCurrent = currentTierId === tier.id;
            const rankDiff = currentTierId ? TIER_RANK[tier.id] - TIER_RANK[currentTierId] : null;
            const busy = busyTier === tier.id;
            const disabledByOther = busyTier !== null && busyTier !== tier.id;
            const err = errorInfo && errorInfo.tierId === tier.id ? errorInfo.message : null;

            return (
              <div key={tier.id} className={`tar-card${isPlus ? " tar-card--plus" : ""}`}>
                <div className="tar-eyebrow-slot">
                  {tier.eyebrow && <span className="cc-eyebrow tar-eyebrow">{tier.eyebrow}</span>}
                </div>
                <h3 className="tar-name">{tier.name}</h3>
                <div className="tar-price">
                  <span className="tar-price-num">
                    {tier.priceRub === 0 ? "Бесплатно" : formatNumber(tier.priceRub)}
                  </span>
                  {tier.priceRub > 0 && <span className="tar-price-period">₽/мес</span>}
                </div>
                {tier.id === "free" && (
                  <div className="tar-quota">
                    <StatInline value="3" unit="в месяц" label="Глубоких разборов" />
                  </div>
                )}
                <p className="tar-desc">{tier.description}</p>
                <ul className="tar-bullets">
                  {tier.bullets.map((b, i) => (
                    <li key={i} className={`tar-bullet${b.accent ? " tar-bullet--accent" : ""}`}>
                      <Check size={15} aria-hidden="true" />
                      <span>{b.text}</span>
                      {b.soon && (
                        <Badge tone="neutral" className="tar-bullet-badge">Скоро</Badge>
                      )}
                    </li>
                  ))}
                </ul>

                <div className="tar-cta-slot">
                  {!user ? (
                    <Button variant="primary" className="tw-w-full" onClick={onShowAuth}>
                      Войти / Регистрация
                    </Button>
                  ) : isCurrent ? (
                    <Badge tone="neutral">Ваш текущий тариф</Badge>
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
          Карточки компаний, поиск, весь Скринер, лента и карты Обозревателя, состав портфеля любого
          размера — доступны без ограничений на всех тарифах. Ниже — только то, чем тарифы отличаются.
        </p>

        <div className="tar-compare-scroll">
          <div className="tar-compare" role="table" aria-label="Отличия между тарифами">
            <div className="tar-compare-head" role="row">
              <div className="tar-compare-head-cell tar-compare-head-cell--label" role="columnheader">
                Что отличается
              </div>
              {TIERS.map((t) => (
                <div
                  key={t.id}
                  role="columnheader"
                  className={`tar-compare-head-cell${currentTierId === t.id ? " tar-compare-head-cell--current" : ""}`}
                >
                  {t.name}
                </div>
              ))}
            </div>
            {COMPARE_GROUPS.map((group) => (
              <div className="tar-compare-group" key={group.title}>
                <div className="tar-compare-group-t">{group.title}</div>
                {group.rows.map((row) => (
                  <div className="tar-compare-row" role="row" key={row.key}>
                    <div className="tar-compare-row-label" role="rowheader">{row.label}</div>
                    {TIERS.map((t) => {
                      const val = t.compareCells[row.key];
                      const isCurrentCol = currentTierId === t.id;
                      return (
                        <div
                          key={t.id}
                          role="cell"
                          className={`tar-compare-cell${isCurrentCol ? " tar-compare-cell--current" : ""}`}
                        >
                          {val === "Скоро" ? (
                            <Badge tone="neutral">Скоро</Badge>
                          ) : val ? (
                            <span>{val}</span>
                          ) : (
                            <span className="tar-compare-cell--dash">—</span>
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
