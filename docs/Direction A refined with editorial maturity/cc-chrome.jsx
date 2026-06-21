// Basis — Company Card · chrome: TopNav, CompanyHeader, TabBar, DecisionSidebar.
// Exported to window. Uses design-system tokens + components only.

const { Button, Badge, Delta, RiskBadge, ConfidenceBadge, SourceTag } = window.BasisDesignSystem_c4316a;

// ---- Top navigation bar ----
function TopNav({ active = "Рынок", onNav }) {
  const NAV = window.CC_NAV;
  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 40, background: "rgba(248,247,244,0.85)",
      backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
      borderBottom: "1px solid var(--border-subtle)",
    }}>
      <div style={{
        maxWidth: 1320, margin: "0 auto", padding: "0 28px", height: 60,
        display: "flex", alignItems: "center", gap: 28,
      }}>
        <a href="#" aria-label="Basis" style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
          <img src="assets/wordmark.svg" width="106" height="26" alt="Basis" style={{ display: "block" }} />
        </a>
        <nav aria-label="Основная навигация" style={{ display: "flex", alignItems: "center", gap: 2, flex: 1, overflowX: "auto" }}>
          {NAV.map((item) => {
            const isActive = item === active;
            return (
              <button key={item} onClick={() => onNav && onNav(item)} aria-current={isActive || undefined}
                style={{
                  border: 0, background: "transparent", cursor: "pointer", whiteSpace: "nowrap",
                  font: "inherit", fontSize: 14, fontWeight: isActive ? 600 : 500,
                  color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                  padding: "8px 12px", borderRadius: "var(--radius-sm)", position: "relative",
                }}>
                {item}
                {isActive && <span aria-hidden="true" style={{ position: "absolute", left: 12, right: 12, bottom: -1, height: 2, background: "var(--accent)", borderRadius: 2 }} />}
              </button>
            );
          })}
        </nav>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 7, height: 36, padding: "0 12px",
            border: "1px solid var(--border-strong)", borderRadius: "var(--radius-sm)",
            background: "var(--bg-elevated)", color: "var(--text-tertiary)", fontSize: 13, minWidth: 180,
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
            <span>Поиск компании, тикера…</span>
          </div>
        </div>
      </div>
    </header>
  );
}

// ---- Company header ----
function CompanyHeader() {
  const c = window.CC_COMPANY;
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 18, flexWrap: "wrap",
      padding: "24px 0 18px",
    }}>
      <div style={{
        width: 56, height: 56, borderRadius: "var(--radius-md)", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 24,
        color: "var(--accent)", background: "var(--accent-soft)", border: "1px solid var(--accent-border)",
      }}>{c.monogram}</div>

      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 700, margin: 0, lineHeight: 1.05, letterSpacing: "var(--ls-display)", color: "var(--text-primary)" }}>{c.name}</h1>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 500,
            color: "var(--success)", background: "var(--success-soft)", padding: "3px 9px", borderRadius: "var(--radius-pill)",
          }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--success)" }} aria-hidden="true" />
            Торги открыты
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text-tertiary)", flexWrap: "wrap" }}>
          <span style={{ color: "var(--text-secondary)", fontWeight: 600 }}>{c.ticker}</span>
          <span aria-hidden="true">·</span><span>{c.exchange}</span>
          <span aria-hidden="true">·</span><span style={{ fontFamily: "var(--font-sans)" }}>{c.sector}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 12, flexWrap: "wrap" }}>
          <div>
            <window.CCEyebrow>Капитализация</window.CCEyebrow>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 500, color: "var(--text-primary)", marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{c.marketCap}</div>
          </div>
          <div style={{ width: 1, height: 30, background: "var(--border-subtle)" }} aria-hidden="true" />
          <div>
            <window.CCEyebrow>Обновлено</window.CCEyebrow>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>{c.updated}</div>
          </div>
        </div>
      </div>

      <div style={{ marginLeft: "auto", textAlign: "right", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 14 }}>
        <div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6, justifyContent: "flex-end" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 32, fontWeight: 500, color: "var(--text-primary)", fontVariantNumeric: "tabular-nums", letterSpacing: "-0.01em" }}>{c.price}</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 18, color: "var(--text-tertiary)" }}>{c.currency}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 4, fontSize: 14 }}>
            <Delta value={c.change} decimals={2} />
            <span style={{ color: "var(--text-tertiary)", marginLeft: 8, fontSize: 13 }}>за день</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" size="md" iconLeft={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 4v16M4 12h16" /></svg>
          }>В наблюдение</Button>
          <Button variant="primary" size="md" iconRight={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h13M13 6l6 6-6 6" /></svg>
          }>Проверить идею</Button>
        </div>
      </div>
    </div>
  );
}

// ---- Tab bar ----
function TabBar({ active, onChange }) {
  const TABS = window.CC_TABS;
  return (
    <div role="tablist" aria-label="Разделы компании" style={{
      display: "flex", gap: 2, borderBottom: "1px solid var(--border-subtle)",
      overflowX: "auto", position: "sticky", top: 60, zIndex: 30,
      background: "rgba(248,247,244,0.9)", backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
    }}>
      {TABS.map((t) => {
        const isActive = t.id === active;
        return (
          <button key={t.id} role="tab" aria-selected={isActive} onClick={() => onChange(t.id)}
            style={{
              border: 0, background: "transparent", cursor: "pointer", whiteSpace: "nowrap",
              font: "inherit", fontSize: 14, fontWeight: 500, padding: "12px 14px",
              borderBottom: "2px solid transparent", marginBottom: -1,
              color: isActive ? "var(--accent)" : "var(--text-secondary)",
              borderBottomColor: isActive ? "var(--accent)" : "transparent",
            }}>
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

// ---- Decision-support sidebar (sticky) ----
function SidebarBlock({ label, children, style }) {
  return (
    <div style={{ padding: "14px 0", borderTop: "1px solid var(--border-subtle)", ...style }}>
      <window.CCEyebrow style={{ marginBottom: 9 }}>{label}</window.CCEyebrow>
      {children}
    </div>
  );
}

function DecisionSidebar() {
  const EXEC = window.CC_EXEC, RISKS = window.CC_RISKS, MONITOR = window.CC_MONITOR, SOURCES = window.CC_SOURCES;
  return (
    <aside style={{ position: "sticky", top: 116, alignSelf: "start" }}>
      <div style={{
        background: "var(--bg-elevated)", border: "1px solid var(--border-strong)",
        borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-md)", padding: "18px 18px 16px",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: 16, fontWeight: 600, margin: 0, color: "var(--text-primary)" }}>Поддержка решения</h2>
        </div>

        <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--warning-soft)", borderRadius: "var(--radius-sm)", borderLeft: "2px solid var(--warning)" }}>
          <window.CCEyebrow style={{ color: "var(--warning)" }}>Текущий тон</window.CCEyebrow>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginTop: 4 }}>{EXEC.toneLabel}</div>
        </div>

        <SidebarBlock label="Ключевые риски" style={{ marginTop: 14 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {RISKS.slice(0, 4).map((r, i) => <div key={i}><RiskBadge type={r.type} severity={r.severity} /></div>)}
          </div>
        </SidebarBlock>

        <SidebarBlock label="Что отслеживать">
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {MONITOR.map((m, i) => (
              <li key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13, lineHeight: 1.45, color: "var(--text-secondary)" }}>
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, marginTop: 2, color: "var(--text-tertiary)" }}><rect x="2.5" y="2.5" width="11" height="11" rx="3" stroke="currentColor" strokeWidth="1.3" /></svg>
                <span>{m}</span>
              </li>
            ))}
          </ul>
        </SidebarBlock>

        <SidebarBlock label="Источники">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{SOURCES.length} источников · актуальны</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--success)" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--success)" }} aria-hidden="true" />проверено
            </span>
          </div>
        </SidebarBlock>

        <SidebarBlock label="Уверенность вывода">
          <ConfidenceBadge level="medium" />
        </SidebarBlock>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16 }}>
          <Button variant="primary" size="md" className="cc-full">Проверить идею</Button>
          <Button variant="secondary" size="md" className="cc-full">Сценарный анализ</Button>
        </div>
        <p style={{ fontSize: 11, lineHeight: 1.5, color: "var(--text-tertiary)", margin: "12px 0 0", textAlign: "center" }}>
          Не является инвестиционной рекомендацией. Второе мнение перед решением.
        </p>
      </div>
    </aside>
  );
}

Object.assign(window, { CCTopNav: TopNav, CCCompanyHeader: CompanyHeader, CCTabBar: TabBar, CCDecisionSidebar: DecisionSidebar });
