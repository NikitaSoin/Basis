// =============================================================
// BASIS DESIGN SYSTEM GALLERY — route /_design (Phase 2)
// Renders every base primitive in all variants/states, shown in
// BOTH themes side by side. Dark sub-tree uses the `.dark` class so
// tokens re-resolve locally without a global theme switch. A top
// toggle also flips the whole page (light/dark) for an overall view.
// Pure JS. Styled only via tw- utilities mapping onto tokens.
// =============================================================
import React, { useState } from "react";
import {
  Button,
  IconButton,
  Card,
  Badge,
  Chip,
  Tooltip,
  Input,
  Select,
  Modal,
  Tabs,
  Table,
  Delta,
  KpiTile,
} from "./primitives";
import { formatNumber, formatMoney, formatPercent, formatMultiple } from "./format";

/* ---- small layout helpers (gallery chrome only) ---- */

function Section({ title, children }) {
  return (
    <section className="tw-mb-12">
      <h2
        className="tw-text-[22px] tw-font-semibold tw-text-text-primary tw-mb-4 tw-pb-2 tw-border-b tw-border-border-subtle"
        style={{ letterSpacing: "0.01em" }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, children }) {
  return (
    <div className="tw-mb-5">
      {label && (
        <div
          className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-2"
          style={{ letterSpacing: "0.06em" }}
        >
          {label}
        </div>
      )}
      <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3">{children}</div>
    </div>
  );
}

const Bolt = (
  <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M9 1L2 9h5l-1 6 7-8H8l1-6z" fill="currentColor" />
  </svg>
);

/* ---- the actual gallery body (rendered once per theme) ---- */

function Gallery() {
  const [modalOpen, setModalOpen] = useState(false);
  const [tab, setTab] = useState("overview");
  const [chips, setChips] = useState({ growth: true, value: false, dividend: false });

  const plRows = [
    { metric: "Выручка", y2023: 1240, y2024: 1388, delta: 11.9 },
    { metric: "EBITDA", y2023: 402, y2024: 421, delta: 4.7 },
    { metric: "Чистая прибыль", y2023: 188, y2024: 166, delta: -11.7 },
    { metric: "Свободный денежный поток", y2023: 95, y2024: 112, delta: 17.9 },
  ];
  const fmtBn = (v) => formatNumber(v, { decimals: 0 });
  const plColumns = [
    { key: "metric", label: "Показатель, млрд ₽" },
    { key: "y2023", label: "2023", render: fmtBn },
    { key: "y2024", label: "2024", render: fmtBn },
    { key: "delta", label: "Δ г/г", render: (v) => <Delta value={v} /> },
  ];

  return (
    <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-py-8 tw-font-sans">
      <Section title="1 · Button">
        <Row label="Варианты (size md)">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
        </Row>
        <Row label="Размеры">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
        </Row>
        <Row label="Иконка / loading / disabled">
          <Button iconLeft={Bolt}>С иконкой слева</Button>
          <Button iconRight={Bolt} variant="secondary">Иконка справа</Button>
          <Button loading>Загрузка</Button>
          <Button disabled>Disabled</Button>
        </Row>
      </Section>

      <Section title="2 · IconButton">
        <Row label="Варианты и размеры (зона ≥ 32×32)">
          <IconButton aria-label="Действие" variant="primary">{Bolt}</IconButton>
          <IconButton aria-label="Действие" variant="secondary">{Bolt}</IconButton>
          <IconButton aria-label="Действие" variant="ghost">{Bolt}</IconButton>
          <IconButton aria-label="Действие" variant="danger">{Bolt}</IconButton>
          <IconButton aria-label="Действие" size="sm">{Bolt}</IconButton>
          <IconButton aria-label="Действие" size="lg">{Bolt}</IconButton>
          <IconButton aria-label="Действие" disabled>{Bolt}</IconButton>
        </Row>
      </Section>

      <Section title="3 · Card">
        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-4">
          <Card>Простая карточка. В светлой теме — мягкая тень, в тёмной — слой + 1px-граница.</Card>
          <Card header="Заголовок карточки">Тело карточки с контентом.</Card>
          <Card header="С футером" footer="Сноска внизу">Карточка с шапкой и подвалом.</Card>
        </div>
      </Section>

      <Section title="4 · Badge">
        <Row>
          <Badge tone="neutral">Neutral</Badge>
          <Badge tone="accent">Accent</Badge>
          <Badge tone="success">▲ Прибыль</Badge>
          <Badge tone="danger">▼ Убыток</Badge>
          <Badge tone="warning">Риск</Badge>
          <Badge tone="info">Инфо</Badge>
        </Row>
      </Section>

      <Section title="5 · Chip">
        <Row label="Выбираемые (selected / default)">
          <Chip selected={chips.growth} onClick={() => setChips((c) => ({ ...c, growth: !c.growth }))}>
            Рост
          </Chip>
          <Chip selected={chips.value} onClick={() => setChips((c) => ({ ...c, value: !c.value }))}>
            Стоимость
          </Chip>
          <Chip selected={chips.dividend} onClick={() => setChips((c) => ({ ...c, dividend: !c.dividend }))}>
            Дивиденды
          </Chip>
          <Chip disabled>Disabled</Chip>
        </Row>
        <Row label="Удаляемый">
          <Chip onRemove={() => {}}>Технологии ✕</Chip>
          <Chip selected onRemove={() => {}}>Нефтегаз ✕</Chip>
        </Row>
      </Section>

      <Section title="6 · Tooltip">
        <Row label="По наведению / фокусу (учитывает reduced-motion)">
          <Tooltip label="Подсказка сверху">
            <Button variant="secondary">Наведи / Tab</Button>
          </Tooltip>
          <Tooltip label="Справа" side="right">
            <Button variant="ghost">Справа</Button>
          </Tooltip>
        </Row>
      </Section>

      <Section title="7 · Input">
        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-4 tw-max-w-3xl">
          <Input label="Тикер" placeholder="SBER" />
          <Input label="Цена входа" defaultValue="abc" error="Введите число" />
          <Input label="Заблокировано" placeholder="недоступно" disabled />
        </div>
      </Section>

      <Section title="8 · Select">
        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-4 tw-max-w-3xl">
          <Select
            label="Сектор"
            options={[
              { value: "oil", label: "Нефтегаз" },
              { value: "metals", label: "Металлургия" },
              { value: "tech", label: "Технологии" },
            ]}
          />
          <Select label="Период" options={[{ value: "y", label: "Год" }, { value: "q", label: "Квартал" }]} />
          <Select label="Недоступно" options={[{ value: "x", label: "—" }]} disabled />
        </div>
      </Section>

      <Section title="9 · Modal">
        <Row label="Esc или крест закрывают; появление 320мс">
          <Button onClick={() => setModalOpen(true)}>Открыть модалку</Button>
        </Row>
        <Modal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          title="Подтверждение"
          footer={
            <>
              <Button variant="ghost" onClick={() => setModalOpen(false)}>Отмена</Button>
              <Button onClick={() => setModalOpen(false)}>Подтвердить</Button>
            </>
          }
        >
          Это базовая модалка дизайн-системы. Затемнение фона + панель на overlay-поверхности с тенью xl.
        </Modal>
      </Section>

      <Section title="10 · Tabs">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "overview", label: "Обзор", content: "Содержимое вкладки «Обзор»." },
            { value: "model", label: "Бизнес-модель", content: "Содержимое вкладки «Бизнес-модель»." },
            { value: "fin", label: "Финансы", content: "Содержимое вкладки «Финансы»." },
          ]}
        />
      </Section>

      <Section title="11 · Table (финансовый стиль)">
        <Table caption="P&L · числа вправо, табличные моноцифры, дельты с ▲/▼" columns={plColumns} rows={plRows} />
      </Section>

      <Section title="12 · KpiTile">
        <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 lg:tw-grid-cols-4 tw-gap-4">
          <KpiTile caption="Выручка" value={formatNumber(1388, { decimals: 0 })} unit="млрд ₽" delta={11.9} spark={[120, 124, 122, 130, 135, 139]} />
          <KpiTile caption="Чистая прибыль" value={formatNumber(166, { decimals: 0 })} unit="млрд ₽" delta={-11.7} spark={[188, 180, 175, 170, 168, 166]} />
          <KpiTile caption="Цена акции" value={formatMoney(4977.5, { decimals: 1 })} delta={1.4} spark={[4810, 4860, 4905, 4940, 4960, 4977]} />
          <KpiTile caption="P/E" value={formatMultiple(6.4)} delta={0} />
          <KpiTile caption="Див. доходность" value={formatPercent(9.2)} delta={2.1} spark={[7, 7.5, 8, 8.4, 9, 9.2]} />
        </div>
      </Section>
    </div>
  );
}

/* ---- page shell: top toggle + both themes side-by-side ---- */

export default function DesignSystem() {
  const [page, setPage] = useState("light"); // overall page toggle

  return (
    <div className={page === "dark" ? "dark" : ""}>
      <div className="tw-min-h-screen tw-bg-bg-base tw-text-text-primary">
        <header className="tw-sticky tw-top-0 tw-z-40 tw-bg-bg-elevated tw-border-b tw-border-border-subtle tw-shadow-sm">
          <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-py-4 tw-flex tw-items-center tw-justify-between">
            <div>
              <h1 className="tw-text-[28px] tw-font-semibold tw-font-display tw-text-text-primary tw-m-0">
                Basis · Дизайн-система
              </h1>
              <p className="tw-text-[13px] tw-text-text-tertiary tw-m-0">
                Фаза 2 · библиотека базовых примитивов · маршрут /_design
              </p>
            </div>
            <Button
              variant="secondary"
              onClick={() => setPage((p) => (p === "dark" ? "light" : "dark"))}
              className="tw-bg-bg-elevated tw-text-text-primary tw-border-border-strong hover:tw-bg-bg-hover"
            >
              {page === "dark" ? "☀ Светлая тема" : "☾ Тёмная тема"}
            </Button>
          </div>
        </header>

        <main className="tw-px-2 tw-py-2">
          {/* LIGHT section */}
          <div className="tw-bg-bg-base">
            <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-pt-6">
              <Badge tone="accent">Светлая тема</Badge>
            </div>
            <Gallery />
          </div>

          {/* DARK section — `.dark` re-resolves tokens locally */}
          <div className="dark tw-bg-bg-base tw-border-t tw-border-border-strong">
            <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-pt-6">
              <Badge tone="accent">Тёмная тема</Badge>
            </div>
            <Gallery />
          </div>
        </main>
      </div>
    </div>
  );
}
