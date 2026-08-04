import { useEffect, useMemo, useState } from "react";
import { IconCalendarEvent, IconCheck, IconChevronLeft, IconChevronRight, IconListCheck } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";

export default function Calendar() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [allTasks, setAllTasks] = useState([]);
  const [mode, setMode] = useState("week");
  const [status, setStatus] = useState("open");
  const [anchor, setAnchor] = useState(startOfToday());
  const [toast, setToast] = useState(null);
  const range = useMemo(() => buildRange(anchor, mode), [anchor, mode]);
  const today = localDateKey(new Date());

  const load = () => Promise.all([
    api.get("/tasks/calendar", { params: { start: localDateKey(range[0]), end: localDateKey(range[range.length - 1]) } }),
    api.get("/tasks"),
  ]).then(([calendar, tasks]) => { setItems(calendar.data); setAllTasks(tasks.data); })
    .catch(() => setToast({ type: "error", message: "Could not load calendar" }));

  useEffect(() => { load(); }, [localDateKey(range[0]), localDateKey(range[range.length - 1])]);

  const visibleItems = items.filter((task) => status === "all" || (status === "done" ? task.status === "done" : task.status !== "done"));
  const byDay = (day) => visibleItems.filter((task) => task.due_date === localDateKey(day));
  const metrics = {
    today: allTasks.filter((task) => task.status !== "done" && task.due_date === today).length,
    overdue: allTasks.filter((task) => task.status !== "done" && task.due_date && task.due_date < today).length,
    upcoming: allTasks.filter((task) => task.status !== "done" && task.due_date && task.due_date > today).length,
    completed: allTasks.filter((task) => task.status === "done").length,
  };

  const complete = (task) => api.post(`/tasks/${task.id}/complete`)
    .then(() => { setToast({ type: "success", message: "Task completed" }); load(); })
    .catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Could not complete task" }));

  const goToday = () => { setAnchor(startOfToday()); setMode("day"); setStatus("open"); };

  return <div className="page calendar-page">
    <div className="calendar-page-head"><div><span>EXECUTION CALENDAR</span><h2>{can(user, "tasks", "assign") ? "Team due dates" : "My due dates"}</h2><p>Tasks and Calendar use the same assignments, due dates and completion status.</p></div><Link className="btn primary" to="/tasks"><IconListCheck size={17} />Manage tasks</Link></div>

    <div className="calendar-summary">
      <Link to="/tasks?view=today"><span>Due today</span><strong>{metrics.today}</strong></Link>
      <Link className="danger" to="/tasks?view=overdue"><span>Overdue</span><strong>{metrics.overdue}</strong></Link>
      <Link to="/tasks?view=upcoming"><span>Upcoming</span><strong>{metrics.upcoming}</strong></Link>
      <Link to="/tasks?view=done"><span>Completed</span><strong>{metrics.completed}</strong></Link>
    </div>

    <Card className="calendar-toolbar"><div className="toolbar-row">
      <div className="tabs compact-tabs"><button className={mode === "day" ? "active" : ""} onClick={() => setMode("day")}>Day</button><button className={mode === "week" ? "active" : ""} onClick={() => setMode("week")}>Week</button></div>
      <div className="calendar-nav"><button aria-label="Previous period" onClick={() => setAnchor(shift(anchor, mode === "week" ? -7 : -1))}><IconChevronLeft size={17} /></button><strong>{rangeLabel(range)}</strong><button aria-label="Next period" onClick={() => setAnchor(shift(anchor, mode === "week" ? 7 : 1))}><IconChevronRight size={17} /></button></div>
      <div className="calendar-toolbar-actions"><button className="ghost-action compact" onClick={goToday}>Today</button><div className="tabs compact-tabs"><button className={status === "open" ? "active" : ""} onClick={() => setStatus("open")}>Open</button><button className={status === "done" ? "active" : ""} onClick={() => setStatus("done")}>Completed</button><button className={status === "all" ? "active" : ""} onClick={() => setStatus("all")}>All</button></div></div>
    </div></Card>

    <div className={`calendar-grid ${mode}`}>
      {range.map((day) => <section className={`calendar-day ${localDateKey(day) === today ? "today" : ""}`} key={localDateKey(day)}>
        <header><span>{day.toLocaleDateString("en-IN", { weekday: "short" })}</span><strong>{day.toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}</strong><small>{byDay(day).length} task{byDay(day).length === 1 ? "" : "s"}</small></header>
        <div className="calendar-stack">
          {byDay(day).map((task) => <article className={`calendar-item ${task.status} ${task.priority.toLowerCase()}`} key={task.id}>
            <div><strong>{task.title}</strong><span>{task.related_name || "Internal work"}</span></div>
            <div className="calendar-badges"><Badge tone={task.status === "done" ? "teal" : priorityTone(task.priority)}>{task.status === "done" ? "Completed" : task.priority}</Badge>{can(user, "tasks", "assign") && <Badge>{task.assigned_name || "Unassigned"}</Badge>}</div>
            {task.notes && <p>{task.notes}</p>}
            <small><IconCalendarEvent size={14} />Due {formatDate(task.due_date)}</small>
            {task.status !== "done" && can(user, "tasks", "complete") && <Button onClick={() => complete(task)}><IconCheck size={15} />Complete</Button>}
          </article>)}
          {!byDay(day).length && <div className="calendar-empty"><IconCalendarEvent size={18} /><span>No {status === "done" ? "completed" : status === "open" ? "open" : ""} tasks</span></div>}
        </div>
      </section>)}
    </div>
    <Toast toast={toast} />
  </div>;
}

function startOfToday() { const value = new Date(); value.setHours(0, 0, 0, 0); return value; }
function localDateKey(date) { const year = date.getFullYear(); const month = String(date.getMonth() + 1).padStart(2, "0"); const day = String(date.getDate()).padStart(2, "0"); return `${year}-${month}-${day}`; }
function buildRange(anchor, mode) { if (mode === "day") return [new Date(anchor)]; const start = new Date(anchor); const mondayOffset = (start.getDay() + 6) % 7; start.setDate(start.getDate() - mondayOffset); return Array.from({ length: 7 }, (_, index) => shift(start, index)); }
function shift(date, days) { const next = new Date(date); next.setDate(next.getDate() + days); return next; }
function rangeLabel(range) { if (range.length === 1) return range[0].toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }); return `${range[0].toLocaleDateString("en-IN", { day: "2-digit", month: "short" })} – ${range[range.length - 1].toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}`; }
function formatDate(value) { const [year, month, day] = value.split("-").map(Number); return new Date(year, month - 1, day).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }); }
function priorityTone(priority) { return priority === "High" ? "red" : priority === "Low" ? "teal" : "amber"; }
