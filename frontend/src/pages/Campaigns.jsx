import { useEffect, useState } from "react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import KpiCard from "../components/UI/KpiCard.jsx";
import Modal from "../components/UI/Modal.jsx";
import Toast from "../components/UI/Toast.jsx";
import DataTable from "../components/shared/DataTable.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";

export default function Campaigns() {
  const { user } = useAuth();
  const [items, setItems] = useState([]), [modal, setModal] = useState(null), [toast, setToast] = useState(null);
  const [form, setForm] = useState({ name: "", channel: "WhatsApp", audience: "All leads", from_name: "Digidara Technologies", message_body: "Hi {name}, we have an update from Digidara Technologies." });
  const load = () => api.get("/campaigns").then(({ data }) => setItems(data)).catch(() => setToast({ type: "error", message: "Could not load campaigns" }));
  useEffect(() => { load(); }, []);
  const save = (status = "draft") => api.post("/campaigns", { ...form, status }).then(({ data }) => { setToast({ type: "success", message: "Campaign saved" }); if (status === "sent") return api.post(`/campaigns/${data.id}/send`).then(load); load(); });
  const send = (id) => api.post(`/campaigns/${id}/send`).then(load);
  const cols = [{ label: "Name", key: "name" }, { label: "Channel", key: "channel" }, { label: "Audience", key: "audience" }, { label: "Sent", key: "sent_count" }, { label: "Opened", key: "opened_count" }, { label: "Replies", key: "reply_count" }, { label: "Status", key: "status", render: (r) => <Badge>{r.status}</Badge> }, { label: "Actions", key: "actions", render: (r) => <div className="row-actions"><button onClick={() => setModal(r)}>View</button>{can(user, "campaigns", "send") && <button onClick={() => send(r.id)}>Send</button>}</div> }];
  const sent = items.reduce((a, b) => a + (b.sent_count || 0), 0), opened = items.reduce((a, b) => a + (b.opened_count || 0), 0);
  return <div className="page campaigns-page"><div className="kpi-grid"><KpiCard label="Campaigns Sent" value={items.filter((x) => x.status === "sent").length} /><KpiCard label="Messages Sent" value={sent} color="teal" /><KpiCard label="Open Rate" value={`${Math.round(opened / Math.max(sent, 1) * 100)}%`} color="amber" /><KpiCard label="Leads Generated" value={items.reduce((a, b) => a + (b.reply_count || 0), 0)} color="red" /></div>{can(user, "campaigns", "create") && <Card className="campaign-composer"><h2>Campaign Composer</h2><div className="form-grid"><input placeholder="Campaign name*" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /><select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}><option>WhatsApp</option><option>Email</option><option>Both</option></select><select value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })}><option>All leads</option><option>Hot leads</option><option>Warm leads</option><option>Cold leads</option><option>All customers</option></select><textarea value={form.message_body} onChange={(e) => setForm({ ...form, message_body: e.target.value })} /><Button onClick={() => save("draft")}>Save Draft</Button>{can(user, "campaigns", "send") && <Button onClick={() => save("sent")}>Send Now</Button>}</div></Card>}<DataTable columns={cols} data={items} /><Modal open={modal} title={modal?.name} onClose={() => setModal(null)}>{modal && <div><p>Open rate: {Math.round((modal.opened_count || 0) / Math.max(modal.sent_count || 1, 1) * 100)}%</p><div className="meter"><span style={{ width: `${Math.round((modal.opened_count || 0) / Math.max(modal.sent_count || 1, 1) * 100)}%` }} /></div><p>Sent {modal.sent_count} - Opened {modal.opened_count} - Replies {modal.reply_count}</p></div>}</Modal><Toast toast={toast} /></div>;
}
