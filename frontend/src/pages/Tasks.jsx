import { useEffect, useMemo, useState } from "react";
import { IconCalendar, IconCheck, IconEdit, IconPlus, IconTrash } from "@tabler/icons-react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Toast from "../components/UI/Toast.jsx";
import DataTable from "../components/shared/DataTable.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";

const emptyTask = { title: "", notes: "", related_type: "internal", related_name: "", due_date: "", reminder_at: "", assigned_to: "", priority: "Medium", status: "pending" };

export default function Tasks() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const isManager = can(user, "tasks", "assign");
  const [items, setItems] = useState([]);
  const [assignees, setAssignees] = useState([]);
  const [filter, setFilter] = useState(searchParams.get("view") || "open");
  const [toast, setToast] = useState(null);
  const [editing, setEditing] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyTask);

  const load = () => api.get("/tasks").then(({ data }) => setItems(data)).catch(() => setToast({ type: "error", message: "Could not load tasks" }));

  useEffect(() => {
    load();
    api.get("/tasks/assignees").then(({ data }) => {
      setAssignees(data);
      setForm((old) => ({ ...old, assigned_to: String(user?.id || "") }));
    }).catch(() => setToast({ type: "error", message: "Could not load staff list" }));
  }, [user?.id]);

  const metrics = useMemo(() => ({
    myOpen: items.filter((task) => task.assigned_to === user?.id && task.status !== "done").length,
    teamOpen: items.filter((task) => task.status !== "done").length,
    today: items.filter(dueToday).length,
    overdue: items.filter(isOverdue).length,
    completed: items.filter((task) => task.status === "done").length,
  }), [items, user?.id]);

  const rows = items.filter((task) => {
    if (filter === "mine") return task.assigned_to === user?.id && task.status !== "done";
    if (filter === "today") return dueToday(task);
    if (filter === "upcoming") return task.status !== "done" && task.due_date && task.due_date > localDateKey(new Date());
    if (filter === "overdue") return isOverdue(task);
    if (filter === "done") return task.status === "done";
    return task.status !== "done";
  });

  const set = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  const resetForm = () => { setEditing(null); setShowForm(false); setForm({ ...emptyTask, assigned_to: String(user?.id || "") }); };
  const startNew = () => { setEditing(null); setForm({ ...emptyTask, assigned_to: String(user?.id || "") }); setShowForm(true); };
  const edit = (task) => { setEditing(task); setForm({ ...emptyTask, ...task, assigned_to: String(task.assigned_to || user?.id || ""), due_date: task.due_date || "", reminder_at: task.reminder_at?.slice(0, 16) || "" }); setShowForm(true); };

  const save = (event) => {
    event.preventDefault();
    const payload = { ...form, assigned_to: Number(form.assigned_to || user.id), reminder_at: form.reminder_at || null };
    const request = editing ? api.put(`/tasks/${editing.id}`, payload) : api.post("/tasks", payload);
    request.then(() => { setToast({ type: "success", message: editing ? "Task updated" : isManager ? "Task assigned" : "Task added to your work" }); resetForm(); load(); })
      .catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Task save failed" }));
  };

  const complete = (task) => api.post(`/tasks/${task.id}/complete`).then(() => { setToast({ type: "success", message: "Task completed" }); load(); }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Could not complete task" }));
  const remove = (task) => {
    if (!window.confirm(`Delete “${task.title}”? This cannot be undone.`)) return;
    api.delete(`/tasks/${task.id}`).then(() => { setToast({ type: "success", message: "Task deleted" }); if (editing?.id === task.id) resetForm(); load(); }).catch(() => setToast({ type: "error", message: "Delete failed" }));
  };

  const actions = (task) => <div className="row-actions icon-actions">
    {can(user, "tasks", "update") && <button title="Edit task" onClick={(event) => { event.stopPropagation(); edit(task); }}><IconEdit size={16} /></button>}
    {can(user, "tasks", "complete") && task.status !== "done" && <button title="Complete task" onClick={(event) => { event.stopPropagation(); complete(task); }}><IconCheck size={16} /></button>}
    {can(user, "tasks", "delete") && <button title="Delete task" onClick={(event) => { event.stopPropagation(); remove(task); }}><IconTrash size={16} /></button>}
  </div>;

  const cols = [
    { label: "Task", key: "title", render: (task) => <div className="task-title-cell"><strong className={isOverdue(task) ? "danger-text" : ""}>{task.title}</strong><small>{task.notes || "No instruction added"}</small></div> },
    { label: "Due", key: "due_date", render: (task) => task.due_date ? formatDate(task.due_date) : "No due date" },
    ...(isManager ? [{ label: "Employee", key: "assigned_name", render: (task) => <strong>{task.assigned_name || "Unassigned"}</strong> }] : []),
    { label: "Context", key: "related_name", render: (task) => task.related_name ? <><strong>{task.related_name}</strong><small>{task.related_type}</small></> : "Internal" },
    { label: "Priority", key: "priority", render: (task) => <Badge tone={priorityTone(task.priority)}>{task.priority}</Badge> },
    { label: "Status", key: "status", render: (task) => <Badge tone={task.status === "done" ? "teal" : isOverdue(task) ? "red" : "purple"}>{task.status === "done" ? "Completed" : isOverdue(task) ? "Overdue" : dueToday(task) ? "Due today" : "Open"}</Badge> },
    { label: "Actions", key: "actions", render: actions },
  ];

  return <div className="page tasks-page">
    <div className="task-page-head"><div><span>TEAM EXECUTION</span><h2>{isManager ? "Assign and track work" : "My assigned work"}</h2><p>{isManager ? "Keep assignments, due dates and next actions clear." : "Focus on what is due, complete work, and keep your manager informed."}</p></div>{can(user, "tasks", "create") && <Button onClick={startNew}><IconPlus size={17} />New task</Button>}</div>

    <div className="task-summary focused">
      <button className={filter === "mine" ? "active" : ""} onClick={() => setFilter("mine")}><span>My open tasks</span><strong>{metrics.myOpen}</strong></button>
      {isManager && <button className={filter === "open" ? "active" : ""} onClick={() => setFilter("open")}><span>Team open</span><strong>{metrics.teamOpen}</strong></button>}
      <button className={filter === "today" ? "active" : ""} onClick={() => setFilter("today")}><span>Due today</span><strong>{metrics.today}</strong></button>
      <button className={filter === "overdue" ? "active danger" : ""} onClick={() => setFilter("overdue")}><span>Overdue</span><strong>{metrics.overdue}</strong></button>
      <button className={filter === "done" ? "active" : ""} onClick={() => setFilter("done")}><span>Completed</span><strong>{metrics.completed}</strong></button>
    </div>

    {showForm && <Card className="focused-task-form"><div className="task-form-head"><div><h2>{editing ? "Edit task" : isManager ? "Assign a task" : "Add my task"}</h2><span>Only the information needed to execute the work is required.</span></div><button className="ghost-action compact" type="button" onClick={resetForm}>Close</button></div>
      <form className="task-form essential" onSubmit={save}>
        <label className="field wide"><span>Task title</span><input value={form.title} onChange={(event) => set("title", event.target.value)} placeholder="State the expected action" required /></label>
        {isManager && <label className="field"><span>Assign to</span><select value={form.assigned_to} onChange={(event) => set("assigned_to", event.target.value)} required><option value="">Select employee</option>{assignees.map((staff) => <option value={staff.id} key={staff.id}>{staff.name}{staff.id === user?.id ? " (Me)" : ""}</option>)}</select></label>}
        <label className="field"><span>Due date</span><input type="date" value={form.due_date} onChange={(event) => set("due_date", event.target.value)} required /></label>
        <label className="field"><span>Priority</span><select value={form.priority} onChange={(event) => set("priority", event.target.value)}><option>High</option><option>Medium</option><option>Low</option></select></label>
        <label className="field"><span>Related to</span><select value={form.related_type} onChange={(event) => set("related_type", event.target.value)}><option value="internal">Internal work</option><option value="lead">Lead</option><option value="customer">Customer</option></select></label>
        {form.related_type !== "internal" && <label className="field"><span>{form.related_type === "lead" ? "Lead" : "Customer"} name</span><input value={form.related_name} onChange={(event) => set("related_name", event.target.value)} required /></label>}
        <label className="field"><span>Reminder (optional)</span><input type="datetime-local" value={form.reminder_at} onChange={(event) => set("reminder_at", event.target.value)} /></label>
        <label className="field wide"><span>Instruction / expected result</span><textarea value={form.notes} onChange={(event) => set("notes", event.target.value)} placeholder="Add the context the employee needs to finish this correctly." /></label>
        <div className="composer-actions wide"><button type="button" className="ghost-action" onClick={resetForm}>Cancel</button><Button>{editing ? "Save changes" : isManager ? "Assign task" : "Add task"}</Button></div>
      </form>
    </Card>}

    <div className="task-list-toolbar"><div className="tabs">{[["open", isManager ? "Team open" : "My open"], ["mine", "Assigned to me"], ["today", "Today"], ["upcoming", "Upcoming"], ["overdue", "Overdue"], ["done", "Completed"]].filter(([key]) => isManager || key !== "mine").map(([key, label]) => <button className={filter === key ? "active" : ""} key={key} onClick={() => setFilter(key)}>{label}</button>)}</div><Link to="/calendar"><IconCalendar size={16} />Open calendar</Link></div>
    <div className="desktop-task-table"><DataTable columns={cols} data={rows} onRow={can(user, "tasks", "update") ? edit : undefined} empty="No tasks match this view." /></div>
    <div className="mobile-task-list">{rows.map((task) => <article className="mobile-task-card" key={task.id}><header><div><strong className={isOverdue(task) ? "danger-text" : ""}>{task.title}</strong><span>{task.related_name || "Internal work"}</span></div><Badge tone={priorityTone(task.priority)}>{task.priority}</Badge></header><p>{task.notes || "No instruction added"}</p><div className="mobile-task-meta"><span>{task.due_date ? formatDate(task.due_date) : "No due date"}</span>{isManager && <span>{task.assigned_name || "Unassigned"}</span>}<Badge tone={task.status === "done" ? "teal" : isOverdue(task) ? "red" : "purple"}>{task.status === "done" ? "Completed" : isOverdue(task) ? "Overdue" : dueToday(task) ? "Due today" : "Open"}</Badge></div><footer>{actions(task)}</footer></article>)}{!rows.length && <div className="empty">No tasks match this view.</div>}</div>
    <Toast toast={toast} />
  </div>;
}

function localDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dueToday(task) { return task.status !== "done" && task.due_date === localDateKey(new Date()); }
function isOverdue(task) { return Boolean(task.due_date && task.due_date < localDateKey(new Date()) && task.status !== "done"); }
function priorityTone(priority) { return priority === "High" ? "red" : priority === "Low" ? "teal" : "amber"; }
function formatDate(value) { const [year, month, day] = value.split("-").map(Number); return new Date(year, month - 1, day).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }); }
