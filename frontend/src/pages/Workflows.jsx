import { useEffect, useMemo, useState } from "react";
import { IconEdit, IconPlus, IconTrash } from "@tabler/icons-react";
import api from "../api/client";
import DataTable from "../components/shared/DataTable.jsx";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Modal from "../components/UI/Modal.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";
import { sentenceCase } from "../utils/text.js";

const statuses = ["any", "new", "contacted", "qualified", "won", "lost", "converted", "closed", "not_interested"];
const sources = ["", "website", "chatbot", "whatsapp", "email", "inperson"];
const blankRule = {
  name: "",
  description: "",
  entity_type: "lead",
  trigger_type: "status_changed",
  trigger_config: { to_status: "qualified" },
  conditions: {},
  actions: [{ type: "assign_to_user", user_id: "" }],
  is_active: true,
};

function parseJson(value, fallback) {
  if (!value) return fallback;
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function hydrate(row) {
  return {
    ...row,
    trigger_config: parseJson(row.trigger_config, { to_status: "any" }),
    conditions: parseJson(row.conditions, {}),
    actions: parseJson(row.actions, []),
  };
}

function actionLabel(action, users) {
  const user = users.find((item) => String(item.id) === String(action.user_id));
  if (action.type === "assign_to_user") return `Assign to ${user?.name || "user"}`;
  if (action.type === "create_notification") return `Notify ${action.target === "specific_user" ? user?.name || "user" : "assignee"}`;
  if (action.type === "send_whatsapp") return "Send WhatsApp";
  if (action.type === "send_email") return "Send email";
  return action.type;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function runTone(status) {
  if (status === "success") return "teal";
  if (status === "error") return "red";
  return "amber";
}

export default function Workflows() {
  const { user } = useAuth();
  const [rules, setRules] = useState([]);
  const [users, setUsers] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(blankRule);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  const selectedRule = useMemo(() => rules.find((rule) => rule.id === selected?.id), [rules, selected]);

  const loadRules = () => api.get("/workflows/")
    .then(({ data }) => {
      const hydrated = data.map(hydrate);
      setRules(hydrated);
      setSelected((current) => current || hydrated[0] || null);
    })
    .catch(() => setToast({ type: "error", message: "Could not load workflows" }));

  const loadUsers = () => api.get("/workflows/assignable-users")
    .then(({ data }) => setUsers(data))
    .catch(() => setToast({ type: "error", message: "Could not load users" }));

  const loadRuns = (rule) => {
    if (!rule?.id) {
      setRuns([]);
      return;
    }
    api.get(`/workflows/${rule.id}/runs`)
      .then(({ data }) => setRuns(data.items || []))
      .catch(() => setToast({ type: "error", message: "Could not load workflow runs" }));
  };

  useEffect(() => {
    loadRules();
    loadUsers();
  }, []);

  useEffect(() => { loadRuns(selected); }, [selected?.id]);

  const startCreate = () => {
    setForm({ ...blankRule, actions: [{ type: "assign_to_user", user_id: users[0]?.id || "" }] });
    setOpen(true);
  };

  const startEdit = (rule) => {
    setForm(hydrate(rule));
    setOpen(true);
  };

  const save = () => {
    if (!form.name.trim()) {
      setToast({ type: "error", message: "Rule name is required" });
      return;
    }
    setLoading(true);
    const payload = {
      ...form,
      conditions: form.conditions?.source ? form.conditions : {},
      actions: form.actions.filter((action) => action.type),
    };
    const request = form.id ? api.put(`/workflows/${form.id}`, payload) : api.post("/workflows/", payload);
    request
      .then(({ data }) => {
        const saved = hydrate(data);
        setOpen(false);
        setSelected(saved);
        setToast({ type: "success", message: "Workflow saved" });
        loadRules();
      })
      .catch(() => setToast({ type: "error", message: "Could not save workflow" }))
      .finally(() => setLoading(false));
  };

  const remove = (rule) => {
    if (!confirm(`Delete workflow "${rule.name}"?`)) return;
    api.delete(`/workflows/${rule.id}`)
      .then(() => {
        setSelected(null);
        setToast({ type: "success", message: "Workflow deleted" });
        loadRules();
      })
      .catch(() => setToast({ type: "error", message: "Could not delete workflow" }));
  };

  const toggle = (rule) => api.post(`/workflows/${rule.id}/toggle`)
    .then(({ data }) => {
      setSelected(hydrate(data));
      loadRules();
    })
    .catch(() => setToast({ type: "error", message: "Could not update workflow" }));

  const updateAction = (index, patch) => {
    setForm((current) => ({
      ...current,
      actions: current.actions.map((action, itemIndex) => itemIndex === index ? { ...action, ...patch } : action),
    }));
  };

  const addAction = () => setForm((current) => ({
    ...current,
    actions: [...current.actions, { type: "create_notification", target: "assignee", title: "Lead updated", body: "{name} is now {status}" }],
  }));

  const deleteAction = (index) => setForm((current) => ({
    ...current,
    actions: current.actions.filter((_, itemIndex) => itemIndex !== index),
  }));

  const columns = [
    { key: "name", label: "Rule" },
    { key: "trigger", label: "Trigger", render: (row) => `Lead status -> ${row.trigger_config?.to_status || "any"}` },
    { key: "actions", label: "Actions", render: (row) => row.actions.map((action) => actionLabel(action, users)).join(", ") || "-" },
    { key: "is_active", label: "Active", render: (row) => <Badge tone={row.is_active ? "teal" : "red"}>{row.is_active ? "Active" : "Off"}</Badge> },
    { key: "manage", label: "Manage", render: (row) => <div className="row-actions">
      <button onClick={(event) => { event.stopPropagation(); toggle(row); }}>{row.is_active ? "Disable" : "Enable"}</button>
      <button onClick={(event) => { event.stopPropagation(); startEdit(row); }}><IconEdit size={16} /></button>
      <button onClick={(event) => { event.stopPropagation(); remove(row); }}><IconTrash size={16} /></button>
    </div> },
  ];

  return <div className="page workflows-page">
    <Card>
      <div className="card-head">
        <div>
          <h2>Workflow automation</h2>
          <small>Rule-based lead automation for assignment, notifications and messages.</small>
        </div>
        {can(user, "workflows", "manage") && <Button onClick={startCreate}><IconPlus size={16} /> New Rule</Button>}
      </div>
      <DataTable columns={columns} data={rules} empty="No workflow rules configured." onRow={setSelected} />
    </Card>

    <Card>
      <div className="card-head">
        <div>
          <h2>Run history</h2>
          <small>{selectedRule ? selectedRule.name : "Select a workflow rule"}</small>
        </div>
        {selectedRule && <Badge tone={selectedRule.is_active ? "teal" : "red"}>{selectedRule.is_active ? "Active" : "Disabled"}</Badge>}
      </div>
      <DataTable
        columns={[
          { key: "status", label: "Status", render: (row) => <Badge tone={runTone(row.status)}>{row.status}</Badge> },
          { key: "entity_id", label: "Lead" },
          { key: "detail", label: "Detail" },
          { key: "created_at", label: "Time", render: (row) => formatDate(row.created_at) },
        ]}
        data={runs}
        empty={selectedRule ? "No runs yet." : "Select a rule to view runs."}
      />
    </Card>

    <Modal open={open} title={form.id ? "Edit Workflow" : "New Workflow"} onClose={() => setOpen(false)}>
      <div className="workflow-modal-body">
      <div className="form-grid">
        <label className="field wide"><span>Name</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label className="field wide"><span>Description</span><textarea rows="2" value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <label className="field"><span>When status changes to</span><select value={form.trigger_config?.to_status || "any"} onChange={(e) => setForm({ ...form, trigger_config: { to_status: e.target.value } })}>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
        <label className="field"><span>Only if the source is</span><select value={form.conditions?.source || ""} onChange={(e) => setForm({ ...form, conditions: e.target.value ? { source: e.target.value } : {} })}>{sources.map((source) => <option key={source || "any"} value={source}>{sentenceCase(source, "Any source")}</option>)}</select></label>
        <label className="field"><span>Active</span><select value={form.is_active ? "1" : "0"} onChange={(e) => setForm({ ...form, is_active: e.target.value === "1" })}><option value="1">Active</option><option value="0">Disabled</option></select></label>
        <div className="wide">
          <div className="card-head compact"><h3>Actions</h3><Button type="button" variant="secondary" onClick={addAction}>Add action</Button></div>
          {form.actions.map((action, index) => <div className="mini-grid" key={`${action.type}-${index}`}>
            <label className="field"><span>Action</span><select value={action.type} onChange={(e) => updateAction(index, { type: e.target.value })}>
              <option value="assign_to_user">Assign to user</option>
              <option value="create_notification">Create notification</option>
              <option value="send_whatsapp">Send WhatsApp</option>
              <option value="send_email">Send email</option>
            </select></label>
            {action.type === "assign_to_user" && <label className="field"><span>User</span><select value={action.user_id || ""} onChange={(e) => updateAction(index, { user_id: e.target.value })}>{users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
            {action.type === "create_notification" && <>
              <label className="field"><span>Target</span><select value={action.target || "assignee"} onChange={(e) => updateAction(index, { target: e.target.value })}><option value="assignee">Assignee</option><option value="specific_user">Specific user</option></select></label>
              {action.target === "specific_user" && <label className="field"><span>User</span><select value={action.user_id || ""} onChange={(e) => updateAction(index, { user_id: e.target.value })}>{users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
              <label className="field"><span>Title</span><input value={action.title || ""} onChange={(e) => updateAction(index, { title: e.target.value })} /></label>
              <label className="field wide"><span>Body</span><textarea rows="2" value={action.body || ""} onChange={(e) => updateAction(index, { body: e.target.value })} /></label>
            </>}
            {action.type === "send_whatsapp" && <label className="field wide"><span>Template</span><textarea rows="3" value={action.template || ""} onChange={(e) => updateAction(index, { template: e.target.value })} /></label>}
            {action.type === "send_email" && <>
              <label className="field"><span>Subject</span><input value={action.subject || ""} onChange={(e) => updateAction(index, { subject: e.target.value })} /></label>
              <label className="field wide"><span>Template</span><textarea rows="3" value={action.template || ""} onChange={(e) => updateAction(index, { template: e.target.value })} /></label>
            </>}
            <Button type="button" variant="ghost" onClick={() => deleteAction(index)}>Remove</Button>
          </div>)}
        </div>
      </div>
      <div className="workflow-modal-actions">
        <button type="button" className="ghost-action" onClick={() => setOpen(false)}>Cancel</button>
        <Button type="button" onClick={save} disabled={loading || !can(user, "workflows", "manage")}>
          {loading ? "Saving..." : "Save Workflow"}
        </Button>
      </div>
      </div>
    </Modal>
    <Toast toast={toast} />
  </div>;
}
