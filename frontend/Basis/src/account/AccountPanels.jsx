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
  const cardRef = useRef(null);
  const triggerRef = useRef(null);

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

  const switchMode = (m) => { setMode(m); setError(null); };

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
        </form>
      </div>

      <div className="auth-foot">© 2026 Basis</div>
    </div>
  );
};

export { AuthModal };
