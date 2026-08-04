import { IconArrowLeft, IconBrandWhatsapp, IconCalendar, IconDatabase, IconMessageCircle, IconRefresh, IconSearch, IconUserPlus, IconX } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState } from "react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Toast from "../components/UI/Toast.jsx";

export default function WhatsAppMessages() {
  const [sessions, setSessions] = useState([]);
  const [rowCount, setRowCount] = useState(0);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState(null);
  const chatRef = useRef(null);

  const loadSessions = () => {
    setLoading(true);
    api.get("/communication/whatsapp-sessions")
      .then(({ data }) => {
        const conversations = consolidateSessions(data.items || []);
        setSessions(conversations);
        setRowCount(data.total || 0);
        if (data.error) setToast({ type: "error", message: data.error });
        setSelected((current) => {
          if (current) return conversations.find((item) => item.phone === current.phone) || null;
          return window.matchMedia("(min-width: 761px)").matches ? conversations[0] || null : null;
        });
      })
      .catch(() => setToast({ type: "error", message: "Could not load WhatsApp conversations" }))
      .finally(() => setLoading(false));
  };

  const syncLeads = () => {
    setSyncing(true);
    api.post("/communication/sync-whatsapp-leads")
      .then(({ data }) => setToast({ type: "success", message: `${data.created || 0} leads added, ${data.updated || 0} leads updated` }))
      .catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Could not sync WhatsApp leads" }))
      .finally(() => setSyncing(false));
  };

  useEffect(() => { loadSessions(); }, []);

  useEffect(() => {
    if (!selected?.phone) {
      setHistory(null);
      return;
    }
    setHistory(null);
    setHistoryLoading(true);
    api.get(`/communication/whatsapp-history/${encodeURIComponent(selected.phone)}`)
      .then(({ data }) => {
        setHistory(data);
        if (data.error) setToast({ type: "error", message: data.error });
      })
      .catch(() => setToast({ type: "error", message: "Could not load conversation" }))
      .finally(() => setHistoryLoading(false));
  }, [selected?.phone]);

  useEffect(() => {
    if (chatRef.current && !historyLoading) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [history, historyLoading]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return sessions;
    return sessions.filter((item) => [item.name, item.phone, item.last_message?.text, item.conversation].some((value) => String(value || "").toLowerCase().includes(term)));
  }, [sessions, query]);

  const groupedMessages = useMemo(() => (history?.messages || []).reduce((groups, message) => {
    const date = message.chat_date || "Unknown date";
    if (!groups[date]) groups[date] = [];
    groups[date].push(message);
    return groups;
  }, {}), [history]);

  const activeMessages = history?.messages || [];
  const activeName = history?.name || selected?.name || selected?.phone || "Unknown contact";

  return <div className={`whatsapp-live-page refined-whatsapp ${selected ? "has-selection" : ""}`}>
    <aside className="wa-live-sidebar">
      <div className="wa-live-title"><div className="wa-live-icon"><IconBrandWhatsapp size={22} /></div><div><h2>Conversations</h2><span>{sessions.length} contacts · {rowCount} database rows</span></div><button className="wa-refresh-icon" type="button" onClick={syncLeads} disabled={syncing} title="Sync contacts to leads"><IconUserPlus className={syncing ? "spinning" : ""} size={17} /></button><button className="wa-refresh-icon" type="button" onClick={loadSessions} disabled={loading} title="Refresh conversations"><IconRefresh className={loading ? "spinning" : ""} size={17} /></button></div>

      <label className="wa-live-search"><IconSearch size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, phone or message" />{query && <button type="button" onClick={() => setQuery("")} aria-label="Clear search"><IconX size={15} /></button>}</label>

      <div className="wa-list-status"><span>{query ? `${filtered.length} matching` : `${filtered.length} conversations`}</span><Badge tone="teal">Lead sync ready</Badge></div>

      <div className="wa-session-list">
        {loading && <ConversationSkeleton />}
        {!loading && filtered.map((item) => <button type="button" className={`wa-session-item ${selected?.phone === item.phone ? "active" : ""}`} key={item.phone} onClick={() => setSelected(item)}>
          <div className="wa-session-avatar">{initialFor(item)}</div>
          <div className="wa-session-copy"><div><strong>{item.name || "Unknown contact"}</strong><time>{compactDate(item.updated_at || item.chat_date)}</time></div><span>{formatPhone(item.phone)}</span><small>{lastText(item)}</small></div>
          <div className="wa-session-count"><IconMessageCircle size={13} /><span>{item.message_count}</span></div>
        </button>)}
        {!loading && !filtered.length && <div className="wa-empty wa-list-empty"><IconSearch size={24} /><strong>{query ? "No matching conversations" : "No WhatsApp conversations"}</strong><span>{query ? "Try a different name, phone number or message." : "Bot database conversations will appear here."}</span></div>}
      </div>
    </aside>

    <section className="wa-live-chat">
      {selected ? <>
        <header className="wa-live-chat-head">
          <button className="wa-mobile-back" type="button" onClick={() => setSelected(null)} aria-label="Back to conversations"><IconArrowLeft size={19} /></button>
          <div className="wa-avatar">{initialFor({ name: activeName, phone: selected.phone })}</div>
          <div className="wa-chat-identity"><h2>{activeName}</h2><span>{formatPhone(selected.phone)}</span></div>
          <div className="wa-chat-meta"><span><IconMessageCircle size={14} />{activeMessages.length || selected.message_count} messages</span><span><IconCalendar size={14} />{history?.total_days || selected.day_count || 1} days</span><Badge tone="teal">Bot history</Badge></div>
        </header>

        <div className="wa-live-chat-window" ref={chatRef}>
          {historyLoading && <ChatSkeleton />}
          {!historyLoading && activeMessages.length > 0 && Object.entries(groupedMessages).map(([date, messages]) => <div className="wa-day-group" key={date}><div className="wa-date-divider">{formatDate(date)}</div>{messages.map((message, index) => <div className={`wa-message-row ${message.role}`} key={`${date}-${message.time}-${index}`}><div className="wa-bubble">{message.role === "user" && <strong>{activeName}</strong>}<p>{message.text}</p><time>{message.time}</time></div></div>)}</div>)}
          {!historyLoading && !activeMessages.length && <div className="wa-empty wa-chat-empty"><IconMessageCircle size={28} /><strong>No parsed messages</strong><span>This database conversation does not contain messages in the supported [User/Bot HH:MM] format.</span></div>}
        </div>

        {history?.summaries?.length > 0 && <details className="wa-live-summaries"><summary><span><IconDatabase size={15} />AI conversation summaries</span><Badge>{history.summaries.length}</Badge></summary><div>{history.summaries.map((summary) => <article key={`${summary.summary_date}-${summary.summary_text}`}><time>{formatDate(summary.summary_date)}</time><p>{summary.summary_text}</p></article>)}</div></details>}
      </> : <div className="wa-empty wa-chat-placeholder"><div className="wa-placeholder-icon"><IconBrandWhatsapp size={34} /></div><strong>Select a conversation</strong><span>Choose a contact to read their complete bot conversation history.</span></div>}
    </section>
    <Toast toast={toast} />
  </div>;
}

function consolidateSessions(rows) {
  const conversations = new Map();
  rows.forEach((row) => {
    const key = normalizePhone(row.phone) || `${row.name || "unknown"}-${row.chat_date || ""}`;
    const existing = conversations.get(key);
    if (!existing) {
      conversations.set(key, { ...row, phone: row.phone || key, message_count: Number(row.message_count || 0), day_count: 1 });
      return;
    }
    existing.message_count += Number(row.message_count || 0);
    existing.day_count += 1;
    if (!existing.name && row.name) existing.name = row.name;
  });
  return [...conversations.values()];
}

function ConversationSkeleton() { return <div className="wa-conversation-skeleton">{[1, 2, 3, 4, 5].map((item) => <div key={item}><span /><p><i /><i /><i /></p></div>)}</div>; }
function ChatSkeleton() { return <div className="wa-chat-skeleton"><span /><p /><p /><p /><p /></div>; }
function normalizePhone(value) { return String(value || "").replace(/\D/g, ""); }
function initialFor(item) { return (item.name || item.phone || "?").trim().slice(0, 1).toUpperCase(); }
function formatPhone(value) { const digits = normalizePhone(value); if (digits.length === 12 && digits.startsWith("91")) return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`; return value || "No phone number"; }
function formatDate(value) { if (!value || value === "Unknown date") return "Unknown date"; const parsed = new Date(`${String(value).slice(0, 10)}T00:00:00`); return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }); }
function compactDate(value) { if (!value) return ""; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? "" : parsed.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }); }
function lastText(item) { const raw = item.last_message?.text || item.conversation?.split("\n").filter(Boolean).at(-1) || "No messages"; return String(raw).replace(/^\[(?:User|Bot)\s+\d{1,2}:\d{2}\]\s*/i, ""); }
