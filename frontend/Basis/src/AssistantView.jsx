import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Plus,
  Trash2,
  Send,
  MessageSquare,
  User,
  AlertTriangle,
  PanelLeft,
  FileSearch,
  X as CloseIcon,
} from "lucide-react";
import "./styles/assistant.css";
import { useMobileSidebarDrawer, MobileDrawerBackdrop } from "./design/MobileSidebarDrawer";
import { BasisLogomark } from "./design/logomarks";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

// Результат разбора документа — вынесен отдельно, чтобы рендериться И в
// композере (inline-режим), И как обычная карточка в ленте (см. AssistantView).
function DocAnalyzeResult({ res }) {
  if (res?.error) {
    return (
      <div className="asst-docpanel-err">
        {res.error === "bad_url" ? "Нужна прямая ссылка http(s)://"
          : res.error === "fetch_failed" ? (res.note || "Документ не открылся (возможно, egress-ограничение сервера).")
          : res.error === "empty_text" ? (res.note || "Текст не извлёкся (вероятно скан-PDF без текстового слоя).")
          : res.error === "llm_unavailable" ? "Интерпретатор временно недоступен."
          : "Не удалось разобрать документ."}
      </div>
    );
  }
  if (!res) return null;
  return (
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
  );
}

// DocAnalyzePanel — демо «файл приходит агенту, он его анализирует» (владелец,
// 2026-07-21): вставь ссылку на PDF-отчётность МСФО/РСБУ или веб-страницу —
// агент открывает документ (pypdf для PDF), DeepSeek структурирует разбор.
// Бэк: POST /api/agents/analyze-document {url}. Egress-нюанс: на проде внешний
// хост может быть недоступен без релея — тогда честная ошибка, не падение.
// inline — компактная строка ввода для композера режима «Агент» (владелец,
// 2026-07-23): результат уходит наверх через onResult и рендерится в ленте
// как обычная карточка ответа, а не внутри самой панели.
function DocAnalyzePanel({ inline = false, onResult }) {
  const [url, setUrl] = useState("");
  const [res, setRes] = useState(null);
  const [state, setState] = useState("idle"); // idle | loading | error
  const run = () => {
    if (!/^https?:\/\//.test(url.trim())) {
      const errRes = { error: "bad_url" };
      setState("error"); setRes(errRes); onResult?.(errRes);
      return;
    }
    setState("loading"); setRes(null);
    onResult?.(null, "loading");
    fetch(`${API}/api/agents/analyze-document`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim() }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setRes(d); setState(d.error ? "error" : "done"); onResult?.(d); })
      .catch(() => { const errRes = { error: "network" }; setRes(errRes); setState("error"); onResult?.(errRes); });
  };

  if (inline) {
    return (
      <>
        <input type="url" value={url} onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          placeholder="https://…/report.pdf или ссылка на страницу с отчётностью"
          className="asst-textarea" aria-label="Ссылка на документ" />
        <button type="button" onClick={run} disabled={state === "loading" || !url.trim()} className="asst-send" aria-label="Разобрать">
          {state === "loading" ? <span className="asst-docpanel-spinner" /> : <FileSearch size={16} />}
        </button>
      </>
    );
  }

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
      <DocAnalyzeResult res={res} />
    </div>
  );
}

// Ассистент Basis — глобальный ИИ-чат. НЕ брокер, НЕ рекомендации «купить/продать».
// Контракт бэка: POST /api/assistant/ask, GET/DELETE /api/assistant/conversations.

// Пул подсказок сгруппирован по категориям (компания/мультипликатор, макро,
// скрининг/сравнение, гео/институты) — на каждое открытие вкладки берём по
// одной случайной из каждой категории (см. pickSuggestions ниже), чтобы
// подсказки были разными при каждом заходе, но не превращались в 4 случайных
// вопроса про одно и то же (владелец, 2026-07-25: раньше список был статичный).
const SUGGESTION_POOL = [
  ["Какой P/E у Сбербанка?", "Дивдоходность Лукойла — сколько и почему?",
   "Что со справедливой ценой Роснефти по модели Basis?", "Что с долгом у Норникеля?"],
  ["Что сейчас с макроэкономикой?", "Как решение по ключевой ставке влияет на банки?",
   "Что с курсом рубля и почему?", "Куда движется инфляция?"],
  ["Недооценённые компании с высокой дивдоходностью", "Сравни Лукойл и Роснефть по мультипликаторам",
   "Самые дешёвые акции по P/E прямо сейчас", "Какие компании сектора металлов сейчас интересны?"],
  ["Как санкции влияют на экспортёров?", "Что с институциональными рисками у госкомпаний?",
   "Что сейчас в ленте новостей по рынку?", "Какие компании больше всего зависят от геополитики?"],
];
function pickSuggestions() {
  return SUGGESTION_POOL.map((group) => group[Math.floor(Math.random() * group.length)]);
}

// Бэкенд-промпт (app/services/assistant.py) СТРОГО требует пометку в скобках
// после каждого численного утверждения — «(факт ... / оценка Basis ... /
// суждение ...)» — гарантированный формат, не хрупкий edge-case. Перехватываем
// и рендерим тегом канона (.bs-tag-fact/estimate/judgment) вместо голого текста.
// (?![а-яё]) вместо \b — в JS \w/\b по умолчанию ASCII-only, границу слова
// после кириллицы НЕ видит (проверено: \b молча не матчил вообще ничего),
// поэтому «не продолжение слова» проверяем явно (не пускаем «оценкам»/«фактически»).
const EPISTEMIC_RE = /\((факт|оценка|суждение|модель)(?![а-яё])([^)]*)\)/gi;
const EPISTEMIC_LABEL = { факт: "ФАКТ", оценка: "ОЦЕНКА", суждение: "СУЖДЕНИЕ", модель: "МОДЕЛЬ" };
const EPISTEMIC_CLASS = {
  факт: "bs-tag-fact", оценка: "bs-tag-estimate",
  суждение: "bs-tag-judgment", модель: "bs-tag-estimate",
};

function withEpistemicTags(text) {
  if (typeof text !== "string") return text;
  const out = [];
  let last = 0, m;
  EPISTEMIC_RE.lastIndex = 0;
  while ((m = EPISTEMIC_RE.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const kind = m[1].toLowerCase();
    out.push(
      <span key={m.index} className={EPISTEMIC_CLASS[kind]} style={{ marginLeft: 4 }}>
        {EPISTEMIC_LABEL[kind]}
      </span>
    );
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

// markdown-компоненты ответа ассистента (проза + таблицы из данных платформы)
const ASSISTANT_MD = {
  h1: ({ children }) => <h3>{children}</h3>,
  h2: ({ children }) => <h3>{children}</h3>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  p: ({ children }) => (
    <p>{React.Children.map(children, (c) => (typeof c === "string" ? withEpistemicTags(c) : c))}</p>
  ),
  li: ({ children }) => (
    <li>{React.Children.map(children, (c) => (typeof c === "string" ? withEpistemicTags(c) : c))}</li>
  ),
};

// «вчера» / «3 дн назад» / «22 июл» — под заголовком диалога в истории, чтобы
// одинаковые по названию диалоги (частый повтор одного вопроса) различались.
function formatRelative(iso) {
  if (!iso) return "";
  const d = new Date(iso), now = new Date();
  const days = Math.floor((now - d) / 86400000);
  if (days === 0) return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (days === 1) return "вчера";
  if (days < 7) return `${days} дн назад`;
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
}

function refIcon(kind) {
  if (kind === "company") return <MessageSquare size={12} aria-hidden="true" />;
  return null;
}

export default function AssistantView({ token, onAuthRequired, onOpenCompany }) {
  // Lazy-инициализатор — считается один раз ПРИ МОНТИРОВАНИИ компонента:
  // вкладка Ассистента рендерится через switch(section) в App.js (не
  // держится смонтированной в фоне), значит уход на другую вкладку и
  // возврат на «Ассистент» — это новый маунт → новый случайный набор.
  const [suggestions] = useState(pickSuggestions);
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
  // ≤760px: .asst-side был просто display:none без замены (владелец, 2026-07-21
  // «в ассистенте тоже фигня» — история диалогов была недостижима на телефоне).
  // Тот же переиспользуемый паттерн, что у Портфеля/Обозревателя/Скринера/Рынка
  // (design/MobileSidebarDrawer.jsx) — тот же хедер-тоггл (asst-sidebar-toggle)
  // на мобильном открывает overlay-drawer вместо grid-column-collapse.
  const [mobileDrawerOpen, setMobileDrawerOpen, drawerNarrow] = useMobileSidebarDrawer();
  const toggleSidebar = () => {
    if (drawerNarrow) setMobileDrawerOpen((v) => !v);
    else setSidebarCollapsed((v) => !v);
  };
  // ОТК (CRITICAL): .asst-side на мобильном — msd-drawer (position:fixed,
  // transform управляет видимостью), но desktop-правило .collapsed гасит его
  // opacity:0/pointer-events:none — та же специфичность и более позднее
  // положение в assistant.css побеждало мою CSS-починку по каскаду. Чище —
  // не переживать desktop-collapsed через смену брейкпоинта вообще: если
  // пользователь свернул сайдбар на десктопе, потом сузил окно до ≤760px,
  // sidebarCollapsed сбрасывается — drawer открывается с чистого состояния,
  // а не унаследованным opacity:0 без transform-компенсации.
  useEffect(() => {
    if (drawerNarrow) setSidebarCollapsed(false);
  }, [drawerNarrow]);

  const feedRef = useRef(null);
  const textareaRef = useRef(null);
  const lastSentRef = useRef(null); // последнее сообщение — для повтора при ошибке

  // Режим «Агент» (разбор отчёта по ссылке) — владелец, 2026-07-23: было плохо
  // видно (мелкая ссылка только в пустом состоянии), нужно как «+» у Клода/
  // ChatGPT: явный переключатель режима, при включении композер меняет смысл
  // (текст поля + текст-подсказка), не отдельная скрытая панель. Функция пока
  // одна — сразу кнопка-тумблер, без меню на одну позицию.
  const [agentMode, setAgentMode] = useState(false);
  const [docResult, setDocResult] = useState(null);
  const [docLoading, setDocLoading] = useState(false);
  const handleDocResult = (res, state) => {
    setDocLoading(state === "loading");
    if (state !== "loading") setDocResult(res);
  };
  const toggleAgentMode = () => {
    setAgentMode((v) => !v);
    setDocResult(null); setDocLoading(false);
  };

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
    // Оптимистично — сайдбар подсвечивает клик и лента чистится СРАЗУ, не после
    // ответа сервера (владелец, 2026-07-23: «клик на любой другой чат не сразу
    // срабатывает» — activeId раньше менялся только post-fetch, поэтому клик
    // визуально «не срабатывал» на весь round-trip, а старые сообщения оставались
    // на экране вперемешку с индикатором «печатает» нового диалога).
    setActiveId(id);
    setMessages([]);
    setLoadingConv(true);
    setMobileDrawerOpen(false);
    setAgentMode(false); setDocResult(null); setDocLoading(false);
    try {
      const r = await fetch(`${API}/api/assistant/conversations/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.status === 401) { onAuthRequired && onAuthRequired(); return; }
      if (r.ok) {
        const data = await r.json();
        setActiveId(data.id);
        setMessages(Array.isArray(data.messages) ? data.messages : []);
      } else {
        setError({ text: "Не удалось загрузить диалог. Попробуйте ещё раз.", canRetry: false });
      }
    } catch {
      setError({ text: "Нет связи с сервером. Проверьте соединение и повторите.", canRetry: false });
    }
    finally { setLoadingConv(false); }
  };

  const startNew = () => {
    setActiveId(null);
    setMessages([]);
    setError(null);
    setInput("");
    setMobileDrawerOpen(false);
    setAgentMode(false); setDocResult(null); setDocLoading(false);
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
          <div className="asst-invite-icon"><BasisLogomark size={36} /></div>
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

  // !loadingConv — иначе на время загрузки другого диалога (messages уже очищен
  // оптимистично в openConversation, см. комментарий там) на миг мелькает
  // приглашение «Чем помочь?» вместо индикатора «печатает».
  const empty = messages.length === 0 && !sending && !loadingConv;

  return (
    <div className="asst-wrap-outer">
      {mobileDrawerOpen && <MobileDrawerBackdrop onClose={() => setMobileDrawerOpen(false)} />}
      <div className={`asst-shell${sidebarCollapsed ? " collapsed" : ""}`}>
        {/* История диалогов — на ≤760px это msd-drawer (overlay), на десктопе
            обычная колонка, которую сворачивает .collapsed (grid-column). */}
        <aside
          className={`asst-side msd-drawer${mobileDrawerOpen ? " msd-drawer--open" : ""}`}
          inert={(drawerNarrow ? !mobileDrawerOpen : sidebarCollapsed) || undefined}
        >
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
                  <MessageSquare size={14} style={{ flexShrink: 0 }} />
                  <span className="asst-conv-title">{c.title || "Без названия"}</span>
                  <span className="asst-conv-time">{formatRelative(c.updated_at)}</span>
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
              onClick={toggleSidebar}
              title="Скрыть/показать историю диалогов"
              aria-label="Скрыть/показать историю диалогов"
              aria-expanded={drawerNarrow ? mobileDrawerOpen : !sidebarCollapsed}
            >
              <PanelLeft size={16} />
            </button>
            <span className="asst-head-icon"><BasisLogomark size={20} /></span>
            <div>
              <div className="asst-head-title">Ассистент Basis</div>
              <div className="asst-head-sub">Помогает ориентироваться в данных платформы · не даёт рекомендаций «купить/продать»</div>
            </div>
          </header>

          <div className="asst-feed" ref={feedRef}>
            {empty ? (
              <div className="asst-empty">
                <div className="asst-empty-icon"><BasisLogomark size={28} /></div>
                <h2>Чем помочь?</h2>
                <p>Спросите о компании, метрике или рыночном фоне обычным языком — я отвечу на основе данных Basis.</p>
                <div className="asst-suggests">
                  {suggestions.map((s) => (
                    <button key={s} type="button" className="asst-suggest" onClick={() => doSend(s)}>{s}</button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {loadingConv && (
                  <div className="asst-row assistant">
                    <span className="asst-avatar"><BasisLogomark size={17} /></span>
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
                      <span className="asst-avatar"><BasisLogomark size={17} /></span>
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
                    <span className="asst-avatar"><BasisLogomark size={17} /></span>
                    <div className="asst-bubble-asst"><div className="asst-typing"><span /><span /><span /></div></div>
                  </div>
                )}
              </>
            )}
            {agentMode && (docLoading || docResult) && (
              <div className="asst-row assistant">
                <span className="asst-avatar"><FileSearch size={15} /></span>
                <div className="asst-bubble-asst">
                  {docLoading ? (
                    <div className="asst-typing"><span /><span /><span /></div>
                  ) : (
                    <DocAnalyzeResult res={docResult} />
                  )}
                </div>
              </div>
            )}
            {!empty && <div className="asst-feed-watermark"><BasisLogomark size={200} /></div>}
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
            {agentMode && (
              <div className="asst-mode-line">
                <span className="asst-mode-dot" />
                <span>
                  <b>Агентский режим</b> — в нём вы разбираете отчёты: пришлите ссылку на PDF (МСФО/РСБУ)
                  или страницу с отчётностью, агент скачает и структурирует разбор.
                </span>
              </div>
            )}
            <div className="asst-inputrow">
              <button
                type="button"
                className={`asst-mode-toggle${agentMode ? " on" : ""}`}
                onClick={toggleAgentMode}
                title="Агентский режим — разбор отчёта по ссылке"
                aria-pressed={agentMode}
              >
                {agentMode ? <CloseIcon size={14} /> : <Plus size={15} />}
                <span>Агент</span>
              </button>
              {agentMode ? (
                <DocAnalyzePanel inline onResult={handleDocResult} />
              ) : (
                <>
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
                </>
              )}
            </div>
            <p className="asst-disclaimer">
              {agentMode
                ? "Разбор документа — демо, не аудит: числа берутся только из текста, без выдумывания."
                : (<>Ассистент не даёт индивидуальных инвестиционных рекомендаций и не советует покупать
                  или продавать — только помогает ориентироваться в данных платформы. Enter — отправить, Shift+Enter — перенос строки.</>)}
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
