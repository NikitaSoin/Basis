import React, { useEffect, useState } from "react";
import { Menu } from "lucide-react";
import "../styles/mobile-sidebar-drawer.css";

// =========================
// MOBILE SIDEBAR DRAWER — переиспользуемый паттерн «выезжающий сайдбар»
// для мобильных экранов ≤760px (Портфель/Скринер, владелец 2026-07-21):
// «сайдбара слева нет — надо сделать чтобы была возможность открыть и
// закрыть его» — toggle-able drawer (не bespoke нижний таббар, как у
// Рынка — тот паттерн уже есть и не трогается).
// CSS-рецепт — styles/mobile-sidebar-drawer.css (классы msd-*). Здесь —
// состояние + доступность (Escape закрывает, лок скролла body, пока
// открыт) и два общих кусочка разметки, чтобы не писать их дважды.
// =========================

/** Состояние drawer'а: [open, setOpen]. Пока открыт — Escape закрывает,
 * фокус переходит внутрь сайдбара и не выходит за его пределы (Tab/
 * Shift+Tab зациклены, тот же паттерн, что у MobileMoreSheet в App.js —
 * без этого клавиатура/скринридер могли бы уйти в скрытый под drawer'ом
 * контент, хоть он и не виден), скролл фона заблокирован, при закрытии
 * фокус возвращается на элемент, с которого открыли. Ищет открытый
 * сайдбар по классам .msd-drawer.msd-drawer--open (сам класс вешает
 * страница-потребитель) — хук не завязан на конкретный DOM-узел через ref,
 * поэтому его можно переиспользовать без изменений на любой странице. */
export function useMobileSidebarDrawer() {
  const [open, setOpen] = useState(false);
  // ОТК (basis-design-reviewer, WARNING): .pf-sidebar/.scmp-sidebar остаются
  // смонтированы и на десктопе (докованы), и на мобильном (просто задвинуты
  // transform'ом, не display:none) — их кнопки навигации всегда есть в DOM.
  // Без этого флага на мобильном, пока drawer закрыт, Tab/скринридер уходили
  // бы в невидимые задвинутые за экран пункты меню ПЕРЕД основным контентом.
  // isNarrow — только сигнал «ниже 760px»; сам inert (см. использование в
  // Портфеле/Скринере) применяют только когда isNarrow && !open, на десктопе
  // сайдбар остаётся полностью интерактивным всегда.
  const [isNarrow, setIsNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 760px)").matches
  );
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 760px)");
    const onChange = () => setIsNarrow(mq.matches);
    onChange();
    (mq.addEventListener ? mq.addEventListener("change", onChange) : mq.addListener(onChange));
    return () => (mq.removeEventListener ? mq.removeEventListener("change", onChange) : mq.removeListener(onChange));
  }, []);
  useEffect(() => {
    if (!open) return undefined;
    const triggerEl = document.activeElement;
    const drawerEl = document.querySelector(".msd-drawer.msd-drawer--open");
    const focusableSelector = "button:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])";
    drawerEl?.querySelector(focusableSelector)?.focus();

    const onKey = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key !== "Tab") return;
      const el = document.querySelector(".msd-drawer.msd-drawer--open");
      if (!el) return;
      const focusable = Array.from(el.querySelectorAll(focusableSelector));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !el.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !el.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      if (triggerEl && document.body.contains(triggerEl)) triggerEl.focus();
    };
  }, [open]);
  return [open, setOpen, isNarrow];
}

/** Мобильная подшапка над контентом: кнопка-гамбургер + название
 * текущего раздела (чтобы после закрытия сайдбара было видно, где
 * находишься). На >760px невидима (см. .msd-section-bar). */
export function MobileSectionBar({ title, open, onOpenMenu }) {
  return (
    <div className="msd-section-bar">
      <button
        type="button"
        className="msd-toggle"
        onClick={onOpenMenu}
        aria-label="Открыть меню разделов"
        aria-haspopup="true"
        aria-expanded={!!open}
      >
        <Menu size={18} aria-hidden="true" />
      </button>
      {title && <span className="msd-section-title">{title}</span>}
    </div>
  );
}

/** Полупрозрачный фон за выехавшим сайдбаром — клик вне сайдбара
 * закрывает drawer. Рендерить только когда open === true. */
export function MobileDrawerBackdrop({ onClose }) {
  return (
    <div
      className="msd-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      aria-hidden="true"
    />
  );
}
