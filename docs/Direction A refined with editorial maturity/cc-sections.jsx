// Basis — Company Card · analytical section tiles. Exported to window.
// Each section is its own tile (conclusion first, evidence below).

const S = window.BasisDesignSystem_c4316a;

function Stack({ children, gap = 16, style }) {
  return <div style={{ display: "flex", flexDirection: "column", gap, ...style }}>{children}</div>;
}

// ===== Executive summary block =====
function OverviewSummary() {
  const E = window.CC_EXEC, C = window.CC_COMPANY;
  const { ExecutiveSummaryCard } = S;
  return (
    <ExecutiveSummaryCard
      tone={E.tone}
      toneLabel={E.toneLabel}
      insights={E.insights}
      mainRisk={E.mainRisk}
      mainRiskType={E.mainRiskType}
      mainRiskSeverity={E.mainRiskSeverity}
      whatWouldChange={E.whatWouldChange}
      updated={C.updated}
    />
  );
}

// ===== Metric grid =====
function MetricGrid() {
  const { MetricCard, FactEstimateJudgmentTag } = S;
  const METRICS = window.CC_METRICS;
  return (
    <div className="cc-metric-grid">
      {METRICS.map((m, i) => (
        <div key={i} style={{ position: "relative" }}>
          <MetricCard caption={m.caption} value={m.value} unit={m.unit} delta={m.delta} />
          <span style={{ position: "absolute", top: 12, right: 12 }}><FactEstimateJudgmentTag level={m.level} /></span>
        </div>
      ))}
    </div>
  );
}

// ===== What's priced in (paired tile used on overview) =====
function PricedInTile() {
  const E = window.CC_EXEC;
  const { CCTile, CCPara } = window;
  return (
    <CCTile title="Что уже может быть в цене" tag="judgment">
      <CCPara style={{ marginBottom: 0 }}>{E.priced}</CCPara>
    </CCTile>
  );
}

// ===== Business model =====
function BusinessTile() {
  const { CCTile, CCPara, CC_SEG_COLS, CC_SEG_ROWS } = window;
  const { DataTable, KeyTakeaway } = S;
  return (
    <CCTile title="Бизнес-модель" tag="fact" id="sec-business">
      <CCPara>
        Роснефть — вертикально интегрированная нефтегазовая компания: от добычи до переработки
        и сбыта. Конкурентное преимущество — одна из самых низких в мире себестоимостей добычи
        барреля и масштабная ресурсная база. Экспорт переориентирован на азиатские рынки.
      </CCPara>
      <div style={{ margin: "14px 0" }}>
        <DataTable columns={CC_SEG_COLS} rows={CC_SEG_ROWS} />
      </div>
      <KeyTakeaway>
        Деньги делает upstream с дешёвым баррелем; стоимость на горизонте 3–5 лет определяет «Восток Ойл».
      </KeyTakeaway>
    </CCTile>
  );
}

// ===== Financials & valuation =====
function FinancialsTile() {
  const { CCTile, CCPara, CC_FIN_COLS, CC_FIN_ROWS } = window;
  const { DataTable, MetricExplainer } = S;
  return (
    <CCTile title="Финансы и оценка" tag="estimate" id="sec-financials">
      <CCPara>
        Денежный поток остаётся высоким, но FCF снижается на фоне роста капзатрат и процентных
        расходов. По мультипликаторам компания торгуется заметно дешевле мировых мейджоров —
        дисконт отражает страновую и санкционную премию за риск, а не качество активов.
      </CCPara>
      <div style={{ margin: "14px 0" }}>
        <DataTable caption="МСФО, трлн ₽ (LTM — за последние 12 мес.)" columns={CC_FIN_COLS} rows={CC_FIN_ROWS} />
      </div>
      <MetricExplainer
        name="EV / EBITDA"
        value="3,4" unit="×" benchmark="мейджоры ~5,5×"
        what="Стоимость бизнеса относительно операционной прибыли до амортизации."
        yourValue="3,4× против ~5,5× у мировых мейджоров — дисконт около 38%."
        action="Дисконт — это не апсайд сам по себе: оцените, оправдан ли он санкционным и валютным риском."
        formula="EV / EBITDA = (Капитализация + Чистый долг) / EBITDA"
        takeaway="Дёшево по мультипликатору, но дешевизна — функция риска, а не недооценки качества."
      />
    </CCTile>
  );
}

// ===== Governance =====
function GovernanceTile() {
  const { CCTile, CCPara } = window;
  const { Callout, Badge } = S;
  return (
    <CCTile title="Корпоративное управление" tag="judgment" id="sec-governance"
      aside={<Badge tone="neutral">Контроль государства</Badge>}>
      <CCPara>
        Основной акционер — государство (через профильный холдинг), что определяет стратегические
        приоритеты и крупные инвестпроекты. Дивидендная политика — не менее 50% чистой прибыли по
        МСФО — выполняется, но размер выплат чувствителен к курсу рубля и цене Urals.
      </CCPara>
      <Callout tone="info">
        Честно: при госконтроле интересы мажоритария и миноритариев могут расходиться по срокам —
        капзатраты в стратегические проекты конкурируют с дивидендной базой.
      </Callout>
    </CCTile>
  );
}

// ===== Markets =====
function MarketsTile() {
  const { CCTile, CCPara } = window;
  const { FactorImpactCard } = S;
  return (
    <CCTile title="Рынки" tag="estimate" id="sec-markets">
      <CCPara>
        Выручка почти полностью определяется ценой нефти Urals (с дисконтом к Brent) и курсом
        рубля. Это два главных рыночных драйвера — отслеживать их важнее, чем дневные котировки акции.
      </CCPara>
      <Stack gap={12} style={{ marginTop: 4 }}>
        <FactorImpactCard
          factor="Цена нефти Urals" effect="positive" horizon="short" confidence="high"
          channel={<>Рост Urals напрямую увеличивает <b>рублёвую выручку и EBITDA</b> при стабильном дисконте к Brent.</>}
          source="Bloomberg" sourceDate="сегодня" sourceHref="#" />
        <FactorImpactCard
          factor="Курс USD/RUB" effect="mixed" horizon="short" confidence="medium"
          channel={<>Слабый рубль повышает <b>рублёвую выручку</b>, но усиливает инфляцию и стоимость импортного оборудования.</>}
          source="ЦБ РФ" sourceDate="сегодня" sourceHref="#" />
      </Stack>
    </CCTile>
  );
}

// ===== Macro =====
function MacroTile() {
  const { MacroTransmissionCard, Callout } = S;
  return (
    <Stack gap={16} style={{ gridColumn: "1 / -1" }}>
      <div id="sec-macro" />
      <MacroTransmissionCard
        title="Цена Urals → денежный поток"
        steps={[
          "Цена нефти Urals и дисконт к Brent",
          "Экспортная выручка в долларах, затем конвертация по курсу рубля",
          "Рублёвая выручка и EBITDA, налоговая нагрузка (НДПI + демпфер)",
          "FCF и дивидендная база после капзатрат и процентов",
          "Устойчивость дивиденда и оценка зависят от цены и курса одновременно",
        ]} />
      <Callout tone="info">
        Эффект для экспортёра двусторонний: высокая цена нефти и слабый рубль работают в одну
        сторону, но укрепление рубля способно нивелировать ценовой выигрыш.
      </Callout>
    </Stack>
  );
}

// ===== Geopolitics =====
function GeopoliticsTile() {
  const { MacroTransmissionCard, Callout } = S;
  return (
    <Stack gap={16} style={{ gridColumn: "1 / -1" }}>
      <div id="sec-geopolitics" />
      <MacroTransmissionCard
        kind="geo"
        title="Санкционный режим → логистика экспорта"
        steps={[
          "Расширение вторичных санкций на покупателей и перевозчиков",
          "Удорожание и усложнение логистики, рост дисконта Urals к Brent",
          "Снижение чистой экспортной цены, давление на маржу",
          "Сжатие FCF и дивидендной базы",
          "Санкционный риск — главный источник дисконта оценки, а не качество активов",
        ]} />
      <Callout tone="caution">
        Геополитика — структурный, а не разовый фактор: сценарии должны учитывать как ужесточение,
        так и частичное смягчение ограничений.
      </Callout>
    </Stack>
  );
}

// ===== Risks =====
function RisksTile() {
  const { CCTile } = window;
  const { RiskBadge } = S;
  const RISKS = window.CC_RISKS;
  return (
    <CCTile title="Риски" tag="judgment" id="sec-risks">
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 12 }}>
        {RISKS.map((r, i) => (
          <li key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <div style={{ flexShrink: 0, paddingTop: 1, minWidth: 132 }}><RiskBadge type={r.type} severity={r.severity} /></div>
            <span style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text-secondary)" }}>{r.text}</span>
          </li>
        ))}
      </ul>
    </CCTile>
  );
}

// ===== Scenarios =====
function ScenariosTile() {
  const { CCTile } = window;
  const { ScenarioTabs } = S;
  return (
    <CCTile title="Сценарный анализ" tag="scenario" id="sec-scenarios">
      <ScenarioTabs scenarios={window.CC_SCENARIOS} />
    </CCTile>
  );
}

// ===== Evidence & sources =====
function EvidenceTile() {
  const { CCTile, CCPara } = window;
  const { SourceTag } = S;
  const SOURCES = window.CC_SOURCES;
  return (
    <CCTile title="Доказательства и источники" tag="fact" id="sec-evidence">
      <CCPara style={{ marginBottom: 12 }}>
        Каждый вывод опирается на источник с датой. Факты подкреплены отчётностью и котировками,
        оценки — модельными расчётами, суждения помечены отдельно.
      </CCPara>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {SOURCES.map((s, i) => <SourceTag key={i} name={s.name} date={s.date} href={s.href} />)}
      </div>
    </CCTile>
  );
}

Object.assign(window, {
  CCStack: Stack,
  CCOverviewSummary: OverviewSummary, CCMetricGrid: MetricGrid, CCPricedInTile: PricedInTile,
  CCBusinessTile: BusinessTile, CCFinancialsTile: FinancialsTile, CCGovernanceTile: GovernanceTile,
  CCMarketsTile: MarketsTile, CCMacroTile: MacroTile, CCGeopoliticsTile: GeopoliticsTile,
  CCRisksTile: RisksTile, CCScenariosTile: ScenariosTile, CCEvidenceTile: EvidenceTile,
});
