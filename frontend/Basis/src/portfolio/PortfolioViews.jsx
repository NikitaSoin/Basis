import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  AlertTriangle,
  ArrowRightLeft,
  Briefcase,
  Pencil,
  PieChart,
  Plus,
  Scale,
  ShieldAlert,
  Target,
  Trash2,
  TrendingDown,
  TrendingUp,
  Upload,
  User,
  X,
  Zap,
} from "lucide-react";
import { Button, Card, Badge, Chip, IconButton, Table, Delta, KpiTile, usePrefersReducedMotion } from "../design/primitives";
import { formatMoney, formatPercent as fmtPercent, formatNumber, formatNumber as fmtNumber } from "../design/format";
import { WeightBar, MetricBar, CorrelationHeatmap, ImpactBar, useCountUp, catFor } from "../design/PortfolioViz";
import { KeyTakeaway, Disclosure } from "../design/textblocks";
import { AppearGroup } from "../design/motion";
import { CompanyLogo, InstrumentLogo } from "../design/CompanyLogo";
import { useMobileSidebarDrawer, MobileSectionBar, MobileDrawerBackdrop } from "../design/MobileSidebarDrawer";
import "../styles/portfolio-v2.css";

const _dmy = (s) => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—";
// Дней с даты цены (ISO) до сегодня — для честного «на 20.07» под ценой
// облигаций/фондов в «Составе» (они обновляются T+1, не раз в 5с, как акции).
const _daysSince = (iso) => iso ? Math.round((Date.now() - new Date(iso).getTime()) / 86400000) : null;

// =========================
// PORTFOLIO MOCK DATA
// =========================

// MOCK_PORTFOLIO (демо СБЕР/Лукойл/Яндекс) удалён 2026-07-19: он подставлялся
// в displayPositions на время загрузки реальных позиций и создавал «прыгающие
// числа» (сначала стоимость мока, потом настоящая). Мокам в проде не место.
const MOCK_CORRELATION = [
  [1.0, 0.45, 0.18],
  [0.45, 1.0, 0.22],
  [0.18, 0.22, 1.0],
];

// =========================
// PORTFOLIO
// =========================

const PortfolioImportModal = ({ onClose, onSuccess, token, existingNames = [] }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};
  const [name, setName] = useState("Мой портфель");
  const [nameError, setNameError] = useState("");
  const [rows, setRows] = useState([
    { ticker: "", quantity: "", avgPrice: "" },
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const addRow = () =>
    setRows((r) => [...r, { ticker: "", quantity: "", avgPrice: "" }]);

  const removeRow = (i) =>
    setRows((r) => r.filter((_, idx) => idx !== i));

  const updateRow = (i, field, val) =>
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, [field]: val } : row)));

  const handleImport = async () => {
    setError(null);
    setNameError("");
    const trimmedName = name.trim() || "Мой портфель";
    const duplicate = existingNames.some(n => n.trim().toLowerCase() === trimmedName.toLowerCase());
    if (duplicate) {
      setNameError("Портфель с таким названием уже существует");
      return;
    }

    const validRows = rows.filter(
      (r) => r.ticker.trim() && r.quantity && r.avgPrice
    );

    setLoading(true);
    try {
      // 1. Загружаем список компаний для маппинга ticker → company_id (только если есть позиции)
      const tickerMap = {};
      if (validRows.length > 0) {
        const companiesResp = await fetch(`${apiUrl}/api/companies`);
        const companies = companiesResp.ok ? await companiesResp.json() : [];
        if (Array.isArray(companies)) {
          companies.forEach((c) => { tickerMap[c.ticker.toUpperCase()] = c; });
        }
      }

      // 2. Создаём портфель
      const portfolioResp = await fetch(`${apiUrl}/api/portfolios`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders },
        body: JSON.stringify({ name }),
      });
      const portfolioData = await portfolioResp.json();
      if (!portfolioResp.ok) throw new Error(portfolioData.detail || "Ошибка создания портфеля");
      const portfolio = portfolioData;

      // 3. Добавляем позиции (только если были введены)
      if (validRows.length === 0) {
        onSuccess(portfolio);
        return;
      }

      const errors = [];
      const unknownTickers = validRows
        .filter((r) => !tickerMap[r.ticker.trim().toUpperCase()])
        .map((r) => r.ticker.trim());

      if (unknownTickers.length) {
        errors.push(`Тикеры не найдены в базе: ${unknownTickers.join(", ")}. Доступные: ${Object.keys(tickerMap).join(", ")}`);
      }

      for (const row of validRows) {
        const company = tickerMap[row.ticker.trim().toUpperCase()];
        if (!company) continue;
        const posResp = await fetch(`${apiUrl}/api/portfolios/${portfolio.id}/positions`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({
            company_id: company.id,
            quantity: parseFloat(row.quantity),
            avg_buy_price: parseFloat(row.avgPrice),
          }),
        });
        if (!posResp.ok) {
          const posErr = await posResp.json().catch(() => ({}));
          errors.push(`${row.ticker}: ${posErr.detail || "ошибка добавления позиции"}`);
        }
      }

      if (errors.length) setError(errors.join("\n"));
      else onSuccess(portfolio);
    } catch (e) {
      setError(e.message || "Ошибка импорта");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-box" style={{ maxWidth: 520, width: "100%", maxHeight: "90vh", display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 24px 16px", borderBottom: "1px solid var(--border)" }}>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "var(--text-1)" }}>Импорт портфеля</h3>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: "4px 8px", minWidth: 0 }}>
            <X size={16} />
          </button>
        </div>

        <div style={{ overflowY: "auto", padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>Название портфеля</label>
            <input
              value={name}
              onChange={(e) => { setName(e.target.value); setNameError(""); }}
              style={{
                width: "100%", background: "var(--bg-surface)",
                border: `1px solid ${nameError ? "var(--negative)" : "var(--border)"}`,
                borderRadius: 10, padding: "9px 14px", color: "var(--text-1)", fontSize: 14,
                outline: "none", boxSizing: "border-box",
              }}
              placeholder="Мой портфель"
            />
            {nameError && (
              <div style={{ fontSize: 12, color: "var(--negative)", marginTop: 5 }}>{nameError}</div>
            )}
          </div>

          <div>
            <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 8 }}>Позиции</label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 90px 110px 28px", gap: 6, marginBottom: 4, padding: "0 2px" }}>
              {["Тикер", "Кол-во", "Цена ₽", ""].map((h) => (
                <span key={h} style={{ fontSize: 11, color: "var(--text-3)" }}>{h}</span>
              ))}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {rows.map((row, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 90px 110px 28px", gap: 6, alignItems: "start" }}>
                  <TickerInput
                    value={row.ticker}
                    onChange={(v) => updateRow(i, "ticker", v)}
                    placeholder="SBER"
                  />
                  <input
                    type="number"
                    value={row.quantity}
                    onChange={(e) => updateRow(i, "quantity", e.target.value)}
                    placeholder="100"
                    style={{
                      background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8,
                      padding: "8px 10px", color: "var(--text-1)", fontSize: 13, outline: "none",
                    }}
                  />
                  <input
                    type="number"
                    value={row.avgPrice}
                    onChange={(e) => updateRow(i, "avgPrice", e.target.value)}
                    placeholder="280.50"
                    style={{
                      background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8,
                      padding: "8px 10px", color: "var(--text-1)", fontSize: 13, outline: "none",
                    }}
                  />
                  <button
                    onClick={() => removeRow(i)}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3)", fontSize: 16, padding: 0, display: "flex", alignItems: "center", justifyContent: "center" }}
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
            <button
              onClick={addRow}
              className="btn btn-ghost"
              style={{ marginTop: 8, padding: "6px 10px", fontSize: 13, color: "var(--accent-text)" }}
            >
              <Plus size={13} /> Добавить строку
            </button>
          </div>

          {error && (
            <p style={{ fontSize: 13, color: "var(--negative)", background: "var(--neg-fade)", border: "1px solid var(--negative)", borderRadius: 8, padding: "10px 14px", margin: 0 }}>
              {error}
            </p>
          )}
        </div>

        <div style={{ padding: "16px 24px", borderTop: "1px solid var(--border)" }}>
          <button
            onClick={handleImport}
            disabled={loading}
            className="btn btn-primary"
            style={{ width: "100%", justifyContent: "center", padding: "10px 20px", opacity: loading ? 0.6 : 1 }}
          >
            {loading ? "Загружаем..." : <><Upload size={15} /> Загрузить портфель</>}
          </button>
        </div>
      </div>
    </div>
  );
};

// =========================
// TICKER AUTOCOMPLETE INPUT
// =========================

const TickerInput = ({ value, onChange, placeholder = "SBER" }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const ref = React.useRef(null);
  const TICKER_COLORS_AC = ["#4f46e5","#3fb950","#f59e0b","#f85149","#a78bfa","#34d399","#fb923c","#38bdf8"];
  const tcolor = (t) => TICKER_COLORS_AC[(t.charCodeAt(0) + (t.charCodeAt(1) || 0)) % TICKER_COLORS_AC.length];

  useEffect(() => {
    if (!value) { setSuggestions([]); setOpen(false); return; }
    const timer = setTimeout(() => {
      fetch(`${apiUrl}/api/companies?search=${encodeURIComponent(value)}`)
        .then(r => r.ok ? r.json() : [])
        .then(data => {
          const exact = data.find(c => c.ticker.toUpperCase() === value.toUpperCase());
          if (exact) { setSuggestions([]); setOpen(false); return; }
          setSuggestions(data.slice(0, 6));
          setOpen(data.length > 0);
        })
        .catch(() => setSuggestions([]));
    }, 220);
    return () => clearTimeout(timer);
  }, [value]);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value.toUpperCase())}
        placeholder={placeholder}
        autoComplete="off"
        style={{
          width: "100%", background: "var(--bg-surface)", border: "1px solid var(--border)",
          borderRadius: 10, padding: "9px 14px", color: "var(--text-1)", fontSize: 16,
          outline: "none", boxSizing: "border-box", textTransform: "uppercase",
        }}
      />
      {open && suggestions.length > 0 && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
          background: "var(--bg-card)", border: "1px solid var(--border-mid)",
          borderRadius: 10, boxShadow: "0 8px 24px var(--shadow-xl, rgba(0,0,0,0.3))",
          zIndex: 9999, overflow: "hidden",
        }}>
          {suggestions.map(c => (
            <div
              key={c.ticker}
              onMouseDown={() => { onChange(c.ticker); setOpen(false); setSuggestions([]); }}
              style={{
                display: "flex", alignItems: "center", gap: 10, padding: "9px 12px",
                cursor: "pointer", transition: "background 0.1s",
              }}
              onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}
            >
              <CompanyLogo ticker={c.ticker} name={c.name} size={28} />
              <div>
                <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-1)" }}>{c.name}</span>
                <span style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-3)", marginLeft: 6 }}>{c.ticker}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// =========================
// EDIT POSITION MODAL — прямое редактирование (кол-во / средняя / удалить)
// =========================

const EditPositionModal = ({ portfolioId, position, token, onClose, onSuccess }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
  const [mode, setMode] = useState("trade"); // "trade" | "fix" — как в прототипе
  const [quantity, setQuantity] = useState(String(position.shares ?? ""));
  const [avgPrice, setAvgPrice] = useState(String(position.avgPrice ?? ""));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Совершить сделку (buy/sell) — заводит запись в истории, не трогает
  // напрямую qty/среднюю (это делает бэкенд по средневзвешенной цене).
  const [tradeSide, setTradeSide] = useState("buy");
  const [tradeQty, setTradeQty] = useState("");
  const [tradePrice, setTradePrice] = useState("");
  const [tradeFee, setTradeFee] = useState("0");
  const [tradeDate, setTradeDate] = useState(() => new Date().toISOString().slice(0, 10));

  // Разбивка П/У по истории сделок (Реализовано/Не реализовано/Дивиденды/Комиссии)
  const [pnl, setPnl] = useState(null);
  useEffect(() => {
    fetch(`${apiUrl}/api/portfolios/${portfolioId}/positions/${position.id}/pnl?current_price=${position.currentPrice || ""}`, { headers: authHeaders })
      .then((r) => (r.ok ? r.json() : null))
      .then(setPnl)
      .catch(() => setPnl(null));
  }, [position.id]); // apiUrl/authHeaders/position.currentPrice пересчитываются на каждый рендер — не нужны в deps

  const check = async (resp, action) => {
    if (resp.ok) return resp;
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Не удалось ${action} (HTTP ${resp.status})`);
  };

  const handleTrade = async () => {
    setError(null);
    const qty = parseFloat(tradeQty);
    const price = parseFloat(tradePrice);
    const fee = parseFloat(tradeFee) || 0;
    if (!(qty > 0) || !(price > 0)) { setError("Количество и цена сделки должны быть больше нуля"); return; }
    setLoading(true);
    try {
      await check(
        await fetch(`${apiUrl}/api/portfolios/${portfolioId}/positions/${position.id}/trades`, {
          method: "POST", headers: authHeaders,
          body: JSON.stringify({ side: tradeSide, quantity: qty, price, fee, trade_date: tradeDate }),
        }),
        tradeSide === "buy" ? "купить" : "продать"
      );
      onSuccess();
    } catch (e) {
      setError(e.message || "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setError(null);
    const qty = parseFloat(quantity);
    const avg = parseFloat(avgPrice);
    if (!(qty > 0) || !(avg > 0)) { setError("Количество и средняя цена должны быть больше нуля"); return; }
    setLoading(true);
    try {
      await check(
        await fetch(`${apiUrl}/api/portfolios/${portfolioId}/positions/${position.id}`, {
          method: "PATCH", headers: authHeaders,
          body: JSON.stringify({ quantity: qty, avg_buy_price: avg }),
        }),
        "сохранить изменения"
      );
      onSuccess();
    } catch (e) {
      setError(e.message || "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    setError(null);
    setLoading(true);
    try {
      await check(
        await fetch(`${apiUrl}/api/portfolios/${portfolioId}/positions/${position.id}`, {
          method: "DELETE", headers: authHeaders,
        }),
        "удалить позицию"
      );
      onSuccess();
    } catch (e) {
      setError(e.message || "Ошибка");
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-box" style={{ maxWidth: 420, width: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 24px 16px", borderBottom: "1px solid var(--border)" }}>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "var(--text-1)" }}>
            {position.ticker} — изменить позицию
          </h3>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: "4px 8px", minWidth: 0 }}><X size={16} /></button>
        </div>

        <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="pf-seg tw-self-start">
            <button type="button" onClick={() => setMode("trade")}
              className={`pf-seg-opt${mode === "trade" ? " pf-seg-opt--on" : ""}`}>
              Совершить сделку
            </button>
            <button type="button" onClick={() => setMode("fix")}
              className={`pf-seg-opt${mode === "fix" ? " pf-seg-opt--on" : ""}`}>
              Исправить позицию
            </button>
          </div>

          {mode === "trade" ? (
            <>
              <div className="pf-seg tw-self-start">
                <button type="button" onClick={() => setTradeSide("buy")}
                  className={`pf-seg-opt${tradeSide === "buy" ? " pf-seg-opt--buy-on" : ""}`}>
                  Купить
                </button>
                <button type="button" onClick={() => setTradeSide("sell")}
                  className={`pf-seg-opt${tradeSide === "sell" ? " pf-seg-opt--sell-on" : ""}`}>
                  Продать
                </button>
              </div>
              {[
                { label: "Количество", value: tradeQty, onChange: (e) => setTradeQty(e.target.value), type: "number", placeholder: "напр. 100" },
                { label: "Цена сделки, ₽", value: tradePrice, onChange: (e) => setTradePrice(e.target.value), type: "number", placeholder: `напр. ${position.currentPrice || ""}` },
                { label: "Дата сделки", value: tradeDate, onChange: (e) => setTradeDate(e.target.value), type: "date" },
                { label: "Комиссия, ₽", value: tradeFee, onChange: (e) => setTradeFee(e.target.value), type: "number" },
              ].map(({ label, value, onChange, type, placeholder }) => (
                <div key={label}>
                  <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>{label}</label>
                  <input
                    type={type} value={value} onChange={onChange} placeholder={placeholder}
                    style={{
                      width: "100%", background: "var(--bg-surface)", border: "1px solid var(--border)",
                      borderRadius: 10, padding: "9px 14px", color: "var(--text-1)", fontSize: 16,
                      outline: "none", boxSizing: "border-box",
                    }}
                  />
                </div>
              ))}
              <p style={{ fontSize: 11.5, color: "var(--text-3)", margin: 0 }}>
                Это новая сделка, а не редактирование позиции целиком — количество и средняя цена пересчитаются
                автоматически (средневзвешенная цена на покупке; продажа не меняет среднюю, но фиксирует реализованный результат).
              </p>
              {error && (
                <p style={{ fontSize: 13, color: "var(--negative)", background: "var(--neg-fade)", border: "1px solid var(--negative)", borderRadius: 8, padding: "10px 14px", margin: 0 }}>
                  {error}
                </p>
              )}
              <Button onClick={handleTrade} disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
                {loading ? "Сохраняем…" : tradeSide === "buy" ? "Купить" : "Продать"}
              </Button>
            </>
          ) : (
            <>
              {[
                { label: "Количество (исправить)", value: quantity, onChange: (e) => setQuantity(e.target.value) },
                { label: "Средняя цена, ₽ (исправить)", value: avgPrice, onChange: (e) => setAvgPrice(e.target.value) },
              ].map(({ label, value, onChange }) => (
                <div key={label}>
                  <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>{label}</label>
                  <input
                    type="number"
                    value={value}
                    onChange={onChange}
                    style={{
                      width: "100%", background: "var(--bg-surface)", border: "1px solid var(--border)",
                      borderRadius: 10, padding: "9px 14px", color: "var(--text-1)", fontSize: 16,
                      outline: "none", boxSizing: "border-box",
                    }}
                  />
                </div>
              ))}
              <p style={{ fontSize: 11.5, color: "var(--text-3)", margin: 0 }}>
                Это не сделка — прямая правка данных позиции (например, опечатка при вводе). Историю сделок и
                реализованный результат не меняет.
              </p>
              {error && (
                <p style={{ fontSize: 13, color: "var(--negative)", background: "var(--neg-fade)", border: "1px solid var(--negative)", borderRadius: 8, padding: "10px 14px", margin: 0 }}>
                  {error}
                </p>
              )}
              <Button onClick={handleSave} disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
                {loading ? "Сохраняем…" : "Сохранить исправление"}
              </Button>
            </>
          )}

          {pnl && (
            <div className="tw-flex tw-gap-3 tw-flex-wrap tw-pt-3" style={{ borderTop: "1px solid var(--border)" }}>
              <div className="pf-chip-stat">
                <span className="pf-chip-stat__lbl">Реализовано</span>
                <span className={`pf-chip-stat__val ${pnl.realized > 0 ? "tw-text-success" : pnl.realized < 0 ? "tw-text-danger" : "tw-text-text-secondary"}`}>{formatMoney(pnl.realized, { decimals: 0 })}</span>
              </div>
              <div className="pf-chip-stat">
                <span className="pf-chip-stat__lbl">Не реализовано</span>
                <span className={`pf-chip-stat__val ${pnl.unrealized > 0 ? "tw-text-success" : pnl.unrealized < 0 ? "tw-text-danger" : "tw-text-text-secondary"}`}>{pnl.unrealized != null ? formatMoney(pnl.unrealized, { decimals: 0 }) : "—"}</span>
              </div>
              <div className="pf-chip-stat">
                <span className="pf-chip-stat__lbl">Дивиденды получено</span>
                <span className="pf-chip-stat__val tw-text-success">+{formatMoney(pnl.dividends_received, { decimals: 0 })}</span>
              </div>
              <div className="pf-chip-stat">
                <span className="pf-chip-stat__lbl">Комиссии уплачено</span>
                <span className="pf-chip-stat__val tw-text-text-secondary">−{formatMoney(pnl.commissions_paid, { decimals: 0 })}</span>
              </div>
            </div>
          )}

          {!confirmDelete ? (
            <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)} disabled={loading}
              iconLeft={<Trash2 size={14} />} style={{ width: "100%", justifyContent: "center", color: "var(--danger)" }}>
              Удалить позицию
            </Button>
          ) : (
            <div className="tw-flex tw-items-center tw-gap-2">
              <span className="tw-text-[13px] tw-text-text-secondary tw-flex-1">Удалить {position.ticker} из портфеля?</span>
              <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)} disabled={loading}>Отмена</Button>
              <Button size="sm" onClick={handleDelete} disabled={loading}
                style={{ background: "var(--danger)", borderColor: "var(--danger)" }}>
                Удалить
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// =========================
// ADD POSITION MODAL
// =========================

// Поиск non-equity инструмента (облигация/фьючерс/фонд) для добавления в
// портфель — по образцу TickerInput, но бьёт в /api/bonds|futures|funds?search=
// вместо /api/companies. onSelect получает выбранную запись целиком (нужны
// secid + short_name + last_price для авто-подстановки).
const INSTRUMENT_SEARCH_CONFIG = {
  bond: { endpoint: "bonds", nameField: "short_name", priceField: null },
  future: { endpoint: "futures", nameField: "short_name", priceField: "settle_price" },
  fund: { endpoint: "funds", nameField: "short_name", priceField: "last_price" },
};
// Логотип строки поиска: облигация с известным эмитентом-акцией — логотип
// компании (CompanyLogo), иначе логотип самого инструмента у брокера
// (InstrumentLogo, ISIN для облигаций / secid для фьючерсов и фондов) —
// тот же принцип, что HoldingLogo в таблице «Состав портфеля».
const InstrumentSearchLogo = ({ instrumentType, item, size = 26 }) => {
  if (instrumentType === "bond" && item.issuer_ticker) {
    return <CompanyLogo ticker={item.issuer_ticker} name={item.issuer_name || item.short_name} size={size} />;
  }
  const id = instrumentType === "bond" ? item.isin : item.secid;
  return <InstrumentLogo id={id} name={item.short_name} size={size} />;
};
const InstrumentSearchInput = ({ instrumentType, value, onChange, onSelect, placeholder }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const cfg = INSTRUMENT_SEARCH_CONFIG[instrumentType];
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const ref = React.useRef(null);

  useEffect(() => {
    if (!cfg || !value) { setSuggestions([]); setOpen(false); return; }
    const timer = setTimeout(() => {
      fetch(`${apiUrl}/api/${cfg.endpoint}?search=${encodeURIComponent(value)}`)
        .then(r => r.ok ? r.json() : [])
        .then(data => { setSuggestions(data.slice(0, 8)); setOpen(data.length > 0); })
        .catch(() => setSuggestions([]));
    }, 220);
    return () => clearTimeout(timer);
  }, [value, instrumentType]);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!cfg) return null;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <input
        type="text" value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder} autoComplete="off"
        style={{
          width: "100%", background: "var(--bg-surface)", border: "1px solid var(--border)",
          borderRadius: 10, padding: "9px 14px", color: "var(--text-1)", fontSize: 16,
          outline: "none", boxSizing: "border-box",
        }}
      />
      {open && suggestions.length > 0 && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
          background: "var(--bg-card)", border: "1px solid var(--border-mid)",
          borderRadius: 10, boxShadow: "0 8px 24px var(--shadow-xl, rgba(0,0,0,0.3))",
          zIndex: 9999, overflow: "hidden", maxHeight: 260, overflowY: "auto",
        }}>
          {suggestions.map(item => (
            <div
              key={item.secid}
              onMouseDown={() => { onSelect(item); setOpen(false); setSuggestions([]); }}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", cursor: "pointer" }}
              onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}
            >
              <InstrumentSearchLogo instrumentType={instrumentType} item={item} size={26} />
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-1)" }}>{item[cfg.nameField]}</span>
                <span style={{ fontFamily: "monospace", fontSize: 11.5, color: "var(--text-3)" }}>{item.secid}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const INSTRUMENT_TYPE_LABELS = {
  equity: "Акция", bond: "Облигация", future: "Фьючерс", fund: "Фонд", cash: "Кэш",
};
const AddPositionModal = ({ portfolioId, existingPositions, token, onClose, onSuccess }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
  const [instrumentType, setInstrumentType] = useState("equity");
  const [side, setSide] = useState("buy");
  const [ticker, setTicker] = useState("");
  const [secid, setSecid] = useState("");       // non-equity: выбранный SECID
  const [secName, setSecName] = useState("");    // non-equity: имя для подстановки цены
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("RUB");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const check = async (resp, action) => {
    if (resp.ok) return resp;
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Не удалось ${action} (HTTP ${resp.status})`);
  };
  const del = async (id) => check(
    await fetch(`${apiUrl}/api/portfolios/${portfolioId}/positions/${id}`, { method: "DELETE", headers: authHeaders }),
    "удалить позицию"
  );
  const post = async (body) => check(
    await fetch(`${apiUrl}/api/portfolios/${portfolioId}/positions`, { method: "POST", headers: authHeaders, body: JSON.stringify(body) }),
    "сохранить позицию"
  );

  const handleSubmitEquity = async () => {
    const qty = parseFloat(quantity), prc = parseFloat(price);
    const companies = await fetch(`${apiUrl}/api/companies`).then(r => r.json());
    const company = Array.isArray(companies)
      ? companies.find(c => c.ticker.toUpperCase() === ticker.trim().toUpperCase())
      : null;
    if (!company) throw new Error(`Тикер «${ticker.trim().toUpperCase()}» не найден в базе`);

    const existing = existingPositions.find(p => p.instrument_type === "equity" && p.company_id === company.id);
    // Бэк отдаёт Decimal строками — приводим к числам ДО сравнений
    const exQty = existing ? parseFloat(existing.quantity) : 0;
    const exAvg = existing ? parseFloat(existing.avg_buy_price) : 0;

    if (side === "sell") {
      if (!existing) throw new Error("Такой позиции нет в портфеле — нечего продавать");
      if (qty > exQty) throw new Error(`Нельзя продать больше чем есть (${exQty} шт.)`);
      const newQty = exQty - qty;
      await del(existing.id);
      if (newQty > 1e-9) await post({ company_id: company.id, instrument_type: "equity", quantity: newQty, avg_buy_price: exAvg });
    } else if (existing) {
      const newQty = exQty + qty;
      const newAvg = (exQty * exAvg + qty * prc) / newQty;
      await del(existing.id);
      await post({ company_id: company.id, instrument_type: "equity", quantity: newQty, avg_buy_price: parseFloat(newAvg.toFixed(4)) });
    } else {
      await post({ company_id: company.id, instrument_type: "equity", quantity: qty, avg_buy_price: prc });
    }
  };

  const handleSubmitInstrument = async () => {
    // Облигация/фьючерс/фонд — та же логика усреднения, что у акций, но ключ
    // «уже есть такая позиция» — instrument_type+secid, а не company_id.
    const qty = parseFloat(quantity), prc = parseFloat(price);
    if (!secid) throw new Error("Выберите бумагу из списка");
    const existing = existingPositions.find(p => p.instrument_type === instrumentType && p.secid === secid);
    const exQty = existing ? parseFloat(existing.quantity) : 0;
    const exAvg = existing ? parseFloat(existing.avg_buy_price) : 0;

    if (side === "sell") {
      if (!existing) throw new Error("Такой позиции нет в портфеле — нечего продавать");
      if (qty > exQty) throw new Error(`Нельзя продать больше чем есть (${exQty} шт.)`);
      const newQty = exQty - qty;
      await del(existing.id);
      if (newQty > 1e-9) await post({ instrument_type: instrumentType, secid, quantity: newQty, avg_buy_price: exAvg });
    } else if (existing) {
      const newQty = exQty + qty;
      const newAvg = (exQty * exAvg + qty * prc) / newQty;
      await del(existing.id);
      await post({ instrument_type: instrumentType, secid, quantity: newQty, avg_buy_price: parseFloat(newAvg.toFixed(4)) });
    } else {
      await post({ instrument_type: instrumentType, secid, quantity: qty, avg_buy_price: prc });
    }
  };

  const handleSubmitCash = async () => {
    // Денежные средства — без покупки/продажи усреднением: одна строка на
    // валюту, редактируется прямым изменением суммы (не через buy/sell).
    const amount = parseFloat(quantity);
    const existing = existingPositions.find(p => p.instrument_type === "cash" && p.currency === currency);
    if (existing) {
      const newAmount = side === "sell" ? parseFloat(existing.quantity) - amount : parseFloat(existing.quantity) + amount;
      if (newAmount < 0) throw new Error("Нельзя списать больше, чем есть на счёте");
      await del(existing.id);
      if (newAmount > 1e-9) await post({ instrument_type: "cash", currency, quantity: newAmount, avg_buy_price: 1 });
    } else {
      if (side === "sell") throw new Error("Такой валюты в портфеле нет — нечего списывать");
      await post({ instrument_type: "cash", currency, quantity: amount, avg_buy_price: 1 });
    }
  };

  const handleSubmit = async () => {
    setError(null);
    if (instrumentType === "cash") {
      if (!quantity) { setError("Укажите сумму"); return; }
      if (parseFloat(quantity) <= 0) { setError("Сумма должна быть больше нуля"); return; }
    } else {
      const needsTicker = instrumentType === "equity" ? ticker.trim() : secid;
      if (!needsTicker || !quantity || !price) { setError("Заполни все поля"); return; }
      if (parseFloat(quantity) <= 0 || parseFloat(price) <= 0) { setError("Количество и цена должны быть больше нуля"); return; }
    }

    setLoading(true);
    try {
      if (instrumentType === "equity") await handleSubmitEquity();
      else if (instrumentType === "cash") await handleSubmitCash();
      else await handleSubmitInstrument();
      onSuccess();
    } catch (e) {
      setError(e.message || "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-box" style={{ maxWidth: 420, width: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 24px 16px", borderBottom: "1px solid var(--border)" }}>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "var(--text-1)" }}>Добавить сделку</h3>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: "4px 8px", minWidth: 0 }}><X size={16} /></button>
        </div>

        <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Класс актива */}
          <div>
            <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>Класс актива</label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 4, background: "var(--bg-surface)", borderRadius: 10, padding: 4 }}>
              {Object.entries(INSTRUMENT_TYPE_LABELS).map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => { setInstrumentType(id); setTicker(""); setSecid(""); setSecName(""); setPrice(""); setQuantity(""); setError(null); }}
                  style={{
                    padding: "7px 2px", borderRadius: 7, border: "none", cursor: "pointer", fontSize: 11.5, fontWeight: 600,
                    background: instrumentType === id ? "var(--accent)" : "transparent",
                    color: instrumentType === id ? "var(--on-accent)" : "var(--text-2)",
                  }}
                >{label}</button>
              ))}
            </div>
          </div>

          {/* Buy / Sell toggle — не для кэша (там прямое пополнение/списание той же кнопкой) */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, background: "var(--bg-surface)", borderRadius: 10, padding: 4 }}>
            {[
              { id: "buy", label: instrumentType === "cash" ? "🟢 Пополнить" : "🟢 Покупка" },
              { id: "sell", label: instrumentType === "cash" ? "🔴 Списать" : "🔴 Продажа" },
            ].map(s => (
              <button
                key={s.id}
                onClick={() => setSide(s.id)}
                style={{
                  padding: "8px 0", borderRadius: 7, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
                  background: side === s.id ? (s.id === "buy" ? "var(--positive)" : "var(--negative)") : "transparent",
                  color: side === s.id ? "var(--on-accent)" : "var(--text-2)",
                  transition: "all var(--motion-fast)",
                }}
              >{s.label}</button>
            ))}
          </div>

          {instrumentType === "equity" && (
            <div>
              <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>Тикер</label>
              <TickerInput value={ticker} onChange={setTicker} placeholder="SBER" />
            </div>
          )}

          {(instrumentType === "bond" || instrumentType === "future" || instrumentType === "fund") && (
            <div>
              <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>Бумага</label>
              <InstrumentSearchInput
                instrumentType={instrumentType}
                value={secName}
                onChange={setSecName}
                onSelect={(item) => {
                  setSecid(item.secid);
                  setSecName(item.short_name);
                  const cfg = INSTRUMENT_SEARCH_CONFIG[instrumentType];
                  if (cfg.priceField && item[cfg.priceField]) setPrice(String(item[cfg.priceField]));
                }}
                placeholder={instrumentType === "bond" ? "напр. ОФЗ 26238" : instrumentType === "future" ? "напр. Si-6.26" : "напр. SBMX"}
              />
            </div>
          )}

          {instrumentType === "cash" && (
            <div>
              <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>Валюта</label>
              <select
                value={currency} onChange={e => setCurrency(e.target.value)}
                style={{
                  width: "100%", background: "var(--bg-surface)", border: "1px solid var(--border)",
                  borderRadius: 10, padding: "9px 14px", color: "var(--text-1)", fontSize: 16, boxSizing: "border-box",
                }}
              >
                {["RUB", "USD", "EUR", "CNY"].map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          {instrumentType === "cash" ? (
            <div>
              <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>Сумма</label>
              <input
                type="number" value={quantity} onChange={e => setQuantity(e.target.value)} placeholder="50000"
                style={{
                  width: "100%", background: "var(--bg-surface)", border: "1px solid var(--border)",
                  borderRadius: 10, padding: "9px 14px", color: "var(--text-1)", fontSize: 16,
                  outline: "none", boxSizing: "border-box",
                }}
              />
            </div>
          ) : (
            [
              { label: `Количество (${instrumentType === "equity" ? "акций" : instrumentType === "bond" ? "штук" : instrumentType === "future" ? "контрактов" : "паёв"})`, value: quantity, onChange: e => setQuantity(e.target.value), placeholder: "100" },
              { label: side === "buy" ? "Цена покупки ₽" : "Цена продажи ₽", value: price, onChange: e => setPrice(e.target.value), placeholder: "280.50" },
            ].map(({ label, value, onChange, placeholder }) => (
              <div key={label}>
                <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>{label}</label>
                <input
                  type="number"
                  value={value}
                  onChange={onChange}
                  placeholder={placeholder}
                  style={{
                    width: "100%", background: "var(--bg-surface)", border: "1px solid var(--border)",
                    borderRadius: 10, padding: "9px 14px", color: "var(--text-1)", fontSize: 16,
                    outline: "none", boxSizing: "border-box",
                  }}
                />
              </div>
            ))
          )}

          {error && (
            <p style={{ fontSize: 13, color: "var(--negative)", background: "var(--neg-fade)", border: "1px solid var(--negative)", borderRadius: 8, padding: "10px 14px", margin: 0 }}>
              {error}
            </p>
          )}

          <button
            onClick={handleSubmit}
            disabled={loading}
            className={`btn ${side === "buy" ? "btn-primary" : ""}`}
            style={{
              width: "100%", justifyContent: "center", padding: "10px 20px", marginTop: 4, opacity: loading ? 0.6 : 1,
              ...(side === "sell" ? { background: "var(--negative)", color: "var(--on-accent)", border: "none" } : {}),
            }}
          >
            {loading ? "Сохраняем..." : side === "buy" ? <><Plus size={15} /> {instrumentType === "cash" ? "Пополнить" : "Купить"}</> : <><TrendingDown size={15} /> {instrumentType === "cash" ? "Списать" : "Продать"}</>}
          </button>
        </div>
      </div>
    </div>
  );
};

// Hoisted to module scope (NOT defined inside PortfolioView) so the page's
// re-renders — tab switch, click, 5s price poll — do NOT remount them and the
// first-load count-up isn't replayed. `gate` carries the once-per-page-visit
// flag (a ref owned by PortfolioView).
// Скролл-появление (IntersectionObserver) — как .reveal/.reveal.in в HTML-
// прототипе: карточка проявляется (fade-in + сдвиг снизу) при входе в зону
// видимости РЕАЛЬНЫМ скроллом страницы, не при монтировании вкладки (это
// отдельно от AppearGroup — тот отыгрывает один раз при первом открытии
// вкладки, а не при скролле; для длинных панелей нужны оба эффекта).
const PfReveal = ({ children, className = "", as: Tag = "div", style: styleProp, ...rest }) => {
  const ref = useRef(null);
  const reduced = usePrefersReducedMotion();
  const [inView, setInView] = useState(reduced);
  useEffect(() => {
    if (reduced || !ref.current) return;
    // Портфель скроллится не в window, а во внутреннем .app-shell
    // (overflow-y:auto). root:null (viewport) по спецификации должен
    // работать и со вложенным скроллом, но на практике первая проверка
    // сразу после монтирования — до того как реальные данные API
    // дозагрузятся и разметка встанет на постоянные размеры — может
    // застать элемент временно в зоне пересечения → сработает один раз
    // и больше никогда не переоценится (unobserve). Явно указываем
    // реальный скролл-контейнер как root и откладываем observe() на
    // 2 кадра — даём разметке устояться перед первым замером.
    let io;
    let raf1;
    const raf2 = requestAnimationFrame(() => {
      raf1 = requestAnimationFrame(() => {
        if (!ref.current) return;
        const root = ref.current.closest(".app-shell") || null;
        io = new IntersectionObserver(
          ([entry]) => { if (entry.isIntersecting) { setInView(true); io.unobserve(entry.target); } },
          { root, threshold: 0.08 }
        );
        io.observe(ref.current);
      });
    });
    return () => { cancelAnimationFrame(raf2); if (raf1) cancelAnimationFrame(raf1); if (io) io.disconnect(); };
  }, [reduced]);
  return (
    <Tag
      ref={ref}
      className={className}
      style={{
        ...styleProp,
        opacity: inView ? 1 : 0,
        transform: inView ? "translateY(0)" : "translateY(16px)",
        transition: reduced ? undefined : "opacity 550ms cubic-bezier(.25,.7,.4,1), transform 550ms cubic-bezier(.25,.7,.4,1)",
      }}
      {...rest}
    >
      {children}
    </Tag>
  );
};

const HeadlineNum = ({ value, gate }) => {
  const n = useCountUp(value, 320, gate);
  // Голое число без валюты: знак ₽ рисует вызывающая разметка отдельным
  // мелким span'ом — formatMoney добавлял свой «₽», и в hero выходило «₽ ₽».
  return <span className="tw-tabular-nums">{formatNumber(Math.round(n), { decimals: 0 })}</span>;
};

// ARIA tablist with a sliding accent underline (the "live language" tab motion).
const PortfolioTabBar = ({ tabs, value, onChange }) => {
  const reduced = usePrefersReducedMotion();
  const refs = useRef({});
  const [bar, setBar] = useState({ left: 0, width: 0 });
  useEffect(() => {
    const el = refs.current[value];
    if (el) setBar({ left: el.offsetLeft, width: el.offsetWidth });
  }, [value]);
  return (
    <div role="tablist" aria-label="Разделы портфеля" className="tw-relative tw-flex tw-gap-1 tw-border-b tw-border-border-subtle tw-overflow-x-auto">
      {tabs.map((t) => {
        const active = value === t.id;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            ref={(el) => { refs.current[t.id] = el; }}
            onClick={() => onChange(t.id)}
            className={`tw-px-4 tw-py-2 tw-text-[14px] tw-font-medium tw-bg-transparent tw-border-0 tw-cursor-pointer tw-whitespace-nowrap tw-rounded-sm focus-visible:tw-outline-none focus-visible:tw-shadow-focus ${active ? "tw-text-accent" : "tw-text-text-secondary hover:tw-text-text-primary"}`}
          >
            {t.label}
          </button>
        );
      })}
      <span
        aria-hidden="true"
        className="tw-absolute tw-bottom-0 tw-h-0.5 tw-bg-accent tw-rounded-pill"
        style={{
          left: bar.left, width: bar.width,
          transition: reduced ? undefined : "left var(--motion-base) var(--ease-out), width var(--motion-base) var(--ease-out)",
        }}
      />
    </div>
  );
};

// Big score dial with once-per-page-visit count-up (gated via PortfolioView ref).
const QUALITY_TONE = (score) =>
  score == null ? "neutral" : score >= 75 ? "success" : score >= 60 ? "info" : score >= 40 ? "neutral" : "danger";
// Цвет шкалы субиндекса по баллу (полоса «от максимума»)
const QUALITY_BAR = (score) =>
  score == null ? "--cat-8" : score >= 75 ? "--success" : score >= 60 ? "--cat-3" : score >= 40 ? "--cat-1" : "--danger";

const ScoreCard = ({ score, label, gate }) => {
  const n = useCountUp(score ?? 0, 320, gate);
  return (
    <Card className="lg:tw-col-span-1 tw-flex tw-flex-col tw-items-center tw-justify-center tw-text-center">
      <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-2" style={{ letterSpacing: "0.06em" }}>
        Индекс качества
      </div>
      <div className="tw-flex tw-items-baseline tw-gap-1 tw-mb-3">
        <span className="tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums" style={{ fontSize: 56, lineHeight: 1, letterSpacing: "-1.5px" }}>
          {score == null ? "—" : fmtNumber(Math.round(n))}
        </span>
        <span className="tw-text-[20px] tw-text-text-tertiary">/100</span>
      </div>
      {label && <Badge tone={QUALITY_TONE(score)}>{label}</Badge>}
    </Card>
  );
};

// Donut-диаграмма распределения: «цвет только в данных» — cat-палитра токенов.
// SVG-кольцо без библиотек, в духе остальных чартов App.js.
const DonutChart = ({ slices, size = 188, thickness = 30 }) => {
  const r = (size - thickness) / 2;
  const C = 2 * Math.PI * r;
  let acc = 0;
  const cx = size / 2, cy = size / 2;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label="Распределение портфеля">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border-subtle)" strokeWidth={thickness} />
      {slices.map((s, i) => {
        const frac = Math.max(0, s.pct) / 100;
        const startAcc = acc;
        acc += frac;
        // подпись процента на самом сегменте — там, где влезает (от ~9%)
        const midAngle = 2 * Math.PI * (startAcc + frac / 2) - Math.PI / 2;
        const lx = cx + r * Math.cos(midAngle);
        const ly = cy + r * Math.sin(midAngle);
        return (
          <g key={i}>
            <circle
              cx={cx} cy={cy} r={r}
              fill="none" stroke={s.color} strokeWidth={thickness}
              strokeDasharray={`${frac * C} ${C}`}
              strokeDashoffset={-startAcc * C}
              transform={`rotate(-90 ${cx} ${cy})`}
            />
            {s.pct >= 9 && (
              <text x={lx} y={ly + 3.5} textAnchor="middle" fontSize="11" fontWeight="700"
                fill="var(--text-on-accent, #fff)" style={{ paintOrder: "stroke", stroke: "rgba(0,0,0,0.25)", strokeWidth: 2 }}>
                {Math.round(s.pct)}%
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

const CAT_COLORS = ["var(--cat-1)", "var(--cat-2)", "var(--cat-3)", "var(--cat-4)", "var(--cat-5)", "var(--cat-6)", "var(--cat-7)", "var(--cat-8)"];
// Донаты Портфеля — буквальная палитра прототипа (copper/estimate/copper-deep/
// up/down), а не наша 8-цветная категориальная (--cat-1..8).
const PF_CAT_COLORS = ["var(--pf-copper)", "var(--pf-estimate)", "var(--pf-copper-deep)", "var(--pf-up)", "var(--pf-down)"];

// Отраслевые TR-индексы MOEX (зеркало SECTOR_TR_TICKERS бэка,
// app/services/moex_history.py) — пресеты быстрого добавления в «+Добавить
// сравнение» (панель «Сравнение»).
const SECTOR_TR_PRESETS = [
  { sector: "Нефть и газ", ticker: "MEOGTR" },
  { sector: "Металлургия", ticker: "MEMMTR" },
  { sector: "Финансы", ticker: "MEFNTR" },
  { sector: "Потребительский сектор", ticker: "MECNTR" },
  { sector: "Транспорт и логистика", ticker: "METNTR" },
  { sector: "Электроэнергетика", ticker: "MEEUTR" },
  { sector: "Химия", ticker: "MECHTR" },
  { sector: "Телеком", ticker: "METLTR" },
  { sector: "IT-сектор", ticker: "MEITTR" },
  { sector: "Девелопмент", ticker: "MERETR" },
];

// Кнопки периода над графиком «Сравнение» — зеркало _PERIOD_DAYS бэка
// (app/services/portfolio.py). Порядок и подписи — как в задаче владельца.
const PERIOD_BUTTONS = [
  { id: "1m", label: "1М" },
  { id: "3m", label: "3М" },
  { id: "6m", label: "6М" },
  { id: "1y", label: "1Г" },
  { id: "3y", label: "3Г" },
  { id: "max", label: "Весь период" },
];
const PERIOD_LABEL_TEXT = {
  "1m": "1 месяц", "3m": "3 месяца", "6m": "полгода",
  "1y": "1 год", "3y": "3 года", max: "весь доступный период",
};

// Сравнение накопленной доходности портфеля с бенчмарком (Этап 3).
// Мультилинейный SVG: портфель и MCFTR — основные, IMOEX — тонкая справочная.
const BenchmarkChart = ({ series, extraSeries = [] }) => {
  const { dates = [], portfolio = [], mcftr = [], imoex = [], sector_blend: sectorBlend = null } = series || {};
  const svgRef = useRef(null);
  const [hover, setHover] = useState(null);   // индекс точки под курсором
  if (!dates.length) return null;
  const W = 640, H = 220, padL = 44, padR = 12, padT = 12, padB = 24;
  // Доп. линии сравнения (произвольный актив/портфель) выровнены на дату по
  // мастер-сетке `dates` вызывающей стороной — здесь только рисуем разрывы,
  // если для какой-то даты значения нет (молодая бумага/несовпадающий календарь).
  const all = [...portfolio, ...mcftr, ...imoex, ...(sectorBlend || []), ...(extraSeries || []).flatMap((s) => s.values)].filter((v) => typeof v === "number");
  const max = Math.max(...all, 0), min = Math.min(...all, 0), span = (max - min) || 1;
  const n = dates.length;
  const xAt = (i) => padL + (n <= 1 ? 0 : (i * (W - padL - padR)) / (n - 1));
  const yAt = (v) => padT + (1 - (v - min) / span) * (H - padT - padB);
  const line = (arr) => arr.map((v, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(" ");
  const lineWithGaps = (arr) => {
    let d = "";
    arr.forEach((v, i) => {
      if (typeof v !== "number") return;
      d += `${d === "" ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)} `;
    });
    return d;
  };
  const zeroY = yAt(0);
  const fmtD = (iso) => { const [y, m] = iso.split("-"); return `${m}.${y.slice(2)}`; };
  // Равномерные X-подписи дат (как в ObsLineChart — было ТОЛЬКО первая/
  // последняя точка без промежуточных меток, жалоба «ось X без пометок»)
  const xTickEvery = Math.max(1, Math.ceil(n / 6));
  const gridN = 4;
  const EXTRA_COLORS = ["#1F5FC4", "#8A4A26", "var(--cat-4)", "var(--cat-6)"];
  const LINES = [
    { key: "portfolio", d: line(portfolio), color: "var(--pf-copper)", w: 2.5, label: "Портфель", values: portfolio },
    { key: "mcftr", d: line(mcftr), color: "var(--cat-1)", w: 1.75, label: "Индекс МосБиржи, полная доходность", values: mcftr },
    { key: "imoex", d: line(imoex), color: "var(--cat-8)", w: 1.5, label: "Индекс МосБиржи (без дивидендов, справочно)", values: imoex },
    ...(sectorBlend ? [{
      key: "sector_blend", d: lineWithGaps(sectorBlend), color: "var(--cat-3)", w: 1.75,
      label: "Ваши секторы (в рыночных пропорциях)", values: sectorBlend,
    }] : []),
    ...(extraSeries || []).map((s, i) => ({
      key: s.key || s.label, d: lineWithGaps(s.values), color: EXTRA_COLORS[i % EXTRA_COLORS.length], w: 1.75,
      label: s.label, values: s.values, removable: true, onRemove: s.onRemove,
    })),
  ];
  // Тултип: ближайшая точка по X под курсором
  const handleMove = (e) => {
    const el = svgRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const xSvg = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((xSvg - padL) / (W - padL - padR)) * (n - 1));
    setHover(i >= 0 && i < n ? i : null);
  };
  const fmtFullD = (iso) => { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; };

  return (
    <div className="tw-relative">
      {hover != null && (
        <div
          className="tw-absolute tw-z-10 tw-pointer-events-none tw-bg-bg-overlay tw-border tw-border-border-subtle tw-rounded-lg tw-shadow-lg tw-px-3.5 tw-py-2.5 tw-text-[12px]"
          style={{ left: `${(xAt(hover) / W) * 100}%`, top: 0, transform: xAt(hover) > W * 0.6 ? "translateX(-105%)" : "translateX(8px)", minWidth: 150 }}
        >
          <div className="tw-text-text-tertiary tw-font-mono tw-mb-1.5 tw-pb-1.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>{fmtFullD(dates[hover])}</div>
          <div className="tw-flex tw-flex-col tw-gap-1">
            {LINES.map((l) => (
              typeof l.values?.[hover] === "number" ? (
                <div key={l.key} className="tw-flex tw-items-center tw-gap-1.5">
                  <span className="tw-inline-block tw-w-2.5 tw-h-2.5 tw-rounded-full tw-shrink-0" style={{ background: l.color }} />
                  <span className="tw-truncate tw-text-text-secondary" style={{ maxWidth: 150 }}>{l.label}</span>
                  <b className="tw-font-mono tw-tabular-nums tw-shrink-0 tw-ml-auto tw-pl-2" style={{ color: l.values[hover] >= 0 ? "var(--pf-up)" : "var(--pf-down)" }}>
                    {fmtPercent(l.values[hover], { sign: true })}
                  </b>
                </div>
              ) : null
            ))}
          </div>
        </div>
      )}
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} role="img" aria-label="Портфель против бенчмарка"
        onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        {Array.from({ length: gridN + 1 }, (_, g) => min + (span * g) / gridN).map((v, k) => (
          <g key={k}>
            <line x1={padL} x2={W - padR} y1={yAt(v)} y2={yAt(v)} stroke="var(--border-subtle)" strokeWidth="1" strokeDasharray={Math.abs(v) < 0.01 ? undefined : "2 6"} />
            <text x={padL - 8} y={yAt(v) + 3.5} textAnchor="end" fontSize="10" fill="var(--text-tertiary)" fontFamily="monospace">{v.toFixed(1)}%</text>
          </g>
        ))}
        {min < 0 && max > 0 && <line x1={padL} x2={W - padR} y1={zeroY} y2={zeroY} stroke="var(--border-strong)" strokeWidth="1.25" />}
        {/* Градиентная заливка под линией портфеля — как в прототипе (медь, 0.26→0 прозрачности) */}
        <defs>
          <linearGradient id="pfBenchFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--pf-copper)" stopOpacity="0.26" />
            <stop offset="100%" stopColor="var(--pf-copper)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {portfolio.length > 0 && (
          <polygon
            points={`${xAt(0)},${padT + (H - padT - padB)} ${portfolio.map((v, i) => `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(" ")} ${xAt(n - 1)},${padT + (H - padT - padB)}`}
            fill="url(#pfBenchFill)"
          />
        )}
        {LINES.map((l) => <path key={l.key} d={l.d} fill="none" stroke={l.color} strokeWidth={l.w} strokeLinejoin="round" strokeLinecap="round" />)}
        {/* Точка-маркер + подпись «сейчас +X%» на конце линии портфеля */}
        {portfolio.length > 0 && typeof portfolio[portfolio.length - 1] === "number" && (() => {
          const lastV = portfolio[portfolio.length - 1];
          const cx = xAt(n - 1), cy = yAt(lastV);
          const sign = lastV >= 0 ? "+" : "";
          const labelX = Math.max(cx - 120, padL);
          return (
            <g>
              <circle cx={cx} cy={cy} r="4.5" fill="var(--pf-copper)" stroke="var(--bg-elevated)" strokeWidth="2.5" />
              <text x={labelX} y={Math.max(cy - 12, 16)} fontFamily="Inter, system-ui, sans-serif" fontSize="12.5" fontWeight="700" fill="var(--pf-copper-deep)">
                сейчас {sign}{lastV.toFixed(1)}%
              </text>
            </g>
          );
        })()}
        {hover != null && (
          <g>
            <line x1={xAt(hover)} x2={xAt(hover)} y1={padT} y2={H - padB} stroke="var(--border-strong)" strokeWidth="1" strokeDasharray="3 3" />
            {LINES.map((l) => (
              typeof l.values?.[hover] === "number" ? (
                <circle key={l.key} cx={xAt(hover)} cy={yAt(l.values[hover])} r="3.5" fill={l.color} stroke="var(--bg-elevated)" strokeWidth="1.5" />
              ) : null
            ))}
          </g>
        )}
        {dates.map((d, i) => (
          i % xTickEvery !== 0 && i !== n - 1 ? null : (
            <text
              key={i} x={xAt(i)} y={H - 8}
              textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}
              fontSize="10" fill="var(--text-tertiary)" fontFamily="monospace"
            >
              {fmtD(d)}
            </text>
          )
        ))}
      </svg>
      <div className="tw-flex tw-flex-wrap tw-gap-4 tw-mt-2 tw-text-[12px] tw-text-text-secondary">
        {LINES.map((l) => (
          <span key={l.label} className="tw-inline-flex tw-items-center tw-gap-1.5">
            <span className="tw-inline-block tw-w-4 tw-h-0.5 tw-rounded-pill" style={{ background: l.color, height: l.w }} />{l.label}
            {l.removable && (
              <button type="button" onClick={l.onRemove} className="tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer tw-text-text-tertiary hover:tw-text-danger tw-font-bold" title="Убрать из сравнения">×</button>
            )}
          </span>
        ))}
      </div>
    </div>
  );
};

// ─── Объяснения метрик (Блок 4) — читаемые примитивы с витрины /_design ───
// СТРУКТУРА под выверенные тексты владельца (НЕ сочинять самим!):
//   what     — «Что это», одна фраза простым языком
//   reading  — «Что значит ваше значение»: (value) => текст по простым порогам
//              (пороги согласовываются вместе с текстами)
//   soWhat   — «Что с этим делать» (кратко; подробно — ИИ-диагноз)
//   formula  — свёрнутый блок «для любопытных»: формула + как считается
// Заполнять по ключам метрик; пока текстов нет — показывается заглушка.
const _pct = (v) => v == null ? "—" : formatNumber(Math.abs(v), { decimals: 1 }).replace(".", ",") + "%";
const _sgn = (v) => v == null ? "—" : (v >= 0 ? "+" : "−") + _pct(v);
const _num1 = (v) => v == null ? "—" : formatNumber(v, { decimals: 2 });

// Тексты — из выверенного документа владельца (config/metric_explaination),
// пороговые варианты «что значит ваше значение» выбираются по фактическому числу.
const METRIC_EXPLANATIONS = {
  return_total: {
    title: "Доходность (полная, за период)",
    type: "fact", icon: "📈",
    what: "Сколько в среднем за год приносила бумага с учётом и роста цены, и дивидендов — за тот период, что она торгуется. Это факт прошлого, не обещание будущего.",
    tone: (v, ctx = {}) => v == null || ctx.shortHistory ? "info" : v >= 0 ? "positive" : "caution",
    reading: (v, ctx = {}) => v == null ? null
      : ctx.shortHistory
        ? `Период слишком короткий (${ctx.period || "меньше года"}), чтобы судить о средней доходности — значение показано как факт за этот отрезок, а не как годовая норма.`
        : v >= 0
          ? `За ${ctx.period || "период расчёта"} портфель в среднем давал ${_pct(v)} в год с учётом дивидендов. Это то, что реально получил бы держатель, а не прогноз на будущее.`
          : `За ${ctx.period || "период расчёта"} портфель в среднем терял ${_pct(v)} в год даже с учётом дивидендов. Прошлый результат не предсказывает будущий — но показывает, какой путь уже пройден.`,
    soWhat: "Доходность прошлого — самый ненадёжный ориентир на будущее из всех метрик (она почти случайна год к году). Смотрите её вместе с риском: высокая доходность, добытая высоким риском, — не то же самое, что спокойный стабильный рост. Для оценки будущего полезнее фундаментальные метрики и CAPM-оценка рядом.",
    formula: { expr: "Доходность = (Итоговая стоимость с дивидендами / Начальная стоимость)^(1/число лет) − 1", note: "Полная доходность считается как среднегодовой темп роста (CAGR) с учётом дивидендов; дивиденды учитываются по датам выплат. Среднегодовой темп (а не простое среднее) честнее: он отражает реально накопленный результат, без завышения от скачков." },
  },
  capm: {
    title: "CAPM (модельная ожидаемая доходность)",
    type: "judgment", icon: "🧮",
    what: "Оценка доходности, которую бумага «должна» приносить за свой уровень рыночного риска — по классической финансовой модели. Это не факт и не прогноз, а ориентир: сколько разумно ожидать с учётом того, насколько бумага чувствительна к рынку.",
    reading: (v, ctx = {}) => v == null ? null
      : (ctx.rf != null && v < ctx.rf)
        ? `Сейчас модель даёт ${_sgn(v)} — ниже доходности ОФЗ. При структурной премии ERP это обычно означает отрицательную бету (бумага в среднем двигалась против рынка) — редкий случай, не общая особенность периода.`
        : `Модель оценивает «справедливую» ожидаемую доходность в ${_sgn(v)} в год — исходя из безрисковой ставки и того, насколько бумага следует за рынком.`,
    soWhat: "CAPM — модельная, а не фактическая величина, и она чувствительна к допущению о премии за риск рынка. Используйте её как один из ориентиров рядом с фактической доходностью, а не как точный прогноз. Когда фактическая доходность сильно выше CAPM-оценки — бумага дала больше «положенного» за свой риск (см. Альфа).",
    formula: { expr: "Ожидаемая доходность = Rf + β × ERP", note: "Rf — безрисковая ставка (ОФЗ ~10 лет — тот же вход, что и в оценке справедливой стоимости на карточке компании). ERP — премия за риск рынка акций РФ по Дамодарану (mature market ERP + страновая премия), структурная оценка, а не историческая доходность индекса. β — чувствительность бумаги к рынку." },
  },
  div_yield: {
    title: "Дивидендная доходность",
    type: "fact", icon: "💵",
    what: "Сколько дивидендов компания выплачивает за год относительно текущей цены акции. Грубо — «процент кэшем», который приносит бумага помимо изменения цены.",
    reading: (v) => v == null ? null
      : v > 8 ? `${_pct(v)} — высокая дивидендная доходность. Заметная часть отдачи приходит деньгами, а не только ростом цены. Типично для зрелых прибыльных компаний (банки, нефтегаз).`
      : v >= 3 ? `${_pct(v)} — умеренная дивидендная доходность, обычная для устойчивой компании, которая делится прибылью, но и вкладывает в рост.`
      : `${_pct(v)} — компания платит мало или не платит дивидендов. Это не плохо: растущие компании часто реинвестируют прибыль вместо выплат, делая ставку на рост цены.`,
    soWhat: "Дивиденды на российском рынке — часто половина всей доходности, поэтому важны для тех, кто хочет денежный поток. Но высокая дивдоходность бывает и тревожным сигналом — если она выросла из-за падения цены, а не роста выплат. Сверяйтесь с тем, устойчивы ли выплаты (история дивидендов в карточке).",
    formula: { expr: "Дивидендная доходность = Дивиденды за год на акцию / Текущая цена акции", note: "Меняется при движении цены: чем дешевле акция, тем выше дивдоходность при тех же выплатах." },
  },
  pe: {
    title: "P/E текущий",
    type: "fact", icon: "🏷️",
    what: "Сколько рублей инвесторы платят за каждый рубль годовой прибыли компании прямо сейчас. Чем выше — тем «дороже» оценена компания относительно её прибыли.",
    reading: (v) => v == null ? null
      : v < 5 ? `${_num1(v)}× — компания оценена дёшево относительно прибыли. Это бывает у недооценённых бумаг, но и у тех, от кого рынок ждёт падения прибыли. Дёшево ≠ автоматически хорошо.`
      : v <= 12 ? `${_num1(v)}× — обычная для рынка оценка: цена соразмерна прибыли.`
      : `${_num1(v)}× — компания оценена дорого относительно текущей прибыли. Рынок закладывает рост прибыли в будущем. Если рост не случится — цена уязвима.`,
    soWhat: "P/E полезно сравнивать с конкурентами в том же секторе и с историческим P/E самой компании (дорогая ли она относительно своего обычного уровня). Низкий P/E — повод разобраться, недооценка это или проблема. Высокий — проверить, оправдан ли он ростом.",
    formula: { expr: "P/E = Цена акции / Прибыль на акцию (EPS)", note: "Обновляется при изменении цены: прибыль меняется раз в квартал с отчётностью, цена — постоянно, поэтому текущий P/E «дышит» вместе с котировкой." },
  },
  pe_hist: {
    title: "P/E исторический",
    type: "fact", icon: "🕰️",
    what: "Средний уровень P/E этой компании за прошлые годы — ориентир, дорого или дёшево она стоит относительно своей собственной нормы, а не рынка вообще.",
    reading: (v, ctx = {}) => {
      const cur = ctx.peCurrent;
      if (v == null) return "Недостаточно истории, чтобы посчитать средний P/E (молодая бумага или периоды без прибыли).";
      if (cur == null) return null;
      if (cur < v * 0.8) return "Сейчас компания оценена дешевле, чем в среднем за свою историю. Возможна недооценка — или рынок пересмотрел ожидания вниз.";
      if (cur <= v * 1.2) return "Компания оценена примерно как обычно за свою историю — без явного перекоса.";
      return "Сейчас компания дороже своей исторической нормы. Рынок ждёт большего, чем раньше, — проверьте, обоснованы ли эти ожидания.";
    },
    soWhat: "Сравнение текущего P/E с историческим — быстрый способ понять, в какой точке своего обычного диапазона оценки находится компания. Но прошлая норма могла устареть, если бизнес сильно изменился.",
    formula: { expr: null, note: "Медиана (или средняя) P/E компании за прошлые годы (обычно 5 лет). Медиана устойчивее к разовым выбросам прибыли, чем простое среднее." },
  },
  earnings_yield: {
    title: "Earnings yield (доходность прибыли)",
    type: "fact", icon: "🔁",
    what: "Обратная сторона P/E: сколько прибыли компания генерирует на каждый вложенный в неё рубль. Удобно сравнивать напрямую с доходностью ОФЗ — «прибыльность» акции против безрисковой ставки.",
    reading: (v, ctx = {}) => {
      if (v == null) return "Нет данных о прибыли (компания убыточна или P/E не рассчитан).";
      if (ctx.rf == null) return null;
      return v >= ctx.rf
        ? `${_pct(v)} — прибыльность компании выше безрисковой ставки. Бизнес генерирует больше на рубль цены, чем дали бы гособлигации, — но у акции есть риск, которого у ОФЗ нет.`
        : `${_pct(v)} — прибыльность ниже безрисковой ставки ОФЗ. За риск акции вы пока получаете меньше прибыли на рубль, чем дал бы безриск. Имеет смысл, только если ждёте роста прибыли.`;
    },
    soWhat: "Earnings yield против доходности ОФЗ — простой тест «стоит ли акция своего риска по прибыли». Если прибыльность акции ниже безриска и роста не ожидается — вопрос, зачем брать на себя риск. Сравнивайте в связке с перспективами роста.",
    formula: { expr: "Earnings yield = 1 / P/E = Прибыль на акцию / Цена", note: "Прямое сравнение с доходностью ОФЗ показывает, дорого ли стоит прибыль компании относительно безрисковой альтернативы." },
  },
  volatility: {
    title: "Волатильность",
    type: "fact", icon: "〰️",
    what: "Насколько сильно цена бумаги колеблется — вверх и вниз — в течение года. Чем выше, тем более «дёрганая» бумага и тем шире разброс возможных результатов.",
    tone: (v) => v == null ? "info" : v > 35 ? "caution" : "info",
    reading: (v) => v == null ? null
      : v < 20 ? `${_pct(v)} в год — относительно спокойный уровень, цена колеблется умеренно. Типично для крупных устойчивых компаний.`
      : v <= 35 ? `${_pct(v)} в год — обычная для российских акций волатильность. Заметные колебания — норма, к ним стоит быть готовым.`
      : `${_pct(v)} в год — сильные колебания. Может быстро расти и так же быстро падать. Требует более крепких нервов и меньшей доли в портфеле.`,
    soWhat: "Волатильность — это не «плохо» само по себе, это мера разброса. Высокая волатильность означает, что и просадки, и взлёты могут быть резкими — важно, готовы ли вы держать бумагу в просадке. В портфеле волатильность отдельных бумаг частично гасится, если они не падают одновременно (см. Корреляции).",
    formula: { expr: "Волатильность = σ(дневных доходностей) × √252", note: "Стандартное отклонение дневных доходностей за период, приведённое к годовому виду (252 — число торговых дней в году; риск растёт как корень из времени)." },
  },
  var_95: {
    title: "VaR 95% (стоимость под риском)",
    type: "estimate", icon: "📉",
    what: "Оценка «плохого, но не катастрофического» периода: с вероятностью 95% убыток не превысит этой величины. В худших 5% случаев потери могут быть и больше.",
    reading: (v, ctx = {}) => v == null ? null
      : `${ctx.horizonLabel || "В обычный день"} (19 случаев из 20) потери не превышают ${_pct(v)}. Но в худшие 5% случаев убыток может оказаться глубже, и насколько, VaR не говорит.`,
    soWhat: "VaR помогает почувствовать масштаб обычной просадки, чтобы она не застала врасплох. Главное ограничение: VaR молчит про «хвост» — самые редкие, но самые болезненные обвалы (кризисы, чёрные лебеди) выходят за рамки 95%. Не воспринимайте VaR как максимально возможный убыток.",
    formula: { expr: "VaR 95% = −(5-й перцентиль дневных доходностей)", note: "Исторический метод: берётся распределение дневных доходностей за период, VaR 95% — граница худших 5% дней. На другой горизонт масштабируется через корень из времени." },
  },
  var_99: {
    title: "VaR 99% (редкий плохой день)",
    type: "estimate", icon: "📉",
    what: "Оценка настоящего плохого дня (1 к 100), а не рядового: с вероятностью 99% потери не превышают эту величину.",
    reading: (v, ctx = {}) => v == null ? null
      : `${ctx.horizonLabel || "В этом горизонте"} с вероятностью 99% потери не превышают ${_pct(v)} — это более редкий и глубокий хвост, чем VaR 95%. Смотрите оба вместе, чтобы увидеть, как быстро растёт потенциальная потеря при переходе от «плохого» к «очень плохому».`,
    soWhat: "VaR 99% реже «срабатывает», чем VaR 95%, но когда срабатывает — потери обычно заметно глубже. Большой разрыв между VaR 95% и VaR 99% — признак «толстого хвоста»: у бумаги/портфеля редкие, но резкие провалы, а не плавное нарастание риска.",
    formula: { expr: "VaR 99% = −(1-й перцентиль дневных доходностей)", note: "Тот же исторический метод, что и VaR 95%, но граница — худший 1% дней вместо 5%. Годовой горизонт — через перекрывающиеся 252-дневные окна, не через корень времени (честнее для нелинейных хвостов)." },
  },
  cvar_95: {
    title: "CVaR 95% (глубина потерь внутри хвоста)",
    type: "estimate", icon: "🌊",
    what: "Не просто ГРАНИЦА плохого хвоста (это VaR) — а средняя потеря ВНУТРИ него. Отвечает на вопрос «а если я всё-таки попал в те самые 5%, насколько плохо там внутри».",
    reading: (v, ctx = {}) => v == null ? null
      : `${ctx.horizonLabel || "В этом горизонте"}, если случился один из худших 5% дней, средняя глубина потери внутри этого хвоста — ${_pct(v)}. Это глубже самого VaR 95% — VaR называет только границу, а CVaR усредняет всё, что за ней.`,
    soWhat: "CVaR честнее VaR в оценке плохого сценария: VaR отвечает «где граница плохого», CVaR — «насколько плохо, если я всё же в этом хвосте». Для риск-менеджмента CVaR предпочтительнее — он не игнорирует то, что происходит за порогом.",
    formula: { expr: "CVaR 95% = среднее из потерь хуже VaR 95%", note: "Иногда называется Expected Shortfall. Считается как средняя доходность по дням хуже 5-го перцентиля — то есть внутри того самого «плохого хвоста», который VaR только очерчивает." },
  },
  cvar_99: {
    title: "CVaR 99% (глубина потерь в редком хвосте)",
    type: "estimate", icon: "🌊",
    what: "Средняя потеря внутри самого редкого и глубокого хвоста (худший 1% дней) — самая консервативная из риск-метрик на этой странице.",
    reading: (v, ctx = {}) => v == null ? null
      : `${ctx.horizonLabel || "В этом горизонте"} средняя глубина потери внутри худшего 1% дней — ${_pct(v)}. Это самый мрачный, но и самый редкий ориентир из всех риск-метрик здесь.`,
    soWhat: "Используйте CVaR 99% как «на что рассчитывать, если случится по-настоящему редкое и плохое событие» — не как повседневный ориентир (для этого — VaR 95% или волатильность). Разница между CVaR 95% и CVaR 99% показывает, насколько тяжелее становится сценарий по мере углубления в хвост.",
    formula: { expr: "CVaR 99% = среднее из потерь хуже VaR 99%", note: "Тот же принцип, что CVaR 95%, но усредняет только худший 1% дней — самый глубокий и самый редкий срез распределения." },
  },
  upside_to_fair_pct: {
    title: "Апсайд к справедливой цене",
    type: "judgment", icon: "🎯",
    what: "Разница между текущей рыночной ценой и справедливой ценой Basis (синтез методов оценки с карточки компании, вкладка «Финансы» → «Справедливая стоимость») — то же суждение, перенесённое в портфель. Не факт и не прогноз, а оценочное мнение модели.",
    reading: (v, ctx = {}) => v == null ? null
      : v > 15 ? `Рынок оценивает бумагу на ${_pct(v)} ниже нашей справедливой цены — модель считает её недооценённой. Дата анализа может быть многомесячной давности — не переоценивайте точность до знака после запятой.`
      : v < -15 ? `Рынок оценивает бумагу на ${_pct(v)} выше нашей справедливой цены — модель считает её переоценённой.`
      : `Апсайд ${_sgn(v)} — рыночная цена примерно соответствует нашей справедливой оценке, без явного перекоса.`,
    soWhat: "Апсайд к цели — суждение модели, а не факт и не прогноз движения цены. Справедливая цена считается по отчётности и может отставать от рынка на месяцы — сверяйтесь с датой анализа в тултипе значения. Используйте как один из ориентиров, не единственный: рынок может годами не «сходиться» к модели.",
    formula: { expr: "Апсайд = (Справедливая цена − Текущая цена) / Текущая цена", note: "Справедливая цена — синтез методов оценки (DCF/мультипликаторы/дивидендная модель и т.п.) с карточки компании. Считается только для акций и только там, где есть законченный анализ справедливой стоимости." },
  },
  downside_vol: {
    title: "Нисходящая волатильность",
    type: "fact", icon: "⬇️",
    what: "Как обычная волатильность, но считает только колебания вниз — «плохой» риск. Рост в расчёт не идёт, потому что инвестора пугают просадки, а не подъёмы.",
    reading: (v, ctx = {}) => {
      if (v == null) return null;
      const vol = ctx.volatility;
      if (vol != null && v < vol * 0.8) return `${_pct(v)} — нисходящий риск ниже общей волатильности. Это значит, что заметная часть «дёрганости» приходится на рост, а не на падения — это скорее хорошо.`;
      return `${_pct(v)} — падения вносят в колебания почти столько же, сколько подъёмы. Риск просадок соразмерен общей волатильности.`;
    },
    soWhat: "Нисходящая волатильность честнее отражает то, чего инвестор реально боится — потери. Две бумаги с одинаковой общей волатильностью могут сильно отличаться по нисходящему риску: одна «дёргается» в основном вверх, другая — болезненно падает. Используется в коэффициенте Сортино.",
    formula: { expr: null, note: "Стандартное отклонение только тех дневных доходностей, что ниже целевого уровня (порог 0), приведённое к годовому виду через √252. Отклонения вверх обнуляются и не наказываются." },
  },
  beta: {
    title: "Бета",
    type: "fact", icon: "🎯",
    what: "Насколько бумага следует за рынком в целом. Бета 1 — движется заодно с рынком; больше 1 — усиливает движения рынка (растёт и падает сильнее); меньше 1 — спокойнее рынка.",
    tone: (v) => v == null ? "info" : v < 0 ? "caution" : "info",
    reading: (v) => v == null ? null
      : v > 1.2 ? `${_num1(v)} — усиливает движения рынка: когда рынок растёт — обычно растёт сильнее, когда падает — падает глубже. Добавляет портфелю рыночного риска.`
      : v >= 0.8 ? `${_num1(v)} — движется примерно вровень с рынком.`
      : v >= 0 ? `${_num1(v)} — спокойнее рынка: меньше реагирует на общие движения. Может служить стабилизатором в портфеле.`
      : `${_num1(v)} — в среднем движется против рынка. Встречается редко и часто связано с низкой ликвидностью — относитесь к такой бете осторожно.`,
    soWhat: "Бета говорит о рыночном (неустранимом диверсификацией) риске, но НЕ о собственной «дёрганости» бумаги — для этого есть волатильность. Бумага может быть очень волатильной (свои новости), но с низкой бетой, если её колебания не синхронны с рынком. Смотрите бету в паре с R² — он показывает, насколько ей можно доверять.",
    formula: { expr: "Бета = Ковариация(доходность бумаги, доходность рынка) / Дисперсия(доходность рынка)", note: "Рынок — индекс Мосбиржи. Где доступно, показывается официальная бета Мосбиржи (маркер «М»), иначе — расчёт Basis (маркер «Б»)." },
  },
  r_squared: {
    title: "R² (надёжность беты)",
    type: "fact", icon: "🔗",
    what: "Какая доля движений бумаги объясняется движением рынка. Идёт в паре с бетой и показывает, насколько ей можно доверять.",
    tone: (v) => v == null ? "info" : v < 0.3 ? "caution" : "info",
    reading: (v) => v == null ? null
      : v > 0.6 ? `${_num1(v)} — бумага движется в основном вместе с рынком, поэтому бета надёжна и хорошо описывает её поведение.`
      : v >= 0.3 ? `${_num1(v)} — рынок объясняет лишь часть движений; у бумаги много собственных факторов, бета описывает её приблизительно.`
      : `${_num1(v)} — движения бумаги слабо связаны с рынком: она живёт своей жизнью (свои новости, низкая ликвидность). Бете доверять опасно — она мало что объясняет.`,
    soWhat: "R² — это «знак качества» беты. Высокий R² — бета осмысленна. Низкий — бета формально посчитана, но мало значит, потому что бумага движется не по рынку. Всегда читайте бету и R² вместе.",
    formula: { expr: "R² = (корреляция доходности бумаги с рынком)²", note: "Значение от 0 до 1: доля дисперсии бумаги, объяснённая рынком." },
  },
  sharpe: {
    title: "Коэффициент Шарпа",
    type: "estimate", icon: "🧭",
    what: "Главная мера «качества» доходности: сколько отдачи сверх безрисковой ставки вы получаете на каждую единицу риска. Отвечает на вопрос — оправдывает ли доходность тот риск, что вы на себя берёте.",
    tone: (v) => v == null ? "info" : v > 1 ? "positive" : v > 0 ? "info" : "caution",
    reading: (v) => v == null ? null
      : v > 1 ? `${_num1(v)} — хороший показатель: портфель приносит достойную отдачу за свой риск.`
      : v > 0 ? `${_num1(v)} — портфель приносит сверх безриска, но немного относительно риска. Риск вознаграждается слабо.`
      : `${_num1(v)} — портфель пока приносит не больше (или меньше), чем безрисковая ОФЗ. Важный контекст: сейчас ставка ОФЗ высокая (около 12–13%), и в этом периоде сам рынок акций отставал от неё — поэтому отрицательный Шарп сейчас типичен не только для вашего портфеля, но и для рынка в целом. Это характеристика момента (высокая ставка), а не обязательно слабость вашего набора бумаг.`,
    soWhat: "Шарп лучше всего работает для сравнения: один портфель против другого, ваш портфель против рынка. Само по себе отрицательное значение в период высокой ставки не означает «плохой портфель» — оно означает, что риск акций сейчас вознаграждается слабо по всему рынку. Если Шарп низкий устойчиво и в нормальные периоды — это повод пересмотреть, оправдан ли риск. Подробный разбор даст ИИ-диагноз.",
    formula: { expr: "Шарп = (Доходность портфеля − Безрисковая ставка) / Волатильность портфеля", note: "Числитель и знаменатель — годовые. Безрисковая ставка — ОФЗ ~10 лет (тот же вход, что и в CAPM и в оценке справедливой стоимости на карточке компании). Волатильность портфеля считается через ковариационную матрицу (с учётом корреляций), поэтому ниже простого среднего волатильностей бумаг." },
  },
  alpha: {
    title: "Альфа (Jensen’s alpha)",
    type: "judgment", icon: "🏆",
    what: "Показывает, обыграл ли актив рынок с поправкой на риск. Положительная альфа — бумага дала больше, чем «положено» за её уровень риска; отрицательная — меньше.",
    tone: (v) => v == null ? "info" : v > 1 ? "positive" : v >= -1 ? "info" : "caution",
    reading: (v) => v == null ? null
      : v > 1 ? `${_sgn(v)} — за свой уровень риска портфель дал БОЛЬШЕ, чем предсказывала модель. Это «премия» сверх рыночной отдачи, скорректированной на риск.`
      : v >= -1 ? `${_sgn(v)} — результат примерно такой, какой и ожидался за этот риск. Ни обгона, ни отставания от модели.`
      : `${_sgn(v)} — за свой риск получено МЕНЬШЕ ожидаемого. Риск не окупился относительно того, что давал рынок.`,
    soWhat: "Альфа — попытка отделить «мастерство/везение» от простого следования за рынком. Но она зависит от модели и от выбранного периода: положительная альфа за три года не гарантирует её в будущем. Читайте альфу как «как бумага показала себя относительно своего риска в этом окне», а не как прогноз.",
    formula: { expr: "Альфа = Фактическая доходность − [Rf + β × ERP]", note: "Разница между тем, что бумага реально дала, и тем, что предсказывает CAPM за её бету (Rf — ОФЗ ~10 лет, ERP — премия Дамодарана). Все величины годовые." },
  },
  sortino: {
    title: "Коэффициент Сортино",
    type: "estimate", icon: "🌊",
    what: "Как Шарп, но наказывает только за «плохой» риск — просадки, а не за колебания вверх. Сколько отдачи сверх безриска вы получаете на единицу риска падения.",
    tone: (v) => v == null ? "info" : v > 1 ? "positive" : v > 0 ? "info" : "caution",
    reading: (v) => v == null ? null
      : v > 1 ? `${_num1(v)} — хорошее соотношение: отдача достойна того риска просадок, что вы несёте.`
      : v > 0 ? `${_num1(v)} — отдача есть, но относительно риска падений она скромная.`
      : `${_num1(v)} — как и Шарп, сейчас давит высокая ставка ОФЗ: отдача портфеля не покрывает безриск. Сортино отличается от Шарпа тем, что считает только риск падений, поэтому если он заметно выше Шарпа — значит часть волатильности приходится на рост, а не на просадки (это в плюс).`,
    soWhat: "Сортино честнее Шарпа для бумаг с асимметрией — тех, что в основном спокойно растут, но изредка резко падают (или наоборот). Сравнивайте Сортино с Шарпом: если Сортино выше — «дёрганость» бумаги в основном здоровая (вверх); если заметно ниже — риск сосредоточен в болезненных просадках.",
    formula: { expr: "Сортино = (Доходность портфеля − Безрисковая ставка) / Нисходящая волатильность", note: "Отличие от Шарпа — в знаменателе только нисходящая волатильность (колебания ниже нуля), а не общая." },
  },
};

// Сноска про текущий режим высокой ставки — показывается рядом с группой «Риск»
const RISK_REGIME_NOTE = "В 2023–2026 безрисковая ставка (ОФЗ) держится высоко — около 12–13% годовых. Когда «безопасные» гособлигации дают так много, риск акций вознаграждается слабее, и метрики вроде Шарпа и Сортино по всему рынку оказываются низкими или отрицательными. Это особенность периода высокой ставки, а не обязательно слабость конкретного портфеля. В периоды низкой ставки картина обычно иная.";

// Объяснения метрик: каждая метрика — ОТДЕЛЬНАЯ белая плита (Card).
// Внутри все смысловые части — равноправные плашки: нейтральная «Что это»,
// тонированная по значению «Что значит ваше значение» (есть не у всех метрик —
// только где есть число пользователя), зелёная «Что с этим делать»,
// формула — свёрнутой плашкой.
const MetricExplainers = ({ metricKeys, values = {}, ctx = {} }) => {
  const items = metricKeys
    .map((k) => ({ key: k, def: METRIC_EXPLANATIONS[k] }))
    .filter((x) => x.def);
  if (!items.length) return null;
  const TYPE_BAR = { fact: "var(--pf-ink-3)", estimate: "var(--pf-estimate)", judgment: "var(--pf-copper)" };
  return (
    <div className="tw-flex tw-flex-col tw-gap-3">
      {items.map(({ key, def }) => (
        <PfReveal key={key} id={`pf-metric-${key}`} style={{ scrollMarginTop: 24 }}>
        {/* Литерально из прототипа: .card.metric-card + t-fact/t-estimate/t-judgment
            (акцентная полоса 4px слева по типу «факт/оценка/суждение»),
            padding:20px 22px 20px 26px. */}
        <div className="pf-card" style={{ position: "relative", padding: "20px 22px 20px 26px", overflow: "hidden" }}>
          <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: "4px", background: TYPE_BAR[def.type] || "var(--pf-ink-3)" }} />
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
            {def.icon && <span style={{ fontSize: "18px", lineHeight: 1 }} aria-hidden="true">{def.icon}</span>}
            <span style={{ fontSize: "14.5px", fontWeight: 700, color: "var(--pf-ink)", flex: 1 }}>{def.title}</span>
            {def.type && <span className={def.type === "fact" ? "pf-tag-fact" : def.type === "estimate" ? "pf-tag-estimate" : "pf-tag-judgment"}>{def.type === "fact" ? "факт" : def.type === "estimate" ? "оценка" : "суждение"}</span>}
          </div>
          <p style={{ margin: 0, fontSize: "13px", color: "var(--pf-ink-2)" }}>
            {(def.reading && def.reading(values[key], ctx)) || def.what}
          </p>
          <Disclosure summary="Подробнее">
            <div className="tw-flex tw-flex-col tw-gap-2.5 tw-pt-1">
              <div className="tw-flex tw-gap-2 tw-items-start">
                <span className="tw-text-[13px] tw-shrink-0" aria-hidden="true">💡</span>
                <p className="tw-m-0 tw-text-[13px] tw-leading-[1.6]" style={{ color: "var(--pf-ink-2)" }}><b style={{ color: "var(--pf-ink)" }}>Что это.</b> {def.what}</p>
              </div>
              {def.soWhat && (
                <div className="tw-flex tw-gap-2 tw-items-start">
                  <span className="tw-text-[13px] tw-shrink-0" aria-hidden="true">🎯</span>
                  <p className="tw-m-0 tw-text-[13px] tw-leading-[1.6]" style={{ color: "var(--pf-ink-2)" }}><b style={{ color: "var(--pf-ink)" }}>Что с этим делать.</b> {def.soWhat}</p>
                </div>
              )}
              {def.formula && (
                <div style={{ background: "var(--pf-surface-3)", borderRadius: "9px", padding: "11px 15px" }}>
                  {def.formula.expr && (
                    <code className="tw-block tw-font-mono tw-whitespace-pre-wrap" style={{ fontSize: "12px", lineHeight: 1.6, color: "var(--pf-ink)", marginBottom: "6px" }}>
                      {def.formula.expr}
                    </code>
                  )}
                  {def.formula.note && (
                    <p className="tw-m-0" style={{ fontSize: "11.5px", lineHeight: 1.5, color: "var(--pf-ink-3)" }}>{def.formula.note}</p>
                  )}
                </div>
              )}
            </div>
          </Disclosure>
        </div>
        </PfReveal>
      ))}
    </div>
  );
};

// Логотип строки «Состав портфеля»: акция — компания по тикеру (CompanyLogo,
// карта /api/companies/logos). Non-equity — как в «Рынке» (MarketNeo): если у
// облигации известен эмитент-акция (issuer_ticker) — тоже логотип компании,
// иначе логотип самого инструмента у брокера (InstrumentLogo, карта
// /api/companies/instrument-logos, ключ ISIN для облигаций / secid для
// фондов, фьючерсов, валюты — r.ticker для non-equity это secid, НЕ тот ключ).
const HoldingLogo = ({ r, size }) => {
  if (!r.instrument_type || r.instrument_type === "equity") {
    return <CompanyLogo ticker={r.ticker} name={r.name} size={size} />;
  }
  if (r.instrument_type === "bond" && r.issuer_ticker) {
    return <CompanyLogo ticker={r.issuer_ticker} name={r.name} size={size} />;
  }
  const id = r.instrument_type === "bond" ? r.isin : r.secid;
  return <InstrumentLogo id={id} name={r.name} size={size} />;
};

// Колонка «Актив» как в «Составе»: иконка + тикер + название, клик —
// переход в карточку компании. Строка «Портфель» — просто жирный итог.
const makeAssetColumn = (onOpenCompany) => ({
  key: "ticker", label: "Актив",
  render: (_, r) => r._isTotal || r.company_id == null ? (
    <span className="tw-text-text-primary tw-font-semibold">{r.ticker}</span>
  ) : (
    <button
      type="button"
      onClick={() => onOpenCompany && onOpenCompany({ id: r.company_id, ticker: r.ticker, name: r.name, sector: r.sector })}
      className="tw-flex tw-items-center tw-gap-2.5 tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer tw-text-left tw-group"
      title={`Открыть карточку ${r.ticker}`}
    >
      <CompanyLogo ticker={r.ticker} name={r.name} size={30} />
      <div>
        <div className="tw-font-semibold tw-text-accent group-hover:tw-underline">{r.name || r.ticker}</div>
        <div className="tw-font-mono tw-text-[11px] tw-text-text-tertiary">{r.ticker}</div>
      </div>
    </button>
  ),
});

// Колонки групповых таблиц — общие для «Агрегирующей» и отдельных вкладок
// Клик по значку ⓘ над заголовком столбца — скролл к карточке-объяснению
// метрики (Доходность и оценка / Риск) + кратковременная вспышка рамкой.
function scrollToPfMetric(key) {
  const el = document.getElementById(`pf-metric-${key}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.remove("pf-flash");
  // eslint-disable-next-line no-void
  void el.offsetWidth;
  el.classList.add("pf-flash");
}
// tagClass — опционально: класс эпистемического чипа (pf-tag-judgment/pf-tag-estimate/
// pf-tag-fact) под подписью колонки, для метрик-моделей/оценок (см. design constitution:
// эпистемические теги обязательны на каждом аналитическом утверждении).
const pfColLabel = (metricKey, text, tagClass) => (
  <span className="tw-inline-flex tw-flex-col tw-items-end tw-gap-1">
    <button
      type="button"
      onClick={() => scrollToPfMetric(metricKey)}
      className="pf-info-icon"
      aria-label={`Подробнее про метрику «${text}»`}
      title="Подробнее"
    >
      i
    </button>
    <span>{text}</span>
    {tagClass && <span className={tagClass} style={{ fontSize: "9px", padding: "2px 6px" }}>
      {tagClass === "pf-tag-judgment" ? "суждение" : tagClass === "pf-tag-estimate" ? "оценка" : "факт"}
    </span>}
  </span>
);

// Литеральная разметка групповой таблицы (докс: .pos-table) для «Доходность
// и оценка» / «Риск» — та же структура, что у таблицы позиций в «Составе»,
// просто с произвольным набором колонок. Не абстрагирует стиль — рендерит
// ДОСЛОВНЫЙ <table className="pf-pos-table"> с теми же классами/тегами,
// что и остальные таблицы вкладки.
const PfMetricTable = ({ columns, rows }) => (
  <div style={{ overflowX: "auto" }}>
    <table className="pf-pos-table" style={{ minWidth: 720 }}>
      <thead>
        <tr>
          {columns.map((c) => <th key={c.key}>{c.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={row.key ?? row.ticker ?? i} style={row._isTotal ? { fontWeight: 700 } : undefined}>
            {columns.map((c) => (
              <td key={c.key}>{c.render ? c.render(row[c.key], row) : (row[c.key] ?? "—")}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// Флаг оценки Basis (см. valuation_flag в positions[]) — порог ±15% апсайда.
// Монохромная иконка-точка везде одинаковая; цвет несёт только подпись
// (конституция: «цвет — только в данных», иконка-глиф не дублирует цвет).
const VALUATION_FLAG_META = {
  undervalued: { label: "Недооценена", color: "var(--pf-up)" },
  fair: { label: "Справедливо", color: "var(--pf-ink-3)" },
  overvalued: { label: "Переоценена", color: "var(--warning)" },
};

const RETURN_COLUMNS = [
                        {
              key: "return3y", label: pfColLabel("return_total", "Доходность рынка"),
              render: (v, row) => v == null ? "—" : (
                <span className={v >= 0 ? "tw-text-success" : "tw-text-danger"} title="ПОЛНАЯ доходность самого актива за 3 года: цена + дивиденды (CAGR), независимо от того, когда вы его купили. Факт прошлого, не прогноз">
                  {fmtPercent(v, { sign: true })}{row?.shortHistory ? "*" : ""}
                  {row?.periodLabel && <span className="tw-text-text-tertiary tw-font-normal"> {row.periodLabel}</span>}
                </span>
              ),
            },
            {
              key: "capm", label: pfColLabel("capm", "CAPM (модель)", "pf-tag-judgment"),
              render: (v) => v == null ? "—" : (
                <span className="tw-text-text-tertiary" title="Модельная forward-оценка: Rf(ОФЗ ~10 лет) + β×ERP(Дамодаран). Оценка, не факт и не прогноз">
                  {fmtPercent(v, { sign: true })}
                </span>
              ),
            },
            {
              // Апсайд к справедливой цене Basis — ТОЛЬКО акции, тег «суждение»
              // (та же семья оценки, что вкладка «Финансы» → «Справедливая
              // стоимость» на карточке компании). Дата анализа может быть
              // многомесячной давности — раскрываем честно в тултипе, не
              // выдаём за свежий факт. Владелец 2026-07-23: заменяет мёртвую
              // «Ваша доходность» (см. правку выше).
              key: "upsideToFair",
              label: pfColLabel("upside_to_fair_pct", "Апсайд к цели", "pf-tag-judgment"),
              render: (v, row) => {
                if (row?._isTotal) {
                  return v == null ? "—" : (
                    <span className={v >= 0 ? "tw-text-success" : "tw-text-danger"} title="Средневзвешенный апсайд к справедливой цене Basis по акциям портфеля">
                      {fmtPercent(v, { sign: true })}
                      {row?.upsideToFairCoverage && <span className="tw-text-text-tertiary tw-font-normal"> ({row.upsideToFairCoverage})</span>}
                    </span>
                  );
                }
                if (row?.instrument_type && row.instrument_type !== "equity") return "—";
                if (v == null) return "—";
                const flag = VALUATION_FLAG_META[row?.valuationFlag];
                const asOf = row?.fairValueAsOf ? _dmy(row.fairValueAsOf) : "—";
                return (
                  <span title={`Апсайд к справедливой цене (аналитика от ${asOf}): рынок vs наша модель. Дата анализа может быть многомесячной давности — не переоценивайте точность.`}>
                    <span style={{ color: flag ? flag.color : "var(--pf-ink-2)" }}>{fmtPercent(v, { sign: true })}</span>
                    {flag && (
                      <span className="tw-inline-flex tw-items-center tw-gap-1 tw-ml-1.5 tw-text-[10.5px] tw-font-semibold tw-whitespace-nowrap" style={{ color: flag.color }}>
                        <span aria-hidden="true" style={{ color: "var(--pf-ink-3)" }}>●</span>{flag.label}
                      </span>
                    )}
                  </span>
                );
              },
            },
            { key: "divYield", label: pfColLabel("div_yield", "Див. дох."), render: (v) => v == null ? "—" : fmtPercent(v, { decimals: 1 }) },
            { key: "pe", label: pfColLabel("pe", "P/E тек."), render: (v) => v == null ? "—" : <span title="Пересчитывается от текущей котировки">{`${fmtNumber(v, { decimals: 1 })}×`}</span> },
            { key: "peHist", label: pfColLabel("pe_hist", "P/E ист."), render: (v) => v == null ? "—" : <span className="tw-text-text-tertiary" title="Медиана P/E за 5 лет">{`${fmtNumber(v, { decimals: 1 })}×`}</span> },
            {
              key: "earningsYield", label: pfColLabel("earnings_yield", "Дох. прибыли"),
              render: (v) => v == null ? "—" : <span title="Earnings yield = 1 / P/E">{fmtPercent(v, { decimals: 1 })}</span>,
            },
          ];

const RISK_COLUMNS = [
                        {
              key: "volatility", label: pfColLabel("volatility", "Волатильность"),
              render: (v, row) => v == null ? "—" : (
                <span title="СКО дневных доходностей × √252, годовая; у портфеля — через ковариационную матрицу">
                  {fmtPercent(v)}{row?.shortHistory ? "*" : ""}
                </span>
              ),
            },
            {
              key: "downsideVol", label: pfColLabel("downside_vol", "Нисходящая волатильность"),
              render: (v) => v == null ? "—" : <span title="Волатильность только по дням падения (порог 0), годовая">{fmtPercent(v)}</span>,
            },
            {
              key: "beta", label: pfColLabel("beta", "Beta"),
              render: (v, row) => v == null ? "—" : (
                <span title={row?.betaSource === "moex" ? "Данные Мосбиржи (файл коэффициентов срочного рынка)" : "Расчёт Basis (Диммсон, окно 3 года)"}>
                  {fmtNumber(v, { decimals: 2 })}{row?.shortHistory ? "*" : ""}
                  {row?.betaSource && <span className="tw-text-text-tertiary"> {row.betaSource === "moex" ? "ᴹ" : "ᴮ"}</span>}
                </span>
              ),
            },
            {
              key: "rSquared", label: pfColLabel("r_squared", "R²"),
              render: (v) => v == null ? "—" : (
                <span title="Доля движения, объяснённая рынком: >0,6 — бета надёжна" className={v >= 0.6 ? "tw-text-text-secondary" : "tw-text-text-tertiary"}>
                  {fmtNumber(v, { decimals: 2 })}
                </span>
              ),
            },
            {
              key: "sharpe", label: pfColLabel("sharpe", "Шарп"),
              render: (v) => v == null ? "—" : <span title="(Полная доходность − ставка ОФЗ) / волатильность. >1 — хорошо; ≤0 — риск не вознаграждается">{fmtNumber(v, { decimals: 2 })}</span>,
            },
            {
              key: "alpha", label: pfColLabel("alpha", "α"),
              render: (v) => v == null ? "—" : (
                <span className={v >= 0 ? "tw-text-success" : "tw-text-danger"} title="Альфа Дженсена: сверх «положенного» за риск по CAPM, % годовых">
                  {fmtPercent(v, { sign: true })}
                </span>
              ),
            },
            {
              key: "sortino", label: pfColLabel("sortino", "Сортино"),
              render: (v) => v == null ? "—" : <span title="(Полная доходность − ставка ОФЗ) / нисходящая волатильность">{fmtNumber(v, { decimals: 2 })}</span>,
            },
          ];

// VaR/CVaR — 2 столбца, значение зависит от переключателей над таблицей
// «Риск» (95%/99% × дневной/годовой). Ключи строк — var95/var99/var95Annual/
// var99Annual/cvar95/cvar99/cvar95Annual/cvar99Annual (см. analyticRows).
const makeRiskVarCvarColumns = (confidence, horizon) => {
  const suffix = horizon === "annual" ? "Annual" : "";
  const varKey = `var${confidence}${suffix}`;
  const cvarKey = `cvar${confidence}${suffix}`;
  const horizonLabel = horizon === "annual" ? "годовой (перекрыв. 252-дн. окна)" : "дневной";
  const explainerKey = confidence === 99 ? "var_99" : "var_95";
  const cvarExplainerKey = confidence === 99 ? "cvar_99" : "cvar_95";
  return [
    {
      key: varKey, label: pfColLabel(explainerKey, `VaR ${confidence}%`),
      render: (v) => v == null ? "—" : <span title={`VaR ${confidence}% (${horizonLabel}): граница «плохого» хвоста — где начинаются худшие ${100 - confidence}% дней`}>−{fmtPercent(v)}</span>,
    },
    {
      key: cvarKey, label: pfColLabel(cvarExplainerKey, `CVaR ${confidence}%`),
      render: (v) => v == null ? "—" : <span title={`CVaR ${confidence}% (${horizonLabel}): средняя потеря ВНУТРИ худших ${100 - confidence}% дней, а не только граница (это VaR)`}>−{fmtPercent(v)}</span>,
    },
  ];
};

// Честная подпись фактического периода метрики: «за 2 мес.», «за 1,9 г», «за 3 г»
const fmtHistoryPeriod = (years) => {
  if (years == null) return null;
  if (years >= 2.95) return "за 3 г";
  if (years >= 1) return `за ${String(Math.round(years * 10) / 10).replace(".", ",")} г`;
  const months = Math.max(1, Math.round(years * 12));
  return `за ${months} мес.`;
};

// =========================
// PORTFOLIO V2 — sidebar-shell layout (Обозреватель-style)
// Same data/logic as PortfolioView below (legacy, kept for reference) —
// this is a refactor of the LAYOUT, not the calculations.
// =========================

const PF_ZONES = [
  {
    id: "overview",
    label: "Обзор",
    items: [
      { id: "composition", label: "Состав", icon: PieChart },
    ],
  },
  {
    id: "returns_risk",
    label: "Доходность и риск",
    items: [
      { id: "compare",     label: "Сравнение",            icon: Scale },
      { id: "returns",     label: "Доходность и оценка",  icon: TrendingUp },
      { id: "risk",        label: "Риск",                 icon: ShieldAlert },
      { id: "correlation", label: "Матрица корреляций",   icon: ArrowRightLeft },
    ],
  },
  {
    id: "breakdown",
    label: "Разбор",
    items: [
      { id: "quality",      label: "Индекс качества", icon: Target },
      { id: "ai-diagnosis", label: "ИИ-Диагноз",       icon: Zap },
      { id: "stress",       label: "Стресс-тест",      icon: AlertTriangle },
    ],
  },
];

const PortfolioV2 = ({ token, onAuthRequired, onOpenCompany, forceSection }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  // forceSection — вход из верхней навигации «Стресс-тестирование» (App.js): та
  // вкладка ведёт прямиком в РЕАЛЬНО работающий стресс-тест портфеля, а не в
  // отдельную заглушку/дубль. PortfolioV2 монтируется заново при каждом входе,
  // поэтому initial state достаточно (тот же паттерн, что forceSection в ObserverV2).
  const [activeSection, setActiveSection] = useState(forceSection || "composition");
  const [visitedSections, setVisitedSections] = useState(() => new Set([forceSection || "composition"]));
  // Мобильный (≤760px) выезжающий сайдбар — design/MobileSidebarDrawer.jsx.
  const [drawerOpen, setDrawerOpen, drawerNarrow] = useMobileSidebarDrawer();
  const [stressScenario, setStressScenario] = useState("black_swan");
  // Доверительный уровень / горизонт для таблицы «Риск» (VaR/CVaR) — владелец
  // 2026-07-23: 95%/99% × дневной/годовой, 4 комбинации без перегрузки экрана
  // (2 независимых сегмент-тумблера вместо 4 кнопок).
  const [riskConfidence, setRiskConfidence] = useState(95); // 95 | 99
  const [riskHorizon, setRiskHorizon] = useState("daily"); // "daily" | "annual"
  // Период сравнения («Сравнение») — влияет ТОЛЬКО на benchmark-график, не на
  // риск-метрики (те всегда на фиксированном 3-летнем окне, см. design-task).
  const [comparePeriod, setComparePeriod] = useState("3y");
  const [benchmarkOverride, setBenchmarkOverride] = useState(null);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [portfolioList, setPortfolioList] = useState([]);
  const [activePortfolioId, setActivePortfolioId] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [positions, setPositions] = useState([]);
  const [rawPositions, setRawPositions] = useState([]);
  const [quotes, setQuotes] = useState({});
  const [portfolioLoading, setPortfolioLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  const [pfMetrics, setPfMetrics] = useState(null);
  const [qualityVersion, setQualityVersion] = useState("v2"); // "v1" | "v2" — методика v2.1 Фаза 1 живёт рядом со старой до приёмки
  const [factorProfile, setFactorProfile] = useState(null);
  const [aiDiagnosis, setAiDiagnosis] = useState(null);
  const [aiDiagnosisLoading, setAiDiagnosisLoading] = useState(false);
  const [aiDiagnosisError, setAiDiagnosisError] = useState(null);
  const [editPosition, setEditPosition] = useState(null);

  const handleSectionChange = (id) => {
    setActiveSection(id);
    setVisitedSections((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    // Панели переключаются через display:none/block (не размонтируются) —
    // общий скролл-контейнер .app-shell сохраняет позицию между ними, и
    // новая вкладка открывалась там же, где был проскроллен старый экран.
    // Сбрасываем скролл на переключении секции.
    const scroller = document.querySelector(".app-shell");
    if (scroller) scroller.scrollTop = 0;
    // Выбор раздела (в т.ч. из выехавшего мобильного сайдбара) закрывает drawer.
    setDrawerOpen(false);
  };

  const reloadPortfolio = () => { setShowAddModal(false); setReloadKey(k => k + 1); };

  const handleDeletePortfolio = async (id) => {
    await fetch(`${apiUrl}/api/portfolios/${id}`, { method: "DELETE", headers: authHeaders });
    setConfirmDeleteId(null);
    if (activePortfolioId === id) setActivePortfolioId(null);
    setReloadKey(k => k + 1);
  };

  useEffect(() => {
    if (!token) { setPortfolioLoading(false); return; }

    const loadData = async () => {
      try {
        const [list, realtimeResp] = await Promise.all([
          fetch(`${apiUrl}/api/portfolios`, { headers: authHeaders }).then(r => r.ok ? r.json() : []),
          fetch(`${apiUrl}/api/quotes/realtime`).then(r => r.ok ? r.json() : {}),
        ]);
        const latestQuotes = Object.fromEntries(
          Object.entries(realtimeResp || {}).map(([t, q]) => [t, q.price])
        );
        setQuotes(latestQuotes);

        if (list.length > 0) {
          setPortfolioList(list);
          const targetId = activePortfolioId && list.find(p => p.id === activePortfolioId)
            ? activePortfolioId
            : list[0].id;
          if (!activePortfolioId) setActivePortfolioId(targetId);

          const active = list.find(p => p.id === targetId) || list[0];
          setPortfolio(active);

          const detail = await fetch(`${apiUrl}/api/portfolios/${active.id}`, { headers: authHeaders }).then(r => r.json());
          if (detail.positions) {
            setRawPositions(detail.positions);
            const companiesResp = await fetch(`${apiUrl}/api/companies`).then(r => r.json());
            const companyMap = {};
            if (Array.isArray(companiesResp)) companiesResp.forEach(c => { companyMap[c.id] = c; });

            // «Состав портфеля» (таблица позиций/пай-чарт по бумагам) пока
            // равится ТОЛЬКО акции — non-equity (bond/future/fund/cash) не
            // имеют company_id/ticker/логотипа, эта строковая модель на них
            // не рассчитана. Они УЖЕ учтены в классах активов/секторах/весе
            // портфеля через pfMetrics.positions (бэк) — просто не дублируются
            // здесь отдельной строкой до отдельной доработки таблицы.
            const mapped = detail.positions.filter(pos => (pos.instrument_type || "equity") === "equity").map(pos => {
              const c = companyMap[pos.company_id] || {};
              const currentPrice = latestQuotes[c.ticker] || parseFloat(pos.avg_buy_price) || 0;
              return {
                id: pos.id,
                company_id: pos.company_id,
                ticker: c.ticker || "—",
                name: c.name || "—",
                shares: parseFloat(pos.quantity) || 0,
                avgPrice: parseFloat(pos.avg_buy_price) || 0,
                currentPrice,
              };
            });
            setPositions(mapped);
          } else {
            setPositions([]);
            setRawPositions([]);
          }

          fetch(`${apiUrl}/api/portfolios/${active.id}/metrics`, { headers: authHeaders })
            .then(r => r.ok ? r.json() : null)
            .then(m => setPfMetrics(m))
            .catch(() => setPfMetrics(null));

          fetch(`${apiUrl}/api/portfolios/${active.id}/factor-profile`, { headers: authHeaders })
            .then(r => r.ok ? r.json() : null)
            .then(m => setFactorProfile(m))
            .catch(() => setFactorProfile(null));

          fetch(`${apiUrl}/api/portfolios/${active.id}/diagnosis`, { headers: authHeaders })
            .then(r => r.ok ? r.json() : null)
            .then(m => setAiDiagnosis(m))
            .catch(() => setAiDiagnosis(null));
        } else {
          setPortfolioList([]);
          setPortfolio(null);
          setPositions([]);
          setRawPositions([]);
          setPfMetrics(null);
          setFactorProfile(null);
          setAiDiagnosis(null);
        }
      } finally {
        setPortfolioLoading(false);
      }
    };

    loadData();
  }, [token, reloadKey, activePortfolioId]);

  // Дивиденды по позициям портфеля — /api/portfolios/{id}/dividends, три
  // сегмента по датам (upcoming/pending/history), уже посчитанные на бэке
  // (доля владения на отсечку — из реплея сделок, не из текущего кол-ва).
  const [pfDividends, setPfDividends] = useState(null);
  useEffect(() => {
    if (!activePortfolioId || !token) { setPfDividends(null); return; }
    fetch(`${apiUrl}/api/portfolios/${activePortfolioId}/dividends`, { headers: authHeaders })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setPfDividends(data))
      .catch(() => setPfDividends(null));
  }, [activePortfolioId, token, reloadKey, apiUrl]);

  // «+ Добавить сравнение» (вкладка Сравнение) — произвольный тикер или другой
  // портфель пользователя. Каждая линия выравнивается на дату по мастер-сетке
  // pfMetrics.benchmark.dates (прямой lookup по ISO-дате из общего календаря
  // котировок — обе стороны читают одну и ту же таблицу quotes).
  const [compareLines, setCompareLines] = useState([]); // [{key, label, values}]
  const [compareTickerInput, setCompareTickerInput] = useState("");
  const [comparePortfolioId, setComparePortfolioId] = useState("");
  const [compareError, setCompareError] = useState(null);
  const [compareBuilderOpen, setCompareBuilderOpen] = useState(false);
  const [compareMode, setCompareMode] = useState("asset"); // "asset" | "portfolio" | "custom"

  // Кнопки периода над графиком «Сравнение» (1М/3М/6М/1Г/3Г/Весь период) —
  // pfMetrics всегда несёт бенчмарк дефолтного окна бэка (3г); для остальных
  // периодов рефетчим ЛЁГКИЙ /metrics?period=... и держим отдельно, не трогая
  // pfMetrics (риск-метрики/ставки должны остаться на фиксированном 3-летнем
  // окне — см. explainCtx.period, который читает ИМЕННО pfMetrics.benchmark).
  useEffect(() => {
    if (!activePortfolioId || !token || comparePeriod === "3y") { setBenchmarkOverride(null); return; }
    setBenchmarkLoading(true);
    fetch(`${apiUrl}/api/portfolios/${activePortfolioId}/metrics?period=${comparePeriod}`, { headers: authHeaders })
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => setBenchmarkOverride(m?.benchmark ?? null))
      .catch(() => setBenchmarkOverride(null))
      .finally(() => setBenchmarkLoading(false));
  }, [comparePeriod, activePortfolioId, token, reloadKey]);
  const activeBenchmark = benchmarkOverride || pfMetrics?.benchmark;
  const masterDates = activeBenchmark?.dates || [];
  // Смена периода меняет длину/сетку дат бенчмарка — ранее добавленные линии
  // сравнения были выровнены на СТАРУЮ сетку и потеряли бы синхронизацию по
  // индексу (не по дате). Честно сбрасываем их при смене периода, а не
  // рисуем молча смещённые числа — пользователь добавляет их заново под
  // новое окно (стоимость этого дешевле, чем тихая рассинхронизация).
  useEffect(() => { setCompareLines([]); }, [comparePeriod]);

  // Добавленная линия сравнения нормализована к СВОЕЙ истории (её "+0%" —
  // самая ранняя дата, которая у НЕЁ есть, а не первая дата мастер-сетки
  // портфеля masterDates[0]) — если её история длиннее окна портфеля
  // (портфель сужен молодой бумагой), к началу графика у линии уже
  // накопилась ненулевая доходность, хотя на графике она должна стартовать
  // с 0%, как остальные. Ребейзим: находим первую дату мастер-сетки, для
  // которой есть значение, и пересчитываем весь ряд относительно НЕЁ через
  // фактор роста (не вычитанием процентов — так неверно при сложном %).
  const rebaseToMasterStart = (byDate) => {
    const baseDate = masterDates.find((d) => d in byDate);
    if (baseDate == null) return masterDates.map(() => null);
    const baseFactor = 1 + byDate[baseDate] / 100;
    return masterDates.map((d) => {
      if (!(d in byDate)) return null;
      const factor = 1 + byDate[d] / 100;
      return Math.round((factor / baseFactor - 1) * 10000) / 100;
    });
  };

  const addCompareAsset = async (ticker) => {
    setCompareError(null);
    const tk = ticker.trim().toUpperCase();
    if (!tk || compareLines.some((l) => l.key === `asset:${tk}`)) return;
    try {
      const r = await fetch(`${apiUrl}/api/market/compare-asset?ticker=${encodeURIComponent(tk)}`);
      if (!r.ok) { setCompareError(`Тикер «${tk}» не найден`); return; }
      const data = await r.json();
      const byDate = Object.fromEntries(data.dates.map((d, i) => [d, data.cum_pct[i]]));
      const values = rebaseToMasterStart(byDate);
      setCompareLines((prev) => [...prev, { key: `asset:${tk}`, label: `${data.name || tk} (полная доходность)`, values }]);
      setCompareTickerInput("");
    } catch {
      setCompareError("Не удалось загрузить данные по тикеру");
    }
  };

  // Пресет «отраслевой индекс» (чипы в «+Добавить сравнение») — ТОТ ЖЕ путь
  // данных, что и ручной ввод тикера (addCompareAsset): тот же эндпоинт
  // /api/market/compare-asset, тот же rebaseToMasterStart, тот же массив
  // compareLines. Разница только в человеческой подписи по названию сектора,
  // а не по сырому коду индекса (MEOGTR и т.п.) — не дублирует логику.
  const addSectorPreset = async (sectorLabel, trTicker) => {
    setCompareError(null);
    const key = `asset:${trTicker}`;
    if (compareLines.some((l) => l.key === key)) return;
    try {
      const r = await fetch(`${apiUrl}/api/market/compare-asset?ticker=${encodeURIComponent(trTicker)}`);
      if (!r.ok) { setCompareError(`Отраслевой индекс «${sectorLabel}» пока недоступен для сравнения`); return; }
      const data = await r.json();
      if (!data?.dates?.length) { setCompareError(`Недостаточно истории по индексу «${sectorLabel}»`); return; }
      const byDate = Object.fromEntries(data.dates.map((d, i) => [d, data.cum_pct[i]]));
      const values = rebaseToMasterStart(byDate);
      setCompareLines((prev) => [...prev, { key, label: `${sectorLabel} (отраслевой индекс)`, values }]);
    } catch {
      setCompareError(`Не удалось загрузить индекс «${sectorLabel}»`);
    }
  };

  const addComparePortfolio = async (otherId) => {
    setCompareError(null);
    const other = portfolioList.find((p) => String(p.id) === String(otherId));
    if (!other || compareLines.some((l) => l.key === `portfolio:${otherId}`)) return;
    try {
      const r = await fetch(`${apiUrl}/api/portfolios/${otherId}/metrics`, { headers: authHeaders });
      if (!r.ok) { setCompareError("Не удалось загрузить второй портфель"); return; }
      const data = await r.json();
      const b = data?.benchmark;
      if (!b?.dates?.length) { setCompareError(`У портфеля «${other.name}» недостаточно истории котировок`); return; }
      const byDate = Object.fromEntries(b.dates.map((d, i) => [d, b.portfolio[i]]));
      const values = rebaseToMasterStart(byDate);
      setCompareLines((prev) => [...prev, { key: `portfolio:${otherId}`, label: other.name, values }]);
    } catch {
      setCompareError("Не удалось загрузить второй портфель");
    }
  };

  const removeCompareLine = (key) => setCompareLines((prev) => prev.filter((l) => l.key !== key));

  // «Свой конструктор» — взвешенная корзина из 2+ бумаг, сравнивается как ещё
  // одна линия. Упрощение: доходности взвешиваются линейно по датам (без
  // ребалансировки/сложного процента комбинации) — честная оценка, не факт,
  // помечено в подписи линии.
  const [customRows, setCustomRows] = useState([{ ticker: "", weight: 50 }, { ticker: "", weight: 50 }]);
  const [customMode, setCustomMode] = useState("basket"); // "basket" | "ratio"
  const [ratioA, setRatioA] = useState("");
  const [ratioB, setRatioB] = useState("");
  const setCustomRow = (idx, patch) => setCustomRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  const addCustomRow = () => setCustomRows((prev) => [...prev, { ticker: "", weight: 0 }]);
  const removeCustomRow = (idx) => setCustomRows((prev) => prev.filter((_, i) => i !== idx));

  const fetchCompareSeries = (ticker) =>
    fetch(`${apiUrl}/api/market/compare-asset?ticker=${encodeURIComponent(ticker.trim().toUpperCase())}`)
      .then((res) => (res.ok ? res.json() : null));

  const addCustomConstructor = async () => {
    setCompareError(null);
    if (customMode === "ratio") {
      if (!ratioA.trim() || !ratioB.trim()) { setCompareError("Укажите обе бумаги для отношения"); return; }
      try {
        const [dataA, dataB] = await Promise.all([fetchCompareSeries(ratioA), fetchCompareSeries(ratioB)]);
        if (!dataA || !dataA.dates?.length) { setCompareError(`Тикер «${ratioA.trim().toUpperCase()}» не найден`); return; }
        if (!dataB || !dataB.dates?.length) { setCompareError(`Тикер «${ratioB.trim().toUpperCase()}» не найден`); return; }
        const byDateA = Object.fromEntries(dataA.dates.map((d, j) => [d, dataA.cum_pct[j]]));
        const byDateB = Object.fromEntries(dataB.dates.map((d, j) => [d, dataB.cum_pct[j]]));
        // Отношение растущих факторов (1+cumA)/(1+cumB), ребейзнутое на начало
        // мастер-сетки — «относительная сила» A против B, классический ratio-chart.
        const rawRatio = {};
        masterDates.forEach((d) => {
          if (d in byDateA && d in byDateB) rawRatio[d] = (1 + byDateA[d] / 100) / (1 + byDateB[d] / 100) - 1 + 0; // growth-factor delta, rebase ниже переведёт в %
        });
        const byDateRatioPct = Object.fromEntries(Object.entries(rawRatio).map(([d, v]) => [d, v * 100]));
        const values = rebaseToMasterStart(byDateRatioPct);
        const label = `${ratioA.trim().toUpperCase()} ÷ ${ratioB.trim().toUpperCase()} · оценка`;
        setCompareLines((prev) => [...prev, { key: `ratio:${Date.now()}`, label, values }]);
        setRatioA(""); setRatioB("");
      } catch {
        setCompareError("Не удалось построить отношение");
      }
      return;
    }

    const rows = customRows.filter((r) => r.ticker.trim());
    if (rows.length < 2) { setCompareError("Добавьте минимум 2 бумаги для конструктора"); return; }
    const totalWeight = rows.reduce((s, r) => s + (Number(r.weight) || 0), 0);
    if (totalWeight <= 0) { setCompareError("Укажите веса бумаг (сумма должна быть больше нуля)"); return; }
    try {
      const results = await Promise.all(rows.map((r) => fetchCompareSeries(r.ticker)));
      const missing = rows.filter((_, i) => !results[i]);
      if (missing.length) { setCompareError(`Тикер «${missing[0].ticker.trim().toUpperCase()}» не найден`); return; }
      const seriesByRow = results.map((data, i) => {
        const byDate = Object.fromEntries(data.dates.map((d, j) => [d, data.cum_pct[j]]));
        const rebased = rebaseToMasterStart(byDate);
        return { weight: (Number(rows[i].weight) || 0) / totalWeight, byDate: Object.fromEntries(masterDates.map((d, j) => [d, rebased[j]]).filter(([, v]) => v != null)) };
      });
      const values = masterDates.map((d) => {
        let sum = 0, wSum = 0;
        seriesByRow.forEach(({ weight, byDate }) => {
          if (d in byDate) { sum += byDate[d] * weight; wSum += weight; }
        });
        return wSum > 0 ? sum / wSum : null;
      });
      const composition = rows.map((r) => `${Math.round(((Number(r.weight) || 0) / totalWeight) * 100)}% ${r.ticker.trim().toUpperCase()}`).join(" + ");
      setCompareLines((prev) => [...prev, { key: `custom:${Date.now()}`, label: `Конструктор: ${composition} · оценка`, values }]);
      setCustomRows([{ ticker: "", weight: 50 }, { ticker: "", weight: 50 }]);
    } catch {
      setCompareError("Не удалось построить конструктор");
    }
  };

  useEffect(() => {
    if (!token) return;
    const inTradingHours = () => {
      const now = new Date();
      const msk = new Date(now.toLocaleString("en-US", { timeZone: "Europe/Moscow" }));
      const day = msk.getDay();
      if (day === 0 || day === 6) return false;
      const t = msk.getHours() * 60 + msk.getMinutes();
      return t >= 10 * 60 && t <= 18 * 60 + 50;
    };
    let timer;
    const pollPrices = () => {
      fetch(`${apiUrl}/api/quotes/realtime`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data) {
            const priceMap = Object.fromEntries(Object.entries(data).map(([t, q]) => [t, q.price]));
            setQuotes(priceMap);
            setPositions(prev => prev.map(p => ({
              ...p,
              currentPrice: priceMap[p.ticker] ?? p.currentPrice,
            })));
          }
        })
        .catch(() => {});
      timer = setTimeout(pollPrices, inTradingHours() ? 5000 : 300000);
    };
    timer = setTimeout(pollPrices, inTradingHours() ? 5000 : 300000);
    return () => clearTimeout(timer);
  }, [token, apiUrl]);

  // 🔴 Раньше при пустом positions сюда подставлялся MOCK_PORTFOLIO (демо
  // СБЕР/Лукойл/Яндекс из первой версии экрана): пока реальные позиции
  // грузились, hero успевал показать стоимость МОК-портфеля, а потом
  // «обновлялся до свежего» реального числа (жалоба владельца 2026-07-19).
  // Мок-портфелю в проде места нет: рендерим только реальные позиции, на
  // время загрузки — гейт portfolioLoading ниже (мигания нуля тоже нет).
  const displayPositions = positions;

  const stats = useMemo(() => {
    const src = displayPositions;
    const totalValue = src.reduce((a, p) => a + p.shares * p.currentPrice, 0);
    const totalCost  = src.reduce((a, p) => a + p.shares * p.avgPrice, 0);
    const totalProfit = totalValue - totalCost;
    const profitPct  = totalCost > 0 ? (totalProfit / totalCost) * 100 : 0;
    return { totalValue, totalCost, totalProfit, profitPct };
  }, [displayPositions]);
  // Грандтотал ПО ВСЕМ классам (акции+облигации+фьючерсы+фонды+кэш).
  // 🔴 Раньше: сначала рисовался stats.totalValue (только акции, живые
  // котировки), а через секунду приезжал /metrics и ПОДМЕНЯЛ число на
  // бэковый total_value (все классы, цены из таблицы quotes) — владелец
  // видел «загрузилось одно число, потом обновилось до другого» (плюс
  // count-up анимация докрутки делала подмену особенно заметной).
  // Теперь источник ОДИН и не меняется: акции — живой клиентский расчёт
  // (те же котировки, что тикают в таблице позиций раз в 5с), non-equity
  // (облигации/фьючерсы/фонды/кэш) — стоимость с бэка (клиент её посчитать
  // не может). Пока non-equity часть не приехала — hero показывает
  // плейсхолдер (grandTotalReady), а не промежуточное «только акции».
  const nonEquityValue = useMemo(
    () => (pfMetrics?.positions || [])
      .filter((p) => p.instrument_type !== "equity" && p.value != null)
      .reduce((a, p) => a + p.value, 0),
    [pfMetrics]
  );
  const hasNonEquity = rawPositions.some((p) => (p.instrument_type || "equity") !== "equity");
  const grandTotalValue = stats.totalValue + nonEquityValue;
  const grandTotalReady = !hasNonEquity || pfMetrics != null;

  // Non-equity строки для таблицы «Состав портфеля» — из pfMetrics.positions
  // (бэк уже посчитал value/вес/цену по классу), не из live-тикающего
  // equity-пайплайна (bonds/funds/cash не обновляются раз в 5с, это ОК).
  const nonEquityRows = (pfMetrics?.positions || [])
    .filter((p) => p.instrument_type !== "equity")
    .map((p) => ({
      id: p.id, ticker: p.ticker, name: p.name, company_id: null,
      instrument_type: p.instrument_type, secid: p.secid,
      isin: p.isin, issuer_ticker: p.issuer_ticker,
      shares: p.quantity ?? 0, avgPrice: p.avg_buy_price ?? 0, currentPrice: p.price ?? 0,
      priceAsOf: p.price_as_of ?? null,
      value: p.value ?? 0, weight: p.weight_pct ?? 0,
      profitRub: p.value != null && p.avg_buy_price != null ? p.value - (p.quantity ?? 0) * p.avg_buy_price : 0,
      profitPct: p.avg_buy_price ? ((p.price ?? p.avg_buy_price) / p.avg_buy_price - 1) * 100 : 0,
    }));

  const valueGate = useRef({ played: false });
  const scoreGate = useRef({ played: false });
  const appearGate = useRef(new Set());

  // Бета портфеля — из реальных риск-метрик (pfMetrics); 1 (рыночная) —
  // честный дефолт, только пока метрики ещё не загрузились/не посчитаны.
  const portfolioBeta = pfMetrics?.portfolio?.beta?.value ?? 1;

  const stressMap = {
    black_swan: {
      label: "Чёрный лебедь (−20%)",
      mech: "Резкая просадка всего рынка на 20% без конкретной причины",
      drop: portfolioBeta * 20,
      valueLoss: stats.totalValue * (portfolioBeta * 0.2),
      text: "При равномерном рыночном шоке разбивка по бумагам близка к их бете — более рискованные бумаги проседают пропорционально сильнее.",
    },
    rate_up: {
      label: "Ставка ЦБ +5%",
      mech: "Ключевая ставка резко растёт — давит на оценку акций и стоимость долга",
      drop: 11.8,
      valueLoss: stats.totalValue * 0.118,
      text: "Наиболее чувствителен банковский блок и бумаги с длинной дюрацией оценки. Резкий рост ставки одновременно бьёт по всему сектору с наибольшим весом в портфеле — та же концентрация, что видна в Индексе качества.",
    },
    oil_crash: {
      label: "Крах нефти ($40)",
      mech: "Цена нефти падает до $40/барр — давление на экспортёров и бюджет",
      drop: 8.6,
      valueLoss: stats.totalValue * 0.086,
      text: "Главный канал — ухудшение переоценки сырьевого сектора и давление на внешний баланс; для портфелей без прямых нефтегазовых экспортёров эффект в основном вторичный, через общий рыночный настрой и курс рубля.",
    },
  };
  const currentStress = stressMap[stressScenario] || null;

  // «+ Свой сценарий» — реальный расчёт через /portfolios/{id}/stress-test
  // (бета × индексный шок + ставочный канал из macro.json, где покрыто).
  const [customStressRateBp, setCustomStressRateBp] = useState(200);
  const [customStressIndexPct, setCustomStressIndexPct] = useState(-10);
  const [customStressResult, setCustomStressResult] = useState(null);
  const [customStressLoading, setCustomStressLoading] = useState(false);
  const [customStressError, setCustomStressError] = useState(null);
  const refreshAiDiagnosis = async () => {
    if (!activePortfolioId) return;
    setAiDiagnosisLoading(true);
    setAiDiagnosisError(null);
    try {
      const r = await fetch(`${apiUrl}/api/portfolios/${activePortfolioId}/diagnosis/refresh`, {
        method: "POST", headers: authHeaders,
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setAiDiagnosisError(body.detail || "Не удалось сгенерировать диагноз");
        return;
      }
      setAiDiagnosis(await r.json());
    } catch {
      setAiDiagnosisError("Не удалось сгенерировать диагноз");
    } finally {
      setAiDiagnosisLoading(false);
    }
  };

  const runCustomStress = async () => {
    if (!activePortfolioId) return;
    setCustomStressLoading(true);
    setCustomStressError(null);
    try {
      const r = await fetch(
        `${apiUrl}/api/portfolios/${activePortfolioId}/stress-test?rate_shock_bp=${customStressRateBp}&index_shock_pct=${customStressIndexPct}`,
        { headers: authHeaders }
      );
      if (!r.ok) { setCustomStressError("Не удалось посчитать сценарий"); return; }
      setCustomStressResult(await r.json());
    } catch {
      setCustomStressError("Не удалось посчитать сценарий");
    } finally {
      setCustomStressLoading(false);
    }
  };

  // Разбивка по бумагам для готовых сценариев (не «Свой») — переиспользует
  // ТОТ ЖЕ бэкенд-расчёт (β×индексный шок + ставочный канал), что и «Свой
  // сценарий»: «Чёрный лебедь» = индексный шок −20%, «Ставка ЦБ +5%» =
  // ставочный шок +500 б.п. «Крах нефти» — своего канала (цена нефти) в
  // модели нет, разбивку для него честно не показываем (не выдумываем).
  const PRESET_STRESS_PARAMS = {
    black_swan: { rate_shock_bp: 0, index_shock_pct: -20 },
    rate_up: { rate_shock_bp: 500, index_shock_pct: 0 },
  };
  const [presetStressResults, setPresetStressResults] = useState({});
  useEffect(() => {
    const params = PRESET_STRESS_PARAMS[stressScenario];
    if (!params || !activePortfolioId || presetStressResults[stressScenario]) return;
    (async () => {
      try {
        const r = await fetch(
          `${apiUrl}/api/portfolios/${activePortfolioId}/stress-test?rate_shock_bp=${params.rate_shock_bp}&index_shock_pct=${params.index_shock_pct}`,
          { headers: authHeaders }
        );
        if (!r.ok) return;
        const data = await r.json();
        setPresetStressResults((prev) => ({ ...prev, [stressScenario]: data }));
      } catch { /* тихая деградация — просто нет разбивки для этого сценария */ }
    })();
  }, [stressScenario, activePortfolioId]);

  const metricByTicker = useMemo(() => {
    const map = {};
    (pfMetrics?.positions || []).forEach((p) => { map[p.ticker] = p; });
    return map;
  }, [pfMetrics]);
  const metricsCoverageNote = useMemo(() => {
    const w = pfMetrics?.portfolio;
    if (!w) return null;
    const parts = [];
    if (w.pe_current && w.pe_current.n < w.pe_current.m)
      parts.push(`P/E тек. рассчитан по ${w.pe_current.n} из ${w.pe_current.m} позиций`);
    if (w.pe_historical && w.pe_historical.n < w.pe_historical.m)
      parts.push(`P/E ист. — по ${w.pe_historical.n} из ${w.pe_historical.m}`);
    if (w.div_yield && w.div_yield.n < w.div_yield.m)
      parts.push(`дивдоходность — по ${w.div_yield.n} из ${w.div_yield.m}`);
    if (w.upside_to_fair_pct && w.upside_to_fair_pct.n < w.upside_to_fair_pct.m)
      parts.push(`апсайд к цели — по ${w.upside_to_fair_pct.n} из ${w.upside_to_fair_pct.m} (только акции с законченным анализом справедливой стоимости)`);
    return parts.length ? `Строка «Портфель» — средневзвешенное по долям; ${parts.join("; ")} (у остальных метрика не рассчитана).` : null;
  }, [pfMetrics]);

  const analyticRows = useMemo(() => ([
    ...displayPositions.map((p) => {
      const value = p.shares * p.currentPrice;
      const weight = stats.totalValue > 0 ? (value / stats.totalValue) * 100 : 0;
      const m = metricByTicker[p.ticker];
      return m ? {
        ...p, weight,
        pe: m.pe_current, peHist: m.pe_historical, divYield: m.div_yield,
        return3y: m.return_total_3y ?? m.return_3y,
        capm: m.capm_expected, alpha: m.alpha_3y,
        sortino: m.sortino_3y, sharpe: m.sharpe_3y,
        volatility: m.volatility, downsideVol: m.downside_vol, beta: m.beta,
        betaSource: m.beta_source, rSquared: m.r_squared,
        var95: m.var_95, earningsYield: m.earnings_yield,
        maxDrawdown: m.max_drawdown, riskContributionPct: m.risk_contribution_pct,
        shortHistory: m.short_history,
        periodLabel: fmtHistoryPeriod(m.history_years),
        // Хвостовой риск (VaR/CVaR 95%/99%, дневной + годовой) — переключатели
        // над таблицей «Риск» решают, какое из этих полей показывать в общей
        // колонке VaR/CVaR (см. makeRiskVarCvarColumns).
        var99: m.var_99, cvar95: m.cvar_95, cvar99: m.cvar_99,
        var95Annual: m.var_95_annual, cvar95Annual: m.cvar_95_annual,
        var99Annual: m.var_99_annual, cvar99Annual: m.cvar_99_annual,
        // Апсайд к справедливой цене Basis (только акции) — суждение, см.
        // METRIC_EXPLANATIONS.upside_to_fair_pct + VALUATION_FLAG_META.
        upsideToFair: m.upside_to_fair_pct ?? null,
        valuationFlag: m.valuation_flag ?? null,
        fairValueAsOf: m.fair_value_as_of ?? null,
      } : { ...p, weight, return3y: null, volatility: null, beta: p.beta ?? null };
    }),
    {
      ticker: "Портфель", _isTotal: true, weight: 100,
      return3y: pfMetrics?.portfolio?.return_total_3y?.value ?? null,
      capm: pfMetrics?.portfolio?.capm ?? null,
      alpha: pfMetrics?.portfolio?.alpha ?? null,
      sortino: pfMetrics?.portfolio?.sortino ?? null,
      sharpe: pfMetrics?.portfolio?.sharpe ?? null,
      periodLabel: null,
      volatility: pfMetrics?.portfolio?.volatility?.value ?? null,
      downsideVol: pfMetrics?.portfolio?.downside_vol ?? null,
      var95: pfMetrics?.portfolio?.var_95 ?? null,
      var99: pfMetrics?.portfolio?.var_99 ?? null,
      cvar95: pfMetrics?.portfolio?.cvar_95 ?? null,
      cvar99: pfMetrics?.portfolio?.cvar_99 ?? null,
      var95Annual: pfMetrics?.portfolio?.var_95_annual ?? null,
      cvar95Annual: pfMetrics?.portfolio?.cvar_95_annual ?? null,
      var99Annual: pfMetrics?.portfolio?.var_99_annual ?? null,
      cvar99Annual: pfMetrics?.portfolio?.cvar_99_annual ?? null,
      rSquared: pfMetrics?.portfolio?.r_squared ?? null,
      beta: pfMetrics?.portfolio?.beta?.value ?? null,
      pe: pfMetrics?.portfolio?.pe_current?.value ?? null,
      peHist: pfMetrics?.portfolio?.pe_historical?.value ?? null,
      divYield: pfMetrics?.portfolio?.div_yield?.value ?? null,
      earningsYield: pfMetrics?.portfolio?.earnings_yield ?? null,
      maxDrawdown: pfMetrics?.portfolio?.max_drawdown ?? null,
      riskContributionPct: 100,
      upsideToFair: pfMetrics?.portfolio?.upside_to_fair_pct?.value ?? null,
      upsideToFairCoverage: pfMetrics?.portfolio?.upside_to_fair_pct
        ? `по ${pfMetrics.portfolio.upside_to_fair_pct.n} из ${pfMetrics.portfolio.upside_to_fair_pct.m}`
        : null,
    },
  ]), [displayPositions, metricByTicker, pfMetrics]);

  const holdingRows = [
    ...displayPositions.map((p) => {
      const value = p.shares * p.currentPrice;
      const weight = grandTotalValue > 0 ? (value / grandTotalValue) * 100 : 0;
      const profitRub = p.shares * (p.currentPrice - p.avgPrice);
      const profitPct = p.avgPrice > 0 ? (p.currentPrice / p.avgPrice - 1) * 100 : 0;
      return { ...p, value, weight, profitRub, profitPct };
    }),
    ...nonEquityRows,
  ];

  const assetColumn = useMemo(() => makeAssetColumn(onOpenCompany), [onOpenCompany]);

  const explainCtx = {
    // CAPM/Шарп/Сортино/альфа теперь считаются от ОФЗ ~10 лет (реальный вход в
    // модель), а не от ОФЗ ~1 год — та ставка осталась только контекстом/для
    // облигаций (rates.risk_free_1y). Владелец 2026-07-23: методологический фикс.
    rf: pfMetrics?.rates?.risk_free_10y ?? null,
    period: pfMetrics?.benchmark?.period_years
      ? `${String(pfMetrics.benchmark.period_years).replace(".", ",")} г`
      : "период расчёта",
    peCurrent: pfMetrics?.portfolio?.pe_current?.value ?? null,
    volatility: pfMetrics?.portfolio?.volatility?.value ?? null,
    shortHistory: false,
  };

  // ---- Панель «Состав» (Обзор) ----
  const pfComposition = () => (
    <div className="pf-panel">
      <div className="pf-sec-head">
        <span className="pf-sec-eyebrow">Обзор</span>
        <h2 className="pf-sec-title">Состав портфеля</h2>
      </div>
      <AppearGroup gate={appearGate.current} groupId="pf-holdings" className="tw-flex tw-flex-col tw-gap-3">
        {/* Стоимость + быстрые показатели — разметка ДОСЛОВНО из прототипа (grid 1.15fr/1fr, медная полоса, clamp 38-62).
            Layout — класс .pf-hero-grid (portfolio-v2.css), НЕ инлайн: на телефоне складывается в 1 колонку, медная
            черта-разделитель уходит с левого края наверх (см. @media(≤640px) в файле). */}
        <div className="pf-card pf-hero-grid" style={{ padding: "32px 36px" }}>
          <div>
            <div style={{ fontSize: "12.5px", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--pf-ink-3)", marginBottom: "10px" }}>Стоимость портфеля</div>
            <div style={{ fontFamily: "var(--pf-serif)", fontVariantNumeric: "tabular-nums", fontSize: "clamp(38px,5.2vw,62px)", fontWeight: 600, lineHeight: 0.95, letterSpacing: "-0.01em" }}>
              {grandTotalReady
                ? <><HeadlineNum value={grandTotalValue} gate={valueGate.current} /><span style={{ fontSize: "0.4em", fontWeight: 500, color: "var(--pf-ink-3)" }}> ₽</span></>
                : <span aria-label="Считаем стоимость портфеля" style={{ color: "var(--pf-ink-3)", opacity: 0.5 }}>···</span>}
            </div>
            <div style={{ display: "flex", gap: "14px", alignItems: "center", marginTop: "14px", fontSize: "13.5px", flexWrap: "wrap" }}>
              <span style={{ color: stats.totalProfit >= 0 ? "var(--pf-up)" : "var(--pf-down)", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: "5px" }}>
                <span aria-hidden="true">{stats.totalProfit >= 0 ? "▲" : "▼"}</span> {formatMoney(Math.abs(stats.totalProfit), { decimals: 0 })} · {fmtPercent(stats.profitPct, { sign: true })}
              </span>
              <span style={{ color: "var(--pf-ink-3)" }}>за всё время владения, без учёта дивидендов</span>
            </div>
          </div>
          <div className="pf-hero-grid__right">
            <div style={{ display: "flex", gap: "28px", flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: "11.5px", fontWeight: 600, color: "var(--pf-ink-2)", marginBottom: "8px" }}>Див. доходность</div>
                <div style={{ fontFamily: "'IBM Plex Mono',ui-monospace,monospace", fontVariantNumeric: "tabular-nums", fontSize: "24px", fontWeight: 700 }}>{pfMetrics?.portfolio?.div_yield?.value != null ? fmtPercent(pfMetrics.portfolio.div_yield.value, { decimals: 1 }) : "—"}</div>
              </div>
              {pfMetrics?.quality?.overall != null && (
                <div style={{ cursor: "pointer" }} onClick={() => handleSectionChange("quality")}>
                  <div style={{ fontSize: "11.5px", fontWeight: 600, color: "var(--pf-ink-2)", marginBottom: "8px" }}>Индекс качества</div>
                  <div style={{ fontFamily: "'IBM Plex Mono',ui-monospace,monospace", fontVariantNumeric: "tabular-nums", fontSize: "24px", fontWeight: 700, color: "var(--pf-copper)" }}>{pfMetrics.quality.overall}<span style={{ fontSize: "14px", color: "var(--pf-ink-3)" }}>/100</span></div>
                </div>
              )}
            </div>
            {pfMetrics?.quality?.overall != null && (
              <p style={{ fontSize: "12.5px", color: "var(--pf-ink-3)", marginTop: "14px", lineHeight: 1.6 }}>
                {pfMetrics.quality.label} — сильнее всего тянет вниз <b style={{ color: "var(--pf-ink-2)" }}>{[...pfMetrics.quality.subindices].sort((a, b) => a.score - b.score)[0]?.label}</b>. Разбор по компонентам → <b style={{ color: "var(--pf-copper-deep)", cursor: "pointer" }} onClick={() => handleSectionChange("quality")}>Индекс качества</b>.
              </p>
            )}
          </div>
        </div>

        {/* Позиции — разметка ДОСЛОВНО из прототипа (.pos-table / .pos-asset / .pos-logo / .pos-name),
            переключатель портфеля живёт в топ-баре — здесь только сами позиции */}
        <div className="pf-card" style={{ padding: "24px 26px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h3 style={{ fontFamily: "var(--pf-serif)", fontSize: "19px", fontWeight: 600, color: "var(--pf-ink)", margin: 0 }}>Состав портфеля</h3>
            <div
              className="pf-pill pf-pill--soft"
              role="button"
              tabIndex={0}
              onClick={() => (portfolio && token ? setShowAddModal(true) : onAuthRequired())}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); (portfolio && token ? setShowAddModal(true) : onAuthRequired()); } }}
            >
              + Добавить позицию
            </div>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="pf-pos-table">
              <thead>
                <tr>
                  <th>Актив</th><th>Кол-во</th><th>Средняя</th><th>Текущая</th>
                  <th>Стоимость</th><th>Доля</th><th>Результат</th><th></th>
                </tr>
              </thead>
              <tbody>
                {holdingRows.map((r) => (
                  <tr key={r.id ?? r.ticker} className="pf-pos-row" onClick={() => { if (r.id != null) setEditPosition(r); }}>
                    <td>
                      <div className="pf-pos-asset">
                        <div
                          className="pf-pos-logo"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (r.company_id != null && onOpenCompany) {
                              onOpenCompany({ id: r.company_id, ticker: r.ticker, name: r.name, sector: r.sector });
                            }
                          }}
                          title={`Открыть карточку ${r.ticker}`}
                        >
                          <HoldingLogo r={r} size={34} />
                        </div>
                        <div className="pf-pos-name">
                          <b>{r.name || r.ticker}</b>
                          <span>{r.ticker}</span>
                        </div>
                      </div>
                    </td>
                    <td>{fmtNumber(r.shares)}</td>
                    <td>{formatMoney(r.avgPrice, { decimals: 1 })}</td>
                    <td>
                      {formatMoney(r.currentPrice, { decimals: 1 })}
                      {r.instrument_type && r.instrument_type !== "equity" && r.priceAsOf && (() => {
                        const stale = _daysSince(r.priceAsOf) > 5;
                        return (
                          <div
                            style={{ fontSize: "10.5px", marginTop: "2px", color: stale ? "var(--warning)" : "var(--pf-ink-3)", fontWeight: stale ? 700 : 400 }}
                            title={stale ? "Цена не обновлялась дольше обычного T+1 лага для облигаций/фондов" : "Облигации/фонды обновляются раз в день (T+1), а не в реальном времени, как акции"}
                          >
                            на {_dmy(r.priceAsOf)}
                          </div>
                        );
                      })()}
                    </td>
                    <td>{formatMoney(r.value, { decimals: 0 })}</td>
                    <td>
                      <div className="pf-pos-weight">
                        <span>{fmtPercent(r.weight, { decimals: 1 })}</span>
                        <div className="pf-pos-weight-track">
                          <div className="pf-pos-weight-fill" style={{ width: `${Math.min(100, r.weight)}%` }} />
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="pf-pos-result">
                        <span style={{ color: r.profitRub >= 0 ? "var(--pf-up)" : "var(--pf-down)" }}>
                          <span aria-hidden="true">{r.profitRub >= 0 ? "▲" : "▼"}</span> {formatMoney(Math.abs(r.profitRub), { decimals: 0 })}
                        </span>
                        <span style={{ color: r.profitRub >= 0 ? "var(--pf-up)" : "var(--pf-down)" }}><Delta value={r.profitPct} /></span>
                      </div>
                    </td>
                    <td>
                      {r.id != null && (
                        <button
                          type="button"
                          className="pf-pos-edit-btn"
                          aria-label={`Изменить позицию ${r.ticker}`}
                          title="Изменить позицию"
                          onClick={(e) => { e.stopPropagation(); setEditPosition(r); }}
                        >
                          <Pencil size={14} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Секторы / классы активов — 2 карточки в ряд, донат+легенда, как в прототипе */}
        {pfMetrics && pfMetrics.sector_allocation.length > 0 && (
          <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-2 tw-gap-3">
            <div className="pf-card" style={{ padding: "22px 24px" }}>
              <h3 style={{ fontFamily: "var(--pf-serif)", fontSize: "16px", fontWeight: 600, color: "var(--pf-ink)", margin: "0 0 16px" }}>Распределение по секторам</h3>
              <div className="tw-flex tw-items-center tw-gap-6 tw-flex-wrap">
                <DonutChart
                  slices={pfMetrics.sector_allocation.map((s, i) => ({ pct: s.share_pct, color: PF_CAT_COLORS[i % PF_CAT_COLORS.length] }))}
                />
                <div className="tw-flex tw-flex-col tw-gap-2.5 tw-min-w-[180px] tw-flex-1">
                  {pfMetrics.sector_allocation.map((s, i) => (
                    <div key={s.sector} className="tw-flex tw-flex-col tw-gap-0.5">
                      <div className="tw-flex tw-items-center tw-gap-2 tw-text-[14px]">
                        <span className="tw-inline-block tw-w-2.5 tw-h-2.5 tw-rounded-pill tw-shrink-0" style={{ background: PF_CAT_COLORS[i % PF_CAT_COLORS.length] }} />
                        <span style={{ color: "var(--pf-ink)", fontWeight: 700 }}>{s.sector}</span>
                        <span className="tw-font-mono tw-tabular-nums" style={{ fontWeight: 700 }}>{fmtPercent(s.share_pct, { decimals: 1 })}</span>
                      </div>
                      <span className="tw-font-mono" style={{ fontSize: "12px", color: "var(--pf-ink-3)", marginLeft: "18px" }}>{formatMoney(s.value, { decimals: 0 })}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="pf-card" style={{ padding: "22px 24px" }}>
              <h3 style={{ fontFamily: "var(--pf-serif)", fontSize: "16px", fontWeight: 600, color: "var(--pf-ink)", margin: "0 0 16px" }}>Классы активов</h3>
              <div className="tw-flex tw-items-center tw-gap-6 tw-flex-wrap">
                <DonutChart
                  slices={pfMetrics.asset_classes.map((a, i) => ({ pct: a.share_pct, color: PF_CAT_COLORS[i % PF_CAT_COLORS.length] }))}
                />
                <div className="tw-flex tw-flex-col tw-gap-2.5 tw-min-w-[180px] tw-flex-1">
                  {pfMetrics.asset_classes.map((a, i) => (
                    <div key={a.name} className="tw-flex tw-items-center tw-gap-2 tw-text-[14px]">
                      <span className="tw-inline-block tw-w-2.5 tw-h-2.5 tw-rounded-pill tw-shrink-0" style={{ background: PF_CAT_COLORS[i % PF_CAT_COLORS.length] }} />
                      <span style={{ color: "var(--pf-ink)", fontWeight: 700 }}>{a.name}</span>
                      {/* 1 знак ВСЕГДА (не только у мелких долей) — иначе 99,8%
                          округляется в отображении до "100%" рядом с "0,2%"
                          у другого класса, и доли визуально не сходятся в 100%
                          (баг из жалобы владельца: "100% акции, 0,2% облигации"). */}
                      <span className="tw-font-mono tw-tabular-nums" style={{ fontWeight: 700 }}>{fmtPercent(a.share_pct, { decimals: 1 })}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Концентрация — отдельная полная строка, 3 колонки внутри (донат+легенда / статы / предупреждение).
            Цвет — ПО СЕКТОРУ позиции (та же карта, что у доната «Секторы»), не по индексу: SBER/T
            (сектор «Финансы») и YDEX (IT) читаются одинаково между обоими донатами. */}
        {pfMetrics?.concentration && (() => {
          const sectorColors = {};
          (pfMetrics.sector_allocation || []).forEach((s, i) => { sectorColors[s.sector] = PF_CAT_COLORS[i % PF_CAT_COLORS.length]; });
          // Внутри одного сектора — родственные, но РАЗЛИЧИМЫЕ тона (не одинаковый
          // цвет на 2+ позиции): 1-я позиция сектора — базовый тон, 2-я — темнее
          // (color-mix + чёрный), 3-я — светлее (+ белый), и т.д. Считается ОДИН
          // РАЗ в фиксированную карту (не при каждом вызове — иначе донат и
          // легенда разъедутся, т.к. обходят holdingRows дважды).
          const tickerColorMap = {};
          const sectorSeen = {};
          holdingRows.forEach((r) => {
            const sector = metricByTicker[r.ticker]?.sector;
            const base = sectorColors[sector] || PF_CAT_COLORS[0];
            const n = sectorSeen[sector] || 0;
            sectorSeen[sector] = n + 1;
            tickerColorMap[r.ticker] = n === 0 ? base
              : n % 2 === 1 ? `color-mix(in srgb, ${base} 65%, black)`
              : `color-mix(in srgb, ${base} 65%, white)`;
          });
          const colorForTicker = (ticker) => tickerColorMap[ticker] || PF_CAT_COLORS[0];
          return (
          <div className="pf-card" style={{ padding: "22px 24px" }}>
            <h3 style={{ fontFamily: "var(--pf-serif)", fontSize: "16px", fontWeight: 600, color: "var(--pf-ink)", margin: "0 0 16px" }}>Концентрация</h3>
            <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-[1.2fr_1fr_1.3fr] tw-gap-6 tw-items-center">
              <div className="tw-flex tw-items-center tw-gap-5">
                <DonutChart
                  size={140}
                  slices={holdingRows.map((r) => ({ pct: r.weight, color: colorForTicker(r.ticker) }))}
                />
                <div className="tw-flex tw-flex-col tw-gap-2">
                  {holdingRows.map((r) => (
                    <div key={r.ticker} className="tw-flex tw-items-center tw-gap-2 tw-text-[13px] tw-font-semibold">
                      <span className="tw-inline-block tw-w-2.5 tw-h-2.5 tw-rounded-pill tw-shrink-0" style={{ background: colorForTicker(r.ticker) }} />
                      <span className="tw-text-text-primary">{r.ticker}</span>
                      <span className="tw-font-mono tw-tabular-nums">{fmtPercent(r.weight, { decimals: 1 })}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="tw-flex tw-flex-col tw-gap-3 tw-items-start">
                <div className="pf-chip-stat">
                  <span className="pf-chip-stat__lbl">Крупнейшая позиция ({pfMetrics.concentration.largest_ticker})</span>
                  <span className={`pf-chip-stat__val ${pfMetrics.concentration.largest_pct >= 30 ? "tw-text-[var(--pf-down)]" : "tw-text-text-primary"}`}>{fmtPercent(pfMetrics.concentration.largest_pct, { decimals: 1 })}</span>
                </div>
                <div className="pf-chip-stat">
                  <span className="pf-chip-stat__lbl">Топ-3 позиции</span>
                  <span className={`pf-chip-stat__val ${pfMetrics.concentration.top3_pct >= 60 ? "tw-text-[var(--pf-down)]" : "tw-text-text-primary"}`}>{fmtPercent(pfMetrics.concentration.top3_pct, { decimals: 1 })}</span>
                </div>
              </div>
              <KeyTakeaway tone={pfMetrics.concentration.largest_pct >= 30 ? "caution" : "neutral"}>
                {pfMetrics.concentration.top3_pct >= 99.5
                  ? `Высокая концентрация: одна позиция держит ${fmtPercent(pfMetrics.concentration.largest_pct, { decimals: 0 })} портфеля, три позиции — весь портфель целиком.`
                  : `Крупнейшая позиция (${pfMetrics.concentration.largest_ticker}) держит ${fmtPercent(pfMetrics.concentration.largest_pct, { decimals: 0 })} портфеля; топ-3 — ${fmtPercent(pfMetrics.concentration.top3_pct, { decimals: 0 })}.`}
              </KeyTakeaway>
            </div>
          </div>
          );
        })()}

        {/* Ближайшие выплаты — /api/portfolios/{id}/dividends. Три сегмента по
            датам (без persisted-статуса, derived от отсечки): upcoming (до
            отсечки, факт объявленного) / pending (отсечка прошла — оценка окна
            зачисления, Basis не брокер и не видит реальных зачислений) /
            history (окно прошло — плитка ниже). */}
        <div className="pf-card" style={{ padding: "24px 26px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h3 style={{ fontFamily: "var(--pf-serif)", fontSize: "18px", fontWeight: 600, color: "var(--pf-ink)", margin: 0 }}>Ближайшие выплаты</h3>
            <span className="pf-tag-fact">факт (объявленные)</span>
          </div>
          {pfDividends === null ? (
            <div style={{ fontSize: "13px", color: "var(--pf-ink-3)" }}>Загрузка…</div>
          ) : pfDividends.upcoming.length === 0 && pfDividends.pending.length === 0 ? (
            <p style={{ fontSize: "13px", color: "var(--pf-ink-2)", margin: 0 }}>
              Нет объявленных выплат по бумагам портфеля на ближайшие полгода — это факт календаря
              (либо эмитенты не платят за этот период, либо ещё не объявили), а не пропуск данных.
            </p>
          ) : (
            <>
              {pfDividends.upcoming.length > 0 && (() => {
                const divRows = pfDividends.upcoming.map((e) => ({
                  key: `${e.position_id}-${e.record_date}`,
                  asset: <span><b>{e.name}</b> <span className="tw-font-mono tw-text-text-tertiary">{e.ticker}</span></span>,
                  buyBy: _dmy(e.buy_by_date),
                  record: _dmy(e.record_date),
                  amount: `${fmtNumber(e.amount, { decimals: 2 })} ₽`,
                  expected: <span className="tw-text-[var(--pf-up)]">+{formatMoney(e.total, { decimals: 0 })}</span>,
                  yieldPct: e.dividend_yield != null ? fmtPercent(e.dividend_yield, { decimals: 1 }) : "—",
                }));
                const totalExpected = pfDividends.upcoming.reduce((sum, e) => sum + e.total, 0);
                return (
                  <>
                    <PfMetricTable
                      columns={[
                        { key: "asset", label: "Актив" },
                        { key: "buyBy", label: "Купить до" },
                        { key: "record", label: "Отсечка" },
                        { key: "amount", label: "Див./акция" },
                        { key: "expected", label: "Ожидаемая сумма" },
                        { key: "yieldPct", label: "Доходность" },
                      ]}
                      rows={divRows}
                    />
                    <p style={{ fontSize: "13px", color: "var(--pf-ink)", marginTop: "12px", fontWeight: 700 }}>
                      Итого ожидается: <span className="tw-font-mono" style={{ color: "var(--pf-up)" }}>+{formatMoney(totalExpected, { decimals: 0 })}</span>
                    </p>
                  </>
                );
              })()}

              {pfDividends.pending.length > 0 && (() => {
                const pendingRows = pfDividends.pending.map((e) => ({
                  key: `${e.position_id}-${e.record_date}`,
                  asset: <span><b>{e.name}</b> <span className="tw-font-mono tw-text-text-tertiary">{e.ticker}</span></span>,
                  record: _dmy(e.record_date),
                  amount: `${fmtNumber(e.amount, { decimals: 2 })} ₽`,
                  expected: <span className="tw-text-[var(--pf-up)]">+{formatMoney(e.total, { decimals: 0 })}</span>,
                  until: _dmy(e.estimated_payment_by),
                }));
                return (
                  <div style={{ marginTop: pfDividends.upcoming.length > 0 ? "20px" : 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px" }}>
                      <span style={{ fontSize: "13.5px", fontWeight: 700, color: "var(--pf-ink)" }}>Ожидается зачисление</span>
                      <span className="pf-tag-estimate">оценка</span>
                    </div>
                    <PfMetricTable
                      columns={[
                        { key: "asset", label: "Актив" },
                        { key: "record", label: "Отсечка прошла" },
                        { key: "amount", label: "Див./акция" },
                        { key: "expected", label: "Ожидаемая сумма" },
                        { key: "until", label: "Обычно зачисляют до" },
                      ]}
                      rows={pendingRows}
                    />
                    <p style={{ fontSize: "11.5px", color: "var(--pf-ink-3)", marginTop: "8px" }}>
                      Отсечка уже прошла — по обычным срокам депозитарной цепочки деньги приходят в течение
                      {" "}{pfDividends.pending_window_days} дней. Это модельная оценка окна, не подтверждение
                      зачисления: Basis не брокер и не видит движений по вашему счёту.
                    </p>
                  </div>
                );
              })()}

              <p style={{ fontSize: "11.5px", color: "var(--pf-ink-3)", marginTop: "12px" }}>
                Показаны только объявленные выплаты (с известной датой и суммой) — для необъявленных будущих
                выплат подтверждённых данных пока не существует, это ограничение источника, а не недоработка расчёта.
              </p>
            </>
          )}
        </div>

        {/* История выплат — отсечки старше окна зачисления, из того же
            /dividends. Свёрнуто по умолчанию, чтобы не захламлять «Состав». */}
        {pfDividends?.history?.length > 0 && (
          <div className="pf-card" style={{ padding: "24px 26px" }}>
            <Disclosure summary={`История выплат (${pfDividends.history.length})`}>
              <PfMetricTable
                columns={[
                  { key: "asset", label: "Актив" },
                  { key: "record", label: "Отсечка" },
                  { key: "amount", label: "Див./акция" },
                  { key: "total", label: "Получено" },
                ]}
                rows={pfDividends.history.map((e) => ({
                  key: `${e.position_id}-${e.record_date}`,
                  asset: <span><b>{e.name}</b> <span className="tw-font-mono tw-text-text-tertiary">{e.ticker}</span></span>,
                  record: _dmy(e.record_date),
                  amount: `${fmtNumber(e.amount, { decimals: 2 })} ₽`,
                  total: <span className="tw-text-[var(--pf-up)]">+{formatMoney(e.total, { decimals: 0 })}</span>,
                }))}
              />
            </Disclosure>
          </div>
        )}
      </AppearGroup>
    </div>
  );

  // ---- Панель «Сравнение» ----
  const pfCompare = () => {
    const bm = activeBenchmark;
    const periodLabelText = PERIOD_LABEL_TEXT[bm?.period] || PERIOD_LABEL_TEXT[comparePeriod] || "выбранный период";
    // Разложение «секторы vs бумаги» — самая ценная идея этого блока (владелец
    // 2026-07-23): разница «Портфель vs Индекс» против «Смешанный vs Индекс»
    // отделяет эффект выбора СЕКТОРОВ (allocation) от выбора БУМАГ (selection).
    const selectionVsIndex = bm?.portfolio_total_pct != null && bm?.benchmark_total_pct != null
      ? bm.portfolio_total_pct - bm.benchmark_total_pct : null;                                  // X
    const allocationEffect = bm?.sector_blend_total_pct != null && bm?.benchmark_total_pct != null
      ? bm.sector_blend_total_pct - bm.benchmark_total_pct : null;                                // Y
    const pureSelectionEffect = bm?.portfolio_total_pct != null && bm?.sector_blend_total_pct != null
      ? bm.portfolio_total_pct - bm.sector_blend_total_pct : null;                                 // X − Y
    return (
      <div className="pf-panel">
        <div className="pf-sec-head">
          <span className="pf-sec-eyebrow">Доходность и риск</span>
          <h2 className="pf-sec-title">Сравнение</h2>
        </div>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mb-5 tw-max-w-2xl">
          Как портфель вёл себя на фоне рынка — и любых ориентиров, которые вы захотите сравнить:
          другая бумага, другой ваш портфель или отраслевой индекс.
        </p>
        <AppearGroup gate={appearGate.current} groupId="pf-compare" className="tw-flex tw-flex-col tw-gap-3">
          <div className="pf-card" style={{ padding: "16px 26px" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--pf-ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "10px" }}>
              Период
            </div>
            <div className="pf-seg" role="group" aria-label="Период сравнения">
              {PERIOD_BUTTONS.map((p) => (
                <button
                  key={p.id} type="button" onClick={() => setComparePeriod(p.id)}
                  className={`pf-seg-opt${comparePeriod === p.id ? " pf-seg-opt--on" : ""}`}
                  aria-pressed={comparePeriod === p.id}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {benchmarkLoading ? (
            <div className="pf-card" style={{ padding: "24px 26px" }}>
              <div style={{ fontSize: "13px", color: "var(--pf-ink-3)" }}>Пересчитываем график под новый период…</div>
            </div>
          ) : bm?.dates?.length > 1 ? (
            <div className="pf-card" style={{ padding: "24px 26px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "10px", marginBottom: "6px" }}>
                <h3 style={{ fontFamily: "var(--pf-serif)", fontSize: "18px", fontWeight: 600, color: "var(--pf-ink)", margin: 0 }}>
                  Портфель против рынка — {periodLabelText}
                </h3>
                <div style={{ display: "flex", gap: "16px", fontSize: "13px" }}>
                  <span>Портфель: <b className="tw-font-mono" style={{ color: bm.portfolio_total_pct >= 0 ? "var(--pf-up)" : "var(--pf-down)" }}>{fmtPercent(bm.portfolio_total_pct, { sign: true })}</b></span>
                  <span>Индекс МосБиржи: <b className="tw-font-mono" style={{ color: bm.benchmark_total_pct >= 0 ? "var(--pf-up)" : "var(--pf-down)" }}>{fmtPercent(bm.benchmark_total_pct, { sign: true })}</b></span>
                  <span>Разница: <b className="tw-font-mono" style={{ color: (bm.portfolio_total_pct - bm.benchmark_total_pct) >= 0 ? "var(--pf-up)" : "var(--pf-down)" }}>{fmtPercent(bm.portfolio_total_pct - bm.benchmark_total_pct, { sign: true })}</b></span>
                </div>
              </div>
              <BenchmarkChart series={bm} extraSeries={compareLines.map((l) => ({ ...l, onRemove: () => removeCompareLine(l.key) }))} />
              <p style={{ fontSize: "12px", color: "var(--pf-ink-3)", marginTop: "8px", maxWidth: "64ch" }}>
                Сравниваем с индексом МосБиржи полной доходности — это то же самое, что «вложить в рынок целиком, с реинвестированием
                дивидендов». Второй, тонкий — тот же индекс, но БЕЗ дивидендов, для справки: разница между линиями — это и есть вклад дивидендов.
                {bm.limited_by && ` Период ограничен историей ${bm.limited_by}.`}
                {bm.note && ` ${bm.note}.`}
              </p>

              {bm.sector_blend && (
                <div style={{ marginTop: "18px" }}>
                  <h4 style={{ fontFamily: "var(--pf-serif)", fontSize: "15px", fontWeight: 600, color: "var(--pf-ink)", margin: "0 0 8px", display: "flex", alignItems: "center", gap: "8px" }}>
                    Что сделало результат: секторы или бумаги?
                    <span className="pf-tag-estimate">оценка</span>
                  </h4>
                  <p style={{ fontSize: "13px", color: "var(--pf-ink-2)", lineHeight: 1.6, margin: "0 0 10px", maxWidth: "68ch" }}>
                    «Ваши секторы» на графике — гипотетический бенчмарк: рынок в тех же пропорциях по секторам, что и ваш реальный
                    портфель, но без выбора конкретных бумаг внутри них. Разница между «Портфель vs Индекс МосБиржи» и «Портфель vs
                    Ваши секторы» разделяет ДВА разных источника результата: удачный/неудачный выбор САМИХ СЕКТОРОВ и удачный/
                    неудачный выбор БУМАГ внутри них.
                  </p>
                  {selectionVsIndex != null && allocationEffect != null && pureSelectionEffect != null && (
                    <KeyTakeaway tone="info" title="Разложение результата">
                      Портфель {selectionVsIndex >= 0 ? "обогнал" : "отстал от"} индекс МосБиржи на {fmtPercent(Math.abs(selectionVsIndex))}.
                      Из них ваши секторы сами по себе {allocationEffect >= 0 ? "обогнали" : "отстали от"} индекс на {fmtPercent(Math.abs(allocationEffect))}
                      {" "}— это вклад <b>выбора секторов</b>. Оставшиеся {fmtPercent(Math.abs(pureSelectionEffect))} — вклад <b>выбора конкретных бумаг</b> внутри секторов.
                    </KeyTakeaway>
                  )}
                  <p style={{ fontSize: "11.5px", color: "var(--pf-ink-3)", marginTop: "10px", maxWidth: "68ch" }}>
                    Индекс покрывает {fmtPercent(bm.sector_blend_coverage_pct, { decimals: 0 })} стоимости акций портфеля
                    {bm.sector_blend_covered_sectors?.length > 0 && <> ({bm.sector_blend_covered_sectors.join(", ")})</>}.
                    {bm.sector_blend_excluded_sectors?.length > 0 && (
                      <> Не учтены (нет отраслевого индекса или недостаточно данных): {bm.sector_blend_excluded_sectors.join(", ")}.</>
                    )}
                  </p>
                </div>
              )}

              <div style={{ marginTop: "16px", paddingTop: "16px", borderTop: "1px solid var(--pf-line)" }}>
                <Button variant="secondary" onClick={() => setCompareBuilderOpen((v) => !v)}>
                  {compareBuilderOpen ? "− Свернуть сравнение" : "+ Добавить сравнение"}
                </Button>

                {compareBuilderOpen && (
                  <div className="tw-mt-4">
                    <div className="pf-seg tw-mb-4">
                      {[
                        { id: "asset", label: "Актив" },
                        { id: "portfolio", label: "Другой портфель" },
                        { id: "custom", label: "Свой конструктор" },
                      ].map((m) => (
                        <button
                          key={m.id} type="button" onClick={() => setCompareMode(m.id)}
                          className={`pf-seg-opt${compareMode === m.id ? " pf-seg-opt--on" : ""}`}
                        >
                          {m.label}
                        </button>
                      ))}
                    </div>

                    {compareMode === "asset" && (
                      <div className="tw-flex tw-flex-col tw-gap-3">
                        <div className="tw-flex tw-items-end tw-gap-2 tw-flex-wrap">
                          <div className="tw-flex tw-flex-col tw-gap-1" style={{ width: 220 }}>
                            <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary">Тикер или название (любая бумага рынка)</label>
                            <TickerInput value={compareTickerInput} onChange={setCompareTickerInput} placeholder="напр. LKOH или Лукойл" />
                          </div>
                          <Button variant="secondary" onClick={() => addCompareAsset(compareTickerInput)}>+ Добавить</Button>
                        </div>
                        <div>
                          <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary tw-block tw-mb-1.5">
                            Или быстро — отраслевой индекс МосБиржи полной доходности
                          </label>
                          <div className="pf-filterbar">
                            {SECTOR_TR_PRESETS.map((s) => {
                              const active = compareLines.some((l) => l.key === `asset:${s.ticker}`);
                              return (
                                <button
                                  key={s.ticker}
                                  type="button"
                                  className={`pf-chip${active ? " pf-chip--active" : ""}`}
                                  onClick={() => addSectorPreset(s.sector, s.ticker)}
                                  disabled={active}
                                  aria-pressed={active}
                                  title={active ? `${s.sector} уже добавлен` : `Добавить индекс сектора «${s.sector}»`}
                                >
                                  {s.sector}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    )}

                    {compareMode === "portfolio" && (
                      portfolioList.length > 1 ? (
                        <div className="tw-flex tw-items-end tw-gap-2 tw-flex-wrap">
                          <div className="tw-flex tw-flex-col tw-gap-1">
                            <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary">Другой ваш портфель</label>
                            <select
                              value={comparePortfolioId}
                              onChange={(e) => setComparePortfolioId(e.target.value)}
                              className="tw-text-[13px] tw-px-3 tw-py-2 tw-border tw-border-border-strong tw-rounded-md tw-bg-bg-elevated"
                            >
                              <option value="">Выбрать…</option>
                              {portfolioList.filter((p) => p.id !== activePortfolioId).map((p) => (
                                <option key={p.id} value={p.id}>{p.name}</option>
                              ))}
                            </select>
                          </div>
                          <Button variant="secondary" onClick={() => comparePortfolioId && addComparePortfolio(comparePortfolioId)}>+ Добавить портфель</Button>
                        </div>
                      ) : (
                        <p className="tw-text-[12.5px] tw-text-text-tertiary tw-m-0">У вас пока только один портфель — сравнивать не с чем.</p>
                      )
                    )}

                    {compareMode === "custom" && (
                      <div className="tw-flex tw-flex-col tw-gap-3">
                        <div className="pf-seg" style={{ width: "fit-content" }}>
                          {[{ id: "basket", label: "Взвешенная корзина" }, { id: "ratio", label: "Отношение А ÷ Б" }].map((m) => (
                            <button
                              key={m.id} type="button" onClick={() => setCustomMode(m.id)}
                              className={`pf-seg-opt${customMode === m.id ? " pf-seg-opt--on" : ""}`}
                            >
                              {m.label}
                            </button>
                          ))}
                        </div>

                        {customMode === "basket" ? (
                          <>
                            <p className="tw-text-[12.5px] tw-text-text-tertiary tw-m-0 tw-max-w-md">
                              Взвешенная корзина из нескольких бумаг — например, «60% нефть + 40% банки» — сравнивается
                              как единая линия на графике. Доходности бумаг взвешиваются по датам без ребалансировки —
                              это оценка формы, а не точный расчёт составного портфеля.
                            </p>
                            {customRows.map((row, idx) => (
                              <div key={idx} className="tw-flex tw-items-end tw-gap-2 tw-flex-wrap">
                                <div className="tw-flex tw-flex-col tw-gap-1" style={{ width: 200 }}>
                                  <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary">Бумага {idx + 1}</label>
                                  <TickerInput value={row.ticker} onChange={(v) => setCustomRow(idx, { ticker: v })} placeholder="напр. SBER" />
                                </div>
                                <div className="tw-flex tw-flex-col tw-gap-1" style={{ width: 90 }}>
                                  <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary">Вес, %</label>
                                  <input
                                    type="number" min="0" max="100" value={row.weight}
                                    onChange={(e) => setCustomRow(idx, { weight: e.target.value })}
                                    className="tw-font-mono tw-text-[13px] tw-px-3 tw-py-2 tw-border tw-border-border-strong tw-rounded-md tw-bg-bg-elevated"
                                  />
                                </div>
                                {customRows.length > 2 && (
                                  <button type="button" onClick={() => removeCustomRow(idx)} className="tw-bg-transparent tw-border-0 tw-cursor-pointer tw-text-text-tertiary hover:tw-text-danger tw-font-bold tw-pb-2" title="Убрать бумагу">×</button>
                                )}
                              </div>
                            ))}
                            <div className="tw-flex tw-items-center tw-gap-2">
                              <Button variant="ghost" onClick={addCustomRow}>+ Ещё бумага</Button>
                              <Button variant="secondary" onClick={addCustomConstructor}>+ Добавить в сравнение</Button>
                            </div>
                          </>
                        ) : (
                          <>
                            <p className="tw-text-[12.5px] tw-text-text-tertiary tw-m-0 tw-max-w-md">
                              Относительная сила одного актива к другому (напр. MCFTR ÷ LQDT — обгоняет ли рынок
                              акций денежный рынок). Можно вводить тикеры акций, фондов (SECID, напр. LQDT) или
                              индексы (MCFTR/IMOEX/RTSI) — не только бумаги из вашего портфеля.
                            </p>
                            <div className="tw-flex tw-items-end tw-gap-2 tw-flex-wrap">
                              <div className="tw-flex tw-flex-col tw-gap-1" style={{ width: 180 }}>
                                <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary">А</label>
                                <TickerInput value={ratioA} onChange={setRatioA} placeholder="напр. MCFTR" />
                              </div>
                              <span className="tw-text-text-tertiary tw-pb-2" style={{ fontSize: 16 }}>÷</span>
                              <div className="tw-flex tw-flex-col tw-gap-1" style={{ width: 180 }}>
                                <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary">Б</label>
                                <TickerInput value={ratioB} onChange={setRatioB} placeholder="напр. LQDT" />
                              </div>
                              <Button variant="secondary" onClick={addCustomConstructor}>+ Добавить в сравнение</Button>
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}
                {compareError && <p className="tw-text-[12px] tw-text-[var(--pf-down)] tw-mt-2">{compareError}</p>}
              </div>
            </div>
          ) : (
            <div className="pf-card" style={{ padding: "24px 26px" }}>
              <div style={{ fontSize: "13px", color: "var(--pf-ink-2)" }}>
                Сравнение с бенчмарком появится, когда в портфеле будет достаточно истории котировок.
              </div>
            </div>
          )}
        </AppearGroup>
      </div>
    );
  };

  // ---- Панель «Доходность и оценка» ----
  const pfReturns = () => (
    <div className="pf-panel">
      <div className="pf-sec-head">
        <span className="pf-sec-eyebrow">Доходность и риск</span>
        <h2 className="pf-sec-title">Доходность и оценка</h2>
      </div>
      <AppearGroup gate={appearGate.current} groupId="pf-returns" className="tw-flex tw-flex-col tw-gap-3">
        <div className="pf-card" style={{ padding: "24px 26px" }}>
          <PfMetricTable
            columns={[
              assetColumn,
              RETURN_COLUMNS[0],
              {
                key: "contribution", label: "Вклад в доходность",
                render: (_, row) => {
                  if (row?.weight == null || row?.return3y == null) return "—";
                  const contrib = row._isTotal ? row.return3y : (row.weight / 100) * row.return3y;
                  return (
                    <span style={{ color: contrib >= 0 ? "var(--pf-up)" : "var(--pf-down)" }}>
                      {row._isTotal ? "=" : contrib >= 0 ? "+" : ""}{fmtNumber(contrib, { decimals: 1 })} п.п.
                    </span>
                  );
                },
              },
              ...RETURN_COLUMNS.slice(1),
            ]}
            rows={analyticRows}
          />
          <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "4px", fontSize: "11.5px", color: "var(--pf-ink-3)" }}>
            {pfMetrics?.positions?.some((p) => p.short_history) && (
              <span>* рассчитано на истории менее года — значение неустойчиво; доходность короче года не приводится к годовой.</span>
            )}
            <span>«Вклад в доходность» = доля в портфеле × доходность бумаги — отвечает на вопрос «кто сделал результат портфеля».</span>
            {metricsCoverageNote && <span>{metricsCoverageNote}</span>}
          </div>
        </div>
        <h4 className="tw-text-[15px] tw-font-semibold tw-text-text-primary tw-m-0 tw-mt-2">Что значат эти метрики</h4>
        <MetricExplainers
          metricKeys={["return_total", "capm", "upside_to_fair_pct", "div_yield", "pe", "pe_hist", "earnings_yield"]}
          values={{
            return_total: pfMetrics?.portfolio?.return_total_3y?.value ?? null,
            capm: pfMetrics?.portfolio?.capm ?? null,
            upside_to_fair_pct: pfMetrics?.portfolio?.upside_to_fair_pct?.value ?? null,
            div_yield: pfMetrics?.portfolio?.div_yield?.value ?? null,
            pe: pfMetrics?.portfolio?.pe_current?.value ?? null,
            pe_hist: pfMetrics?.portfolio?.pe_historical?.value ?? null,
            earnings_yield: pfMetrics?.portfolio?.pe_current?.value > 0
              ? Math.round(1000 / pfMetrics.portfolio.pe_current.value) / 10 : null,
          }}
          ctx={explainCtx}
        />
      </AppearGroup>
    </div>
  );

  // ---- Панель «Риск» ----
  const pfRisk = () => {
    const varCvarCols = makeRiskVarCvarColumns(riskConfidence, riskHorizon);
    const horizonNounLabel = riskHorizon === "annual" ? "За год" : "В обычный день";
    const totalValue = pfMetrics?.portfolio?.total_value ?? grandTotalValue;
    const var95Annual = pfMetrics?.portfolio?.var_95_annual ?? null;
    const cvar99Annual = pfMetrics?.portfolio?.cvar_99_annual ?? null;
    return (
    <div className="pf-panel">
      <div className="pf-sec-head">
        <span className="pf-sec-eyebrow">Доходность и риск</span>
        <h2 className="pf-sec-title">Риск</h2>
      </div>
      <AppearGroup gate={appearGate.current} groupId="pf-risk" className="tw-flex tw-flex-col tw-gap-3">
        <div className="pf-card" style={{ padding: "16px 26px" }}>
          <div className="tw-flex tw-flex-wrap tw-gap-6">
            <div>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--pf-ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "8px" }}>
                Доверительный уровень
              </div>
              <div className="pf-seg" role="group" aria-label="Доверительный уровень VaR/CVaR">
                {[95, 99].map((c) => (
                  <button
                    key={c} type="button" onClick={() => setRiskConfidence(c)}
                    className={`pf-seg-opt${riskConfidence === c ? " pf-seg-opt--on" : ""}`}
                    aria-pressed={riskConfidence === c}
                  >
                    {c}%
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--pf-ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "8px" }}>
                Горизонт
              </div>
              <div className="pf-seg" role="group" aria-label="Горизонт VaR/CVaR">
                {[{ id: "daily", label: "Дневной" }, { id: "annual", label: "Годовой" }].map((h) => (
                  <button
                    key={h.id} type="button" onClick={() => setRiskHorizon(h.id)}
                    className={`pf-seg-opt${riskHorizon === h.id ? " pf-seg-opt--on" : ""}`}
                    aria-pressed={riskHorizon === h.id}
                  >
                    {h.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
        {totalValue > 0 && var95Annual != null && cvar99Annual != null && (
          <KeyTakeaway tone="caution" title="Что это значит в рублях">
            Ваш портфель — {formatMoney(totalValue, { decimals: 0 })}. В обычный плохой год (1 из 20) вы можете правдоподобно оказаться на уровне
            {" "}≈{formatMoney(totalValue * (1 - var95Annual / 100), { decimals: 0 })} (VaR 95% годовой). Если случится тот самый редкий провал
            {" "}(1 из 100) — глубина потерь в среднем внутри этого хвоста — ≈{formatMoney(totalValue * (1 - cvar99Annual / 100), { decimals: 0 })} (CVaR 99% годовой).
            Числа ориентировочные — основаны на истории котировок за 3 года, не на прогнозе.
          </KeyTakeaway>
        )}
        <div className="pf-card" style={{ padding: "24px 26px" }}>
          <PfMetricTable
            columns={[
              assetColumn, RISK_COLUMNS[0], ...varCvarCols,
              {
                key: "maxDrawdown", label: "Макс. просадка",
                render: (v) => v == null ? "—" : <span style={{ color: "var(--pf-down)" }} title="Самое глубокое падение от исторического максимума до последующего минимума">{fmtPercent(v)}</span>,
              },
              ...RISK_COLUMNS.slice(1),
              {
                key: "riskContributionPct", label: "Вклад в риск",
                render: (v) => v == null ? "—" : <span title="Доля бумаги в ОБЩЕЙ волатильности портфеля (не в стоимости!) — сумма даёт 100%">{fmtPercent(v, { decimals: 0 })}</span>,
              },
            ]}
            rows={analyticRows}
          />
          <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "6px", fontSize: "11.5px" }}>
            <span style={{ color: "var(--pf-ink-3)" }}>
              Окно риск-метрик — 3 года дневных данных, независимо от периода на вкладке «Сравнение». VaR/CVaR — {riskHorizon === "annual" ? "годовой (перекрывающиеся 252-дневные окна)" : "дневной"} горизонт, {riskConfidence}%. Beta: ᴹ — данные Мосбиржи, ᴮ — расчёт Basis.
            </span>
            {pfMetrics?.rates?.risk_free_10y != null && (
              <span style={{ color: "var(--pf-ink)" }}>
                <b>В модели (CAPM/Шарп/Сортино/альфа):</b> безрисковая ставка — ОФЗ ~10 лет {fmtPercent(pfMetrics.rates.risk_free_10y)} на {pfMetrics.rates.risk_free_as_of}; премия за риск рынка акций (ERP, по Дамодарану) — {fmtPercent(pfMetrics.rates.erp_pct)}.
              </span>
            )}
            {pfMetrics?.rates?.market_return_3y != null && (
              <span style={{ color: "var(--pf-ink-3)" }}>
                <b>Для контекста (не вход в модель):</b> рынок (MCFTR) фактически заработал за 3 года {fmtPercent(pfMetrics.rates.market_return_3y)} — это НЕ то же самое, что ERP выше: историческая доходность индекса — шумный ориентир, ERP — структурная оценка.
              </span>
            )}
          </div>
        </div>
        <KeyTakeaway tone="info" title="Почему многие риск-метрики сейчас выглядят слабо">
          {RISK_REGIME_NOTE}
        </KeyTakeaway>
        {(() => {
          const withData = analyticRows.filter((r) => !r._isTotal && r.weight != null && r.riskContributionPct != null);
          if (!withData.length) return null;
          const top = [...withData].sort((a, b) => b.weight - a.weight)[0];
          const gap = Math.abs(top.weight - top.riskContributionPct);
          if (gap < 3) return null;
          return (
            <KeyTakeaway tone="neutral" title="Скрытая деталь">
              {top.ticker} — {fmtPercent(top.weight, { decimals: 0 })} стоимости портфеля, но {fmtPercent(top.riskContributionPct, { decimals: 0 })} его риска:
              {top.weight > top.riskContributionPct ? " спокойнее, чем в среднем по портфелю" : " рискованнее, чем следует из её доли"}.
              Деньги и риск распределены не одинаково — это и есть разница между «долей» и «вкладом в риск».
            </KeyTakeaway>
          );
        })()}
        <h4 className="tw-text-[15px] tw-font-semibold tw-text-text-primary tw-m-0 tw-mt-2">Что значат эти метрики</h4>
        <MetricExplainers
          metricKeys={["volatility", "var_95", "var_99", "cvar_95", "cvar_99", "downside_vol", "beta", "r_squared", "sharpe", "alpha", "sortino"]}
          values={{
            volatility: pfMetrics?.portfolio?.volatility?.value ?? null,
            // Значения следуют переключателю «Горизонт» выше — иначе текст
            // объяснения сказал бы «за год», а число осталось бы дневным.
            var_95: (riskHorizon === "annual" ? pfMetrics?.portfolio?.var_95_annual : pfMetrics?.portfolio?.var_95) ?? null,
            var_99: (riskHorizon === "annual" ? pfMetrics?.portfolio?.var_99_annual : pfMetrics?.portfolio?.var_99) ?? null,
            cvar_95: (riskHorizon === "annual" ? pfMetrics?.portfolio?.cvar_95_annual : pfMetrics?.portfolio?.cvar_95) ?? null,
            cvar_99: (riskHorizon === "annual" ? pfMetrics?.portfolio?.cvar_99_annual : pfMetrics?.portfolio?.cvar_99) ?? null,
            downside_vol: pfMetrics?.portfolio?.downside_vol ?? null,
            beta: pfMetrics?.portfolio?.beta?.value ?? null,
            r_squared: pfMetrics?.portfolio?.r_squared ?? null,
            sharpe: pfMetrics?.portfolio?.sharpe ?? null,
            alpha: pfMetrics?.portfolio?.alpha ?? null,
            sortino: pfMetrics?.portfolio?.sortino ?? null,
          }}
          ctx={{ ...explainCtx, horizonLabel: horizonNounLabel }}
        />
      </AppearGroup>
    </div>
    );
  };

  // ---- Панель «Матрица корреляций» ----
  const pfCorrelation = () => {
    const corr = pfMetrics?.correlation;
    const labels = corr?.tickers?.length ? corr.tickers : ["SBER", "LKOH", "YDEX"];
    const matrix = corr?.tickers?.length ? corr.matrix : MOCK_CORRELATION;
    const offDiag = [];
    matrix.forEach((row, i) => row.forEach((v, j) => { if (i < j && typeof v === "number") offDiag.push(v); }));
    const avgCorr = offDiag.length ? offDiag.reduce((a, b) => a + b, 0) / offDiag.length : null;
    const divSub = pfMetrics?.quality?.subindices?.find((s) => s.key === "diversification");
    const verdict = avgCorr == null
      ? "Недостаточно данных для оценки связей между бумагами."
      : avgCorr >= 0.6
        ? `Средняя корреляция между бумагами высокая (${fmtNumber(avgCorr, { decimals: 2 })}): портфель склонен падать целиком — диверсификация слабая.`
        : avgCorr >= 0.3
          ? `Средняя корреляция умеренная (${fmtNumber(avgCorr, { decimals: 2 })}): бумаги частично движутся вместе — диверсификация есть, но связь с общим рынком заметна.`
          : `Средняя корреляция низкая (${fmtNumber(avgCorr, { decimals: 2 })}): бумаги движутся независимо — хорошая диверсификация.`;

    return (
      <div className="pf-panel">
        <div className="pf-sec-head">
          <span className="pf-sec-eyebrow">Доходность и риск</span>
          <h2 className="pf-sec-title">Матрица корреляций</h2>
        </div>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mb-6 tw-max-w-2xl">
          Как активы движутся относительно друг друга (1,0 = синхронно, 0 = независимо). Тёплые ячейки — высокая связь
          (концентрация), холодные — реальная диверсификация. Рассчитано по дневным доходностям за 3 года.
        </p>
        <AppearGroup gate={appearGate.current} groupId="pf-correlation" className="tw-flex tw-flex-col tw-gap-4">
          <div className="pf-card" style={{ padding: "24px 26px", marginBottom: "4px" }}>
            <CorrelationHeatmap labels={labels} matrix={matrix} />
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "14px", marginTop: "20px", flexWrap: "wrap" }}>
              <span className="tw-font-mono" style={{ fontSize: "12px", color: "var(--pf-ink-2)" }}>−1 · разбавляет риск</span>
              <span
                style={{ width: 220, height: 10, borderRadius: 5, background: "linear-gradient(90deg, var(--pf-up), var(--pf-surface-3) 50%, var(--pf-down))" }}
              />
              <span className="tw-font-mono" style={{ fontSize: "12px", color: "var(--pf-ink-2)" }}>+1 · риск не разбавляет</span>
            </div>
            <div style={{ textAlign: "center", marginTop: "8px" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "11.5px", color: "var(--pf-ink-3)" }}>
                <span style={{ display: "inline-block", width: 11, height: 11, background: "var(--pf-surface-3)", border: "1px dashed var(--pf-line-2)", borderRadius: 3 }} />
                диагональ — бумага сама с собой, не данные
              </span>
            </div>
          </div>

          <KeyTakeaway tone={avgCorr == null ? "neutral" : avgCorr >= 0.6 ? "caution" : avgCorr >= 0.3 ? "info" : "positive"} title="Что это значит для диверсификации">
            {verdict} Корреляции рассчитаны по дневным доходностям за 3 года.
            {corr?.low_overlap && " У части пар мало совпадающих торговых дат (молодые бумаги) — их значения менее надёжны."}
          </KeyTakeaway>

          {(corr?.strongest_pair || corr?.weakest_pair) && (
            <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 tw-gap-4">
              {corr?.strongest_pair && (
                <div className="pf-card" style={{ padding: "18px 20px" }}>
                  <div style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", color: "var(--pf-down)", marginBottom: "8px" }}>Где диверсификации нет</div>
                  <div className="tw-font-mono" style={{ fontSize: "20px", fontWeight: 700, marginBottom: "4px", color: "var(--pf-ink)" }}>
                    {corr.strongest_pair.a} ↔ {corr.strongest_pair.b} · {fmtNumber(corr.strongest_pair.value, { decimals: 2 })}
                  </div>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--pf-ink-2)" }}>Самая связанная пара — эти бумаги ходят почти заодно, друг друга не подстраховывают.</p>
                </div>
              )}
              {corr?.weakest_pair && (
                <div className="pf-card" style={{ padding: "18px 20px" }}>
                  <div style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", color: "var(--pf-up)", marginBottom: "8px" }}>Что реально разбавляет риск</div>
                  <div className="tw-font-mono" style={{ fontSize: "20px", fontWeight: 700, marginBottom: "4px", color: "var(--pf-ink)" }}>
                    {corr.weakest_pair.a} ↔ {corr.weakest_pair.b} · {fmtNumber(corr.weakest_pair.value, { decimals: 2 })}
                  </div>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--pf-ink-2)" }}>Наименее связанная пара — именно она снижает общий риск портфеля.</p>
                </div>
              )}
            </div>
          )}

          {divSub && (
            <div className="tw-text-[12.5px] tw-text-text-tertiary">
              Эта картина учтена в субиндексе <b className="tw-text-text-secondary">«Диверсификация»</b> (раздел «Индекс качества»): средняя корреляция — одна из его компонент, сейчас балл {divSub.score}/100.
            </div>
          )}
        </AppearGroup>
      </div>
    );
  };

  // ---- Панель «Индекс качества» ----
  const pfQuality = () => {
    const q = qualityVersion === "v2" ? pfMetrics?.quality_v2 : pfMetrics?.quality;
    const weightedFormula = q?.subindices
      ? q.subindices.map((s) => `${Math.round((q.weights[s.key] || 0) * 100)}% ${s.label}`).join(" + ")
      : null;
    return (
      <div className="pf-panel">
        <div className="pf-sec-head">
          <span className="pf-sec-eyebrow">Разбор</span>
          <h2 className="pf-sec-title">Индекс качества портфеля</h2>
        </div>
        <div className="pf-seg tw-mb-4" style={{ width: "fit-content" }}>
          {[{ id: "v2", label: "Методика v2.1" }, { id: "v1", label: "Методика v1" }].map((m) => (
            <button
              key={m.id} type="button" onClick={() => setQualityVersion(m.id)}
              className={`pf-seg-opt${qualityVersion === m.id ? " pf-seg-opt--on" : ""}`}
            >
              {m.label}
            </button>
          ))}
        </div>
        {qualityVersion === "v2" && (
          <p className="tw-text-[12.5px] tw-text-text-tertiary tw-mb-4 tw-max-w-2xl">
            Новая методика (docs/Basis_методика_индекса_качества_портфеля_v2.1.md) считает все 7 модулей.
            «Фундаментальное качество» пока частичное — только финансовая устойчивость и управление;
            бизнес-модель, рыночная позиция и capital allocation требуют нового аналитического
            субагента (см. пометку «Охват методики» ниже). Обе методики показаны рядом, пока v2.1 не
            откалибрована и не принята.
          </p>
        )}
        {!q || q.overall == null ? (
          <Card>
            <div className="tw-text-[13px] tw-text-text-secondary">
              {qualityVersion === "v2"
                ? "Индекс v2.1 пока применим только к портфелям с акциями (MVP-охват методики Фазы 1 — раздел 12): облигации/фонды/фьючерсы ещё не участвуют."
                : "Индекс качества появится, когда в портфеле будут позиции с историей котировок."}
            </div>
          </Card>
        ) : (
          <AppearGroup gate={appearGate.current} groupId={`pf-quality-${qualityVersion}`} className="tw-flex tw-flex-col tw-gap-4">
            <Card>
              <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-7 tw-mb-6">
                <div className="tw-flex tw-items-baseline tw-gap-1">
                  <span className="tw-font-display tw-font-light tw-text-accent tw-tabular-nums" style={{ fontSize: 56, lineHeight: 1, letterSpacing: "-1.5px" }}>
                    {q.overall}
                  </span>
                  <span className="tw-text-[20px] tw-text-text-tertiary">/100</span>
                </div>
                <p className="tw-text-[13.5px] tw-text-text-secondary tw-m-0 tw-max-w-md">
                  Общий балл — взвешенное среднее: {weightedFormula}.
                  Сильнее всего тянет вниз — <b className="tw-text-text-primary">«{[...q.subindices].sort((a, b) => a.score - b.score)[0]?.label}»</b> ({[...q.subindices].sort((a, b) => a.score - b.score)[0]?.score}/100).
                </p>
              </div>
              {/* Крупные полосы верхнего уровня — как в прототипе, сразу под баллом */}
              <div className="tw-flex tw-flex-col tw-gap-3">
                {q.subindices.map((s) => (
                  <div key={s.key} className="tw-grid tw-grid-cols-[160px_1fr_70px] tw-items-center tw-gap-4">
                    <div className="tw-text-[14px] tw-text-text-primary">{s.label}</div>
                    <div className="tw-h-3 tw-rounded-pill tw-bg-bg-base tw-overflow-hidden">
                      <div className="tw-h-full tw-rounded-pill" style={{ width: `${s.score}%`, background: `var(${QUALITY_BAR(s.score)})` }} />
                    </div>
                    <div className="tw-font-mono tw-text-[14px] tw-font-bold tw-text-right" style={{ color: `var(${QUALITY_BAR(s.score)})` }}>
                      {s.score}<span className="tw-text-[11px] tw-text-text-tertiary tw-font-normal">/100</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
            <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.06em" }}>
              Из чего сложился · субиндексы
            </div>
            <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-3 tw-gap-4 lg:tw-items-start">
              {q.subindices.map((s) => {
                const CONF_TONE = { "факт": "pf-tag-fact", "оценка": "pf-tag-estimate", "суждение": "pf-tag-judgment" };
                return (
                  <Card key={s.key}>
                    <div className="tw-flex tw-items-baseline tw-justify-between tw-gap-2 tw-flex-wrap tw-mb-1">
                      <span className="tw-text-[14px] tw-font-semibold tw-text-text-primary">{s.label}</span>
                      {s.confidence && <span className={CONF_TONE[s.confidence] || "pf-tag-fact"}>{s.confidence}</span>}
                    </div>
                    <div className="tw-font-mono tw-text-[26px] tw-font-bold tw-mb-2" style={{ color: `var(${QUALITY_BAR(s.score)})` }}>{s.score}</div>
                    <div className="tw-h-1.5 tw-rounded-pill tw-bg-bg-base tw-overflow-hidden tw-mb-3">
                      <div className="tw-h-full tw-rounded-pill" style={{ width: `${s.score}%`, background: `var(${QUALITY_BAR(s.score)})` }} />
                    </div>
                    <div className="tw-flex tw-flex-col tw-gap-1.5 tw-mb-2">
                      {s.components.map((c) => (
                        <div key={c.name}>
                          <div className="tw-flex tw-items-center tw-justify-between tw-text-[12px] tw-text-text-tertiary">
                            <span>{c.name}</span>
                            <span className="tw-text-text-secondary tw-font-mono">{c.value}</span>
                          </div>
                          {c.score != null && (
                            <div className="tw-h-1 tw-rounded-pill tw-bg-bg-base tw-overflow-hidden tw-mt-0.5">
                              <div className="tw-h-full tw-rounded-pill" style={{ width: `${c.score}%`, background: `var(${QUALITY_BAR(c.score)})` }} />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                    <p className="tw-m-0 tw-text-[12.5px] tw-text-text-secondary tw-leading-snug">{s.verdict}</p>
                    {s.limitation && (
                      <div className="tw-flex tw-gap-1.5 tw-text-[12px] tw-text-text-tertiary tw-mt-2">
                        <ShieldAlert size={13} className="tw-shrink-0 tw-mt-0.5 tw-text-warning" />
                        <span>{s.limitation}</span>
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
            {(() => {
              const weighted = q.subindices.map((s) => `${Math.round((q.weights[s.key] || 0) * 100)}% ${s.label}`).join(" + ");
              const lowest = [...q.subindices].sort((a, b) => a.score - b.score)[0];
              return (
                <div className="tw-text-[13px] tw-text-text-secondary tw-px-1">
                  Общий балл — взвешенное среднее: {weighted}.{" "}
                  {lowest && (
                    <>Сильнее всего тянет вниз — <b className="tw-text-text-primary">«{lowest.label}»</b> ({lowest.score}/100): с него стоит начать, если хотите улучшить портфель.</>
                  )}
                </div>
              );
            })()}
            <KeyTakeaway tone="neutral" title="Как читать индекс">{q.note}</KeyTakeaway>
            {qualityVersion === "v2" && q.phase_note && (
              <KeyTakeaway tone="caution" title="Охват методики">{q.phase_note}</KeyTakeaway>
            )}
          </AppearGroup>
        )}
      </div>
    );
  };

  // ---- Панель «ИИ-Диагноз» ----
  const EPISTEMIC_TAG_CLASS = { "факт": "pf-tag-fact", "оценка": "pf-tag-estimate", "модель": "pf-tag-model", "суждение": "pf-tag-judgment" };
  const pfAiDiagnosis = () => {
    const shield = aiDiagnosis?.shield || [];
    const vulnerabilities = aiDiagnosis?.vulnerabilities || [];
    return (
      <div className="pf-panel">
        <div className="pf-sec-head">
          <span className="pf-sec-eyebrow">Разбор</span>
          <h2 className="pf-sec-title">ИИ-Диагноз</h2>
        </div>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mb-4 tw-max-w-2xl">
          Не рекомендация «купить/продать» — синтез того, что уже видно в метриках, карточках компаний и новостном фоне.
        </p>
        <AppearGroup gate={appearGate.current} groupId="pf-ai" className="tw-flex tw-flex-col tw-gap-4">
          {/* Служебная строка: дата + кнопка. Сигнал (вердикт) идёт СРАЗУ под
              ней, без декоративных карточек-источников между заголовком и
              содержательным выводом (см. рекомендацию product-analyst —
              «сигнал прежде доказательства», источники методологии — вниз). */}
          <div className="tw-flex tw-items-center tw-justify-between tw-gap-3 tw-flex-wrap">
            <div className="tw-text-[12.5px] tw-text-text-tertiary">
              {aiDiagnosis?.generated_at
                ? `Диагноз от ${new Date(aiDiagnosis.generated_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}`
                : "Диагноз ещё не строился"}
            </div>
            <Button variant="secondary" onClick={refreshAiDiagnosis} disabled={aiDiagnosisLoading}>
              {aiDiagnosisLoading ? "Строю диагноз…" : aiDiagnosis ? "Обновить диагноз" : "Построить диагноз"}
            </Button>
          </div>
          {aiDiagnosisError && <p className="tw-text-[12.5px] tw-text-[var(--pf-down)] tw-m-0">{aiDiagnosisError}</p>}

          {!aiDiagnosis && !aiDiagnosisLoading && !aiDiagnosisError && (
            <Card>
              <p className="tw-text-[13px] tw-text-text-secondary tw-m-0">
                Диагноз ещё не строился — нажмите «Построить диагноз», чтобы синтезировать метрики портфеля,
                сигналы карточек компаний-держаний и рыночный контекст Обозревателя в итог, щит и уязвимости.
              </p>
            </Card>
          )}

          {/* Слой «сигнал» — главный вывод, крупнейший визуальный вес после
              заголовка страницы. Тег «суждение» специально не мельче тегов
              щита/уязвимостей ниже — это синтез LLM, не факт и не расчёт,
              несмотря на визуальный вес. */}
          {aiDiagnosis?.summary?.text && (
            <Card className="pf-ai-verdict">
              <div className="tw-flex tw-items-center tw-gap-2 tw-mb-2.5">
                <span className="tw-text-[13px] tw-font-bold tw-uppercase tw-tracking-wide tw-text-accent">Итог диагноза</span>
                <span className={EPISTEMIC_TAG_CLASS[aiDiagnosis.summary.type] || "pf-tag-judgment"}>{aiDiagnosis.summary.type || "суждение"}</span>
              </div>
              <p className="tw-text-[17px] tw-text-text-primary tw-leading-relaxed tw-m-0 tw-font-medium">
                {aiDiagnosis.summary.text}
              </p>
            </Card>
          )}

          {/* Слой «доказательство» — щит/уязвимости, сразу под вердиктом. */}
          {(shield.length > 0 || vulnerabilities.length > 0) && (
            <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-2 tw-gap-5">
              <div>
                <h3 className="tw-text-[16px] tw-font-semibold tw-text-[var(--pf-up)] tw-mb-3 tw-mt-0">Щит портфеля</h3>
                <div className="tw-flex tw-flex-col tw-gap-2.5">
                  {shield.map((p, i) => (
                    <Card key={i}>
                      <p className="tw-text-[13.5px] tw-text-text-primary tw-m-0 tw-mb-2">{p.text}</p>
                      <span className={EPISTEMIC_TAG_CLASS[p.type] || "pf-tag-fact"}>{p.type || "факт"}</span>
                    </Card>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="tw-text-[16px] tw-font-semibold tw-text-[var(--pf-down)] tw-mb-3 tw-mt-0">Уязвимости</h3>
                <div className="tw-flex tw-flex-col tw-gap-2.5">
                  {vulnerabilities.map((c, i) => (
                    <Card key={i}>
                      <p className="tw-text-[13.5px] tw-text-text-primary tw-m-0 tw-mb-2">{c.text}</p>
                      <span className={EPISTEMIC_TAG_CLASS[c.type] || "pf-tag-fact"}>{c.type || "факт"}</span>
                    </Card>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Углубление в один конкретный разрез риска — после общего вердикта,
              не перед ним (было наоборот). */}
          <Card>
            <div className="tw-flex tw-items-center tw-justify-between tw-gap-2 tw-mb-1">
              <div className="tw-text-[14px] tw-font-semibold tw-text-text-primary">Факторный профиль портфеля</div>
              <span className="pf-tag-judgment">суждение</span>
            </div>
            <p className="tw-text-[12.5px] tw-text-text-secondary tw-mb-4 tw-max-w-lg">
              Чувствительность к ставке ЦБ, взвешенная по чистой прибыли покрытых бумаг — из карточек компаний.
            </p>
            {factorProfile ? (
              <>
                <div className="tw-grid tw-grid-cols-[150px_1fr_70px] tw-items-center tw-gap-3 tw-py-2">
                  <div className="tw-text-[13px] tw-font-semibold tw-text-text-primary">Ключевая ставка ЦБ</div>
                  <ImpactBar value={factorProfile.rate_pct_per_100bp} max={10} />
                  <div className={`tw-font-mono tw-text-[12.5px] tw-font-bold tw-text-right ${factorProfile.rate_pct_per_100bp > 0 ? "tw-text-[var(--pf-up)]" : factorProfile.rate_pct_per_100bp < 0 ? "tw-text-[var(--pf-down)]" : "tw-text-text-secondary"}`}>
                    {fmtPercent(factorProfile.rate_pct_per_100bp, { sign: true })}
                  </div>
                </div>
                <p className="tw-text-[11.5px] tw-text-text-tertiary tw-mt-2 tw-mb-0">
                  Оценка изменения чистой прибыли на +100 б.п. ключевой ставки, средневзвешенно по доле бумаг в портфеле
                  (покрытие {fmtPercent(factorProfile.coverage_pct, { decimals: 0 })} стоимости портфеля: {factorProfile.covered_tickers.join(", ")}
                  {factorProfile.uncovered_tickers.length > 0 && `; без макро-профиля: ${factorProfile.uncovered_tickers.join(", ")}`}).
                  {" "}{factorProfile.note}
                </p>
              </>
            ) : (
              <p className="tw-text-[12.5px] tw-text-text-secondary tw-m-0">
                Ни одна бумага портфеля пока не покрыта макро-профилем чувствительности — раскатка по компаниям продолжается.
              </p>
            )}
          </Card>

          <Card>
            <div className="tw-font-semibold tw-text-[14px] tw-text-text-primary tw-mb-1">Проверить гипотезу: а если добавить бумагу?</div>
            <div className="tw-flex tw-items-center tw-justify-between tw-gap-3 tw-flex-wrap">
              <p className="tw-text-[12.5px] tw-text-text-secondary tw-m-0">
                Задать тикер и вес — увидеть, как изменятся Индекс качества, диверсификация и стресс-тест до фактической сделки.
              </p>
              <span className="pf-badge-soon">Скоро</span>
            </div>
          </Card>

          {/* Методологическая прозрачность — откуда данные для диагноза;
              важно для доверия, но это НЕ сигнал, поэтому внизу и компактно
              (одна строка-плашка, не три полноразмерные карточки). */}
          <div className="tw-flex tw-items-center tw-gap-4 tw-flex-wrap tw-text-[11.5px] tw-text-text-tertiary tw-pt-2" style={{ borderTop: "1px solid var(--pf-line)" }}>
            <span>Источники диагноза:</span>
            <span>📊 Метрики портфеля</span>
            <span>🏢 Карточки компаний-держаний</span>
            <span>📰 Новостной фон Обозревателя</span>
          </div>
        </AppearGroup>
      </div>
    );
  };

  // ---- Панель «Стресс-тест» ----
  const pfStress = () => (
    <div className="pf-panel">
      <div className="pf-sec-head">
        <span className="pf-sec-eyebrow">Разбор</span>
        <h2 className="pf-sec-title">Стресс-тест</h2>
      </div>
      <p className="tw-text-[13px] tw-text-text-secondary tw-mb-5 tw-max-w-2xl">
        Оценка по текущей структуре портфеля — гипотетический сценарий, не прогноз. Выберите сценарий, чтобы увидеть детали.
      </p>
      <AppearGroup gate={appearGate.current} groupId="pf-stress" className="tw-flex tw-flex-col tw-gap-4">
        <div className="pf-stress-grid">
          {Object.entries(stressMap).map(([id, s]) => (
            <button
              key={id}
              type="button"
              className={`pf-stress-card${stressScenario === id ? " pf-stress-card--on" : ""}`}
              onClick={() => setStressScenario(id)}
              aria-pressed={stressScenario === id}
            >
              <div className="pf-stress-name">{s.label}</div>
              <div className="pf-stress-mech">{s.mech}</div>
            </button>
          ))}
          <button
            type="button"
            className={`pf-stress-card pf-stress-card--custom${stressScenario === "custom" ? " pf-stress-card--on" : ""}`}
            onClick={() => setStressScenario("custom")}
            aria-pressed={stressScenario === "custom"}
          >
            <div className="pf-stress-name">+ Свой сценарий</div>
            <div className="pf-stress-mech">Задать собственные параметры шока</div>
          </button>
        </div>
        <p className="tw-text-[11.5px] tw-text-text-tertiary tw-m-0 tw-max-w-2xl">
          Готовые сценарии соответствуют факторам из «Факторного профиля портфеля» (вкладка «ИИ-Диагноз»); разбивка
          по бумагам ниже считается от беты и отраслевых коэффициентов, не от факторного профиля напрямую — прямая
          связь расчётов (профиль → просадка сценария) следующий шаг.
        </p>

        {stressScenario === "custom" ? (
          <Card>
            <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-3" style={{ letterSpacing: "0.06em" }}>Параметры своего сценария</div>
            <div className="tw-flex tw-gap-4 tw-flex-wrap tw-items-end tw-mb-4">
              <div className="tw-flex tw-flex-col tw-gap-1">
                <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary">Ключевая ставка, б.п.</label>
                <input type="number" value={customStressRateBp} onChange={(e) => setCustomStressRateBp(Number(e.target.value))}
                  className="tw-font-mono tw-text-[13px] tw-px-3 tw-py-2 tw-border tw-border-border-strong tw-rounded-md tw-bg-bg-elevated tw-w-24" />
              </div>
              <div className="tw-flex tw-flex-col tw-gap-1">
                <label className="tw-text-[11px] tw-font-semibold tw-text-text-tertiary">Индекс МосБиржи, %</label>
                <input type="number" value={customStressIndexPct} onChange={(e) => setCustomStressIndexPct(Number(e.target.value))}
                  className="tw-font-mono tw-text-[13px] tw-px-3 tw-py-2 tw-border tw-border-border-strong tw-rounded-md tw-bg-bg-elevated tw-w-24" />
              </div>
              <Button variant="primary" onClick={runCustomStress} disabled={customStressLoading}>
                {customStressLoading ? "Считаю…" : "Пересчитать"}
              </Button>
            </div>
            <p className="tw-text-[11.5px] tw-text-text-tertiary tw-mb-4">
              Курс USD/RUB в расчёт пока не входит — чувствительность к курсу ещё не приведена к общему знаменателю
              по всем секторам портфеля (см. факторный профиль в «ИИ-Диагнозе»).
            </p>
            {customStressError && <p className="tw-text-[12px] tw-text-[var(--pf-down)] tw-mb-3">{customStressError}</p>}
            {customStressResult && (
              <>
                <div className="tw-flex tw-gap-8 tw-flex-wrap tw-mb-4">
                  <div>
                    <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-1" style={{ letterSpacing: "0.06em" }}>Ожидаемое падение</div>
                    <div className="tw-text-[28px] tw-font-display tw-font-light tw-text-[var(--pf-down)] tw-tabular-nums">
                      <span aria-hidden="true">▼ </span>{fmtPercent(Math.abs(customStressResult.drop_pct), { decimals: 1 })}
                    </div>
                  </div>
                  <div>
                    <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-1" style={{ letterSpacing: "0.06em" }}>Потеря стоимости</div>
                    <div className="tw-text-[28px] tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums">
                      {formatMoney(Math.abs(customStressResult.value_loss), { decimals: 0 })}
                    </div>
                  </div>
                </div>
                <ImpactBar value={customStressResult.drop_pct} max={25} />
                <Table
                  columns={[
                    { key: "name", label: "Актив" },
                    { key: "beta", label: "Бета" },
                    { key: "drop_pct", label: "Просадка", render: (v) => <span className="tw-text-[var(--pf-down)]">{fmtPercent(v, { decimals: 1 })}</span> },
                    { key: "value_loss", label: "Потеря, ₽", render: (v) => <span className="tw-text-[var(--pf-down)]">{formatMoney(Math.abs(v), { decimals: 0 })}</span> },
                  ]}
                  rows={customStressResult.positions}
                />
              </>
            )}
          </Card>
        ) : (
          <Card>
            <div className="tw-flex tw-gap-8 tw-flex-wrap tw-mb-4">
              <div>
                <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-1" style={{ letterSpacing: "0.06em" }}>Ожидаемое падение</div>
                <div className="tw-text-[28px] tw-font-display tw-font-light tw-text-[var(--pf-down)] tw-tabular-nums">
                  <span aria-hidden="true">▼ </span>{fmtPercent(currentStress.drop, { decimals: 1 })}
                </div>
              </div>
              <div>
                <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-1" style={{ letterSpacing: "0.06em" }}>Потеря стоимости</div>
                <div className="tw-text-[28px] tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums">
                  {formatMoney(currentStress.valueLoss, { decimals: 0 })}
                </div>
              </div>
            </div>
            <ImpactBar value={-currentStress.drop} max={25} />
            {presetStressResults[stressScenario]?.positions ? (
              <>
                <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mt-5 tw-mb-2" style={{ letterSpacing: "0.06em" }}>Разбивка по бумагам</div>
                <Table
                  columns={[
                    { key: "name", label: "Актив" },
                    { key: "beta", label: "Бета" },
                    { key: "drop_pct", label: "Просадка", render: (v) => <span className="tw-text-[var(--pf-down)]">{fmtPercent(v, { decimals: 1 })}</span> },
                    { key: "value_loss", label: "Потеря, ₽", render: (v) => <span className="tw-text-[var(--pf-down)]">{formatMoney(Math.abs(v), { decimals: 0 })}</span> },
                  ]}
                  rows={presetStressResults[stressScenario].positions}
                />
              </>
            ) : stressScenario === "oil_crash" ? (
              <p className="tw-text-[11.5px] tw-text-text-tertiary tw-mt-4 tw-mb-0">
                Разбивка по бумагам для этого сценария не считается: канал «цена нефти» в модели пока не разложен на
                коэффициенты по компаниям (честная деградация, не выдумываем числа).
              </p>
            ) : null}
            <div className="tw-mt-4 tw-flex tw-gap-3 tw-rounded-md tw-p-4 tw-bg-[var(--pf-down-soft)]" style={{ borderLeft: "3px solid var(--danger)" }}>
              <p className="tw-text-[13px] tw-text-text-secondary tw-m-0">
                <span className="tw-font-semibold tw-text-[var(--pf-down)]">Интерпретация платформы: </span>
                {currentStress.text}
              </p>
            </div>
          </Card>
        )}
      </AppearGroup>
    </div>
  );

  const PF_RENDER = {
    composition: pfComposition,
    compare: pfCompare,
    returns: pfReturns,
    risk: pfRisk,
    correlation: pfCorrelation,
    quality: pfQuality,
    "ai-diagnosis": pfAiDiagnosis,
    stress: pfStress,
  };

  // ---- Empty states (без сайдбара — как раньше) ----
  if (!token) {
    return (
      <div>
        <div className="view-header">
          <h1 className="view-title">Аналитика портфеля</h1>
          <p className="view-subtitle">Управляйте позициями и отслеживайте результаты</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "80px 24px", textAlign: "center" }}>
          <div style={{ width: 72, height: 72, borderRadius: 20, background: "var(--accent-fade)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 20 }}>
            <Briefcase size={32} style={{ color: "var(--accent-text)" }} />
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-1)", margin: "0 0 8px" }}>Аналитика портфеля</h2>
          <p style={{ fontSize: 14, color: "var(--text-2)", margin: "0 0 28px", maxWidth: 340, lineHeight: 1.6 }}>
            Войдите в аккаунт, чтобы загружать портфели и отслеживать результаты
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn btn-primary" style={{ padding: "11px 24px" }} onClick={onAuthRequired}>Войти</button>
            <button className="btn btn-ghost" style={{ padding: "11px 24px" }} onClick={onAuthRequired}>Зарегистрироваться</button>
          </div>
        </div>
      </div>
    );
  }

  // Пока грузятся портфель и позиции — честный лоадер вместо рендера
  // экрана с пустыми/промежуточными числами (см. displayPositions выше).
  if (portfolioLoading) {
    return (
      <div className="tw-flex tw-items-center tw-justify-center tw-py-24 tw-text-text-tertiary tw-text-[18px] tw-animate-pulse">
        Загружаем портфель...
      </div>
    );
  }

  if (!portfolioLoading && portfolioList.length === 0) {
    return (
      <div>
        <div className="view-header">
          <h1 className="view-title">Аналитика портфеля</h1>
          <p className="view-subtitle">Управляйте позициями и отслеживайте результаты</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "80px 24px", textAlign: "center" }}>
          <div style={{ width: 72, height: 72, borderRadius: 20, background: "var(--accent-fade)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 20 }}>
            <Upload size={32} style={{ color: "var(--accent-text)" }} />
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-1)", margin: "0 0 8px" }}>Загрузите первый портфель</h2>
          <p style={{ fontSize: 14, color: "var(--text-2)", margin: "0 0 28px", maxWidth: 340, lineHeight: 1.6 }}>
            Добавьте свои позиции, чтобы начать отслеживать результаты
          </p>
          <button className="btn btn-primary" style={{ padding: "13px 32px", fontSize: 15 }} onClick={() => setShowUploadModal(true)}>
            <Upload size={16} /> Загрузить портфель
          </button>
        </div>
        {showUploadModal && (
          <PortfolioImportModal token={token} existingNames={portfolioList.map(p => p.name)} onClose={() => setShowUploadModal(false)} onSuccess={() => { setShowUploadModal(false); setReloadKey(k => k + 1); }} />
        )}
      </div>
    );
  }

  const activeZoneLabel = PF_ZONES.flatMap((z) => z.items).find((it) => it.id === activeSection)?.label;

  return (
    <div className="pf-shell" style={{ background: "var(--pf-tan)" }}>
      {/* ---- Мобильный (≤760px) выезжающий сайдбар — backdrop + drawer-класс на .pf-sidebar ---- */}
      {drawerOpen && <MobileDrawerBackdrop onClose={() => setDrawerOpen(false)} />}
      {/* ---- Dark sidebar ---- */}
      <nav
        className={`pf-sidebar msd-drawer${drawerOpen ? " msd-drawer--open" : ""}`}
        aria-label="Разделы аналитики портфеля"
        inert={drawerNarrow && !drawerOpen}
      >
        <div className="pf-depth-strip" aria-hidden="true" />
        <div className="pf-eyebrow">Аналитика портфеля</div>

        {PF_ZONES.map((zone) => (
          <div key={zone.id} className="pf-zone">
            <div className="pf-zone-label">{zone.label}</div>
            {zone.items.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                className={`pf-item${activeSection === id ? " pf-item--active" : ""}`}
                onClick={() => handleSectionChange(id)}
                aria-current={activeSection === id ? "page" : undefined}
              >
                <span className="pf-item__icon"><Icon size={15} aria-hidden="true" /></span>
                {label}
              </button>
            ))}
          </div>
        ))}

        <div className="pf-foot">Basis не брокер и не&nbsp;даёт рекомендаций «купить/продать».</div>
      </nav>

      {/* ---- Light main area ---- */}
      <main className="pf-main" style={{ background: "var(--pf-tan)" }}>
        <MobileSectionBar title={activeZoneLabel} open={drawerOpen} onOpenMenu={() => setDrawerOpen(true)} />
        <div className="pf-topbar">
          <div className="pf-topbar__hint">Полная картина по портфелю — состав, риск, сравнение и разбор</div>
          <div className="pf-topbar__actions">
            {portfolioList.map(p => (
              <div key={p.id} className="tw-flex tw-items-center tw-gap-1">
                <Chip
                  selected={activePortfolioId === p.id}
                  onClick={() => { setActivePortfolioId(p.id); setReloadKey(k => k + 1); }}
                >
                  {p.name}
                </Chip>
                <IconButton
                  size="sm"
                  aria-label="Удалить портфель"
                  onClick={() => setConfirmDeleteId(p.id)}
                >
                  <Trash2 size={13} />
                </IconButton>
              </div>
            ))}
            <Button variant="secondary" size="sm" iconLeft={<Plus size={14} />} onClick={() => token ? setShowUploadModal(true) : onAuthRequired()}>
              Добавить портфель
            </Button>
          </div>
        </div>

        {/* Keep-alive: посещённые разделы монтируются один раз, скрываются через display */}
        {[...visitedSections].map((sectionId) => (
          <div key={sectionId} style={{ display: activeSection === sectionId ? "block" : "none" }}>
            {(PF_RENDER[sectionId] || pfComposition)()}
          </div>
        ))}
      </main>

      {showUploadModal && (
        <PortfolioImportModal
          token={token}
          existingNames={portfolioList.map(p => p.name)}
          onClose={() => setShowUploadModal(false)}
          onSuccess={(newPortfolio) => {
            setPortfolio(newPortfolio);
            setShowUploadModal(false);
            window.location.reload();
          }}
        />
      )}

      {showAddModal && portfolio && (
        <AddPositionModal
          portfolioId={portfolio.id}
          existingPositions={rawPositions}
          token={token}
          onClose={() => setShowAddModal(false)}
          onSuccess={reloadPortfolio}
        />
      )}

      {editPosition && portfolio && (
        <EditPositionModal
          portfolioId={portfolio.id}
          position={editPosition}
          token={token}
          onClose={() => setEditPosition(null)}
          onSuccess={() => { setEditPosition(null); setReloadKey(k => k + 1); }}
        />
      )}

      {confirmDeleteId && (
        <div className="modal-backdrop">
          <div className="modal-box" style={{ maxWidth: 400 }}>
            <div style={{ padding: 28, textAlign: "center" }}>
              <div style={{ width: 52, height: 52, borderRadius: 14, background: "var(--neg-fade)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                <Trash2 size={24} style={{ color: "var(--negative)" }} />
              </div>
              <h3 style={{ margin: "0 0 8px", fontSize: 17, fontWeight: 700, color: "var(--text-1)" }}>
                Удалить портфель?
              </h3>
              <p style={{ margin: "0 0 24px", fontSize: 13, color: "var(--text-2)", lineHeight: 1.6 }}>
                Все позиции будут удалены безвозвратно.
              </p>
              <div style={{ display: "flex", gap: 10 }}>
                <button className="btn btn-ghost" style={{ flex: 1, justifyContent: "center" }} onClick={() => setConfirmDeleteId(null)}>
                  Отмена
                </button>
                <button
                  className="btn"
                  style={{ flex: 1, justifyContent: "center", background: "var(--negative)", color: "var(--on-accent)", border: "none" }}
                  onClick={() => handleDeletePortfolio(confirmDeleteId)}
                >
                  Удалить
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export { PortfolioV2 };
