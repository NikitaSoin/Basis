import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Sparkles,
  Plus,
  Trash2,
  Send,
  MessageSquare,
  User,
  AlertTriangle,
  PanelLeft,
  FileSearch,
} from "lucide-react";
import "./styles/assistant.css";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

// DocAnalyzePanel — демо «файл приходит агенту, он его анализирует» (владелец,
// 2026-07-21): вставь ссылку на PDF-отчётность МСФО/РСБУ или веб-страницу —
// агент открывает документ (pypdf для PDF), DeepSeek структурирует разбор.
// Бэк: POST /api/agents/analyze-document {url}. Egress-нюанс: на проде внешний
// хост может быть недоступен без релея — тогда честная ошибка, не падение.
function DocAnalyzePanel() {
  const [url, setUrl] = useState("");
  const [res, setRes] = useState(null);
  const [state, setState] = useState("idle"); // idle | loading | error
  const run = () => {
    if (!/^https?:\/\//.test(url.trim())) { setState("error"); setRes({ error: "bad_url" }); return; }
    setState("loading"); setRes(null);
    fetch(`${API}/api/agents/analyze-document`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim() }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setRes(d); setState(d.error ? "error" : "done"); })
      .catch(() => { setRes({ error: "network" }); setState("error"); });
  };
  return (
    <div className="asst-docpanel">
      <div className="asst-docpanel-head"><FileSearch size={16} /> Разбор документа по ссылке <span className="asst-docpanel-demo">демо</span></div>
      <p className="asst-docpanel-sub">Вставьте ссылку на PDF-отчётность (МСФО/РСБУ) или страницу — агент откроет и структурирует разбор.</p>
      <div className="asst-docpanel-row">
        <input type="url" value={url} onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          placeholder="https://…/report.pdf" className="asst-docpanel-input" />
        <button type="button" onClick={run} disabled={state === "loading"} className="asst-docpanel-btn">
          {state === "loading" ? "Читаю документ…" : "Разобрать"}
        </button>
      </div>
      {res?.error && (
        <div className="asst-docpanel-err">
          {res.error === "bad_url" ? "Нужна прямая ссылка http(s)://"
            : res.error === "fetch_failed" ? (res.note || "Документ не открылся (возможно, egress-ограничение сервера).")
            : res.error === "empty_text" ? (res.note || "Текст не извлёкся (вероятно скан-PDF без текстового слоя).")
            : res.error === "llm_unavailable" ? "Интерпретатор временно недоступен."
            : "Не удалось разобрать документ."}
        </div>
      )}
      {res && !res.error && (
        <div className="asst-docpanel-res">
          <div className="asst-docpanel-type">{res.doc_type}</div>
          <p className="asst-docpanel-summary">{res.summary}</p>
          {res.key_figures?.length > 0 && (
            <table className="asst-docpanel-table"><tbody>
              {res.key_figures.map((k, i) => (
                <tr key={i}><td>{k.metric}</td><td className="num">{k.value}</td><td className="note">{k.note}</td></tr>
              ))}
            </tbody></table>
          )}
          {res.highlights?.length > 0 && (
            <ul className="asst-docpanel-list">{res.highlights.map((h, i) => <li key={i}>{h}</li>)}</ul>
          )}
          {res.risks_or_caveats?.length > 0 && (
            <div className="asst-docpanel-risks"><b>На что обратить внимание:</b> {res.risks_or_caveats.join(" · ")}</div>
          )}
          <div className="asst-docpanel-foot">
            Источник: {res.source?.kind?.toUpperCase()} · {res.source?.chars} симв. · разбор ИИ (демо), не аудит.
          </div>
        </div>
      )}
    </div>
  );
}

// Ассистент Basis — глобальный ИИ-чат. НЕ брокер, НЕ рекомендации «купить/продать».
// Контракт бэка: POST /api/assistant/ask, GET/DELETE /api/assistant/conversations.

const SUGGESTIONS = [
  "Какой P/E у Сбербанка?",
  "Что сейчас с макроэкономикой?",
  "Недооценённые компании с высокой дивдоходностью",
  "Сравни Лукойл и Роснефть по мультипликаторам",
];

// markdown-компоненты ответа ассистента (проза + таблицы из данных платформы)
const ASSISTANT_MD = {
  h1: ({ children }) => <h3>{children}</h3>,
  h2: ({ children }) => <h3>{children}</h3>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
};

function refIcon(kind) {
  if (kind === "company") return <MessageSquare size={12} aria-hidden="true" />;
  return null;
}

export default function AssistantView({ token, onAuthRequired, onOpenCompany }) {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null); // { text, canRetry }
  const [loadingConv, setLoadingConv] = useState(false);
  // Сворачивает историю диалогов на всю ширину чата (мокап: кнопка в шапке
  // переключает .asst-shell.collapsed, grid-template-columns 280px 1fr → 0px 1fr).
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const feedRef = useRef(null);
  const textareaRef = useRef(null);
  const lastSentRef = useRef(null); // последнее сообщение — для повтора при ошибке

  const authHeaders = useCallback(
    () => ({ "Content-Type": "application/json", Authorization: `Bearer ${token}` }),
    [token]
  );

  // ---- список диалогов ----
  const loadConversations = useCallback(async () => {
    if (!token) return;
    try {
      const r = await fetch(`${API}/api/assistant/conversations?limit=30`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.status === 401) { onAuthRequired && onAuthRequired(); return; }
      if (!r.ok) return;
      const data = await r.json();
      if (Array.isArray(data)) setConversations(data);
    } catch { /* сеть — тихо, чат остаётся рабочим */ }
  }, [token, onAuthRequired]);

  useEffect(() => { loadConversations(); }, [loadConversations]);

  // автоскролл ленты вниз при новом сообщении / индикаторе
  useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  // авто-высота textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [input]);

  const openConversation = async (id) => {
    if (id === activeId) return;
    setError(null);
    setLoadingConv(true);
    try {
      const r = await fetch(`${API}/api/assistant/conversations/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.status === 401) { onAuthRequired && onAuthRequired(); return; }
      if (r.ok) {
        const data = await r.json();
        setActiveId(data.id);
        setMessages(Array.isArray(data.messages) ? data.messages : []);
      }
    } catch { /* оставляем как есть */ }
    finally { setLoadingConv(false); }
  };

  const startNew = () => {
    setActiveId(null);
    setMessages([]);
    setError(null);
    setInput("");
    if (textareaRef.current) textareaRef.current.focus();
  };

  const deleteConversation = async (id, e) => {
    e.stopPropagation();
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (id === activeId) startNew();
    try {
      await fetch(`${API}/api/assistant/conversations/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch { /* даже если не удалось на сервере — вернём при следующей загрузке */ }
  };

  const doSend = async (text) => {
    const msg = (text != null ? text : input).trim();
    if (!msg || sending) return;
    lastSentRef.current = msg;
    setError(null);
    setInput("");
    setSending(true);
    // оптимистично добавляем реплику пользователя
    const optimistic = { id: `tmp-${Date.now()}`, role: "user", content: msg, source_refs: [] };
    setMessages((prev) => [...prev, optimistic]);
    try {
      const r = await fetch(`${API}/api/assistant/ask`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ message: msg, conversation_id: activeId }),
      });
      if (r.status === 401) { onAuthRequired && onAuthRequired(); setSending(false); return; }
      if (!r.ok) {
        let detail = "";
        try { detail = (await r.json()).detail || ""; } catch { /* нет тела */ }
        if (r.status === 503) {
          setError({ text: detail || "Ассистент временно недоступен. Попробуйте ещё раз.", canRetry: true });
        } else if (r.status === 400) {
          setError({ text: detail || "Вопрос слишком короткий или слишком длинный.", canRetry: false });
        } else {
          setError({ text: detail || "Не удалось получить ответ. Попробуйте ещё раз.", canRetry: true });
        }
        // откатываем оптимистичную реплику, возвращаем текст в поле
        setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
        setInput(msg);
        setSending(false);
        return;
      }
      const data = await r.json();
      setActiveId(data.id);
      setMessages(Array.isArray(data.messages) ? data.messages : []);
      loadConversations();
    } catch {
      setError({ text: "Нет связи с сервером. Проверьте соединение и повторите.", canRetry: true });
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setInput(msg);
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSend();
    }
  };

  // ---- не залогинен: приглашение ----
  if (!token) {
    return (
      <div>
        <div className="asst-invite">
          <div className="asst-invite-icon"><Sparkles size={32} /></div>
          <h2>Ассистент Basis</h2>
          <p>
            Задавайте вопросы о компаниях, мультипликаторах, макроэкономике и данных
            платформы обычным языком. Войдите в аккаунт, чтобы начать диалог.
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn btn-primary" style={{ padding: "11px 24px" }} onClick={onAuthRequired}>Войти</button>
            <button className="btn btn-ghost" style={{ padding: "11px 24px" }} onClick={onAuthRequired}>Зарегистрироваться</button>
          </div>
          <p style={{ fontSize: 11, color: "var(--text-3)", marginTop: 24, maxWidth: 420 }}>
            Ассистент не даёт индивидуальных инвестиционных рекомендаций и не советует покупать
            или продавать — только помогает ориентироваться в данных Basis.
          </p>
        </div>
      </div>
    );
  }

  const empty = messages.length === 0 && !sending;

  return (
    <div className="asst-wrap-outer">
      <div className={`asst-shell${sidebarCollapsed ? " collapsed" : ""}`}>
        {/* История диалогов */}
        <aside className="asst-side" inert={sidebarCollapsed || undefined}>
          <button type="button" className="asst-new" onClick={startNew}>
            <Plus size={15} /> Новый диалог
          </button>
          <div className="asst-side-label">История</div>
          <div className="asst-side-list">
            {conversations.length === 0 ? (
              <div className="asst-side-empty">Пока нет диалогов. Задайте первый вопрос — он появится здесь.</div>
            ) : (
              conversations.map((c) => (
                <div
                  key={c.id}
                  className={`asst-conv${c.id === activeId ? " is-active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => openConversation(c.id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openConversation(c.id); } }}
                >
                  <MessageSquare size={14} style={{ flexShrink: 0, color: "var(--text-3)" }} />
                  <span className="asst-conv-title">{c.title || "Без названия"}</span>
                  <button
                    type="button"
                    className="asst-conv-del"
                    aria-label="Удалить диалог"
                    onClick={(e) => deleteConversation(c.id, e)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Чат */}
        <section className="asst-main">
          <header className="asst-head">
            <button
              type="button"
              className="asst-sidebar-toggle"
              onClick={() => setSidebarCollapsed((v) => !v)}
              title="Скрыть/показать историю диалогов"
              aria-label="Скрыть/показать историю диалогов"
              aria-expanded={!sidebarCollapsed}
            >
              <PanelLeft size={16} />
            </button>
            <span className="asst-head-icon"><Sparkles size={18} /></span>
            <div>
              <div className="asst-head-title">Ассистент Basis</div>
              <div className="asst-head-sub">Помогает ориентироваться в данных платформы · не даёт рекомендаций «купить/продать»</div>
            </div>
          </header>

          <div className="asst-feed" ref={feedRef}>
            {empty ? (
              <div className="asst-empty">
                <div className="asst-empty-icon"><Sparkles size={26} /></div>
                <h2>Чем помочь?</h2>
                <p>Спросите о компании, метрике или рыночном фоне обычным языком — я отвечу на основе данных Basis.</p>
                <div className="asst-suggests">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" className="asst-suggest" onClick={() => doSend(s)}>{s}</button>
                  ))}
                </div>
                <DocAnalyzePanel />
              </div>
            ) : (
              <>
                {loadingConv && (
                  <div className="asst-row assistant">
                    <span className="asst-avatar"><Sparkles size={15} /></span>
                    <div className="asst-bubble-asst"><div className="asst-typing"><span /><span /><span /></div></div>
                  </div>
                )}
                {messages.map((m) => (
                  m.role === "user" ? (
                    <div key={m.id} className="asst-row user">
                      <div className="asst-bubble-user">{m.content}</div>
                    </div>
                  ) : (
                    <div key={m.id} className="asst-row assistant">
                      <span className="asst-avatar"><Sparkles size={15} /></span>
                      <div className="asst-bubble-asst">
                        <div className="asst-md">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={ASSISTANT_MD}>
                            {m.content || ""}
                          </ReactMarkdown>
                        </div>
                        {Array.isArray(m.source_refs) && m.source_refs.length > 0 && (
                          <div className="asst-refs">
                            {m.source_refs.map((ref, i) => {
                              const label = ref.title || ref.ticker || ref.kind;
                              const clickable = ref.kind === "company" && ref.ticker && onOpenCompany;
                              const inner = (
                                <>
                                  {refIcon(ref.kind)}
                                  {ref.ticker && <span className="asst-ref-tk">{ref.ticker}</span>}
                                  <span>{label}</span>
                                  {ref.as_of && <span style={{ color: "var(--text-3)" }}>· {ref.as_of}</span>}
                                </>
                              );
                              return clickable ? (
                                <button key={i} type="button" className="asst-ref" onClick={() => onOpenCompany(ref.ticker)}>{inner}</button>
                              ) : (
                                <span key={i} className="asst-ref">{inner}</span>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                ))}
                {sending && (
                  <div className="asst-row assistant">
                    <span className="asst-avatar"><Sparkles size={15} /></span>
                    <div className="asst-bubble-asst"><div className="asst-typing"><span /><span /><span /></div></div>
                  </div>
                )}
              </>
            )}
          </div>

          {error && (
            <div className="asst-error" role="alert">
              <AlertTriangle size={16} style={{ color: "var(--danger)", flexShrink: 0 }} />
              <span>{error.text}</span>
              {error.canRetry && (
                <button className="asst-error-retry" onClick={() => doSend(lastSentRef.current)}>Повторить</button>
              )}
            </div>
          )}

          <div className="asst-composer">
            <div className="asst-inputrow">
              <textarea
                ref={textareaRef}
                className="asst-textarea"
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Спросите о компании, метрике или рынке…"
                aria-label="Сообщение ассистенту"
                disabled={sending}
              />
              <button
                type="button"
                className="asst-send"
                onClick={() => doSend()}
                disabled={sending || !input.trim()}
                aria-label="Отправить"
              >
                <Send size={17} />
              </button>
            </div>
            <p className="asst-disclaimer">
              Ассистент не даёт индивидуальных инвестиционных рекомендаций и не советует покупать
              или продавать — только помогает ориентироваться в данных платформы. Enter — отправить, Shift+Enter — перенос строки.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
