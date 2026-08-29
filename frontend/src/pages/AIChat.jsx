import { useEffect, useMemo, useRef, useState } from "react";
import {
  IconArrowLeft, IconArrowUp, IconDatabase, IconHistory, IconMenu2, IconMessage,
  IconPlus, IconRobot, IconShieldCheck, IconSparkles, IconTable, IconX,
} from "@tabler/icons-react";
import api from "../api/client";
import Button from "../components/UI/Button.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";

const suggestions = [
  "How many leads were added today?",
  "Show today's leads in a table",
  "Compare academic and project demand",
  "Which tasks are overdue?",
];

const sourceNames = {
  leads: "Leads", customers: "Customers", tasks: "Tasks", notifications: "Notifications",
  communications: "Communication", campaigns: "Campaigns", employees: "Employees", workflows: "Workflows",
  ai_followups: "AI Follow-ups",
};

function AnswerTable({ table }) {
  if (!table?.rows?.length || !table?.columns?.length) return null;
  return <div className="ai-table-wrap"><table className="ai-result-table">
    <thead><tr>{table.columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead>
    <tbody>{table.rows.map((row, index) => <tr key={row.id ?? index}>{table.columns.map((column) => <td data-label={column.label} key={column.key}>{row[column.key] ?? "-"}</td>)}</tr>)}</tbody>
  </table></div>;
}

function ChatExchange({ item }) {
  const data = item.structured;
  const sources = (item.sources || "CRM database").split(",").filter(Boolean);
  const points = data?.points?.length ? data.points : (data?.metrics || []).map((metric) => `${metric.label}: ${metric.value}`);
  const sections = data?.sections?.length ? data.sections : (points.length ? [{ title: "Key details", points }] : []);
  return <article className="ai-exchange">
    <div className="ai-user-message"><div className="ai-message-avatar">You</div><div className="ai-user-bubble">{item.prompt}</div></div>
    <div className="ai-assistant-message">
      <div className="ai-bot-avatar"><IconSparkles size={18} /></div>
      <div className="ai-assistant-content">
        <div className="ai-assistant-title"><strong>{data?.title || "CRM answer"}</strong><span><i />Live CRM data</span></div>
        <p>{item.response}</p>
        {!!sections.length && <div className="ai-answer-sections">{sections.map((section, sectionIndex) => <section key={`${section.title}-${sectionIndex}`}><h4>{section.title}</h4><ul className="ai-answer-points">{(section.points || []).map((point, index) => <li key={`${point}-${index}`}>{point}</li>)}</ul></section>)}</div>}
        <AnswerTable table={data?.table} />
        {!!data?.notes?.length && <div className="ai-notes">{data.notes.map((note) => <span key={note}>{note}</span>)}</div>}
        <footer className="ai-message-meta"><span><IconDatabase size={14} />{sources.map((source) => sourceNames[source] || source).join(" · ")}</span><span><IconShieldCheck size={14} />{data?.scope || "Authorized records"}</span><time>{formatMessageTime(item.created_at)}</time></footer>
      </div>
    </div>
  </article>;
}

export default function AIChat() {
  const { user } = useAuth();
  const [prompt, setPrompt] = useState("");
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [capabilities, setCapabilities] = useState({ sources: ["leads", "customers", "tasks"], scope: "assigned" });
  const [asking, setAsking] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const endRef = useRef(null);
  const visibleSources = useMemo(() => capabilities.sources.map((source) => sourceNames[source] || source), [capabilities.sources]);
  const activeConversation = conversations.find((item) => item.id === activeId);

  const loadConversations = (selectFirst = false) => api.get("/ai-chat/conversations").then(({ data }) => {
    setConversations(data);
    if (selectFirst && data.length) setActiveId(data[0].id);
    return data;
  });

  useEffect(() => {
    Promise.allSettled([loadConversations(true), api.get("/ai-chat/capabilities")]).then(([, capabilityResult]) => {
      if (capabilityResult.status === "fulfilled") setCapabilities(capabilityResult.value.data);
    });
  }, []);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    setLoadingChat(true);
    api.get("/ai-chat/history", { params: { conversation_id: activeId } })
      .then(({ data }) => setMessages(data))
      .catch(() => setToast({ type: "error", message: "Could not load this conversation" }))
      .finally(() => setLoadingChat(false));
  }, [activeId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, asking]);

  const newChat = () => {
    setActiveId(null);
    setMessages([]);
    setPrompt("");
    setHistoryOpen(false);
  };

  const openConversation = (id) => {
    setActiveId(id);
    setHistoryOpen(false);
  };

  const ask = (event, text = prompt) => {
    event?.preventDefault();
    const question = text.trim();
    if (!question || asking) return;
    setAsking(true);
    api.post("/ai-chat/ask", { prompt: question, conversation_id: activeId }).then(({ data }) => {
      setMessages((items) => [...items, data]);
      setActiveId(data.conversation_id);
      setPrompt("");
      loadConversations();
    }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "AI Chat could not answer" }))
      .finally(() => setAsking(false));
  };

  const onComposerKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      ask(event);
    }
  };

  return <div className={`page ai-page ai-chat-shell ${historyOpen ? "history-open" : ""}`}>
    <button className="ai-history-backdrop" type="button" aria-label="Close chat history" onClick={() => setHistoryOpen(false)} />
    <aside className="ai-conversation-sidebar">
      <div className="ai-sidebar-head">
        <div><IconHistory size={18} /><strong>Recent chats</strong></div>
        <button className="ai-sidebar-close" type="button" onClick={() => setHistoryOpen(false)} aria-label="Close history"><IconX size={19} /></button>
      </div>
      <button className="ai-new-chat" type="button" onClick={newChat}><IconPlus size={18} /><span>New chat</span></button>
      <nav className="ai-conversation-list" aria-label="AI chat history">
        {conversations.map((item) => <button type="button" className={activeId === item.id ? "active" : ""} onClick={() => openConversation(item.id)} key={item.id}>
          <IconMessage size={16} /><span><strong>{item.title}</strong><small>{formatConversationDate(item.updated_at)}</small></span>
        </button>)}
        {!conversations.length && <div className="ai-no-conversations"><IconMessage size={22} /><span>Your conversations will appear here.</span></div>}
      </nav>
      <div className="ai-sidebar-scope"><IconDatabase size={16} /><span>{visibleSources.length} connected CRM areas</span></div>
    </aside>

    <main className="ai-chat-main">
      <header className="ai-chat-header">
        <button className="ai-history-toggle" type="button" onClick={() => setHistoryOpen(true)} aria-label="Open chat history"><IconMenu2 size={20} /></button>
        <div><strong>{activeConversation?.title || "New CRM chat"}</strong><span><i />Live company data</span></div>
        <button className="ai-header-new" type="button" onClick={newChat}><IconPlus size={17} /><span>New chat</span></button>
      </header>

      <section className="ai-chat-scroll">
        {!activeId && !messages.length && <div className="ai-chat-welcome">
          <div className="ai-welcome-orb"><IconSparkles size={28} /></div>
          <span>CRM data analyst</span>
          <h1>What can I help you understand?</h1>
          <p>Ask questions about your live leads, customers, tasks and operations. Your answers remain saved in chat history.</p>
          <div className="ai-starter-grid">{suggestions.map((text) => <button type="button" key={text} disabled={asking} onClick={() => ask(null, text)}>{text}<IconArrowUp size={16} /></button>)}</div>
        </div>}
        {loadingChat && <div className="ai-chat-loading"><IconRobot size={24} /><span>Loading conversation…</span></div>}
        {!loadingChat && messages.map((item) => <ChatExchange item={item} key={item.id} />)}
        {asking && <div className="ai-thinking"><div className="ai-bot-avatar"><IconSparkles size={18} /></div><span /><span /><span /><small>Analyzing live CRM data…</small></div>}
        <div ref={endRef} />
      </section>

      {can(user, "ai_chat", "ask") && <div className="ai-composer-dock">
        <form className="ai-chat-composer" onSubmit={ask}>
          <textarea rows="1" maxLength="1000" value={prompt} onChange={(event) => setPrompt(event.target.value)} onKeyDown={onComposerKeyDown} placeholder="Message your CRM analyst" aria-label="Message your CRM analyst" required />
          <Button disabled={asking || !prompt.trim()} aria-label="Send message">{asking ? <IconRobot size={19} /> : <IconArrowUp size={19} />}</Button>
        </form>
        <small><IconTable size={13} />Ask for a table when you need record-level detail · Enter to send, Shift+Enter for a new line</small>
      </div>}
    </main>
    <Toast toast={toast} />
  </div>;
}

function formatConversationDate(value) {
  if (!value) return "";
  const date = new Date(value);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatMessageTime(value) {
  return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
}
