import { IconBell, IconCalendarStats, IconCheck, IconChecks, IconMenu2, IconMoon, IconSearch, IconSun, IconX } from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import api from "../../api/client.js";
import { useAuth } from "../../context/AuthContext.jsx";
import { sentenceCase } from "../../utils/text.js";

const titles = {
  dashboard: ["Business dashboard", "Academic and client-project lead health, losses and team execution"],
  leads: ["Leads", "Capture, qualify and convert opportunities"],
  customers: ["Customers", "Manage active accounts and relationship value"],
  tasks: ["Tasks", "Track follow-ups, internal work and overdue actions"],
  calendar: ["Calendar", "Daily agenda, reminders and meeting schedule"],
  "ai-chat": ["AI chat", "Ask questions about your live CRM database"],
  campaigns: ["Campaigns", "Run WhatsApp and email outreach"],
  communication: ["Customer communication", "Send individual or bulk WhatsApp messages to customers"],
  whatsapp: ["WhatsApp messages", "Read bot conversations and AI summaries by contact"],
  reports: ["Reports", "Conversion, demand, sources and team accountability"],
  employees: ["Employees", "Team access, departments and permissions"],
  settings: ["Settings", "Company profile and business integrations"],
};

export default function Topbar({ onMenuClick, navigationOpen = false }) {
  const { user } = useAuth();
  const pathname = useLocation().pathname;
  const key = pathname === "/communication/whatsapp" ? "whatsapp" : pathname.split("/")[1] || "dashboard";
  const [title, subtitle] = titles[key] || titles.dashboard;
  const [notifications, setNotifications] = useState([]);
  const [open, setOpen] = useState(false);
  const [notificationFilter, setNotificationFilter] = useState("all");
  const notifyRef = useRef(null);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem("crm_theme") || "light";
    document.documentElement.dataset.theme = saved;
    return saved;
  });
  const now = new Date();
  const today = now.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  const todayDateTime = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const unread = notifications.filter((item) => !item.is_read);
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("crm_theme", theme); }, [theme]);

  useEffect(() => {
    if (!user) return;
    const loadNotifications = () => api.get("/notifications", { params: { limit: 30 } })
      .then(({ data }) => setNotifications(data))
      .catch(() => setNotifications([]));
    loadNotifications();
    const timer = setInterval(loadNotifications, 60000);
    return () => clearInterval(timer);
  }, [user, key]);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event) => { if (!notifyRef.current?.contains(event.target)) setOpen(false); };
    const closeEscape = (event) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("keydown", closeEscape); };
  }, [open]);

  useEffect(() => {
    const query = search.trim();
    if (!user || query.length < 2) {
      setSearchResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = setTimeout(() => {
      api.get("/search", { params: { q: query } })
        .then(({ data }) => setSearchResults(data.items || []))
        .catch(() => setSearchResults([]))
        .finally(() => setSearching(false));
    }, 220);
    return () => clearTimeout(timer);
  }, [search, user]);

  const markAllRead = () => {
    api.post("/notifications/read-all")
      .then(() => setNotifications((items) => items.map((item) => ({ ...item, is_read: true }))))
      .catch(() => {});
  };

  const openNotification = (item) => {
    if (item.href) setOpen(false);
    if (!item.is_read) {
      api.post(`/notifications/${item.id}/read`)
        .then(() => setNotifications((items) => items.map((row) => row.id === item.id ? { ...row, is_read: true } : row)))
        .catch(() => {});
    }
  };

  const markRead = (item) => {
    if (item.is_read) return;
    api.post(`/notifications/${item.id}/read`)
      .then(() => setNotifications((items) => items.map((row) => row.id === item.id ? { ...row, is_read: true } : row)))
      .catch(() => {});
  };

  const visibleNotifications = notificationFilter === "unread" ? unread : notifications;

  return (
    <header className="topbar">
      <button className="icon-btn mobile-menu-button" type="button" onClick={onMenuClick} aria-label="Open CRM navigation" aria-expanded={navigationOpen} aria-controls="crm-navigation"><IconMenu2 size={20} /></button>
      <div className="page-title">
        <h1>{title}</h1>
        <span>{subtitle}</span>
      </div>
      <time className="topbar-date" dateTime={todayDateTime}><IconCalendarStats size={16} aria-hidden="true" />{today}</time>
      <div className="global-search">
        <div className="search">
          <IconSearch size={16} />
          <input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setSearchOpen(true);
            }}
            onFocus={() => setSearchOpen(true)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setSearchOpen(false);
            }}
            placeholder="Search CRM"
          />
        </div>
        {searchOpen && search.trim().length >= 2 && (
          <div className="search-results">
            <div className="search-results-head">
              <strong>Global search</strong>
              <span>{searching ? "Searching..." : `${searchResults.length} result${searchResults.length === 1 ? "" : "s"}`}</span>
            </div>
            {!searching && searchResults.map((item) => (
              <Link className="search-result" key={`${item.module}-${item.meta?.id}-${item.title}`} to={item.href} onClick={() => setSearchOpen(false)}>
                <span>{sentenceCase(item.module)}</span>
                <strong>{item.title}</strong>
                <small>{item.subtitle}</small>
              </Link>
            ))}
            {!searching && !searchResults.length && <div className="search-empty">No matching CRM records.</div>}
          </div>
        )}
      </div>
      <button className="icon-btn theme-toggle" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} title={`Use ${theme === "dark" ? "light" : "dark"} theme`} aria-label="Toggle color theme">{theme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}</button>
      <div className="notify-wrap" ref={notifyRef}>
        <button className={`icon-btn notify ${unread.length ? "has-unread" : ""}`} onClick={() => setOpen((value) => !value)} aria-label={`${unread.length} unread notifications`} aria-expanded={open} aria-haspopup="dialog">
          <IconBell size={18} />
          {unread.length > 0 && <span>{unread.length > 99 ? "99+" : unread.length}</span>}
        </button>
        {open && <div className="notify-menu" role="dialog" aria-label="Notifications">
          <div className="notify-menu-head">
            <div><strong>Notifications</strong><span>{unread.length} unread</span></div>
            <div>{unread.length > 0 && <button onClick={markAllRead}><IconChecks size={15} />Mark all read</button>}<button className="notify-close" onClick={() => setOpen(false)} aria-label="Close notifications"><IconX size={16} /></button></div>
          </div>
          <div className="notify-filters"><button className={notificationFilter === "all" ? "active" : ""} onClick={() => setNotificationFilter("all")}>All <span>{notifications.length}</span></button><button className={notificationFilter === "unread" ? "active" : ""} onClick={() => setNotificationFilter("unread")}>Unread <span>{unread.length}</span></button></div>
          <div className="notify-list">
            {visibleNotifications.map((item) => <div className={`notify-item-row ${item.is_read ? "" : "unread"}`} key={item.id}>
              {item.href ? <Link className="notify-item" to={item.href} onClick={() => openNotification(item)}><NotificationContent item={item} /></Link> : <button className="notify-item" onClick={() => openNotification(item)}><NotificationContent item={item} /></button>}
              {!item.is_read && <button className="notify-read" title="Mark as read" aria-label={`Mark ${item.title} as read`} onClick={() => markRead(item)}><IconCheck size={15} /></button>}
            </div>)}
            {!visibleNotifications.length && <div className="notify-empty"><IconBell size={22} /><strong>{notificationFilter === "unread" ? "You’re all caught up." : "No notifications yet."}</strong><span>{notificationFilter === "unread" ? "New task and workflow alerts will appear here." : "Alerts will appear here when CRM activity needs your attention."}</span></div>}
          </div>
        </div>}
      </div>
      <div className="avatar" style={{ background: user.avatar_color }}>{user.avatar_initials}</div>
    </header>
  );
}

function NotificationContent({ item }) {
  return <><div className="notify-item-title"><span className="notify-dot" /><strong>{item.title}</strong><time>{relativeTime(item.created_at)}</time></div><span>{item.body || "CRM activity update"}</span></>;
}

function relativeTime(value) {
  if (!value) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "Now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return days < 7 ? `${days}d` : new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}
