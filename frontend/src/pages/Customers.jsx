import { useEffect, useMemo, useState } from "react";
import { IconChevronLeft, IconChevronRight, IconDownload, IconSearch } from "@tabler/icons-react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Drawer from "../components/UI/Drawer.jsx";
import KpiCard from "../components/UI/KpiCard.jsx";
import Toast from "../components/UI/Toast.jsx";
import DataTable from "../components/shared/DataTable.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";

const emptyOverview = { total: 0, active: 0, followup: 0, contact_overdue: 0, segments: {} };
const segments = [
  ["all", "All customers"],
  ["academic", "Academic"],
  ["course", "Courses"],
  ["internship", "Internships"],
  ["project", "Projects"],
];

export default function Customers() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [overview, setOverview] = useState(emptyOverview);
  const [filters, setFilters] = useState({ search: "", status: "", attention: "", segment: "all", page: 1 });
  const [pagination, setPagination] = useState({ total: 0, pages: 1 });
  const [selected, setSelected] = useState(null);
  const [customer360, setCustomer360] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loading360, setLoading360] = useState(false);
  const [tab360, setTab360] = useState("overview");
  const [noteForm, setNoteForm] = useState({ note: "", note_type: "general" });
  const [docForm, setDocForm] = useState({ file: null, description: "" });
  const [toast, setToast] = useState(null);

  const load = () => {
    setLoading(true);
    const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== "" && value !== "all"));
    Promise.all([api.get("/customers", { params }), api.get("/customers/overview")])
      .then(([list, summary]) => {
        setItems(list.data.items);
        setPagination({ total: list.data.total, pages: list.data.pages || 1 });
        setOverview(summary.data);
      })
      .catch(() => setToast({ type: "error", message: "Could not load customers" }))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [filters.status, filters.attention, filters.segment, filters.page]);

  useEffect(() => {
    if (!selected?.id) {
      setCustomer360(null);
      setTab360("overview");
      return;
    }
    setLoading360(true);
    api.get(`/customers/${selected.id}/360`)
      .then(({ data }) => setCustomer360(data))
      .catch(() => setToast({ type: "error", message: "Could not load customer details" }))
      .finally(() => setLoading360(false));
  }, [selected?.id]);

  const current = customer360?.customer || selected;
  const healthTone = useMemo(() => customer360?.health?.label === "healthy" ? "teal" : customer360?.health?.label === "risk" ? "red" : "amber", [customer360]);
  const setFilter = (changes) => setFilters((old) => ({ ...old, ...changes, page: changes.page || 1 }));
  const reload360 = () => selected?.id && api.get(`/customers/${selected.id}/360`).then(({ data }) => { setCustomer360(data); setSelected(data.customer); });

  const updateCustomer = (changes) => {
    api.put(`/customers/${current.id}`, changes)
      .then(() => { setToast({ type: "success", message: "Customer updated" }); reload360(); load(); })
      .catch(() => setToast({ type: "error", message: "Customer update failed" }));
  };

  const addNote = (event) => {
    event.preventDefault();
    api.post(`/customers/${current.id}/notes`, noteForm)
      .then(() => { setNoteForm({ note: "", note_type: "general" }); setToast({ type: "success", message: "Note added" }); reload360(); })
      .catch(() => setToast({ type: "error", message: "Note save failed" }));
  };

  const addDocument = async (event) => {
    event.preventDefault();
    if (!docForm.file) return;
    const content = await fileToBase64(docForm.file);
    api.post(`/customers/${current.id}/documents`, {
      file_name: docForm.file.name,
      mime_type: docForm.file.type,
      file_size: docForm.file.size,
      content_base64: content,
      description: docForm.description,
    }).then(() => { setDocForm({ file: null, description: "" }); setToast({ type: "success", message: "Document uploaded" }); reload360(); })
      .catch(() => setToast({ type: "error", message: "Upload failed" }));
  };

  const downloadDocument = (doc) => api.get(`/customers/${current.id}/documents/${doc.id}`, { responseType: "blob" }).then((response) => {
    const url = URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = doc.file_name;
    link.click();
    URL.revokeObjectURL(url);
  });

  const cols = [
    { label: "Customer", key: "name", render: (row) => <div className="customer-name-cell"><strong>{row.name}</strong><small>{row.phone}{row.email ? ` · ${row.email}` : ""}</small></div> },
    { label: "Business", key: "service", render: (row) => <><strong>{row.interest || row.service}</strong><small>{categoryLabel(row.lead_category)}</small></> },
    { label: "Assigned Staff", key: "assigned_name", render: (row) => row.assigned_name || "Unassigned" },
    { label: "Last contact", key: "last_contact", render: (row) => row.last_contact ? formatDate(row.last_contact) : "Never" },
    { label: "Status", key: "status", render: (row) => <Badge tone={row.status === "active" ? "teal" : "amber"}>{row.status === "followup" ? "Follow-up" : row.status}</Badge> },
  ];

  return <div className="page customers-page">
    <div className="customer-kpis">
      <KpiCard label="Total Customers" value={overview.total} sub="All converted relationships" onClick={() => setFilter({ status: "", attention: "", segment: "all" })} />
      <KpiCard label="Active Customers" value={overview.active} sub="Currently being served" color="teal" onClick={() => setFilter({ status: "active", attention: "", segment: "all" })} />
      <KpiCard label="Follow-up Needed" value={overview.followup} sub="Marked for next action" color="amber" onClick={() => setFilter({ status: "followup", attention: "", segment: "all" })} />
      <KpiCard label="Contact Overdue" value={overview.contact_overdue} sub="No contact in 7+ days" color="red" onClick={() => setFilter({ status: "", attention: "contact_overdue", segment: "all" })} />
    </div>

    <Card className="customer-toolbar">
      <div className="customer-segments">
        {segments.map(([key, label]) => <button key={key} className={filters.segment === key ? "active" : ""} onClick={() => setFilter({ segment: key })}>{label}<small>{key === "all" ? overview.total : overview.segments?.[key] || 0}</small></button>)}
      </div>
      <form className="customer-search" onSubmit={(event) => { event.preventDefault(); setFilter({ page: 1 }); load(); }}>
        <IconSearch size={17} /><input aria-label="Search customers" placeholder="Search name, phone or email" value={filters.search} onChange={(event) => setFilters((old) => ({ ...old, search: event.target.value }))} />
        <Button>Search</Button>
        <Button variant="secondary" type="button" onClick={() => downloadCsv("/customers/export", "customers.csv")}><IconDownload size={16} />Export</Button>
      </form>
    </Card>

    <div className="desktop-customer-table"><DataTable columns={cols} data={items} loading={loading} onRow={setSelected} empty="No customers match this view." /></div>
    <div className="mobile-customer-list">
      {items.map((row) => <button type="button" className="mobile-customer-card" key={row.id} onClick={() => setSelected(row)}>
        <header><div><strong>{row.name}</strong><span>{row.phone}</span></div><Badge tone={row.status === "active" ? "teal" : "amber"}>{row.status === "followup" ? "Follow-up" : row.status}</Badge></header>
        <div><span>Business</span><strong>{row.interest || row.service}</strong></div>
        <footer><span>{row.assigned_name || "Unassigned"}</span><span>Last contact: {row.last_contact ? formatDate(row.last_contact) : "Never"}</span></footer>
      </button>)}
      {!loading && !items.length && <div className="empty">No customers match this view.</div>}
    </div>
    {pagination.pages > 1 && <div className="list-pagination"><span>{pagination.total} customers</span><div><button disabled={filters.page <= 1} onClick={() => setFilter({ page: filters.page - 1 })}><IconChevronLeft size={16} />Previous</button><strong>Page {filters.page} of {pagination.pages}</strong><button disabled={filters.page >= pagination.pages} onClick={() => setFilter({ page: filters.page + 1 })}>Next<IconChevronRight size={16} /></button></div></div>}

    <Drawer open={Boolean(selected)} title={current?.name || "Customer"} onClose={() => setSelected(null)}>
      {selected && <div className="customer-360">
        {loading360 && <div className="skeleton table-skeleton" />}
        {!loading360 && current && <>
          <div className="customer-hero"><div><Badge tone={healthTone}>{customer360?.health?.label || current.status}</Badge><h2>{current.name}</h2><p>{current.service}</p></div><div className="health-score"><strong>{customer360?.health?.score ?? "--"}%</strong><span>Health</span></div></div>
          <div className="customer-facts"><div><span>Phone</span><strong>{current.phone}</strong></div><div><span>Email</span><strong>{current.email || "-"}</strong></div><div><span>Company</span><strong>{current.company || "-"}</strong></div><div><span>Assigned Staff</span><strong>{current.assigned_name || "Unassigned"}</strong></div></div>
          <div className="tabs compact-tabs">{[["overview", "Overview"], ["activity", "Activity"], ["work", "Work & notes"], ["files", "Files"]].map(([key, label]) => <button key={key} className={tab360 === key ? "active" : ""} onClick={() => setTab360(key)}>{label}</button>)}</div>

          {tab360 === "overview" && <div className="customer-section">
            <div className="customer-metrics"><div><strong>{customer360?.health?.open_tasks || 0}</strong><span>Open tasks</span></div><div><strong>{customer360?.health?.overdue_tasks || 0}</strong><span>Overdue</span></div><div><strong>{customer360?.health?.message_count || 0}</strong><span>Messages</span></div></div>
            <div className="next-action"><strong>Next action</strong><p>{customer360?.ai_summary?.next_action || "No pending action"}</p></div>
            {can(user, "customers", "update") && <div className="customer-update-grid"><label className="field"><span>Relationship status</span><select value={current.status} onChange={(event) => updateCustomer({ status: event.target.value })}><option value="active">Active</option><option value="followup">Follow-up needed</option><option value="inactive">Inactive</option></select></label><label className="field"><span>Last contacted</span><input type="date" value={current.last_contact || ""} onChange={(event) => updateCustomer({ last_contact: event.target.value })} /></label></div>}
            <p><strong>Relationship notes:</strong> {current.notes || "No relationship summary added."}</p>
          </div>}

          {tab360 === "activity" && <div className="customer-section timeline-list">{(customer360?.timeline || []).map((item, index) => <div key={`${item.kind}-${index}`}><Badge>{item.kind}</Badge><strong>{item.title}</strong><span>{formatDateTime(item.timestamp)}</span><p>{item.body || "-"}</p></div>)}{!customer360?.timeline?.length && <div className="empty compact-empty">No activity yet.</div>}</div>}

          {tab360 === "work" && <div className="customer-section relation-list">
            <h3>Open work</h3>{(customer360?.tasks || []).map((task) => <div key={task.id}><strong>{task.title}</strong><span>{task.status} · {task.priority} · {task.due_date ? formatDate(task.due_date) : "No due date"}</span><p>{task.notes || "-"}</p></div>)}{!customer360?.tasks?.length && <div className="empty compact-empty">No customer tasks yet.</div>}
            {can(user, "customers", "update") && <form className="form-grid customer-note-form" onSubmit={addNote}><label className="field"><span>Note type</span><select value={noteForm.note_type} onChange={(event) => setNoteForm({ ...noteForm, note_type: event.target.value })}><option value="general">General</option><option value="call">Call</option><option value="meeting">Meeting</option><option value="risk">Risk</option><option value="success">Success</option></select></label><label className="field wide"><span>New note</span><textarea value={noteForm.note} onChange={(event) => setNoteForm({ ...noteForm, note: event.target.value })} required /></label><Button>Add note</Button></form>}
            <h3>Notes</h3>{(customer360?.notes || []).map((note) => <div key={note.id}><strong>{note.note_type} · {note.user_name || "CRM"}</strong><span>{formatDateTime(note.created_at)}</span><p>{note.note}</p></div>)}
          </div>}

          {tab360 === "files" && <div className="customer-section relation-list">{can(user, "customers", "update") && <form className="form-grid" onSubmit={addDocument}><label className="field wide"><span>File</span><input type="file" onChange={(event) => setDocForm({ ...docForm, file: event.target.files?.[0] || null })} required /></label><label className="field wide"><span>Description</span><input value={docForm.description} onChange={(event) => setDocForm({ ...docForm, description: event.target.value })} /></label><Button>Upload file</Button></form>}{(customer360?.documents || []).map((doc) => <div key={doc.id}><strong>{doc.file_name}</strong><span>{Number(doc.file_size || 0).toLocaleString("en-IN")} bytes</span><p>{doc.description || "-"}</p><button type="button" onClick={() => downloadDocument(doc)}>Download</button></div>)}{!customer360?.documents?.length && <div className="empty compact-empty">No files attached yet.</div>}</div>}
        </>}
      </div>}
    </Drawer>
    <Toast toast={toast} />
  </div>;
}

function categoryLabel(value) {
  return { course: "Course", internship: "Internship", client_project: "Client project" }[value] || "Customer";
}

function formatDate(value) {
  if (!value) return "-";
  const [year, month, day] = String(value).slice(0, 10).split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "-";
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = reject; reader.readAsDataURL(file); });
}

function downloadCsv(path, filename) {
  api.get(path, { responseType: "blob" }).then((response) => { const url = URL.createObjectURL(response.data); const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url); });
}
