import { useEffect, useMemo, useState } from "react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import KpiCard from "../components/UI/KpiCard.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { sentenceCase } from "../utils/text.js";
import { can } from "../permissions.js";

const emptyState = {
  settings: {},
  metrics: {},
  leads: [],
  history: [],
};

function formatDate(value) {
  if (!value) return "-";
  const utcValue = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return new Date(utcValue).toLocaleString();
}

function tone(status) {
  if (status === "sent" || status === "ready") return "teal";
  if (status === "failed" || status === "stopped") return "red";
  if (status === "generated") return "amber";
  return "purple";
}

export default function AIFollowups() {
  const { user } = useAuth();
  const [data, setData] = useState(emptyState);
  const [selectedLeadId, setSelectedLeadId] = useState("");
  const [selectedHistory, setSelectedHistory] = useState(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  const selectedLead = useMemo(
    () => data.leads.find((lead) => String(lead.id) === String(selectedLeadId)),
    [data.leads, selectedLeadId]
  );

  const load = () => api.get("/ai-followups/workbench")
    .then(({ data: body }) => {
      setData(body);
      setSelectedLeadId((current) => current || body.leads?.[0]?.id || "");
    })
    .catch(() => setToast({ type: "error", message: "Could not load AI follow-ups" }));

  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!data.settings.test_mode) return undefined;
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, [data.settings.test_mode]);

  const generate = () => {
    if (!selectedLeadId) return;
    setLoading(true);
    api.post(`/ai-followups/lead/${selectedLeadId}/generate`)
      .then(({ data: row }) => {
        setSelectedHistory(row);
        setMessage(row.generated_message || "");
        setToast({ type: "success", message: "Message generated" });
        load();
      })
      .catch(() => setToast({ type: "error", message: "Could not generate message" }))
      .finally(() => setLoading(false));
  };

  const send = () => {
    if (!selectedHistory?.id) return;
    setLoading(true);
    api.post(`/ai-followups/history/${selectedHistory.id}/send`, { message })
      .then(({ data: row }) => {
        setSelectedHistory(row);
        setToast({ type: row.status === "sent" ? "success" : "error", message: row.status === "sent" ? "Message sent" : "Message not sent" });
        load();
      })
      .catch(() => setToast({ type: "error", message: "Could not send message" }))
      .finally(() => setLoading(false));
  };

  const runDue = () => {
    setLoading(true);
    api.post("/ai-followups/run", { limit: 25 })
      .then(({ data: result }) => {
        setToast({ type: "success", message: `Run complete: ${result.sent} sent, ${result.skipped} skipped, ${result.failed} failed` });
        load();
      })
      .catch(() => setToast({ type: "error", message: "Could not run scheduled follow-ups" }))
      .finally(() => setLoading(false));
  };

  const pickHistory = (row) => {
    setSelectedHistory(row);
    setSelectedLeadId(row.lead_id);
    setMessage(row.edited_message || row.generated_message || "");
  };

  return <div className="page ai-followups-page">
    <div className="kpi-grid">
      <KpiCard label="Ready Now" value={data.metrics.ready_now || 0} color="teal" />
      <KpiCard label="Due Today" value={data.metrics.due_today || 0} color="amber" />
      <KpiCard label="Messages Sent" value={data.metrics.sent || 0} color="purple" />
      <KpiCard label="Failed" value={data.metrics.failed || 0} color="red" />
    </div>

    <div className="grid two">
      <Card>
        <div className="card-head">
          <div>
            <h2>AI follow-up test</h2>
            <small>{data.settings.enabled ? "Automation enabled" : "Automation disabled"} - {data.settings.preferred_channel || "WhatsApp"} - {data.settings.model || "fallback"}</small>
          </div>
          {can(user, "ai_followups", "run") && <Button onClick={runDue} disabled={loading}>Run scheduled follow-ups</Button>}
        </div>

        {data.settings.test_mode && <div className="notice amber">
          Local minute test is active: Hot every {data.settings.test_intervals_minutes?.hot} minutes, Warm every {data.settings.test_intervals_minutes?.warm} minutes, and Cold every {data.settings.test_intervals_minutes?.cold} minutes. Keep the backend running.
        </div>}

        <div className="form-grid">
          <label className="field wide">
            <span>Lead</span>
            <select value={selectedLeadId} onChange={(e) => { setSelectedLeadId(e.target.value); setSelectedHistory(null); setMessage(""); }}>
              {data.leads.map((lead) => <option key={lead.id} value={lead.id}>{lead.name} - {sentenceCase(lead.tag, "Warm")} - {sentenceCase(lead.channel)}</option>)}
            </select>
          </label>
          {selectedLead && <div className="mini-grid wide">
            <div><span>Status</span><strong>{sentenceCase(selectedLead.status)}</strong></div>
            <div><span>Temperature</span><strong>{sentenceCase(selectedLead.tag, "Warm")}</strong></div>
            <div><span>Next</span><strong>{formatDate(selectedLead.ai_next_followup_at)}</strong></div>
            <div><span>Count</span><strong>{selectedLead.ai_followup_count || 0}</strong></div>
          </div>}
          <label className="field wide">
            <span>Generated or edited message</span>
            <textarea rows="8" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Generate a message to preview it here." />
          </label>
          {selectedLead?.stop_reason && <div className="notice red wide">{selectedLead.stop_reason}</div>}
          <Button onClick={generate} disabled={loading || !selectedLeadId || !can(user, "ai_followups", "generate")}>Generate message</Button>
          <Button onClick={send} disabled={loading || !selectedHistory?.id || !message || !can(user, "ai_followups", "send")}>Send via WhatsApp or email</Button>
        </div>
      </Card>

      <Card>
        <h2>Lead queue</h2>
        <div className="compact-list">
          {data.leads.map((lead) => <button className={`list-row ${String(lead.id) === String(selectedLeadId) ? "active-row" : ""}`} key={lead.id} onClick={() => setSelectedLeadId(lead.id)}>
            <span><strong>{lead.name}</strong><small>{lead.phone || lead.email || lead.company || "-"}</small></span>
            <Badge tone={tone(lead.automation_status)}>{lead.automation_status}</Badge>
          </button>)}
          {!data.leads.length && <div className="empty compact-empty">No active leads found.</div>}
        </div>
      </Card>
    </div>

    <Card>
      <div className="card-head"><h2>Follow-up history</h2><Badge>{data.history.length}</Badge></div>
      <div className="table-wrap data-table-wrap">
        <table className="data-table">
          <thead><tr><th>Lead</th><th>Channel</th><th>Status</th><th>Scheduled</th><th>Sent</th><th>Message</th><th>Action</th></tr></thead>
          <tbody>
            {data.history.map((row) => <tr key={row.id}>
              <td data-label="Lead">{row.lead_id}</td>
              <td data-label="Channel">{sentenceCase(row.channel)}</td>
              <td data-label="Status"><Badge tone={tone(row.status)}>{row.status}</Badge></td>
              <td data-label="Scheduled">{formatDate(row.scheduled_for)}</td>
              <td data-label="Sent">{formatDate(row.sent_at)}</td>
              <td data-label="Message" className="clip-cell">{row.edited_message || row.generated_message || row.skip_reason || "-"}</td>
              <td data-label="Action"><button onClick={() => pickHistory(row)}>Open</button></td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </Card>
    <Toast toast={toast} />
  </div>;
}
