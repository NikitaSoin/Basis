import React, { useState, useEffect, useRef } from "react";
import { X } from "lucide-react";
import { Button, IconButton } from "../design/primitives";
import "../styles/account.css";

// AuthModal — вариант 1b прототипа docs/«Регистрация и профиль.dc.html»
// (раскатка 2026-07-17): центрированная карточка, вкладки «Вход/Регистрация»
// с медным подчёркиванием, лого над карточкой, футер под ней. Стили — .auth-*
// в styles/account.css. Осознанные отходы от прототипа (бэкенд умеет только
// email+пароль, backend/app/api/auth.py): телефон/SMS и «Забыли пароль?» не
// раскатаны; строка согласия «условия сервиса / политика конфиденциальности»
// не перенесена — таких страниц на сайте ещё нет, мёртвые ссылки не рисуем.
//
// Поведение модала повторяет примитив Modal (design/primitives.jsx): Escape,
// focus-trap по Tab/Shift+Tab, возврат фокуса на триггер при закрытии, клик
// по скриму закрывает. Сам примитив не используется: у него жёсткий хром
// (тайтл-бар, свои паддинги), в который композиция 1b не укладывается.
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

const AuthModal = ({ onClose, onSuccess }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // Двухшаговая регистрация с кодом на email: step "form" → "code".
  // Шаг кода появляется, ТОЛЬКО если бэк ответил, что отправил письмо
  // (SMTP настроен); иначе register/request-code вернёт "disabled" и
  // регистрация проходит по-старому одним шагом.
  const [regStep, setRegStep] = useState("form");
  const [code, setCode] = useState("");
  const [resendIn, setResendIn] = useState(0);
  const cardRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (resendIn <= 0) return;
    const t = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [resendIn]);

  useEffect(() => {
    triggerRef.current = document.activeElement;
    const onKey = (e) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !cardRef.current) return;
      const focusable = Array.from(cardRef.current.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
        (el) => el.offsetParent !== null
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !cardRef.current.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !cardRef.current.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (triggerRef.current && typeof triggerRef.current.focus === "function") {
        triggerRef.current.focus();
      }
    };
  }, [onClose]);

  const finishAuth = (data) => {
    localStorage.setItem("basis_token", data.access_token);
    localStorage.setItem("basis_user", JSON.stringify(data.user));
    onSuccess(data.user, data.access_token);
  };

  const post = async (path, body) => {
    const resp = await fetch(`${apiUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || "Ошибка авторизации");
    return data;
  };

  const doRegister = (withCode) =>
    post("/api/auth/register", withCode ? { email, password, code: code.trim() } : { email, password });

  const requestCode = () => post("/api/auth/register/request-code", { email });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") {
        finishAuth(await post("/api/auth/login", { email, password }));
      } else if (regStep === "form") {
        const r = await requestCode();
        if (r.status === "sent") { setRegStep("code"); setCode(""); setResendIn(60); }
        else finishAuth(await doRegister(false)); // подтверждение на бэке выключено
      } else {
        finishAuth(await doRegister(true));
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const resend = async () => {
    if (resendIn > 0 || loading) return;
    setError(null);
    try {
      await requestCode();
      setResendIn(60);
    } catch (e) {
      setError(e.message);
    }
  };

  const switchMode = (m) => { setMode(m); setError(null); setRegStep("form"); setCode(""); };

  return (
    <div
      className="auth-overlay"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="auth-brand" aria-hidden="true">
        <span className="auth-brand-mark">◆</span>
        <span className="auth-brand-name">Basis</span>
      </div>

      <div className="auth-card" ref={cardRef} role="dialog" aria-modal="true" aria-label="Вход и регистрация">
        <IconButton size="sm" className="auth-close" aria-label="Закрыть" onClick={onClose}>
          <X size={16} aria-hidden="true" />
        </IconButton>

        <div className="auth-tabs" role="tablist" aria-label="Вход или регистрация">
          {[["login", "Вход"], ["register", "Регистрация"]].map(([m, label]) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              className={`auth-tab${mode === m ? " auth-tab--on" : ""}`}
              onClick={() => switchMode(m)}
            >
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {mode === "register" && regStep === "code" ? (
            <>
              <div className="auth-field">
                <label className="auth-label" htmlFor="auth-code">Код из письма</label>
                <input
                  id="auth-code"
                  className="auth-input"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  required
                  autoFocus
                  autoComplete="one-time-code"
                  placeholder="000000"
                  style={{ fontFamily: "var(--cc-mono)", letterSpacing: "0.35em", textAlign: "center" }}
                />
                <span className="auth-hint">
                  Мы отправили 6-значный код на {email}. Код действует 15 минут.
                </span>
              </div>

              {error && <p className="auth-error" role="alert">{error}</p>}

              <Button type="submit" variant="primary" loading={loading} className="acct-pill tw-w-full">
                Подтвердить и создать аккаунт
              </Button>
              <div className="auth-code-actions">
                <button type="button" className="auth-linkbtn" disabled={resendIn > 0} onClick={resend}>
                  {resendIn > 0 ? `Отправить ещё раз (${resendIn}с)` : "Отправить код ещё раз"}
                </button>
                <button type="button" className="auth-linkbtn" onClick={() => { setRegStep("form"); setError(null); }}>
                  Изменить email
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="auth-field">
                <label className="auth-label" htmlFor="auth-email">Email</label>
                <input
                  id="auth-email"
                  className="auth-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                  autoComplete="email"
                  placeholder="anna@example.com"
                />
              </div>
              <div className="auth-field">
                <label className="auth-label" htmlFor="auth-password">Пароль</label>
                <input
                  id="auth-password"
                  className="auth-input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={mode === "register" ? 8 : undefined}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  placeholder={mode === "login" ? "••••••••" : "Минимум 8 символов"}
                />
                {mode === "register" && <span className="auth-hint">Не короче 8 символов</span>}
              </div>

              {error && <p className="auth-error" role="alert">{error}</p>}

              <Button type="submit" variant="primary" loading={loading} className="acct-pill tw-w-full">
                {mode === "login" ? "Войти" : "Создать аккаунт"}
              </Button>
              {mode === "register" && (
                <p className="auth-hint" style={{ textAlign: "center" }}>Бесплатно, банковская карта не нужна</p>
              )}
            </>
          )}
        </form>
      </div>

      <div className="auth-foot">© 2026 Basis</div>
    </div>
  );
};

export { AuthModal };
