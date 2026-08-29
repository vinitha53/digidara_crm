import { useEffect, useMemo, useState } from "react";
import { IconBrandWhatsapp, IconCheck, IconSearch, IconSend, IconUsers } from "@tabler/icons-react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";

const templates = {
  "Customer update": "Hi {name}, here is an update from Digidara Technologies regarding {service}.",
  "Follow-up": "Hi {name}, we are following up regarding {service}. Please let us know if you need any assistance.",
  "Feedback": "Hi {name}, thank you for choosing Digidara Technologies for {service}. We would appreciate your feedback.",
  "Important notice": "Hi {name}, we have an important update regarding {service}. Please reply to this message when convenient.",
};

const utilityUpdates = {
  "Customer update": "Your service request is currently being reviewed by our team.",
  "Follow-up": "We are waiting for your response before we can continue processing this service request.",
  "Feedback": "Your service request has been completed. Please reply with feedback about the completed service.",
  "Important notice": "There is an important status update on your service request. Please reply if you need clarification.",
};

export default function Communication() {
  const { user } = useAuth();
  const [customers, setCustomers] = useState([]);
  const [recipientTotal, setRecipientTotal] = useState(0);
  const [limited, setLimited] = useState(false);
  const [logs, setLogs] = useState([]);
  const [mode, setMode] = useState("single");
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedCustomerIds, setSelectedCustomerIds] = useState([]);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const [form, setForm] = useState({ recipient_id: "", template_used: "Customer update", message_body: utilityUpdates["Customer update"] });
  const [bulkForm, setBulkForm] = useState({ template_used: "Customer update", message_body: templates["Customer update"] });

  const load = () => Promise.all([
    api.get("/communication/customer-recipients"),
    api.get("/communication/message-log", { params: { recipient_type: "customer" } }),
  ]).then(([recipients, history]) => {
    setCustomers(recipients.data.items || []);
    setRecipientTotal(recipients.data.total || 0);
    setLimited(Boolean(recipients.data.limited));
    setLogs(history.data || []);
  });

  useEffect(() => {
    load()
      .catch(() => setToast({ type: "error", message: "Could not load customer communication data" }))
      .finally(() => setLoading(false));
  }, []);

  const visibleCustomers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return customers.filter((customer) => {
      if (status !== "all" && customer.status !== status) return false;
      if (!term) return true;
      return [customer.name, customer.phone, customer.email, customer.service].some((value) => String(value || "").toLowerCase().includes(term));
    });
  }, [customers, search, status]);

  const selectedCustomer = customers.find((customer) => String(customer.id) === String(form.recipient_id));
  const selectedCount = selectedCustomerIds.length;
  const visibleIds = visibleCustomers.map((customer) => customer.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedCustomerIds.includes(id));
  const delivery = {
    sent: logs.filter((log) => log.status === "sent").length,
    skipped: logs.filter((log) => log.status === "skipped").length,
    failed: logs.filter((log) => log.status === "failed").length,
  };

  const chooseTemplate = (template, bulk = false) => {
    if (bulk) setBulkForm({ template_used: template, message_body: templates[template] });
    else setForm((old) => ({ ...old, template_used: template, message_body: utilityUpdates[template] }));
  };

  const sendSingle = (event) => {
    event.preventDefault();
    setSending(true);
    api.post("/communication/quick-send", {
      recipient_type: "customer",
      recipient_id: Number(form.recipient_id),
      channel: "WhatsApp",
      template_used: form.template_used,
      message_body: form.message_body,
    }).then(({ data }) => {
      setToast({ type: data.status === "failed" ? "error" : "success", message: data.status === "sent" ? `WhatsApp sent to ${selectedCustomer?.name}` : `WhatsApp ${data.status}` });
      load();
    }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "WhatsApp message failed" }))
      .finally(() => setSending(false));
  };

  const sendBulk = (event) => {
    event.preventDefault();
    if (!selectedCount) return setToast({ type: "error", message: "Select at least one customer" });
    setSending(true);
    api.post("/communication/bulk-whatsapp", {
      customer_ids: selectedCustomerIds,
      template_used: bulkForm.template_used,
      message_body: bulkForm.message_body,
    }).then(({ data }) => {
      const result = data.summary || {};
      setToast({ type: result.failed ? "error" : "success", message: `Bulk complete: ${result.sent || 0} sent, ${result.skipped || 0} skipped, ${result.failed || 0} failed` });
      setSelectedCustomerIds([]);
      load();
    }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Bulk WhatsApp failed" }))
      .finally(() => setSending(false));
  };

  const toggleCustomer = (id) => setSelectedCustomerIds((old) => old.includes(id) ? old.filter((value) => value !== id) : [...old, id]);
  const toggleVisible = () => setSelectedCustomerIds((old) => allVisibleSelected ? old.filter((id) => !visibleIds.includes(id)) : [...new Set([...old, ...visibleIds])]);

  return <div className="page communication-page focused-communication">
    <div className="communication-head"><div><span>Customer communication</span><h2>Send WhatsApp messages to customers</h2><p>Select one customer for a personal update or select multiple customers for a personalized bulk message.</p></div><div className="whatsapp-mark"><IconBrandWhatsapp size={28} /><span>WhatsApp</span></div></div>

    <div className="communication-summary">
      <Card><span>Available customers</span><strong>{recipientTotal}</strong><small>{limited ? "Showing first 200" : "Within your access"}</small></Card>
      <Card><span>Selected for bulk</span><strong>{selectedCount}</strong><small>Current audience</small></Card>
      <Card><span>Recently sent</span><strong>{delivery.sent}</strong><small>Latest delivery log</small></Card>
      <Card className={delivery.failed ? "attention" : ""}><span>Needs attention</span><strong>{delivery.failed + delivery.skipped}</strong><small>Failed or skipped</small></Card>
    </div>

    {can(user, "communication", "send") && <>
      <div className="communication-mode" role="tablist"><button role="tab" className={mode === "single" ? "active" : ""} onClick={() => setMode("single")}><IconBrandWhatsapp size={18} />Single customer</button><button role="tab" className={mode === "bulk" ? "active" : ""} onClick={() => setMode("bulk")}><IconUsers size={18} />Bulk customers <span>{selectedCount}</span></button></div>

      {mode === "single" && <div className="communication-workspace single">
        <Card className="recipient-panel"><div className="communication-card-head"><div><span>STEP 1</span><h2>Choose customer</h2></div><Badge>{visibleCustomers.length} shown</Badge></div><CustomerFilters search={search} setSearch={setSearch} status={status} setStatus={setStatus} customers={customers} />
          <div className="communication-recipient-list">{loading && <CommunicationListSkeleton />}{!loading && visibleCustomers.map((customer) => <button type="button" className={String(customer.id) === String(form.recipient_id) ? "active" : ""} key={customer.id} onClick={() => setForm((old) => ({ ...old, recipient_id: String(customer.id) }))}><span className="recipient-check">{String(customer.id) === String(form.recipient_id) && <IconCheck size={14} />}</span><div><strong>{customer.name}</strong><span>{customer.phone}</span><small>{customer.service}</small></div><Badge tone={customer.status === "active" ? "teal" : "amber"}>{customer.status === "followup" ? "Follow-up" : customer.status}</Badge></button>)}{!loading && !visibleCustomers.length && <div className="empty compact-empty">No customers match this view.</div>}</div>
        </Card>
        <Card className="message-composer"><div className="communication-card-head"><div><span>STEP 2</span><h2>Write and send</h2></div><IconBrandWhatsapp size={24} /></div>
          <form onSubmit={sendSingle} className="communication-form">{selectedCustomer && <SelectedRecipient customer={selectedCustomer} />}<label className="field"><span>Utility update</span><select value={form.template_used} onChange={(event) => chooseTemplate(event.target.value)}>{Object.keys(utilityUpdates).map((name) => <option key={name}>{name}</option>)}</select></label><label className="field"><span>Status update</span><textarea rows="7" value={form.message_body} onChange={(event) => setForm({ ...form, message_body: event.target.value })} required /></label><MessagePreview message={form.message_body} customer={selectedCustomer} /><Button disabled={!selectedCustomer || sending}><IconSend size={17} />{sending ? "Sending..." : "Send WhatsApp"}</Button></form>
        </Card>
      </div>}

      {mode === "bulk" && <div className="communication-workspace bulk">
        <Card className="recipient-panel"><div className="communication-card-head"><div><span>STEP 1</span><h2>Select customers</h2></div><button type="button" className="ghost-action compact" onClick={toggleVisible}>{allVisibleSelected ? "Clear shown" : "Select shown"}</button></div><CustomerFilters search={search} setSearch={setSearch} status={status} setStatus={setStatus} customers={customers} />
          <div className="communication-recipient-list check-list">{loading && <CommunicationListSkeleton />}{!loading && visibleCustomers.map((customer) => <label className={selectedCustomerIds.includes(customer.id) ? "active" : ""} key={customer.id}><input type="checkbox" checked={selectedCustomerIds.includes(customer.id)} onChange={() => toggleCustomer(customer.id)} /><div><strong>{customer.name}</strong><span>{customer.phone}</span><small>{customer.service}</small></div><Badge tone={customer.status === "active" ? "teal" : "amber"}>{customer.status === "followup" ? "Follow-up" : customer.status}</Badge></label>)}{!loading && !visibleCustomers.length && <div className="empty compact-empty">No customers match this view.</div>}</div>
        </Card>
        <Card className="message-composer"><div className="communication-card-head"><div><span>STEP 2</span><h2>Personalize bulk message</h2></div><Badge tone="teal">{selectedCount} selected</Badge></div>
          <form onSubmit={sendBulk} className="communication-form"><label className="field"><span>Template</span><select value={bulkForm.template_used} onChange={(event) => chooseTemplate(event.target.value, true)}>{Object.keys(templates).map((name) => <option key={name}>{name}</option>)}</select></label><label className="field"><span>Message sent separately to each customer</span><textarea rows="7" value={bulkForm.message_body} onChange={(event) => setBulkForm({ ...bulkForm, message_body: event.target.value })} required /></label><TokenHelp /><MessagePreview message={bulkForm.message_body} customer={customers.find((customer) => selectedCustomerIds.includes(customer.id))} /><Button disabled={!selectedCount || sending}><IconSend size={17} />{sending ? "Sending..." : `Send to ${selectedCount} customer${selectedCount === 1 ? "" : "s"}`}</Button></form>
        </Card>
      </div>}
    </>}

    <Card className="communication-history"><div className="communication-card-head"><div><span>DELIVERY HISTORY</span><h2>Recent customer WhatsApp messages</h2></div><div className="delivery-legend"><Badge tone="teal">{delivery.sent} sent</Badge>{delivery.skipped > 0 && <Badge tone="amber">{delivery.skipped} skipped</Badge>}{delivery.failed > 0 && <Badge tone="red">{delivery.failed} failed</Badge>}</div></div>
      <div className="communication-log-head"><span>Customer</span><span>Message</span><span>Sent</span><span>Status</span></div>
      <div className="communication-log-list">{loading && <div className="skeleton table-skeleton" />}{!loading && logs.map((log) => <article key={log.id}><div><strong>{log.recipient_name || "Customer"}</strong><small>{log.template_used || "WhatsApp"}</small></div><p>{log.message_body}</p><time>{formatDateTime(log.sent_at)}</time><Badge tone={statusTone(log.status)}>{log.status}</Badge></article>)}{!loading && !logs.length && <div className="empty">No customer WhatsApp messages have been sent yet.</div>}</div>
    </Card>
    <Toast toast={toast} />
  </div>;
}

function CustomerFilters({ search, setSearch, status, setStatus, customers }) {
  const count = (value) => value === "all" ? customers.length : customers.filter((customer) => customer.status === value).length;
  return <div className="recipient-filters"><div className="recipient-search"><IconSearch size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search customer, phone or service" /></div><div className="recipient-status"><button type="button" className={status === "all" ? "active" : ""} onClick={() => setStatus("all")}>All <span>{count("all")}</span></button><button type="button" className={status === "active" ? "active" : ""} onClick={() => setStatus("active")}>Active <span>{count("active")}</span></button><button type="button" className={status === "followup" ? "active" : ""} onClick={() => setStatus("followup")}>Follow-up <span>{count("followup")}</span></button></div></div>;
}

function SelectedRecipient({ customer }) { return <div className="selected-recipient"><span className="selected-recipient-icon"><IconCheck size={15} /></span><div><small>Sending to</small><strong>{customer.name}</strong><span>{customer.phone} · {customer.service}</span></div><Badge tone="teal">Selected</Badge></div>; }
function CommunicationListSkeleton() { return <div className="communication-list-skeleton"><span /><span /><span /><span /></div>; }
function TokenHelp() { return <div className="token-help"><strong>Personalization:</strong><span>{"{name}"}</span><span>{"{phone}"}</span><span>{"{email}"}</span><span>{"{service}"}</span></div>; }
function MessagePreview({ message, customer }) { return <div className="whatsapp-preview"><div><IconBrandWhatsapp size={16} /><strong>Preview</strong><span>{customer?.name || "Select a customer"}</span></div><p>{customer ? personalize(message, customer) : "Choose a customer to preview the personalized message."}</p></div>; }
function personalize(message, customer) { return message.replaceAll("{name}", customer.name || "").replaceAll("{phone}", customer.phone || "").replaceAll("{email}", customer.email || "").replaceAll("{service}", customer.service || ""); }
function statusTone(status) { return status === "sent" ? "teal" : status === "failed" ? "red" : "amber"; }
function formatDateTime(value) { return value ? new Date(value).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-"; }
