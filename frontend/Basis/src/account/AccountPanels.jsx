import React, { useState, useRef } from "react";
import { Check, LogOut, User, Zap } from "lucide-react";
import { Button, Card, Badge } from "../design/primitives";
import { formatMoney } from "../design/format";
import { AppearGroup, PageDecor, DECOR_ENABLED } from "../design/motion";

const AuthModal = ({ onClose, onSuccess }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const resp = await fetch(`${apiUrl}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Ошибка авторизации");
      localStorage.setItem("basis_token", data.access_token);
      localStorage.setItem("basis_user", JSON.stringify(data.user));
      onSuccess(data.user, data.access_token);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between p-6 border-b border-slate-700">
          <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
            {["login", "register"].map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(null); }}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${mode === m ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"}`}
              >
                {m === "login" ? "Войти" : "Регистрация"}
              </button>
            ))}
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white text-xl">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="text-slate-400 text-sm mb-1 block">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-indigo-500"
            />
          </div>
          <div>
            <label className="text-slate-400 text-sm mb-1 block">Пароль</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="••••••••"
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-indigo-500"
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white py-3 rounded-xl font-bold transition-all"
          >
            {loading ? "Загружаем..." : mode === "login" ? "Войти в систему" : "Создать аккаунт"}
          </button>
        </form>
      </div>
    </div>
  );
};

// =========================
// PROFILE VIEW (full page)
// =========================

const ProfileView = ({ user, token, onLogout, onNavigate, onShowAuth }) => {
  if (!user) {
    return (
      <div style={{ maxWidth: 440, margin: "80px auto", textAlign: "center" }}>
        <div style={{
          width: 80, height: 80, borderRadius: "50%",
          background: "var(--bg-surface)",
          border: "1px solid var(--border-mid)",
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 20px",
        }}>
          <User size={36} style={{ color: "var(--text-3)" }} />
        </div>
        <h2 style={{ color: "var(--text-1)", fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Войдите в аккаунт</h2>
        <p style={{ color: "var(--text-2)", marginBottom: 24 }}>Для доступа к профилю необходимо авторизоваться</p>
        <button className="btn btn-primary" style={{ justifyContent: "center", width: "100%", padding: "12px" }} onClick={onShowAuth}>
          Войти / Регистрация
        </button>
      </div>
    );
  }

  const isPremium = user.subscription_type === "premium";
  const initials = user.email.slice(0, 2).toUpperCase();

  const capabilities = [
    { label: "Экспресс-обзор рынка", ok: true },
    { label: "Детальный и глубокий обзор", ok: isPremium },
    { label: "Портфель (до 5 позиций)", ok: true },
    { label: "Безлимитный портфель", ok: isPremium },
    { label: "AI-анализ компаний", ok: isPremium },
    { label: "Стресс-тестирование", ok: isPremium },
  ];

  return (
    <div style={{ maxWidth: 800, margin: "0 auto" }}>
      <div className="view-header">
        <h1 className="view-title">Профиль</h1>
        <p className="view-subtitle">Настройки аккаунта и тарифный план</p>
      </div>

      <div className="profile-grid" style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 20, alignItems: "start" }}>
        {/* Left column: avatar + tier */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ textAlign: "center", padding: 28 }}>
            <div style={{
              width: 72, height: 72, borderRadius: "50%",
              background: "linear-gradient(135deg, var(--accent), var(--accent-h))",
              display: "flex", alignItems: "center", justifyContent: "center",
              margin: "0 auto 16px",
              fontSize: 24, fontWeight: 800, color: "var(--on-accent)",
            }}>
              {initials}
            </div>
            <div style={{ fontWeight: 700, color: "var(--text-1)", marginBottom: 4, wordBreak: "break-all" }}>
              {user.email}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 14 }}>
              В системе с {new Date(user.created_at).toLocaleDateString("ru-RU")}
            </div>
            {isPremium ? (
              <span className="badge badge-gold">★ Premium</span>
            ) : (
              <span className="badge badge-neu">Базовый тариф</span>
            )}
          </div>

          <div className="card" style={{
            background: isPremium ? "linear-gradient(135deg, var(--gold-fade), var(--bg-card))" : undefined,
            borderColor: isPremium ? "var(--gold-border)" : undefined,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontWeight: 600, color: "var(--text-1)", fontSize: 14 }}>Тариф</span>
              <span className={isPremium ? "badge badge-gold" : "badge badge-neu"}>{isPremium ? "PREMIUM" : "FREE"}</span>
            </div>
            {isPremium && user.subscription_expires_at && (
              <p style={{ fontSize: 12, color: "var(--text-2)", marginBottom: 12 }}>
                Активен до {new Date(user.subscription_expires_at).toLocaleDateString("ru-RU")}
              </p>
            )}
            <button
              className={`btn w-full ${isPremium ? "btn-gold" : "btn-primary"}`}
              style={{ justifyContent: "center" }}
              onClick={() => onNavigate("pricing")}
            >
              {isPremium ? "Управлять подпиской" : "Перейти на Premium →"}
            </button>
          </div>

          <button
            className="btn btn-ghost"
            style={{ justifyContent: "center", color: "var(--negative)", borderColor: "var(--neg-fade)" }}
            onClick={onLogout}
          >
            <LogOut size={15} />
            Выйти из аккаунта
          </button>
        </div>

        {/* Right column: info + capabilities */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text-1)", marginBottom: 16 }}>Данные аккаунта</div>
            {[
              { label: "Email", value: user.email },
              { label: "Тариф", value: isPremium ? "Premium (Максимум)" : "Базовый (Free)" },
              { label: "Дата регистрации", value: new Date(user.created_at).toLocaleDateString("ru-RU", { year: "numeric", month: "long", day: "numeric" }) },
              { label: "Статус", value: user.is_active ? "Активен" : "Заблокирован" },
            ].map(({ label, value }) => (
              <div key={label} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ color: "var(--text-2)", fontSize: 13 }}>{label}</span>
                <span style={{ color: "var(--text-1)", fontSize: 13, fontWeight: 500 }}>{value}</span>
              </div>
            ))}
          </div>

          <div className="card">
            <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text-1)", marginBottom: 16 }}>Возможности тарифа</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {capabilities.map(({ label, ok }) => (
                <div key={label} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "10px 12px", borderRadius: 10,
                  background: ok ? "var(--accent-fade)" : "var(--bg-surface)",
                  border: `1px solid ${ok ? "var(--accent-border)" : "var(--border)"}`,
                  fontSize: 13, color: ok ? "var(--text-1)" : "var(--text-3)",
                }}>
                  <span style={{ color: ok ? "var(--accent-text)" : "var(--text-3)" }}>{ok ? "✓" : "✕"}</span>
                  {label}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// =========================
// PRICING VIEW
// =========================

const PricingView = ({ user, onShowAuth }) => {
  // Appear gate (Phase 4b): page-level so the plan cards stagger once on entry.
  const appearGate = useRef(new Set());
  const isPremium = user?.subscription_type === "premium";
  const isFree = !isPremium && !!user;

  const freeFeatures = [
    "Экспресс-обзор рынка",
    "Карточки всех компаний",
    "Портфель до 5 позиций",
    "Базовая аналитика",
  ];

  const premiumFeatures = [
    "Детальный и глубокий обзор рынка",
    "Безлимитный портфель",
    "AI-анализ компаний (Claude)",
    "Стресс-тестирование",
    "Приоритетные обновления",
    "Ранний доступ к новым функциям",
  ];

  // Feature row: coloured check glyph + label. `tone` lets premium-exclusive
  // perks read in cobalt-accent (dosed colour) while base perks stay success-green.
  const FeatureItem = ({ children, tone = "success" }) => (
    <li className="tw-flex tw-items-start tw-gap-2 tw-text-[14px] tw-leading-[22px] tw-text-text-secondary">
      <Check
        size={16}
        className={`tw-shrink-0 tw-mt-0.5 ${tone === "accent" ? "tw-text-accent" : "tw-text-success"}`}
        aria-hidden="true"
      />
      <span>{children}</span>
    </li>
  );

  return (
    // The PAGE (not the short header) owns the decor now. The pricing header is
    // only ~76px tall, so a full orbit placed inside it had its lower half clipped
    // by overflow-hidden (owner: «орбита со спутником пропала»). Lifting the decor
    // to the page gives it vertical room: a full-size orbit + accent glow live in
    // the top-right corner, behind the cards (content is tw-relative → above decor),
    // so the WHOLE ring + its tracing satellite read. pointer-events-none, no layout
    // shift; overflow-hidden clips only the decorative bleed (no h-scroll), and the
    // orbit is inset enough that card hover-lift is never clipped.
    <div className="tw-relative tw-overflow-hidden">
      {DECOR_ENABLED && (
        <div
          aria-hidden="true"
          className="tw-pointer-events-none tw-fixed tw-right-0 tw-top-0"
          style={{
            zIndex: 0,
            width: 480,
            height: 480,
            /* Same corner-anchored language as the landing hero, and FIXED to the
               window's top-right corner for the same reason: inside the narrow
               overflow-hidden wrapper its right edge was sliced into a hard vertical
               line. position:fixed pulls it out of the clipping box, anchors it to
               the viewport corner, no horizontal scroll, behind content. The mid
               violet (--accent-2) stop adds a subtle hue shift; light-theme tokens
               are transparent → dark-only decor. */
            background:
              "radial-gradient(120% 120% at 100% 0%, var(--decor-glow) 0%, var(--decor-glow-2) 35%, transparent 70%)",
          }}
        />
      )}
      {/* Orbit pinned to the SAME window top-right corner as the glow above
          (position:fixed overrides PageDecor's default tw-absolute) so ring +
          planet sit inside the glow as one unified corner element. Dark-only via
          --decor-opacity (0 in light); reduced-motion keeps the ring static. */}
      <PageDecor
        variant="orbit"
        className=""
        style={{ position: "fixed", top: 128, right: 16, width: 220, height: 220, opacity: "var(--decor-opacity)" }}
      />
      {/* Hero header — MARKETING surface (conversion / first touch). Same language
          as the landing hero: violet→cobalt gradient title clipped into the glyphs
          + one-time sweep. Content sits above the page decor (tw-relative). */}
      <div className="tw-relative tw-pb-2 tw-mb-6">
        <h1
          className="tw-relative tw-font-display tw-m-0 tw-mb-2"
          style={{
            fontSize: 36,
            lineHeight: "44px",
            letterSpacing: "-0.01em",
            fontWeight: 600,
            backgroundImage: "linear-gradient(135deg, var(--accent-2) 0%, var(--accent) 100%)",
            backgroundSize: "200% 100%",
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            WebkitTextFillColor: "transparent",
            color: "transparent",
            display: "inline-block",
            animation: "basis-hero-sweep 600ms var(--ease-out) both",
          }}
        >
          Тарифные планы
        </h1>
        <p className="tw-relative tw-text-text-secondary tw-m-0" style={{ fontSize: 16, lineHeight: "24px" }}>
          Выберите уровень доступа, который вам подходит
        </p>
      </div>

      <AppearGroup gate={appearGate.current} groupId="pricing" stagger={70} rise={16} className="tw-relative tw-grid tw-gap-6 tw-grid-cols-1 md:tw-grid-cols-2 tw-max-w-3xl">
        {/* FREE */}
        <Card className={isFree ? "tw-ring-1 tw-ring-accent" : ""}>
          <div className="tw-flex tw-flex-col tw-gap-2">
            <div className="tw-flex tw-items-center tw-justify-between tw-gap-2">
              <p className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-m-0">Базовый</p>
              {isFree && <Badge tone="accent">Текущий план</Badge>}
            </div>
            <p className="tw-text-[14px] tw-text-text-tertiary tw-m-0">Для начинающих инвесторов</p>
            <div className="tw-mt-2 tw-mb-4">
              <span
                className="tw-font-display tw-font-light tw-text-text-primary"
                style={{ fontSize: "32px", lineHeight: "1", letterSpacing: "-0.5px" }}
              >
                Бесплатно
              </span>
            </div>
            <ul className="tw-flex tw-flex-col tw-gap-2.5 tw-list-none tw-p-0 tw-m-0">
              {freeFeatures.map((f, i) => (
                <FeatureItem key={i}>{f}</FeatureItem>
              ))}
            </ul>
            {!user && (
              <Button variant="primary" className="tw-w-full tw-mt-4" onClick={onShowAuth}>
                Начать бесплатно
              </Button>
            )}
          </div>
        </Card>

        {/* PREMIUM — recommended plan, highlighted BRIGHTER (marketing): a 2px
            accent ring + a soft accent-tinted surface + a violet→cobalt gradient
            "Рекомендуем" badge. Colour lives in the ring/badge/accent checks ONLY;
            the CTA button stays the single cobalt primary (untouched). */}
        <Card className={`tw-relative tw-ring-2 tw-ring-accent ${isPremium ? "" : "tw-bg-accent-soft"}`}>
          {/* Gradient "recommended" badge — top-right corner ribbon, marketing accent. */}
          <span
            className="tw-absolute tw-top-3 tw-right-3 tw-inline-flex tw-items-center tw-gap-1 tw-rounded-pill tw-px-2.5 tw-py-0.5 tw-text-[11px] tw-font-semibold tw-leading-[18px] tw-text-on-accent tw-shadow-sm"
            style={{ backgroundImage: "linear-gradient(135deg, var(--accent-2) 0%, var(--accent) 100%)" }}
          >
            <Zap size={11} aria-hidden="true" />
            Рекомендуем
          </span>
          <div className="tw-flex tw-flex-col tw-gap-2">
            <div className="tw-flex tw-items-center tw-gap-2">
              <p className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-m-0">Максимум</p>
              {isPremium ? <Badge tone="success">Активен</Badge> : <Badge tone="accent">Premium</Badge>}
            </div>
            <p className="tw-text-[14px] tw-text-text-tertiary tw-m-0">Полный арсенал аналитика</p>
            <div className="tw-mt-2 tw-mb-4 tw-flex tw-items-baseline tw-gap-1.5">
              <span
                className="tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums"
                style={{ fontSize: "32px", lineHeight: "1", letterSpacing: "-0.5px" }}
              >
                {formatMoney(990)}
              </span>
              <span className="tw-text-[14px] tw-text-text-tertiary">/мес</span>
            </div>
            <ul className="tw-flex tw-flex-col tw-gap-2.5 tw-list-none tw-p-0 tw-m-0">
              {premiumFeatures.map((f, i) => (
                <FeatureItem key={i} tone="accent">{f}</FeatureItem>
              ))}
            </ul>
            {!isPremium && (
              <Button variant="primary" className="tw-w-full tw-mt-4">
                Перейти на Premium
              </Button>
            )}
            {isPremium && user?.subscription_expires_at && (
              <p className="tw-text-[13px] tw-text-success tw-mt-3 tw-mb-0">
                Подписка активна до {new Date(user.subscription_expires_at).toLocaleDateString("ru-RU")}
              </p>
            )}
          </div>
        </Card>
      </AppearGroup>
    </div>
  );
};

// =========================
// PROFILE PANEL (sidebar popup)
// =========================
// NEWS FEED (Обозреватель · Направление 1 — Лента новостей)
// =========================

const _RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря"];

// «Выпуск HH:MM, DD месяца» из cluster_id (префикс YYYYMMDDHHMM в UTC → МСК +3).
function _issueLabel(clusterId) {
  if (!clusterId || clusterId.length < 12) return "Выпуск";
  const p = clusterId.slice(0, 12);
  const y = +p.slice(0, 4), mo = +p.slice(4, 6) - 1, d = +p.slice(6, 8),
        h = +p.slice(8, 10), mi = +p.slice(10, 12);
  const dt = new Date(Date.UTC(y, mo, d, h, mi));
  dt.setUTCHours(dt.getUTCHours() + 3); // МСК
  const hh = String(dt.getUTCHours()).padStart(2, "0");
  const mm = String(dt.getUTCMinutes()).padStart(2, "0");
  return `Выпуск ${hh}:${mm}, ${dt.getUTCDate()} ${_RU_MONTHS[dt.getUTCMonth()]}`;
}

// Время публикации новости в МСК: «13:45» если сегодня, иначе «14.06 13:45».
function _newsTime(iso) {
  try {
    const dt = new Date(iso);
    if (isNaN(dt)) return "";
    const msk = new Date(dt.getTime() + (dt.getTimezoneOffset() + 180) * 60000);
    const hh = String(msk.getHours()).padStart(2, "0");
    const mm = String(msk.getMinutes()).padStart(2, "0");
    const nowMsk = new Date(Date.now() + (new Date().getTimezoneOffset() + 180) * 60000);
    const sameDay = msk.getDate() === nowMsk.getDate() && msk.getMonth() === nowMsk.getMonth();
    return sameDay ? `${hh}:${mm}` : `${String(msk.getDate()).padStart(2, "0")}.${String(msk.getMonth() + 1).padStart(2, "0")} ${hh}:${mm}`;
  } catch { return ""; }
}


export { AuthModal, ProfileView, PricingView };
