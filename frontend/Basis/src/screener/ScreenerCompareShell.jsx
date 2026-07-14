import React, { useState } from "react";
import { Filter, Scale } from "lucide-react";
import { ScreenerView } from "../company/CompanyCardView";
import CompareView from "../compare/CompareView";
import "../styles/screener-compare.css";

// =========================
// SCREENER + COMPARE — общий тёмный сайдбар (владелец, 2026-07-14: «объединить
// скринер и сравнение в один блок, сделать такой же сайдбар как в портфельной
// аналитике и обозревателе»). Структура — точная копия ObserverV2/PortfolioV2:
// фиксированный тёмный сайдбар слева + переключаемая светлая main-зона.
// Оба экрана сохранены как есть (весь функционал), просто переключаются
// пунктом сайдбара вместо двух отдельных пунктов верхней навигации.
// =========================

const SCMP_ZONES = [
  {
    id: "tools",
    label: "Инструменты",
    items: [
      { id: "screener", label: "Скринер", icon: Filter },
      { id: "compare", label: "Сравнение активов", icon: Scale },
    ],
  },
];

export default function ScreenerCompareView({ token, onSelectCompany, onAuthRequired }) {
  const [activeSection, setActiveSection] = useState("screener");

  return (
    <div className="scmp-shell">
      <nav className="scmp-sidebar" aria-label="Скринер и сравнение">
        <div className="scmp-depth-strip" aria-hidden="true" />
        <div className="scmp-eyebrow">Рынок</div>

        {SCMP_ZONES.map((zone) => (
          <div key={zone.id} className="scmp-zone">
            <div className="scmp-zone-label">{zone.label}</div>
            {zone.items.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                className={`scmp-item${activeSection === id ? " scmp-item--active" : ""}`}
                onClick={() => setActiveSection(id)}
                aria-current={activeSection === id ? "page" : undefined}
              >
                <span className="scmp-item__icon"><Icon size={15} aria-hidden="true" /></span>
                {label}
              </button>
            ))}
          </div>
        ))}

        <div className="scmp-foot">Basis не брокер и не&nbsp;даёт рекомендаций «купить/продать».</div>
      </nav>

      <main className="scmp-main">
        <div className="scmp-panel">
          {activeSection === "compare"
            ? <CompareView onOpenCompany={onSelectCompany} />
            : <ScreenerView onSelectCompany={onSelectCompany} token={token} onAuthRequired={onAuthRequired} />}
        </div>
      </main>
    </div>
  );
}
