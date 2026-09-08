import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Drawer from "../components/UI/Drawer.jsx";
import KpiCard from "../components/UI/KpiCard.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";
import { sentenceCase } from "../utils/text.js";

const emptyState = { settings: {}, metrics: {}, leads: [], history: [], owners: [], pagination: {} };
const blankFilters = { search: "", temperature: "", status: "", owner: "", source: "", due: "", date_from: "", date_to: "" };

function formatDate(value) {
  if (!value) return "—";
  const utc = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return new Date(utc).toLocaleString();
}

function tone(status) {
  if (["sent", "accepted", "delivered", "read", "scheduled"].includes(status)) return "teal";
  if (["failed", "stopped", "cancelled"].includes(status)) return "red";
  if (["generated", "pending", "due"].includes(status)) return "amber";
  return "purple";
}

function errorMessage(error, fallback) {
  return error?.response?.data?.message || fallback;
}

export default function AIFollowups() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialFilters = { ...blankFilters, ...Object.fromEntries(searchParams.entries()) };
  const [filters, setFilters] = useState(initialFilters);
  const [data, setData] = useState(emptyState);
  const [page, setPage] = useState(Number(searchParams.get("page") || 1));
  const [tab, setTab] = useState("queue");
  const [drawer, setDrawer] = useState(null);
  const [draft, setDraft] = useState("");
  const [selectedHistory, setSelectedHistory] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [templateTemperature, setTemplateTemperature] = useState("hot");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  const params = useMemo(() => {
    const result = { page, per_page: 25 };
    Object.entries(filters).forEach(([key, value]) => { if (value) result[key] = value; });
    return result;
  }, [filters, page]);

  const load = useCallback(() => api.get("/ai-followups/workbench", { params })
    .then(({ data: body }) => setData(body))
    .catch((error) => setToast({ type: "error", message: errorMessage(error, "Could not load AI follow-ups") })), [params]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const query = {};
    Object.entries(filters).forEach(([key, value]) => { if (value) query[key] = value; });
    if (page > 1) query.page = String(page);
    setSearchParams(query, { replace: true });
  }, [filters, page, setSearchParams]);
  useEffect(() => {
    if (!data.settings.test_mode) return undefined;
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, [data.settings.test_mode, load]);

  const updateFilter = (key, value) => { setFilters((current) => ({ ...current, [key]: value })); setPage(1); };
  const resetFilters = () => { setFilters(blankFilters); setPage(1); };

  const openLead = async (leadId) => {
    setBusy(true);
    try {
      const { data: detail } = await api.get(`/ai-followups/lead/${leadId}`);
      setDrawer(detail);
      const latest = [...(detail.history || [])].reverse().find((row) => ["generated", "failed"].includes(row.status));
      setSelectedHistory(latest || null);
      setDraft(latest?.edited_message || latest?.generated_message || "");
    } catch (error) {
      setToast({ type: "error", message: errorMessage(error, "Could not open follow-up details") });
    } finally { setBusy(false); }
  };

  const refreshDrawer = async () => {
    if (!drawer?.lead?.id) return;
    const { data: detail } = await api.get(`/ai-followups/lead/${drawer.lead.id}`);
    setDrawer(detail);
  };

  const generate = async () => {
    setBusy(true);
    try {
      const { data: row } = await api.post(`/ai-followups/lead/${drawer.lead.id}/generate`);
      setSelectedHistory(row);
      setDraft(row.generated_message || "");
      await refreshDrawer();
      setToast({ type: "success", message: `Message ${row.sequence_step || "preview"} generated` });
    } catch (error) { setToast({ type: "error", message: errorMessage(error, "Could not generate message") }); }
    finally { setBusy(false); }
  };

  const send = async () => {
    if (!selectedHistory?.id || !draft.trim()) return;
    if (drawer.lead.stop_reason) {
      setToast({ type: "error", message: `Cannot send: ${drawer.lead.stop_reason}` });
      return;
    }
    setBusy(true);
    try {
      const { data: row } = await api.post(`/ai-followups/history/${selectedHistory.id}/send`, { message: draft });
      setSelectedHistory(row);
      await Promise.all([refreshDrawer(), load()]);
      setToast({ type: row.status === "sent" ? "success" : "error", message: row.status === "sent" ? "WhatsApp accepted the message" : `Message ${row.status}` });
    } catch (error) { setToast({ type: "error", message: errorMessage(error, "Could not send message") }); }
    finally { setBusy(false); }
  };

  const changeAutomation = async (action) => {
    setBusy(true);
    try {
      await api.post(`/ai-followups/lead/${drawer.lead.id}/${action}`, action === "pause" ? { reason: "Paused from AI follow-up operations" } : {});
      await Promise.all([refreshDrawer(), load()]);
      setToast({ type: "success", message: `Automation ${action === "pause" ? "paused" : "resumed"}` });
    } catch (error) { setToast({ type: "error", message: errorMessage(error, `Could not ${action} automation`) }); }
    finally { setBusy(false); }
  };

  const runDue = async () => {
    setBusy(true);
    try {
      const { data: result } = await api.post("/ai-followups/run", { limit: 50 });
      await load();
      setToast({ type: result.failed ? "error" : "success", message: `${result.sent} sent, ${result.skipped} skipped, ${result.failed} failed` });
    } catch (error) { setToast({ type: "error", message: errorMessage(error, "Could not run due follow-ups") }); }
    finally { setBusy(false); }
  };

  const loadTemplates = async () => {
    setBusy(true);
    try { const { data: rows } = await api.get("/ai-followups/templates"); setTemplates(rows); setTab("templates"); }
    catch (error) { setToast({ type: "error", message: errorMessage(error, "Could not load templates") }); }
    finally { setBusy(false); }
  };

  const editTemplate = (id, key, value) => setTemplates((rows) => rows.map((row) => row.id === id ? { ...row, [key]: value } : row));
  const saveTemplate = async (row) => {
    setBusy(true);
    try {
      const { data: saved } = await api.put(`/ai-followups/templates/${row.id}`, row);
      setTemplates((rows) => rows.map((item) => item.id === saved.id ? saved : item));
      setToast({ type: "success", message: `${sentenceCase(saved.temperature)} message ${saved.sequence_step} saved` });
    } catch (error) { setToast({ type: "error", message: errorMessage(error, "Could not save template") }); }
    finally { setBusy(false); }
  };
  const restoreTemplate = async (row) => {
    setBusy(true);
    try {
      const { data: restored } = await api.post(`/ai-followups/templates/${row.id}/restore`);
      setTemplates((rows) => rows.map((item) => item.id === restored.id ? restored : item));
      setToast({ type: "success", message: `Message ${restored.sequence_step} restored` });
    } catch (error) { setToast({ type: "error", message: errorMessage(error, "Could not restore template") }); }
    finally { setBusy(false); }
  };

  const m = data.metrics;
  return <div className="page ai-followups-page ai-operations-page">
    <section className="ai-ops-head">
      <div><span>Sequence operations</span><h2>AI follow-up control center</h2><p>Manage 10-step HOT and WARM sequences, exact recipients, schedules, and provider delivery evidence.</p></div>
      <div className="row-actions">
        {user?.role === "admin" && <Button variant="secondary" onClick={loadTemplates} disabled={busy}>Manage templates</Button>}
        {can(user, "ai_followups", "run") && <Button onClick={runDue} disabled={busy}>Run due now</Button>}
      </div>
    </section>

    {data.settings.test_mode && <div className="notice amber"><strong>Local minute test mode</strong><span>Production scheduling still uses the worker command and configured day intervals.</span></div>}

    <div className="followup-kpi-grid">
      <KpiCard label="Active automation leads" value={m.active_leads || 0} onClick={() => resetFilters()} />
      <KpiCard label="HOT leads in sequence" value={m.hot_active || 0} color="red" onClick={() => updateFilter("temperature", "hot")} />
      <KpiCard label="WARM leads in sequence" value={m.warm_active || 0} color="amber" onClick={() => updateFilter("temperature", "warm")} />
      <KpiCard label="Due now" value={m.ready_now || 0} color="amber" onClick={() => updateFilter("due", "now")} />
      <KpiCard label="Due today" value={m.due_today || 0} onClick={() => updateFilter("due", "today")} />
      <KpiCard label="Messages sent" value={m.sent || 0} color="teal" onClick={() => updateFilter("status", "sent")} />
      <KpiCard label="Delivered" value={m.delivered || 0} color="teal" onClick={() => updateFilter("status", "delivered")} />
      <KpiCard label="Failed" value={m.failed || 0} color="red" onClick={() => updateFilter("status", "failed")} />
      <KpiCard label="Paused or stopped" value={m.paused_stopped || 0} onClick={() => updateFilter("status", "stopped")} />
      <KpiCard label="Converted after follow-up" value={m.converted_after_followup || 0} color="teal" onClick={() => updateFilter("status", "converted")} />
    </div>

    {tab !== "templates" && <Card className="followup-filter-card">
      <div className="filter-head"><div><h2>Filters and search</h2><span>Results remain limited to leads you are authorized to access.</span></div><Button variant="secondary" onClick={resetFilters}>Clear filters</Button></div>
      <div className="followup-filter-grid">
        <label className="field filter-search"><span>Name or phone</span><input value={filters.search} onChange={(e) => updateFilter("search", e.target.value)} placeholder="Search recipient" /></label>
        <Filter label="Temperature" value={filters.temperature} onChange={(v) => updateFilter("temperature", v)} options={["hot", "warm", "cold"]} />
        <Filter label="Status" value={filters.status} onChange={(v) => updateFilter("status", v)} options={["generated", "pending", "sent", "delivered", "read", "failed", "skipped", "stopped", "cancelled"]} />
        <Filter label="Due" value={filters.due} onChange={(v) => updateFilter("due", v)} options={["now", "today"]} />
        <Filter label="Source" value={filters.source} onChange={(v) => updateFilter("source", v)} options={["website", "chatbot", "whatsapp", "email", "inperson"]} />
        {user?.role === "admin" && <label className="field"><span>Owner</span><select value={filters.owner} onChange={(e) => updateFilter("owner", e.target.value)}><option value="">All owners</option>{data.owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.name}</option>)}</select></label>}
        <label className="field"><span>From date</span><input type="date" value={filters.date_from} onChange={(e) => updateFilter("date_from", e.target.value)} /></label>
        <label className="field"><span>To date</span><input type="date" value={filters.date_to} onChange={(e) => updateFilter("date_to", e.target.value)} /></label>
      </div>
    </Card>}

    <div className="followup-tabs"><button className={tab === "queue" ? "active" : ""} onClick={() => setTab("queue")}>Follow-up queue</button><button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>Delivery history</button>{user?.role === "admin" && <button className={tab === "templates" ? "active" : ""} onClick={loadTemplates}>Sequence templates</button>}</div>

    {tab === "queue" && <QueueTable rows={data.leads} onOpen={openLead} />}
    {tab === "history" && <HistoryTable rows={data.history} onOpen={(row) => openLead(row.lead_id)} pagination={data.pagination} page={page} setPage={setPage} />}
    {tab === "templates" && <TemplateEditor rows={templates} temperature={templateTemperature} setTemperature={setTemplateTemperature} edit={editTemplate} save={saveTemplate} restore={restoreTemplate} busy={busy} settings={data.settings} canEdit={can(user, "settings", "update")} />}

    <Drawer open={Boolean(drawer)} title={drawer?.lead?.name || "Follow-up details"} onClose={() => setDrawer(null)}>
      {drawer && <LeadDrawer detail={drawer} selected={selectedHistory} setSelected={(row) => { setSelectedHistory(row); setDraft(row.edited_message || row.generated_message || ""); }} draft={draft} setDraft={setDraft} generate={generate} send={send} changeAutomation={changeAutomation} busy={busy} user={user} />}
    </Drawer>
    <Toast toast={toast} />
  </div>;
}

function Filter({ label, value, onChange, options }) {
  return <label className="field"><span>{label}</span><select value={value} onChange={(e) => onChange(e.target.value)}><option value="">All</option>{options.map((item) => <option value={item} key={item}>{sentenceCase(item)}</option>)}</select></label>;
}

function QueueTable({ rows, onOpen }) {
  return <Card><div className="card-head"><div><h2>Follow-up queue</h2><small>Exact recipient, message, schedule, and outcome</small></div><Badge>{rows.length}</Badge></div><div className="table-wrap data-table-wrap"><table className="data-table followup-queue-table"><thead><tr><th>Lead</th><th>Recipient</th><th>Temp</th><th>Owner</th><th>Sequence</th><th>Next scheduled</th><th>Status</th><th>Last / exact message</th><th>Delivery</th><th>Stop reason</th><th>Action</th></tr></thead><tbody>{rows.map((lead) => <tr key={lead.id}>
    <td data-label="Lead"><strong>{lead.name}</strong><small>{sentenceCase(lead.status)}</small></td>
    <td data-label="Recipient"><strong>{lead.normalized_phone || "No valid phone"}</strong><small>Original: {lead.phone || "—"}</small></td>
    <td data-label="Temperature"><Badge tone={lead.tag === "hot" ? "red" : lead.tag === "warm" ? "amber" : "purple"}>{lead.tag}</Badge></td>
    <td data-label="Owner">{lead.owner}</td><td data-label="Sequence">{lead.sequence_step} of {lead.sequence_length}</td><td data-label="Next scheduled">{formatDate(lead.ai_next_followup_at)}</td>
    <td data-label="Status"><Badge tone={tone(lead.automation_status)}>{sentenceCase(lead.automation_status)}</Badge></td>
    <td data-label="Exact message" className="message-preview-cell">{lead.last_message?.final_message || lead.last_message?.generated_message || "Not generated"}</td>
    <td data-label="Delivery"><Badge tone={tone(lead.last_message?.delivery_status)}>{sentenceCase(lead.last_message?.delivery_status || "pending")}</Badge></td>
    <td data-label="Stop reason">{lead.stop_reason || "—"}</td><td data-label="Action"><button onClick={() => onOpen(lead.id)}>Open</button></td>
  </tr>)}{!rows.length && <tr><td colSpan="11"><div className="empty compact-empty">No follow-ups match these filters.</div></td></tr>}</tbody></table></div></Card>;
}

function HistoryTable({ rows, onOpen, pagination, page, setPage }) {
  return <Card><div className="card-head"><div><h2>Delivery and provider audit</h2><small>Accepted does not mean delivered; provider evidence is retained.</small></div><Badge>{pagination.total || 0}</Badge></div><div className="table-wrap data-table-wrap"><table className="data-table"><thead><tr><th>Lead</th><th>Recipient</th><th>Step</th><th>Status</th><th>Scheduled</th><th>Sent</th><th>Exact final message</th><th>Provider ID</th><th>Action</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td data-label="Lead"><strong>{row.lead_name}</strong><small>{row.owner_name}</small></td><td data-label="Recipient">{row.recipient_phone || row.lead_phone || "—"}</td><td data-label="Step">{row.sequence_step ? `${row.sequence_step} of 10` : "—"}</td><td data-label="Status"><Badge tone={tone(row.delivery_status || row.status)}>{sentenceCase(row.delivery_status || row.status)}</Badge></td><td data-label="Scheduled">{formatDate(row.scheduled_for)}</td><td data-label="Sent">{formatDate(row.sent_at)}</td><td data-label="Exact final message" className="message-preview-cell">{row.final_message || row.edited_message || row.generated_message || row.skip_reason || "—"}</td><td data-label="Provider ID">{row.provider_message_id || "—"}</td><td data-label="Action"><button onClick={() => onOpen(row)}>Open lead</button></td></tr>)}</tbody></table></div><div className="pagination-row"><Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {pagination.page || 1} of {pagination.pages || 1}</span><Button variant="secondary" disabled={page >= (pagination.pages || 1)} onClick={() => setPage(page + 1)}>Next</Button></div></Card>;
}

function LeadDrawer({ detail, selected, setSelected, draft, setDraft, generate, send, changeAutomation, busy, user }) {
  const lead = detail.lead;
  const byStep = Object.fromEntries(detail.history.filter((row) => row.sequence_step).map((row) => [row.sequence_step, row]));
  return <div className="followup-detail"><div className="lead-detail-grid"><div><span>Phone</span><strong>{lead.normalized_phone || "No valid phone"}</strong><small>{lead.phone}</small></div><div><span>Email</span><strong>{lead.email || "—"}</strong></div><div><span>Owner</span><strong>{lead.owner}</strong></div><div><span>Source</span><strong>{sentenceCase(lead.source)}</strong></div><div><span>Temperature</span><strong>{sentenceCase(lead.tag)}</strong></div><div><span>Lead status</span><strong>{sentenceCase(lead.status)}</strong></div><div><span>Next scheduled</span><strong>{formatDate(lead.ai_next_followup_at)}</strong></div><div><span>Successful messages</span><strong>{lead.successful_messages} of {lead.sequence_length}</strong></div></div>
    {lead.stop_reason && <div className="notice red"><strong>Automation stopped</strong><span>{lead.stop_reason}</span></div>}
    <div className="drawer-actions">{lead.ai_followup_enabled ? <Button variant="danger" disabled={busy || !can(user, "ai_followups", "generate")} onClick={() => changeAutomation("pause")}>Pause automation</Button> : <Button disabled={busy || !can(user, "ai_followups", "generate")} onClick={() => changeAutomation("resume")}>Resume automation</Button>}</div>
    <Card className="message-composer"><div className="card-head"><div><h2>Preview and manual send</h2><small>Recipient: {lead.normalized_phone || "No valid phone"}</small></div><Badge>Message {selected?.sequence_step || lead.sequence_step}</Badge></div>{selected?.template_text && <div className="source-template"><span>Approved source template</span><p>{selected.template_text}</p></div>}<label className="field"><span>AI-generated or edited final message</span><textarea rows="7" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Generate the next approved sequence message" /></label><div className="drawer-actions"><Button variant="secondary" onClick={generate} disabled={busy || Boolean(lead.stop_reason) || !can(user, "ai_followups", "generate")}>Generate next message</Button><Button onClick={send} disabled={busy || Boolean(lead.stop_reason) || !selected?.id || !draft.trim() || selected?.status === "sent" || !can(user, "ai_followups", "send")}>Send to {lead.normalized_phone || "recipient"}</Button></div></Card>
    <div className="sequence-timeline"><h2>Complete 1-to-10 sequence timeline</h2>{Array.from({ length: 10 }, (_, index) => index + 1).map((step) => { const row = byStep[step]; return <button key={step} className={`sequence-item ${selected?.id === row?.id ? "active" : ""}`} onClick={() => row && setSelected(row)} disabled={!row}><span className="sequence-number">{step}</span><div><strong>Message {step}</strong><small>{row ? `${sentenceCase(row.delivery_status || row.status)} · ${formatDate(row.sent_at || row.scheduled_for)}` : "Planned"}</small>{row && <p>{row.final_message || row.generated_message || row.template_text || row.skip_reason}</p>}{row?.provider_message_id && <small>Provider ID: {row.provider_message_id}</small>}{row?.provider_error && <small className="error-text">{row.provider_error}</small>}</div></button>; })}</div>
  </div>;
}

function TemplateEditor({ rows, temperature, setTemperature, edit, save, restore, busy, settings, canEdit }) {
  const interval = temperature === "hot" ? settings.ai_followup_hot_interval_days : settings.ai_followup_warm_interval_days;
  return <Card className="template-editor"><div className="card-head"><div><h2>Approved sequence templates</h2><small>{interval} day interval · placeholders: {"{lead_name}"}, {"{service}"}, {"{owner_name}"}</small></div><div className="segmented"><button className={temperature === "hot" ? "active" : ""} onClick={() => setTemperature("hot")}>HOT 1–10</button><button className={temperature === "warm" ? "active" : ""} onClick={() => setTemperature("warm")}>WARM 1–10</button></div></div><div className="template-list">{rows.filter((row) => row.temperature === temperature).map((row) => <div className="template-row" key={row.id}><div className="template-step"><strong>Message {row.sequence_step}</strong><label><input type="checkbox" checked={Boolean(row.is_active)} disabled={!canEdit} onChange={(e) => edit(row.id, "is_active", e.target.checked)} /> Active</label></div><div><label className="field"><span>Approved template text</span><textarea rows="3" value={row.template_body} disabled={!canEdit} onChange={(e) => edit(row.id, "template_body", e.target.value)} /></label><div className="template-sample"><span>Sample preview</span><p>{row.template_body.replaceAll("{lead_name}", "Priya").replaceAll("{service}", "AI Course").replaceAll("{owner_name}", "Sales Team")}</p></div></div><label className="field"><span>Internal description</span><input value={row.description || ""} disabled={!canEdit} onChange={(e) => edit(row.id, "description", e.target.value)} /></label>{canEdit && <div className="template-actions"><Button variant="secondary" onClick={() => restore(row)} disabled={busy}>Restore</Button><Button onClick={() => save(row)} disabled={busy}>Save message {row.sequence_step}</Button></div>}</div>)}</div></Card>;
}
