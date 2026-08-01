// =============================================================
// InfoTip — кружок «i», по клику раскрывающий пояснение.
//
// Владелец (2026-08-02): длинные методические оговорки под графиками
// Геополитики («Относится только к очагу СВО. История — по АРХИВНЫМ картам
// ISW…», «Шкала по вертикали НЕЛИНЕЙНАЯ…») читались как простыня и мешали
// смотреть на сам график — «вот это в таком формате: кружочек буква i, при
// нажатии появляется менюшка с пояснением».
//
// Компонент общий, а не третья копия: тот же паттерн уже жил ДВАЖДЫ —
// screener/ScreenerNeo.jsx::InfoTip и screener/BondScreenerNeo.jsx::InfoTip
// (одинаковый код, свои классы sc-infotip*). Здесь канонический вариант;
// скринеры можно перевести на него отдельным заходом — трогать их сейчас
// значило бы рисковать регрессом ради косметики.
//
// Клик, а не hover: доступнее и работает на телефоне (на тач-устройствах
// hover-подсказка либо не открывается, либо залипает).
// position: fixed с координатами от getBoundingClientRect, НЕ absolute:
// кнопка часто лежит внутри контейнеров с overflow:hidden (карта, панели
// Обозревателя) — absolute-поповер там обрезается родителем. fixed от
// overflow предков не зависит вообще.
// =============================================================
import React, { useEffect, useRef, useState } from "react";

const POP_WIDTH = 300;

export default function InfoTip({ text, label = "Пояснение", className = "" }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const popRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (btnRef.current && btnRef.current.contains(e.target)) return;
      if (popRef.current && popRef.current.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    const onScroll = () => setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    // capture: поповер закрывается при скролле ЛЮБОГО предка (координаты fixed
    // иначе «отстанут» от кнопки и подсказка повиснет посреди экрана)
    window.addEventListener("scroll", onScroll, { capture: true });
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, { capture: true });
    };
  }, [open]);

  if (!text) return null;

  const toggle = (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      const left = Math.max(12, Math.min(r.left, window.innerWidth - POP_WIDTH - 12));
      // если снизу мало места — открываем вверх, иначе на мобильном подсказка
      // уезжает за нижний край экрана
      const openUp = r.bottom + 220 > window.innerHeight && r.top > 240;
      setPos({ top: openUp ? undefined : r.bottom + 6, bottom: openUp ? window.innerHeight - r.top + 6 : undefined, left });
    }
    setOpen((o) => !o);
  };

  return (
    <span className={`bs-infotip${className ? ` ${className}` : ""}`}>
      <button
        ref={btnRef}
        type="button"
        className="bs-infotip-btn"
        aria-label={label}
        aria-expanded={open}
        onClick={toggle}
      >
        i
      </button>
      {open && pos && (
        <span
          ref={popRef}
          className="bs-infotip-pop"
          style={{ position: "fixed", top: pos.top, bottom: pos.bottom, left: pos.left, width: POP_WIDTH }}
          onClick={(e) => e.stopPropagation()}
          role="tooltip"
        >
          {text}
        </span>
      )}
    </span>
  );
}
