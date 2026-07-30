import React, { useState, useEffect, useRef } from "react";

// Кружок «i» с пояснением. Позиционирование ФИКСИРОВАННОЕ с зажимом в границы окна:
// с absolute+left:0 всплывашка обрезалась правым краем экрана, когда кнопка стоит у
// правого края (владелец прислал скриншот с телефона 2026-07-30 — текст уезжал за
// экран и читалась половина). Тот же приём, что у InfoTip в скринере.
// Кнопка сделана заметнее (медный контур и цвет вместо серого): владелец «эту букву i
// плохо видно».
export const InfoDot = ({ text, label = "Пояснение" }) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const popRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (btnRef.current && btnRef.current.contains(e.target)) return;
      if (popRef.current && popRef.current.contains(e.target)) return;
      setOpen(false);
    };
    const onEsc = (e) => { if (e.key === "Escape") setOpen(false); };
    const onScroll = () => setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    window.addEventListener("scroll", onScroll, { capture: true, passive: true });
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
      window.removeEventListener("scroll", onScroll, { capture: true });
    };
  }, [open]);
  if (!text) return null;
  const toggle = (e) => {
    e.stopPropagation(); e.preventDefault();
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      const W = Math.min(320, window.innerWidth - 24);
      const left = Math.max(12, Math.min(r.left, window.innerWidth - W - 12));
      // если снизу мало места — открываем вверх, чтобы не уезжало под нижнюю панель
      const openUp = r.bottom + 240 > window.innerHeight && r.top > 260;
      setPos({ top: openUp ? undefined : r.bottom + 8, bottom: openUp ? window.innerHeight - r.top + 8 : undefined, left, width: W });
    }
    setOpen((o) => !o);
  };
  return (
    <span className="tw-inline-flex tw-align-middle">
      <button ref={btnRef} type="button" aria-label={label} aria-expanded={open} onClick={toggle}
        className="tw-w-[18px] tw-h-[18px] tw-rounded-full tw-border tw-border-accent tw-bg-accent-soft tw-text-accent tw-text-[11px] tw-font-bold tw-leading-none tw-inline-flex tw-items-center tw-justify-center tw-cursor-pointer tw-p-0 hover:tw-bg-accent hover:tw-text-white">i</button>
      {open && pos && (
        <span ref={popRef} role="tooltip" onClick={(e) => e.stopPropagation()}
          style={{ position: "fixed", top: pos.top, bottom: pos.bottom, left: pos.left, width: pos.width, zIndex: 90 }}
          className="tw-p-3 tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-elevated tw-shadow-lg tw-text-[12.5px] tw-leading-relaxed tw-text-text-secondary tw-font-normal tw-normal-case tw-tracking-normal">
          {text}
        </span>
      )}
    </span>
  );
};

export default InfoDot;
