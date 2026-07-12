import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Briefcase,
  Pencil,
  Plus,
  ShieldAlert,
  Trash2,
  TrendingDown,
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
import { CompanyLogo } from "../design/CompanyLogo";

// =========================
// PORTFOLIO MOCK DATA
// =========================

const MOCK_PORTFOLIO = [
  { ticker: "SBER", name: "Сбербанк", shares: 100, avgPrice: 280, currentPrice: 295, beta: 1.2, divYield: 11.0, expReturn: 18, stdDev: 22, pe: 5.1, pe_hist: 7.2 },
  { ticker: "LKOH", name: "Лукойл", shares: 20, avgPrice: 6800, currentPrice: 7100, beta: 0.9, divYield: 9.5, expReturn: 14, stdDev: 18, pe: 5.8, pe_hist: 7.0 },
  { ticker: "YDEX", name: "Яндекс", shares: 15, avgPrice: 3900, currentPrice: 4200, beta: 1.5, divYield: 0.0, expReturn: 25, stdDev: 30, pe: 22, pe_hist: 35 },
];

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
    if (value.length < 2) { setSuggestions([]); setOpen(false); return; }
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
  const [quantity, setQuantity] = useState(String(position.shares ?? ""));
  const [avgPrice, setAvgPrice] = useState(String(position.avgPrice ?? ""));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const check = async (resp, action) => {
    if (resp.ok) return resp;
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Не удалось ${action} (HTTP ${resp.status})`);
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
          {[
            { label: "Количество акций", value: quantity, onChange: (e) => setQuantity(e.target.value) },
            { label: "Средняя цена покупки, ₽", value: avgPrice, onChange: (e) => setAvgPrice(e.target.value) },
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

          {error && (
            <p style={{ fontSize: 13, color: "var(--negative)", background: "var(--neg-fade)", border: "1px solid var(--negative)", borderRadius: 8, padding: "10px 14px", margin: 0 }}>
              {error}
            </p>
          )}

          <Button onClick={handleSave} disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
            {loading ? "Сохраняем…" : "Сохранить"}
          </Button>

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

const AddPositionModal = ({ portfolioId, existingPositions, token, onClose, onSuccess }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
  const [side, setSide] = useState("buy");
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async () => {
    setError(null);
    if (!ticker.trim() || !quantity || !price) { setError("Заполни все поля"); return; }
    const qty = parseFloat(quantity);
    const prc = parseFloat(price);
    if (qty <= 0 || prc <= 0) { setError("Количество и цена должны быть больше нуля"); return; }

    setLoading(true);
    try {
      const companies = await fetch(`${apiUrl}/api/companies`).then(r => r.json());
      const company = Array.isArray(companies)
        ? companies.find(c => c.ticker.toUpperCase() === ticker.trim().toUpperCase())
        : null;
      if (!company) throw new Error(`Тикер «${ticker.trim().toUpperCase()}» не найден в базе`);

      const existing = existingPositions.find(p => p.company_id === company.id);
      // Бэк отдаёт Decimal строками — приводим к числам ДО сравнений
      // (раньше qty === existing.quantity сравнивало число со строкой,
      // «продажа всех» не распознавалась и в портфеле застревала позиция с 0 шт.)
      const exQty = existing ? parseFloat(existing.quantity) : 0;
      const exAvg = existing ? parseFloat(existing.avg_buy_price) : 0;

      // Любая ошибка запроса — наружу, не молча (раньше 403 лимита глотался)
      const check = async (resp, action) => {
        if (resp.ok) return resp;
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail || `Не удалось ${action} (HTTP ${resp.status})`);
      };
      const del = async () => check(
        await fetch(`${apiUrl}/api/portfolios/${portfolioId}/positions/${existing.id}`, { method: "DELETE", headers: authHeaders }),
        "удалить позицию"
      );
      const post = async (body) => check(
        await fetch(`${apiUrl}/api/portfolios/${portfolioId}/positions`, { method: "POST", headers: authHeaders, body: JSON.stringify(body) }),
        "сохранить позицию"
      );

      if (side === "sell") {
        if (!existing) throw new Error("Такой позиции нет в портфеле — нечего продавать");
        if (qty > exQty) throw new Error(`Нельзя продать больше чем есть (${exQty} шт.)`);
        const newQty = exQty - qty;
        await del();
        // продажа в ноль (или из-за округления почти в ноль) = позиция удалена,
        // нулевые строки в портфеле не появляются
        if (newQty > 1e-9) {
          await post({ company_id: company.id, quantity: newQty, avg_buy_price: exAvg });
        }
      } else {
        if (existing) {
          const newQty = exQty + qty;
          const newAvg = (exQty * exAvg + qty * prc) / newQty;
          await del();
          await post({ company_id: company.id, quantity: newQty, avg_buy_price: parseFloat(newAvg.toFixed(4)) });
        } else {
          await post({ company_id: company.id, quantity: qty, avg_buy_price: prc });
        }
      }
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
          {/* Buy / Sell toggle */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, background: "var(--bg-surface)", borderRadius: 10, padding: 4 }}>
            {[{ id: "buy", label: "🟢 Покупка" }, { id: "sell", label: "🔴 Продажа" }].map(s => (
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

          <div>
            <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 6 }}>Тикер</label>
            <TickerInput value={ticker} onChange={setTicker} placeholder="SBER" />
          </div>
          {[
            { label: "Количество (акций)", value: quantity, onChange: e => setQuantity(e.target.value), placeholder: "100" },
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
          ))}

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
            {loading ? "Сохраняем..." : side === "buy" ? <><Plus size={15} /> Купить</> : <><TrendingDown size={15} /> Продать</>}
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
const HeadlineNum = ({ value, gate }) => {
  const n = useCountUp(value, 320, gate);
  return <span className="tw-tabular-nums">{formatMoney(Math.round(n), { decimals: 0 })}</span>;
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

// Сравнение накопленной доходности портфеля с бенчмарком (Этап 3).
// Мультилинейный SVG: портфель и MCFTR — основные, IMOEX — тонкая справочная.
const BenchmarkChart = ({ series }) => {
  const { dates = [], portfolio = [], mcftr = [], imoex = [] } = series || {};
  const svgRef = useRef(null);
  const [hover, setHover] = useState(null);   // индекс точки под курсором
  if (!dates.length) return null;
  const W = 640, H = 220, padL = 44, padR = 12, padT = 12, padB = 24;
  const all = [...portfolio, ...mcftr, ...imoex].filter((v) => typeof v === "number");
  const max = Math.max(...all, 0), min = Math.min(...all, 0), span = (max - min) || 1;
  const n = dates.length;
  const xAt = (i) => padL + (n <= 1 ? 0 : (i * (W - padL - padR)) / (n - 1));
  const yAt = (v) => padT + (1 - (v - min) / span) * (H - padT - padB);
  const line = (arr) => arr.map((v, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(" ");
  const zeroY = yAt(0);
  const fmtD = (iso) => { const [y, m] = iso.split("-"); return `${m}.${y.slice(2)}`; };
  const LINES = [
    { d: line(portfolio), color: "var(--accent)", w: 2.25, label: "Портфель" },
    { d: line(mcftr), color: "var(--cat-1)", w: 2, label: "MCFTR (с дивидендами)" },
    { d: line(imoex), color: "var(--cat-8)", w: 1.25, label: "IMOEX (ценовой)" },
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
          className="tw-absolute tw-z-10 tw-pointer-events-none tw-bg-bg-overlay tw-border tw-border-border-subtle tw-rounded-md tw-shadow-lg tw-px-3 tw-py-2 tw-text-[12px]"
          style={{ left: `${(xAt(hover) / W) * 100}%`, top: 0, transform: xAt(hover) > W * 0.6 ? "translateX(-105%)" : "translateX(8px)" }}
        >
          <div className="tw-text-text-tertiary tw-font-mono tw-mb-1">{fmtFullD(dates[hover])}</div>
          <div className="tw-text-text-primary">Портфель <b className="tw-font-mono tw-tabular-nums">{fmtPercent(portfolio[hover], { sign: true })}</b></div>
          <div className="tw-text-text-secondary">MCFTR <b className="tw-font-mono tw-tabular-nums">{fmtPercent(mcftr[hover], { sign: true })}</b></div>
          {typeof imoex[hover] === "number" && (
            <div className="tw-text-text-tertiary">IMOEX <span className="tw-font-mono tw-tabular-nums">{fmtPercent(imoex[hover], { sign: true })}</span></div>
          )}
        </div>
      )}
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} role="img" aria-label="Портфель против бенчмарка"
        onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        {[max, (max + min) / 2, min].map((v, k) => (
          <g key={k}>
            <line x1={padL} x2={W - padR} y1={yAt(v)} y2={yAt(v)} stroke="var(--border-subtle)" strokeWidth="1" strokeDasharray={v === 0 ? "" : "3 4"} />
            <text x={padL - 6} y={yAt(v) + 4} textAnchor="end" fontSize="10.5" fill="var(--text-tertiary)" fontFamily="monospace">{Math.round(v)}%</text>
          </g>
        ))}
        {min < 0 && max > 0 && <line x1={padL} x2={W - padR} y1={zeroY} y2={zeroY} stroke="var(--border-strong)" strokeWidth="1" />}
        {LINES.map((l, k) => <path key={k} d={l.d} fill="none" stroke={l.color} strokeWidth={l.w} strokeLinejoin="round" />)}
        {hover != null && (
          <g>
            <line x1={xAt(hover)} x2={xAt(hover)} y1={padT} y2={H - padB} stroke="var(--border-strong)" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={xAt(hover)} cy={yAt(portfolio[hover])} r="3.5" fill="var(--accent)" />
            <circle cx={xAt(hover)} cy={yAt(mcftr[hover])} r="3" fill="var(--cat-1)" />
            {typeof imoex[hover] === "number" && (
              <circle cx={xAt(hover)} cy={yAt(imoex[hover])} r="2.5" fill="var(--cat-8)" />
            )}
          </g>
        )}
        <text x={padL} y={H - 8} fontSize="10.5" fill="var(--text-tertiary)" fontFamily="monospace">{fmtD(dates[0])}</text>
        <text x={W - padR} y={H - 8} textAnchor="end" fontSize="10.5" fill="var(--text-tertiary)" fontFamily="monospace">{fmtD(dates[dates.length - 1])}</text>
      </svg>
      <div className="tw-flex tw-flex-wrap tw-gap-4 tw-mt-2 tw-text-[12px] tw-text-text-secondary">
        {LINES.map((l) => (
          <span key={l.label} className="tw-inline-flex tw-items-center tw-gap-1.5">
            <span className="tw-inline-block tw-w-4 tw-h-0.5 tw-rounded-pill" style={{ background: l.color, height: l.w }} />{l.label}
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
    what: "Оценка доходности, которую бумага «должна» приносить за свой уровень рыночного риска — по классической финансовой модели. Это не факт и не прогноз, а ориентир: сколько разумно ожидать с учётом того, насколько бумага чувствительна к рынку.",
    reading: (v, ctx = {}) => v == null ? null
      : (ctx.rf != null && v < ctx.rf)
        ? `Сейчас модель даёт ${_sgn(v)} — ниже доходности ОФЗ. Так выходит потому, что в текущем периоде сам рынок акций отставал от безрисковой ставки (премия за риск отрицательная). Это особенность периода высокой ставки, а не свойство конкретно этой бумаги.`
        : `Модель оценивает «справедливую» ожидаемую доходность в ${_sgn(v)} в год — исходя из безрисковой ставки и того, насколько бумага следует за рынком.`,
    soWhat: "CAPM — модельная, а не фактическая величина, и она чувствительна к допущению о доходности рынка. Используйте её как один из ориентиров рядом с фактической доходностью, а не как точный прогноз. Когда фактическая доходность сильно выше CAPM-оценки — бумага дала больше «положенного» за свой риск (см. Альфа).",
    formula: { expr: "Ожидаемая доходность = Rf + β × (Rm − Rf)", note: "Rf — безрисковая ставка (ОФЗ ~1 год), Rm — доходность рынка (индекс полной доходности Мосбиржи), β — чувствительность бумаги к рынку, (Rm − Rf) — премия за рыночный риск. В текущем периоде премия отрицательна, поэтому модельные оценки занижены." },
  },
  div_yield: {
    title: "Дивидендная доходность",
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
    what: "Оценка «плохого, но не катастрофического дня»: с вероятностью 95% дневной убыток не превысит этой величины. В 1 дне из 20 (худшие 5%) потери могут быть и больше.",
    reading: (v) => v == null ? null
      : `В обычный день (19 случаев из 20) потери не превышают ${_pct(v)}. Но в 1 дне из 20 — в худшие 5% дней — убыток может оказаться глубже, и насколько, VaR не говорит.`,
    soWhat: "VaR помогает почувствовать масштаб обычной дневной просадки, чтобы она не застала врасплох. Главное ограничение: VaR молчит про «хвост» — самые редкие, но самые болезненные обвалы (кризисы, чёрные лебеди) выходят за рамки 95%. Не воспринимайте VaR как максимально возможный убыток.",
    formula: { expr: "VaR 95% = −(5-й перцентиль дневных доходностей)", note: "Исторический метод: берётся распределение дневных доходностей за период, VaR 95% — граница худших 5% дней. На другой горизонт масштабируется через корень из времени." },
  },
  downside_vol: {
    title: "Нисходящая волатильность",
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
    what: "Главная мера «качества» доходности: сколько отдачи сверх безрисковой ставки вы получаете на каждую единицу риска. Отвечает на вопрос — оправдывает ли доходность тот риск, что вы на себя берёте.",
    tone: (v) => v == null ? "info" : v > 1 ? "positive" : v > 0 ? "info" : "caution",
    reading: (v) => v == null ? null
      : v > 1 ? `${_num1(v)} — хороший показатель: портфель приносит достойную отдачу за свой риск.`
      : v > 0 ? `${_num1(v)} — портфель приносит сверх безриска, но немного относительно риска. Риск вознаграждается слабо.`
      : `${_num1(v)} — портфель пока приносит не больше (или меньше), чем безрисковая ОФЗ. Важный контекст: сейчас ставка ОФЗ высокая (около 12–13%), и в этом периоде сам рынок акций отставал от неё — поэтому отрицательный Шарп сейчас типичен не только для вашего портфеля, но и для рынка в целом. Это характеристика момента (высокая ставка), а не обязательно слабость вашего набора бумаг.`,
    soWhat: "Шарп лучше всего работает для сравнения: один портфель против другого, ваш портфель против рынка. Само по себе отрицательное значение в период высокой ставки не означает «плохой портфель» — оно означает, что риск акций сейчас вознаграждается слабо по всему рынку. Если Шарп низкий устойчиво и в нормальные периоды — это повод пересмотреть, оправдан ли риск. Подробный разбор даст ИИ-диагноз.",
    formula: { expr: "Шарп = (Доходность портфеля − Безрисковая ставка) / Волатильность портфеля", note: "Числитель и знаменатель — годовые. Безрисковая ставка — ОФЗ ~1 год. Волатильность портфеля считается через ковариационную матрицу (с учётом корреляций), поэтому ниже простого среднего волатильностей бумаг." },
  },
  alpha: {
    title: "Альфа (Jensen’s alpha)",
    what: "Показывает, обыграл ли актив рынок с поправкой на риск. Положительная альфа — бумага дала больше, чем «положено» за её уровень риска; отрицательная — меньше.",
    tone: (v) => v == null ? "info" : v > 1 ? "positive" : v >= -1 ? "info" : "caution",
    reading: (v) => v == null ? null
      : v > 1 ? `${_sgn(v)} — за свой уровень риска портфель дал БОЛЬШЕ, чем предсказывала модель. Это «премия» сверх рыночной отдачи, скорректированной на риск.`
      : v >= -1 ? `${_sgn(v)} — результат примерно такой, какой и ожидался за этот риск. Ни обгона, ни отставания от модели.`
      : `${_sgn(v)} — за свой риск получено МЕНЬШЕ ожидаемого. Риск не окупился относительно того, что давал рынок.`,
    soWhat: "Альфа — попытка отделить «мастерство/везение» от простого следования за рынком. Но она зависит от модели и от выбранного периода: положительная альфа за три года не гарантирует её в будущем. Читайте альфу как «как бумага показала себя относительно своего риска в этом окне», а не как прогноз.",
    formula: { expr: "Альфа = Фактическая доходность − [Rf + β × (Rm − Rf)]", note: "Разница между тем, что бумага реально дала, и тем, что предсказывает CAPM за её бету. Все величины годовые." },
  },
  sortino: {
    title: "Коэффициент Сортино",
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
  return (
    <div className="tw-flex tw-flex-col tw-gap-3">
      {items.map(({ key, def }) => (
        <Card key={key}>
          {/* Крупный заголовок плиты: акцентная полоса + название 18px bold
              на лёгкой акцентной подложке — метрика читается как раздел */}
          <div className="tw-flex tw-items-center tw-gap-2.5 tw--mx-4 tw--mt-4 tw-mb-3 tw-px-4 tw-py-3 tw-bg-accent-soft tw-border-b tw-border-border-subtle">
            <span className="tw-w-1 tw-h-5 tw-rounded-pill tw-bg-accent tw-shrink-0" aria-hidden="true" />
            <h4 className="tw-m-0 tw-text-[18px] tw-font-bold tw-text-text-primary">{def.title}</h4>
          </div>
          <div className="tw-flex tw-flex-col tw-gap-3">
            <KeyTakeaway tone="neutral" title="Что это">{def.what}</KeyTakeaway>

            {def.reading && def.reading(values[key], ctx) && (
              <KeyTakeaway
                tone={def.tone ? def.tone(values[key], ctx) : "info"}
                title="Что значит ваше значение"
              >
                {def.reading(values[key], ctx)}
              </KeyTakeaway>
            )}

            {def.soWhat && (
              <KeyTakeaway tone="positive" title="Что с этим делать">{def.soWhat}</KeyTakeaway>
            )}

            {def.formula && (
              <Disclosure summary="Формула — для любопытных">
                <div className="tw-rounded-md tw-bg-bg-base tw-border tw-border-border-strong tw-p-3 tw-mt-1">
                  {def.formula.expr && (
                    <code className="tw-block tw-font-mono tw-text-[13px] tw-leading-[1.6] tw-text-text-primary tw-whitespace-pre-wrap tw-mb-2">
                      {def.formula.expr}
                    </code>
                  )}
                  {def.formula.note && (
                    <p className="tw-m-0 tw-text-[13px] tw-leading-[1.55] tw-text-text-secondary">{def.formula.note}</p>
                  )}
                </div>
              </Disclosure>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
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
const RETURN_COLUMNS = [
                        {
              key: "return3y", label: "Доходность",
              render: (v, row) => v == null ? "—" : (
                <span className={v >= 0 ? "tw-text-success" : "tw-text-danger"} title="ПОЛНАЯ доходность: цена + дивиденды (CAGR). Факт прошлого, не прогноз">
                  {fmtPercent(v, { sign: true })}{row?.shortHistory ? "*" : ""}
                  {row?.periodLabel && <span className="tw-text-text-tertiary tw-font-normal"> {row.periodLabel}</span>}
                </span>
              ),
            },
            {
              key: "capm", label: "CAPM (модель)",
              render: (v) => v == null ? "—" : (
                <span className="tw-text-text-tertiary" title="Модельная forward-оценка: Rf + β×(Rm − Rf). Оценка, не факт и не прогноз">
                  {fmtPercent(v, { sign: true })}
                </span>
              ),
            },
            { key: "divYield", label: "Див. дох.", render: (v) => v == null ? "—" : fmtPercent(v, { decimals: 1 }) },
            { key: "pe", label: "P/E тек.", render: (v) => v == null ? "—" : <span title="Пересчитывается от текущей котировки">{`${fmtNumber(v, { decimals: 1 })}×`}</span> },
            { key: "peHist", label: "P/E ист.", render: (v) => v == null ? "—" : <span className="tw-text-text-tertiary" title="Медиана P/E за 5 лет">{`${fmtNumber(v, { decimals: 1 })}×`}</span> },
            {
              key: "earningsYield", label: "Дох. прибыли",
              render: (v) => v == null ? "—" : <span title="Earnings yield = 1 / P/E">{fmtPercent(v, { decimals: 1 })}</span>,
            },
          ];

const RISK_COLUMNS = [
                        {
              key: "volatility", label: "Волатильность",
              render: (v, row) => v == null ? "—" : (
                <span title="СКО дневных доходностей × √252, годовая; у портфеля — через ковариационную матрицу">
                  {fmtPercent(v)}{row?.shortHistory ? "*" : ""}
                </span>
              ),
            },
            {
              key: "var95", label: "VaR 95%",
              render: (v) => v == null ? "—" : <span title="Дневная потеря, которую превышали лишь 5% дней окна">−{fmtPercent(v)}</span>,
            },
            {
              key: "downsideVol", label: "Нисходящая волатильность",
              render: (v) => v == null ? "—" : <span title="Волатильность только по дням падения (порог 0), годовая">{fmtPercent(v)}</span>,
            },
            {
              key: "beta", label: "Beta",
              render: (v, row) => v == null ? "—" : (
                <span title={row?.betaSource === "moex" ? "Данные Мосбиржи (файл коэффициентов срочного рынка)" : "Расчёт Basis (Диммсон, окно 3 года)"}>
                  {fmtNumber(v, { decimals: 2 })}{row?.shortHistory ? "*" : ""}
                  {row?.betaSource && <span className="tw-text-text-tertiary"> {row.betaSource === "moex" ? "ᴹ" : "ᴮ"}</span>}
                </span>
              ),
            },
            {
              key: "rSquared", label: "R²",
              render: (v) => v == null ? "—" : (
                <span title="Доля движения, объяснённая рынком: >0,6 — бета надёжна" className={v >= 0.6 ? "tw-text-text-secondary" : "tw-text-text-tertiary"}>
                  {fmtNumber(v, { decimals: 2 })}
                </span>
              ),
            },
            {
              key: "sharpe", label: "Шарп",
              render: (v) => v == null ? "—" : <span title="(Полная доходность − ставка ОФЗ) / волатильность. >1 — хорошо; ≤0 — риск не вознаграждается">{fmtNumber(v, { decimals: 2 })}</span>,
            },
            {
              key: "alpha", label: "α",
              render: (v) => v == null ? "—" : (
                <span className={v >= 0 ? "tw-text-success" : "tw-text-danger"} title="Альфа Дженсена: сверх «положенного» за риск по CAPM, % годовых">
                  {fmtPercent(v, { sign: true })}
                </span>
              ),
            },
            {
              key: "sortino", label: "Сортино",
              render: (v) => v == null ? "—" : <span title="(Полная доходность − ставка ОФЗ) / нисходящая волатильность">{fmtNumber(v, { decimals: 2 })}</span>,
            },
          ];

// Честная подпись фактического периода метрики: «за 2 мес.», «за 1,9 г», «за 3 г»
const fmtHistoryPeriod = (years) => {
  if (years == null) return null;
  if (years >= 2.95) return "за 3 г";
  if (years >= 1) return `за ${String(Math.round(years * 10) / 10).replace(".", ",")} г`;
  const months = Math.max(1, Math.round(years * 12));
  return `за ${months} мес.`;
};

const PortfolioView = ({ token, onAuthRequired, onOpenCompany }) => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};
  const [tab, setTab] = useState("holdings");
  const [stressScenario, setStressScenario] = useState("black_swan");
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
  // Этап 1 аналитики: метрики из company_metrics (P/E, дивдоходность,
  // секторное распределение, концентрация) — GET /portfolios/{id}/metrics
  const [pfMetrics, setPfMetrics] = useState(null);
  // Прямое редактирование позиции (строка таблицы «Состав»)
  const [editPosition, setEditPosition] = useState(null);

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

            const mapped = detail.positions.map(pos => {
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

          // Лёгкие метрики портфеля (Этап 1) — одним запросом из company_metrics
          fetch(`${apiUrl}/api/portfolios/${active.id}/metrics`, { headers: authHeaders })
            .then(r => r.ok ? r.json() : null)
            .then(m => setPfMetrics(m))
            .catch(() => setPfMetrics(null));
        } else {
          setPortfolioList([]);
          setPortfolio(null);
          setPositions([]);
          setRawPositions([]);
          setPfMetrics(null);
        }
      } finally {
        setPortfolioLoading(false);
      }
    };

    loadData();
  }, [token, reloadKey, activePortfolioId]);

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

  const displayPositions = positions.length > 0 ? positions : MOCK_PORTFOLIO.map(p => ({
    ...p, currentPrice: quotes[p.ticker] || p.currentPrice,
  }));

  const stats = useMemo(() => {
    const src = displayPositions;
    const totalValue = src.reduce((a, p) => a + p.shares * p.currentPrice, 0);
    const totalCost  = src.reduce((a, p) => a + p.shares * p.avgPrice, 0);
    const totalProfit = totalValue - totalCost;
    const profitPct  = totalCost > 0 ? (totalProfit / totalCost) * 100 : 0;
    return { totalValue, totalCost, totalProfit, profitPct, avgBeta: 0, avgYield: 0, portExp: 0, portStd: 0 };
  }, [displayPositions]);


  // Count-up gates live at PAGE level (refs survive tab switches / re-renders),
  // so the headline value and the index animate ONCE per page visit and snap
  // (no replay) on tab switch, click or background price refresh. The animated
  // components are hoisted to module scope (above) so re-renders of this page
  // do not remount them.
  const valueGate = useRef({ played: false });
  const scoreGate = useRef({ played: false });
  // Appear gate (Phase 4b): page-level Set keyed by tab, so each tab's cards
  // stagger once on first open and never replay on tab switch / re-render /
  // background price refresh.
  const appearGate = useRef(new Set());

  const stressMap = {
    black_swan: {
      label: "Черный лебедь (-20%)",
      drop: stats.avgBeta * 20,
      valueLoss: stats.totalValue * (stats.avgBeta * 0.2),
      text: "Сценарий широкой рыночной коррекции. Главный риск — концентрация в нескольких бумагах и высокий удельный вес финансового сектора.",
    },
    rate_up: {
      label: "Ставка ЦБ +5%",
      drop: 11.8,
      valueLoss: stats.totalValue * 0.118,
      text: "Наиболее чувствителен банковский блок и бумаги с длинной дюрацией оценки.",
    },
    oil_crash: {
      label: "Крах нефти ($40)",
      drop: 8.6,
      valueLoss: stats.totalValue * 0.086,
      text: "Главный канал — ухудшение переоценки сырьевого сектора и давление на внешний баланс.",
    },
  };

  const currentStress = stressMap[stressScenario];

  // Метрики по тикерам из company_metrics + примечание о покрытии («по n из m»)
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
    return parts.length ? `Строка «Портфель» — средневзвешенное по долям; ${parts.join("; ")} (у остальных метрика не рассчитана).` : null;
  }, [pfMetrics]);

  // Ряды аналитики (метрики из company_metrics поверх позиций) — общие для
  // двух групповых таблиц «Доходность и оценка» и «Риск» (вкладка Агрегирующая)
  const analyticRows = useMemo(() => ([
    ...displayPositions.map((p) => {
      const m = metricByTicker[p.ticker];
      return m ? {
        ...p,
        pe: m.pe_current, peHist: m.pe_historical, divYield: m.div_yield,
        return3y: m.return_total_3y ?? m.return_3y,
        capm: m.capm_expected, alpha: m.alpha_3y,
        sortino: m.sortino_3y, sharpe: m.sharpe_3y,
        volatility: m.volatility, downsideVol: m.downside_vol, beta: m.beta,
        betaSource: m.beta_source, rSquared: m.r_squared,
        var95: m.var_95, earningsYield: m.earnings_yield,
        shortHistory: m.short_history,
        periodLabel: fmtHistoryPeriod(m.history_years),
      } : { ...p, return3y: null, volatility: null, beta: p.beta ?? null };
    }),
    {
      ticker: "Портфель", _isTotal: true,
      return3y: pfMetrics?.portfolio?.return_total_3y?.value ?? null,
      capm: pfMetrics?.portfolio?.capm ?? null,
      alpha: pfMetrics?.portfolio?.alpha ?? null,
      sortino: pfMetrics?.portfolio?.sortino ?? null,
      sharpe: pfMetrics?.portfolio?.sharpe ?? null,
      periodLabel: null,
      // σ портфеля — через ковариационную матрицу (не среднее волатильностей)
      volatility: pfMetrics?.portfolio?.volatility?.value ?? null,
      downsideVol: pfMetrics?.portfolio?.downside_vol ?? null,
      var95: pfMetrics?.portfolio?.var_95 ?? null,
      rSquared: pfMetrics?.portfolio?.r_squared ?? null,
      beta: pfMetrics?.portfolio?.beta?.value ?? null,
      pe: pfMetrics?.portfolio?.pe_current?.value ?? null,
      peHist: pfMetrics?.portfolio?.pe_historical?.value ?? null,
      divYield: pfMetrics?.portfolio?.div_yield?.value ?? null,
      earningsYield: pfMetrics?.portfolio?.earnings_yield ?? null,
    },
  ]), [displayPositions, metricByTicker, pfMetrics]);

  // Holdings rows enriched with derived value / weight / P&L for the Table.
  const holdingRows = displayPositions.map((p) => {
    const value = p.shares * p.currentPrice;
    const weight = stats.totalValue > 0 ? (value / stats.totalValue) * 100 : 0;
    const profitRub = p.shares * (p.currentPrice - p.avgPrice);
    const profitPct = p.avgPrice > 0 ? (p.currentPrice / p.avgPrice - 1) * 100 : 0;
    return { ...p, value, weight, profitRub, profitPct };
  });

  const renderHoldings = () => (
    <AppearGroup gate={appearGate.current} groupId="pf-holdings" className="tw-flex tw-flex-col tw-gap-3 tw-p-1">
      {/* Portfolio switcher */}
      <div className="tw-flex tw-items-center tw-gap-2 tw-flex-wrap">
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
        <Button variant="ghost" size="sm" iconLeft={<Plus size={14} />} onClick={() => token ? setShowUploadModal(true) : onAuthRequired()}>
          Новый портфель
        </Button>
        <Button variant="secondary" size="sm" iconLeft={<Plus size={14} />} className="tw-ml-auto" onClick={() => portfolio && token ? setShowAddModal(true) : onAuthRequired()}>
          Добавить сделку
        </Button>
      </div>

      {/* Positions table — собственная плитка на фоне.
          Клик разведён: актив (первый столбец) — ссылка «вглубь» в карточку
          компании; остальная строка — редактирование позиции. */}
      <Card header="Состав портфеля">
      <Table
        onRowClick={(r) => { if (r.id != null) setEditPosition(r); }}
        columns={[
          {
            key: "ticker", label: "Актив",
            render: (_, r) => (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  if (r.company_id != null && onOpenCompany) {
                    onOpenCompany({ id: r.company_id, ticker: r.ticker, name: r.name, sector: r.sector });
                  }
                }}
                className="tw-flex tw-items-center tw-gap-2.5 tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer tw-text-left tw-group"
                title={`Открыть карточку ${r.ticker}`}
              >
                <CompanyLogo ticker={r.ticker} name={r.name} size={30} />
                <div>
                  <div className="tw-font-semibold tw-text-accent group-hover:tw-underline">{r.ticker}</div>
                  <div className="tw-text-[11px] tw-text-text-tertiary">{r.name}</div>
                </div>
              </button>
            ),
          },
          { key: "shares", label: "Кол-во", render: (v) => fmtNumber(v) },
          { key: "avgPrice", label: "Средняя", render: (v) => formatMoney(v, { decimals: 1 }) },
          { key: "currentPrice", label: "Текущая", render: (v) => <span className="tw-text-text-primary tw-font-medium">{formatMoney(v, { decimals: 1 })}</span> },
          {
            key: "value", label: "Стоимость",
            render: (v) => <span className="tw-text-text-primary tw-font-medium">{formatMoney(v, { decimals: 0 })}</span>,
          },
          {
            key: "weight", label: "Доля",
            render: (v, r) => (
              <div className="tw-flex tw-items-center tw-justify-end tw-gap-2">
                <span>{fmtPercent(v, { decimals: 1 })}</span>
                <WeightBar pct={v} n={catFor(r.ticker)} />
              </div>
            ),
          },
          {
            key: "profitRub", label: "Результат ₽",
            render: (v) => (
              <span className={v >= 0 ? "tw-text-success" : "tw-text-danger"}>
                <span aria-hidden="true">{v >= 0 ? "▲ " : "▼ "}</span>{formatMoney(Math.abs(v), { decimals: 0 })}
              </span>
            ),
          },
          { key: "profitPct", label: "Результат %", render: (v) => <Delta value={v} /> },
          {
            key: "_edit", label: "",
            render: (_, r) => r.id == null ? null : (
              <IconButton
                size="sm"
                aria-label={`Изменить позицию ${r.ticker}`}
                onClick={() => setEditPosition(r)}
              >
                <Pencil size={13} />
              </IconButton>
            ),
          },
        ]}
        rows={holdingRows}
      />

      {/* Явный способ добавить бумагу — сразу в режиме покупки */}
      <div className="tw-mt-2">
        <Button
          variant="ghost"
          size="sm"
          iconLeft={<Plus size={14} />}
          onClick={() => (portfolio && token ? setShowAddModal(true) : onAuthRequired())}
        >
          Добавить позицию
        </Button>
      </div>
      </Card>

      {/* Распределение и концентрация (Этап 1) — из /portfolios/{id}/metrics */}
      {pfMetrics && pfMetrics.sector_allocation.length > 0 && (
        <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-3 tw-gap-3 tw-mt-1">
          <Card header="Распределение по секторам" className="lg:tw-col-span-2">
            <div className="tw-flex tw-items-center tw-gap-5 tw-flex-wrap">
              <DonutChart
                slices={pfMetrics.sector_allocation.map((s, i) => ({ pct: s.share_pct, color: CAT_COLORS[i % CAT_COLORS.length] }))}
              />
              <div className="tw-flex tw-flex-col tw-gap-2.5 tw-min-w-[220px] tw-flex-1">
                {pfMetrics.sector_allocation.map((s, i) => (
                  <div key={s.sector} className="tw-flex tw-items-center tw-gap-2.5 tw-text-[14px]">
                    <span className="tw-inline-block tw-w-3 tw-h-3 tw-rounded-sm tw-shrink-0" style={{ background: CAT_COLORS[i % CAT_COLORS.length] }} />
                    {/* название + процент вместе, читаемо */}
                    <span className="tw-text-text-primary tw-font-medium">
                      {s.sector} <span className="tw-font-mono tw-tabular-nums">{fmtPercent(s.share_pct, { decimals: s.share_pct < 10 ? 1 : 0 })}</span>
                    </span>
                    <span className="tw-text-[12px] tw-text-text-tertiary tw-ml-auto tw-font-mono tw-tabular-nums">{formatMoney(s.value, { decimals: 0 })}</span>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <div className="tw-flex tw-flex-col tw-gap-3">
            <Card header="Классы активов">
              {pfMetrics.asset_classes.map((a) => (
                <div key={a.name} className="tw-flex tw-items-center tw-justify-between tw-text-[13px] tw-mb-1.5">
                  <span className="tw-text-text-primary">{a.name}</span>
                  <span className="tw-font-mono tw-tabular-nums tw-text-text-secondary">{fmtPercent(a.share_pct, { decimals: 0 })}</span>
                </div>
              ))}
              <div className="tw-text-[12px] tw-text-text-tertiary tw-mt-2">
                Облигации и фонды появятся после расширения модели портфеля.
              </div>
            </Card>
            {pfMetrics.concentration && (
              <Card header="Концентрация">
                <div className="tw-flex tw-items-center tw-justify-between tw-text-[13px] tw-mb-1.5">
                  <span className="tw-text-text-primary">Крупнейшая позиция ({pfMetrics.concentration.largest_ticker})</span>
                  <span className="tw-font-mono tw-tabular-nums tw-text-text-secondary">{fmtPercent(pfMetrics.concentration.largest_pct, { decimals: 1 })}</span>
                </div>
                <div className="tw-flex tw-items-center tw-justify-between tw-text-[13px]">
                  <span className="tw-text-text-primary">Топ-3 позиции</span>
                  <span className="tw-font-mono tw-tabular-nums tw-text-text-secondary">{fmtPercent(pfMetrics.concentration.top3_pct, { decimals: 1 })}</span>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </AppearGroup>
  );

  // Колонка «Актив» с переходом в карточку — общая для групповых таблиц
  const assetColumn = useMemo(() => makeAssetColumn(onOpenCompany), [onOpenCompany]);

  // Контекст пороговых текстов объяснений (значения портфеля + ставки)
  const explainCtx = {
    rf: pfMetrics?.rates?.risk_free_1y ?? null,
    period: pfMetrics?.benchmark?.period_years
      ? `${String(pfMetrics.benchmark.period_years).replace(".", ",")} г`
      : "период расчёта",
    peCurrent: pfMetrics?.portfolio?.pe_current?.value ?? null,
    volatility: pfMetrics?.portfolio?.volatility?.value ?? null,
    shortHistory: false,
  };

  // Вкладка «Доходность и оценка»: полная таблица группы + читаемые объяснения
  const renderReturnsTab = () => (
    <AppearGroup gate={appearGate.current} groupId="pf-returns" as="div" className="tw-p-1 tw-flex tw-flex-col tw-gap-3">
      <Card header="Доходность и оценка">
        <Table columns={[assetColumn, ...RETURN_COLUMNS]} rows={analyticRows} />
        <div className="tw-mt-2 tw-flex tw-flex-col tw-gap-1 tw-text-[12px] tw-text-text-tertiary">
          {pfMetrics?.positions?.some((p) => p.short_history) && (
            <span>* рассчитано на истории менее года — значение неустойчиво; доходность короче года не приводится к годовой.</span>
          )}
          {metricsCoverageNote && <span>{metricsCoverageNote}</span>}
        </div>
      </Card>
      <h4 className="tw-text-[15px] tw-font-semibold tw-text-text-primary tw-m-0 tw-mt-2">Что значат эти метрики</h4>

        <MetricExplainers
          metricKeys={["return_total", "capm", "div_yield", "pe", "pe_hist", "earnings_yield"]}
          values={{
            return_total: pfMetrics?.portfolio?.return_total_3y?.value ?? null,
            capm: pfMetrics?.portfolio?.capm ?? null,
            div_yield: pfMetrics?.portfolio?.div_yield?.value ?? null,
            pe: pfMetrics?.portfolio?.pe_current?.value ?? null,
            pe_hist: pfMetrics?.portfolio?.pe_historical?.value ?? null,
            earnings_yield: pfMetrics?.portfolio?.pe_current?.value > 0
              ? Math.round(1000 / pfMetrics.portfolio.pe_current.value) / 10 : null,
          }}
          ctx={explainCtx}
        />

    </AppearGroup>
  );

  // Вкладка «Риск»: полная таблица группы + объяснения + сноска о режиме ставки
  const renderRiskTab = () => (
    <AppearGroup gate={appearGate.current} groupId="pf-risk" as="div" className="tw-p-1 tw-flex tw-flex-col tw-gap-3">
      <Card header="Риск">
        <Table columns={[assetColumn, ...RISK_COLUMNS]} rows={analyticRows} />
        <div className="tw-mt-2 tw-flex tw-flex-col tw-gap-1 tw-text-[12px] tw-text-text-tertiary">
          <span>Окно риск-метрик — 3 года дневных данных. VaR 95% — дневной горизонт. Beta: ᴹ — данные Мосбиржи, ᴮ — расчёт Basis.</span>
          {pfMetrics?.rates?.risk_free_1y != null && (
            <span>
              Безрисковая ставка: ОФЗ ~1 г {fmtPercent(pfMetrics.rates.risk_free_1y)} на {pfMetrics.rates.risk_free_as_of} (кривая ZCYC МосБиржи).
              Рынок (MCFTR, 3 г): {fmtPercent(pfMetrics.rates.market_return_3y)}; премия: {fmtPercent(pfMetrics.rates.market_premium, { sign: true })}.
            </span>
          )}
        </div>
      </Card>
      <KeyTakeaway tone="info" title="Почему многие риск-метрики сейчас выглядят слабо">
        {RISK_REGIME_NOTE}
      </KeyTakeaway>
      <h4 className="tw-text-[15px] tw-font-semibold tw-text-text-primary tw-m-0 tw-mt-2">Что значат эти метрики</h4>

        <MetricExplainers
          metricKeys={["volatility", "var_95", "downside_vol", "beta", "r_squared", "sharpe", "alpha", "sortino"]}
          values={{
            volatility: pfMetrics?.portfolio?.volatility?.value ?? null,
            var_95: pfMetrics?.portfolio?.var_95 ?? null,
            downside_vol: pfMetrics?.portfolio?.downside_vol ?? null,
            beta: pfMetrics?.portfolio?.beta?.value ?? null,
            r_squared: pfMetrics?.portfolio?.r_squared ?? null,
            sharpe: pfMetrics?.portfolio?.sharpe ?? null,
            alpha: pfMetrics?.portfolio?.alpha ?? null,
            sortino: pfMetrics?.portfolio?.sortino ?? null,
          }}
          ctx={explainCtx}
        />

    </AppearGroup>
  );

  const renderAggregate = () => (
    <AppearGroup gate={appearGate.current} groupId="pf-metrics" as="div" className="tw-p-4">
      <h3 className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-mb-4 tw-mt-0">
        Агрегирующие метрики и Индекс портфеля
      </h3>

      {/* Этап 3: коэффициенты на базе безрисковой ставки */}
      {pfMetrics?.portfolio?.sharpe != null && (
        <div className="tw-grid tw-grid-cols-2 lg:tw-grid-cols-4 tw-gap-3 tw-mb-4">
          <KpiTile
            caption="Шарп"
            value={<span title="(Полная доходность − ставка ОФЗ) / волатильность. >1 — хорошо; около 0 и ниже — риск не вознаграждается">{fmtNumber(pfMetrics.portfolio.sharpe, { decimals: 2 })}</span>}
          />
          <KpiTile
            caption="Сортино"
            value={pfMetrics.portfolio.sortino == null ? "—" : <span title="Как Шарп, но штрафует только падения (нисходящая волатильность)">{fmtNumber(pfMetrics.portfolio.sortino, { decimals: 2 })}</span>}
          />
          <KpiTile
            caption="Альфа (3г)"
            value={pfMetrics.portfolio.alpha == null ? "—" : <span title="Сверх «положенного» за риск по CAPM, % годовых">{fmtPercent(pfMetrics.portfolio.alpha, { sign: true })}</span>}
          />
          <KpiTile
            caption="Безрисковая ставка"
            value={pfMetrics?.rates?.risk_free_1y == null ? "—" : <span title={`ОФЗ ~1 год, кривая ZCYC МосБиржи, на ${pfMetrics.rates.risk_free_as_of}`}>{fmtPercent(pfMetrics.rates.risk_free_1y)}</span>}
          />
        </div>
      )}

      {/* Этап 3: если бы держал портфель — против MCFTR (обе стороны с дивидендами) */}
      {pfMetrics?.benchmark?.dates?.length > 1 && (
        <Card
          header={`Если бы держал этот портфель ${String(pfMetrics.benchmark.period_years).replace(".", ",")} г`}
          className="tw-mb-4"
        >
          <BenchmarkChart series={pfMetrics.benchmark} />
          <div className="tw-mt-3 tw-flex tw-flex-wrap tw-gap-x-6 tw-gap-y-1 tw-text-[13px]">
            <span>Портфель: <b className={pfMetrics.benchmark.portfolio_total_pct >= 0 ? "tw-text-success" : "tw-text-danger"}>{fmtPercent(pfMetrics.benchmark.portfolio_total_pct, { sign: true })}</b></span>
            <span>MCFTR: <b className="tw-text-text-primary">{fmtPercent(pfMetrics.benchmark.benchmark_total_pct, { sign: true })}</b></span>
            <span>Разница: <b className={(pfMetrics.benchmark.portfolio_total_pct - pfMetrics.benchmark.benchmark_total_pct) >= 0 ? "tw-text-success" : "tw-text-danger"}>{fmtPercent(pfMetrics.benchmark.portfolio_total_pct - pfMetrics.benchmark.benchmark_total_pct, { sign: true })}</b></span>
          </div>
          <div className="tw-mt-2 tw-text-[12px] tw-text-text-tertiary">
            Обе кривые — полная доходность (портфель с дивидендами против индекса полной доходности MCFTR); IMOEX — ценовой, для справки.
            {pfMetrics.benchmark.limited_by && ` Период ограничен историей ${pfMetrics.benchmark.limited_by}.`}
            {" "}{pfMetrics.benchmark.note}.
          </div>
        </Card>
      )}

      {/* Метрики в двух смысловых группах (вместо одной широкой «каши») */}
      <Card header="Доходность и оценка" className="tw-mb-4">
        <Table
          columns={[assetColumn, ...RETURN_COLUMNS]}
          rows={analyticRows}
        />
        <div className="tw-mt-2 tw-flex tw-flex-col tw-gap-1 tw-text-[12px] tw-text-text-tertiary">
          {pfMetrics?.positions?.some((p) => p.short_history) && (
            <span>* рассчитано на истории менее года — значение неустойчиво; доходность короче года не приводится к годовой.</span>
          )}
          {metricsCoverageNote && <span>{metricsCoverageNote}</span>}
        </div>
      </Card>
      <div className="tw-mb-4">
        <MetricExplainers
          metricKeys={["return_total", "capm", "div_yield", "pe", "pe_hist", "earnings_yield"]}
          values={{
            return_total: pfMetrics?.portfolio?.return_total_3y?.value ?? null,
            capm: pfMetrics?.portfolio?.capm ?? null,
            div_yield: pfMetrics?.portfolio?.div_yield?.value ?? null,
            pe: pfMetrics?.portfolio?.pe_current?.value ?? null,
            pe_hist: pfMetrics?.portfolio?.pe_historical?.value ?? null,
            earnings_yield: pfMetrics?.portfolio?.pe_current?.value > 0
              ? Math.round(1000 / pfMetrics.portfolio.pe_current.value) / 10 : null,
          }}
          ctx={explainCtx}
        />
      </div>


      <Card header="Риск" className="tw-mb-4">
        <Table
          columns={[assetColumn, ...RISK_COLUMNS]}
          rows={analyticRows}
        />
        <div className="tw-mt-2 tw-flex tw-flex-col tw-gap-1 tw-text-[12px] tw-text-text-tertiary">
          <span>Окно риск-метрик — 3 года дневных данных. VaR 95% — дневной горизонт. Beta: ᴹ — данные Мосбиржи, ᴮ — расчёт Basis.</span>
          {pfMetrics?.rates?.risk_free_1y != null && (
            <span>
              Безрисковая ставка: ОФЗ ~1 г {fmtPercent(pfMetrics.rates.risk_free_1y)} на {pfMetrics.rates.risk_free_as_of} (кривая ZCYC МосБиржи).
              Рынок (MCFTR, 3 г): {fmtPercent(pfMetrics.rates.market_return_3y)}; премия: {fmtPercent(pfMetrics.rates.market_premium, { sign: true })}
              {pfMetrics.rates.market_premium < 0 && " — за это окно рынок проиграл ОФЗ, поэтому CAPM-оценки ниже ставки"}.
            </span>
          )}
        </div>
      </Card>
      <div className="tw-mb-4">
        <MetricExplainers
          metricKeys={["volatility", "var_95", "downside_vol", "beta", "r_squared", "sharpe", "alpha", "sortino"]}
          values={{
            volatility: pfMetrics?.portfolio?.volatility?.value ?? null,
            var_95: pfMetrics?.portfolio?.var_95 ?? null,
            downside_vol: pfMetrics?.portfolio?.downside_vol ?? null,
            beta: pfMetrics?.portfolio?.beta?.value ?? null,
            r_squared: pfMetrics?.portfolio?.r_squared ?? null,
            sharpe: pfMetrics?.portfolio?.sharpe ?? null,
            alpha: pfMetrics?.portfolio?.alpha ?? null,
            sortino: pfMetrics?.portfolio?.sortino ?? null,
          }}
          ctx={explainCtx}
        />
      </div>


      {renderQuality()}
    </AppearGroup>
  );

  // Индекс качества + субиндексы (реальный расчёт, методика — docs).
  // Декомпозиция видна: общий балл, вклад каждого субиндекса, что внутри.
  const renderQuality = () => {
    const q = pfMetrics?.quality;
    if (!q || q.overall == null) {
      return (
        <Card>
          <div className="tw-text-[13px] tw-text-text-secondary">
            Индекс качества появится, когда в портфеле будут позиции с историей котировок.
          </div>
        </Card>
      );
    }
    const CONF_TONE = { "факт": "tw-text-success", "оценка": "tw-text-info", "суждение": "tw-text-text-tertiary" };
    return (
      <div className="tw-flex tw-flex-col tw-gap-4">
        <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-3 tw-gap-4">
          <ScoreCard score={q.overall} label={q.label} gate={scoreGate.current} />

          {/* Декомпозиция: субиндексы шкалами «от максимума» + что внутри */}
          <Card className="lg:tw-col-span-2">
            <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-4" style={{ letterSpacing: "0.06em" }}>
              Из чего сложился · субиндексы
            </div>
            <div className="tw-flex tw-flex-col tw-gap-5">
              {q.subindices.map((s) => (
                <div key={s.key} className="tw-flex tw-flex-col tw-gap-1.5">
                  <div className="tw-flex tw-items-baseline tw-justify-between tw-gap-2">
                    <span className="tw-text-[14px] tw-font-semibold tw-text-text-primary">{s.label}</span>
                    <span className="tw-flex tw-items-baseline tw-gap-2">
                      {s.confidence && <span className={`tw-text-[11px] ${CONF_TONE[s.confidence] || "tw-text-text-tertiary"}`}>{s.confidence}</span>}
                      <span className="tw-text-[14px] tw-font-mono tw-tabular-nums tw-font-bold" style={{ color: `var(${QUALITY_BAR(s.score)})` }}>{s.score}</span>
                    </span>
                  </div>
                  {/* шкала от максимума */}
                  <div className="tw-h-2 tw-rounded-pill tw-bg-bg-base tw-overflow-hidden">
                    <div className="tw-h-full tw-rounded-pill" style={{ width: `${s.score}%`, background: `var(${QUALITY_BAR(s.score)})` }} />
                  </div>
                  {/* компоненты — что внутри субиндекса (значения + мини-баллы) */}
                  <div className="tw-flex tw-flex-wrap tw-gap-x-4 tw-gap-y-0.5 tw-mt-0.5">
                    {s.components.map((c) => (
                      <span key={c.name} className="tw-text-[12px] tw-text-text-tertiary">
                        {c.name}: <span className="tw-text-text-secondary tw-font-mono">{c.value}</span>
                        {c.score != null && <span className="tw-text-text-tertiary"> ({c.score})</span>}
                      </span>
                    ))}
                  </div>
                  <p className="tw-m-0 tw-text-[12.5px] tw-text-text-secondary tw-leading-snug">{s.verdict}</p>
                  {s.limitation && (
                    <div className="tw-flex tw-gap-1.5 tw-text-[12px] tw-text-text-tertiary tw-mt-0.5">
                      <ShieldAlert size={13} className="tw-shrink-0 tw-mt-0.5 tw-text-warning" />
                      <span>{s.limitation}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </div>
        {/* как сложился общий балл + навигация к слабому звену */}
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
        {/* честная подпись: не магическое число */}
        <KeyTakeaway tone="neutral" title="Как читать индекс">{q.note}</KeyTakeaway>
      </div>
    );
  };

  const renderCorrelation = () => {
    // Реальные попарные корреляции из /portfolios/{id}/metrics (Этап 2);
    // мок остаётся только как демо без портфеля.
    const corr = pfMetrics?.correlation;
    const labels = corr?.tickers?.length ? corr.tickers : ["SBER", "LKOH", "YDEX"];
    const matrix = corr?.tickers?.length ? corr.matrix : MOCK_CORRELATION;
    // средняя внедиагональная корреляция — для вывода простым языком
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
      <AppearGroup gate={appearGate.current} groupId="pf-correlation" as="div" className="tw-p-4">
        <h3 className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-mb-2 tw-mt-0">
          Оценка диверсификации и скрытой концентрации
        </h3>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mb-6 tw-mt-0">
          Тепловая карта показывает, как активы движутся относительно друг друга
          (1,0 = синхронно, 0 = независимо). Тёплые ячейки — высокая связь
          (концентрация), холодные — диверсификация.
        </p>

        <Card className="tw-max-w-lg tw-mx-auto">
          <CorrelationHeatmap labels={labels} matrix={matrix} />
          <div className="tw-mt-4 tw-flex tw-items-center tw-gap-4 tw-text-[12px] tw-text-text-tertiary">
            <span className="tw-inline-flex tw-items-center tw-gap-1.5">
              <span className="tw-w-3 tw-h-3 tw-rounded-sm" style={{ background: "color-mix(in srgb, var(--danger) 45%, var(--bg-elevated))" }} />
              высокая
            </span>
            <span className="tw-inline-flex tw-items-center tw-gap-1.5">
              <span className="tw-w-3 tw-h-3 tw-rounded-sm" style={{ background: "color-mix(in srgb, var(--cat-8) 14%, var(--bg-elevated))" }} />
              средняя
            </span>
            <span className="tw-inline-flex tw-items-center tw-gap-1.5">
              <span className="tw-w-3 tw-h-3 tw-rounded-sm" style={{ background: "color-mix(in srgb, var(--success) 35%, var(--bg-elevated))" }} />
              низкая
            </span>
          </div>
        </Card>

        {/* Интерпретация человеческим языком: вывод + крайние пары + связь
            с субиндексом диверсификации */}
        <div className="tw-mt-6 tw-flex tw-flex-col tw-gap-3">
          <KeyTakeaway tone={avgCorr == null ? "neutral" : avgCorr >= 0.6 ? "caution" : avgCorr >= 0.3 ? "info" : "positive"} title="Что это значит для диверсификации">
            {verdict} Корреляции рассчитаны по дневным доходностям за 3 года.
            {corr?.low_overlap && " У части пар мало совпадающих торговых дат (молодые бумаги) — их значения менее надёжны."}
          </KeyTakeaway>

          {(corr?.strongest_pair || corr?.weakest_pair) && (
            <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 tw-gap-3">
              {corr?.strongest_pair && (
                <Card>
                  <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-1" style={{ letterSpacing: "0.06em" }}>Где диверсификации нет</div>
                  <div className="tw-text-[15px] tw-font-semibold tw-text-text-primary">
                    {corr.strongest_pair.a} ↔ {corr.strongest_pair.b}
                    <span className="tw-ml-2 tw-font-mono tw-text-danger">{fmtNumber(corr.strongest_pair.value, { decimals: 2 })}</span>
                  </div>
                  <p className="tw-m-0 tw-mt-1 tw-text-[12.5px] tw-text-text-secondary">Самая связанная пара — эти бумаги ходят почти заодно, друг друга не подстраховывают.</p>
                </Card>
              )}
              {corr?.weakest_pair && (
                <Card>
                  <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-1" style={{ letterSpacing: "0.06em" }}>Что реально разбавляет риск</div>
                  <div className="tw-text-[15px] tw-font-semibold tw-text-text-primary">
                    {corr.weakest_pair.a} ↔ {corr.weakest_pair.b}
                    <span className="tw-ml-2 tw-font-mono tw-text-success">{fmtNumber(corr.weakest_pair.value, { decimals: 2 })}</span>
                  </div>
                  <p className="tw-m-0 tw-mt-1 tw-text-[12.5px] tw-text-text-secondary">Наименее связанная пара — именно она снижает общий риск портфеля.</p>
                </Card>
              )}
            </div>
          )}

          {divSub && (
            <div className="tw-text-[12.5px] tw-text-text-tertiary">
              Эта картина учтена в субиндексе <b className="tw-text-text-secondary">«Диверсификация»</b> (вкладка «Агрегирующая таблица»): средняя корреляция — одна из его компонент, сейчас балл {divSub.score}/100.
            </div>
          )}
        </div>
      </AppearGroup>
    );
  };

  const renderAiDiagnosis = () => {
    const pros = [
      "Высокая ожидаемая див. доходность (около 11% годовых), создающая подушку безопасности.",
      "Наличие Яндекса защищает портфель от стагнации, добавляя сильный фактор роста.",
      "Устойчивость к девальвации рубля благодаря доле экспортёра (Лукойл).",
    ];
    const cons = [
      "Жёсткая концентрация в 3 бумагах — риск отдельных корпоративных событий критичен.",
      "Сильная зависимость финансового сектора от роста ключевой ставки.",
      "Отсутствие защитных активов при высоких ставках на рынке.",
    ];
    return (
      <AppearGroup gate={appearGate.current} groupId="pf-ai" as="div" className="tw-p-6">
        <h3 className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-mb-4 tw-mt-0 tw-flex tw-items-center tw-gap-2">
          <Zap size={20} className="tw-text-accent" />
          Общий диагноз портфеля
        </h3>

        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-2 tw-gap-6 tw-mb-6">
          <Card>
            <h4 className="tw-text-[14px] tw-font-semibold tw-text-success tw-mt-0 tw-mb-3">
              Щит портфеля (Аргументы ЗА)
            </h4>
            <ul className="tw-flex tw-flex-col tw-gap-2 tw-m-0 tw-p-0 tw-list-none">
              {pros.map((t, i) => (
                <li key={i} className="tw-flex tw-items-start tw-gap-2 tw-text-[13px] tw-text-text-secondary">
                  <span aria-hidden="true" className="tw-text-success tw-mt-px tw-shrink-0">▲</span>
                  {t}
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <h4 className="tw-text-[14px] tw-font-semibold tw-text-danger tw-mt-0 tw-mb-3">
              Уязвимости (Аргументы ПРОТИВ)
            </h4>
            <ul className="tw-flex tw-flex-col tw-gap-2 tw-m-0 tw-p-0 tw-list-none">
              {cons.map((t, i) => (
                <li key={i} className="tw-flex tw-items-start tw-gap-2 tw-text-[13px] tw-text-text-secondary">
                  <span aria-hidden="true" className="tw-text-danger tw-mt-px tw-shrink-0">▼</span>
                  {t}
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <Card>
          <h4 className="tw-text-[13px] tw-font-medium tw-text-accent tw-mt-0 tw-mb-2">
            Резюме платформы
          </h4>
          <p className="tw-text-[14px] tw-text-text-secondary tw-leading-relaxed tw-m-0">
            Портфель представляет собой агрессивную ставку на российские голубые
            фишки с перекосом в дивидендную историю Сбербанка. Он хорошо держит
            инфляционный удар, но уязвим к сценарию жесткой ДКП и геополитическим
            шокам. Базовая рекомендация — ребалансировка и добавление защитных
            инструментов.
          </p>
        </Card>
      </AppearGroup>
    );
  };

  const renderStress = () => (
    <AppearGroup gate={appearGate.current} groupId="pf-stress" as="div" className="tw-p-6 tw-flex tw-flex-col tw-gap-6">
      <Card>
        <h4 className="tw-text-[16px] tw-font-semibold tw-text-text-primary tw-mb-4 tw-mt-0 tw-flex tw-items-center tw-gap-2">
          <ShieldAlert size={18} className="tw-text-accent" />
          Стресс-тестирование портфеля
        </h4>

        <div className="tw-flex tw-flex-wrap tw-gap-2 tw-mb-6">
          {[
            { id: "black_swan", label: "Черный лебедь (-20%)" },
            { id: "rate_up", label: "Ставка ЦБ +5%" },
            { id: "oil_crash", label: "Крах нефти ($40)" },
          ].map((s) => (
            <Chip key={s.id} selected={stressScenario === s.id} onClick={() => setStressScenario(s.id)}>
              {s.label}
            </Chip>
          ))}
        </div>

        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-2 tw-gap-4">
          <div className="tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-p-4">
            <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-1" style={{ letterSpacing: "0.06em" }}>
              Ожидаемое падение
            </div>
            <div className="tw-text-[24px] tw-font-display tw-font-light tw-text-danger tw-tabular-nums tw-mb-2">
              <span aria-hidden="true">▼ </span>{fmtPercent(currentStress.drop, { decimals: 1 })}
            </div>
            <ImpactBar value={-currentStress.drop} max={25} />
            <div className="tw-text-[12px] tw-text-text-tertiary tw-mt-2">{currentStress.label}</div>
          </div>

          <div className="tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-p-4">
            <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-1" style={{ letterSpacing: "0.06em" }}>
              Потеря стоимости
            </div>
            <div className="tw-text-[24px] tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums tw-mb-2">
              {formatMoney(currentStress.valueLoss, { decimals: 0 })}
            </div>
            <ImpactBar value={-currentStress.drop} max={25} />
            <div className="tw-text-[12px] tw-text-text-tertiary tw-mt-2">Оценка по текущей структуре портфеля</div>
          </div>
        </div>

        <div className="tw-mt-4 tw-flex tw-gap-3 tw-rounded-md tw-p-4 tw-bg-danger-soft" style={{ borderLeft: "3px solid var(--danger)" }}>
          <p className="tw-text-[13px] tw-text-text-secondary tw-m-0">
            <span className="tw-font-semibold tw-text-danger">Интерпретация платформы: </span>
            {currentStress.text}
          </p>
        </div>
      </Card>
    </AppearGroup>
  );

  // Empty states
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

  return (
    <div className="space-y-6">
      <div className="view-header">
        <h1 className="view-title">Аналитика портфеля</h1>
        <p className="view-subtitle">Управляйте позициями и отслеживайте результаты</p>
      </div>

      <div style={{
        display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center",
        gap: 16, background: "var(--accent-fade)", border: "1px solid var(--accent-border)",
        padding: "20px 24px", borderRadius: 16,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{
            padding: 10, background: "var(--accent)", color: "var(--on-accent)",
            borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Upload size={22} />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: "var(--text-1)" }}>Загрузить портфель</div>
            <div style={{ fontSize: 13, color: "var(--text-2)", marginTop: 2 }}>
              Импортируйте данные через текст или фото отчета брокера
            </div>
          </div>
        </div>

        {token ? (
          <button className="btn btn-primary" style={{ padding: "10px 20px" }} onClick={() => setShowUploadModal(true)}>
            <Plus size={16} /> Начать импорт
          </button>
        ) : (
          <button className="btn btn-ghost" style={{ padding: "10px 20px" }} onClick={onAuthRequired}>
            <User size={16} /> Войти для импорта
          </button>
        )}
      </div>

      {/* Stats row */}
      <div className="tw-grid tw-gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
        <KpiTile caption="Стоимость" value={<HeadlineNum value={stats.totalValue} gate={valueGate.current} />} />
        <KpiTile
          caption="Прибыль"
          value={<span className="tw-tabular-nums">{(stats.totalProfit >= 0 ? "▲ " : "▼ ") + formatMoney(Math.abs(stats.totalProfit), { decimals: 0 })}</span>}
          delta={stats.profitPct}
        />
        <KpiTile caption="Beta (Риск)" value={pfMetrics?.portfolio?.beta?.value != null ? fmtNumber(pfMetrics.portfolio.beta.value, { decimals: 2 }) : "—"} />
        <KpiTile caption="Див. доходность" value={pfMetrics?.portfolio?.div_yield?.value != null ? fmtPercent(pfMetrics.portfolio.div_yield.value, { decimals: 1 }) : "—"} />
      </div>

      {/* Здоровье портфеля — реальный индекс качества (сводка; полная
          декомпозиция и объяснения — во вкладке «Агрегирующая таблица») */}
      {pfMetrics?.quality?.overall != null && (
        <Card>
          <div className="tw-flex tw-items-baseline tw-gap-2 tw-mb-4">
            <span className="tw-text-[15px] tw-font-semibold tw-text-text-primary">Индекс качества</span>
            <span className="tw-text-[13px] tw-font-mono tw-tabular-nums tw-text-text-tertiary">{pfMetrics.quality.overall}/100</span>
            <Badge tone={QUALITY_TONE(pfMetrics.quality.overall)} className="tw-ml-auto">{pfMetrics.quality.label}</Badge>
          </div>
          <div className="tw-flex tw-flex-col tw-gap-3">
            {pfMetrics.quality.subindices.map((s) => (
              <MetricBar key={s.key} label={s.label} value={s.score} colorVar={QUALITY_BAR(s.score)} />
            ))}
          </div>
          <div className="tw-mt-3 tw-text-[12px] tw-text-text-tertiary">
            Из чего сложился и почему — во вкладке «Агрегирующая таблица».
          </div>
        </Card>
      )}

      {/* Tab bar — ARIA tablist with sliding accent underline (live language) */}
      <PortfolioTabBar
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "holdings", label: "Состав" },
          { id: "metrics", label: "Агрегирующая таблица" },
          { id: "returns", label: "Доходность и оценка" },
          { id: "risk", label: "Риск" },
          { id: "correlation", label: "Матрица корреляций" },
          { id: "ai", label: "ИИ-Диагноз" },
          { id: "stress", label: "Стресс-тест" },
        ]}
      />

      {/* Без внешней белой обёртки: внутренние карточки (таблицы, диаграмма,
          концентрация) лежат плитками прямо на фоне, как на других страницах —
          двойной «коробки в коробке» нет */}
      <div style={{ minHeight: 400 }}>
        {tab === "holdings" && renderHoldings()}
        {tab === "metrics" && renderAggregate()}
        {tab === "returns" && renderReturnsTab()}
        {tab === "risk" && renderRiskTab()}
        {tab === "correlation" && renderCorrelation()}
        {tab === "ai" && renderAiDiagnosis()}
        {tab === "stress" && renderStress()}
      </div>

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

// =========================
// PROFILE
// =========================

// =========================
// AUTH MODAL
// =========================


export { PortfolioView };
