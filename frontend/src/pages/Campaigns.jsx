import { useEffect, useMemo, useState } from "react";
import { IconAlertTriangle, IconArrowLeft, IconArrowRight, IconBrandWhatsapp, IconCheck, IconDownload, IconPlayerPause, IconPlayerPlay, IconRefresh, IconSearch, IconSend, IconTemplate } from "@tabler/icons-react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import DataTable from "../components/shared/DataTable.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";
import { sentenceCase } from "../utils/text.js";

const audienceCards = [
  ["all", "All Leads", "Every lead in your permitted scope"],
  ["hot", "Hot Leads", "High-intent leads ready for action"],
  ["warm", "Warm Leads", "Engaged leads needing a nudge"],
  ["cold", "Cold Leads", "Re-engagement audience"],
  ["custom", "Custom Filters", "Build a precise audience"],
];
const emptyFilters = { search: "", status: "", source: "", service: "", destination: "", city: "", assigned_to: "", branch: "", created_from: "", created_to: "", marketing_consent: "", opted_out: "false" };
const emptyAudience = { total_count: 0, eligible_count: 0, excluded_count: 0, exclusion_reasons: {}, preview: [] };
const variableFields = [
  ["name", "Lead name"], ["first_name", "First name"], ["last_name", "Last name"], ["phone", "Phone"],
  ["email", "Email"], ["company", "Company"], ["service", "Service"], ["destination", "Destination"],
  ["city", "City"], ["deal_value", "Budget / deal value"], ["travel_date", "Travel date"], ["tag", "Lead classification"],
  ["status", "Lead status"], ["source", "Source"], ["assigned_name", "Assigned staff"], ["branch", "Branch"], ["fixed", "Fixed value"],
];

function templateText(template, type) {
  return (template?.components || []).find((item) => item.type === type)?.text || "";
}

function variableNumbers(template) {
  return [...new Set((templateText(template, "BODY").match(/\{\{\d+\}\}/g) || []).map((item) => Number(item.replace(/\D/g, ""))))].sort((a, b) => a - b);
}

function downloadBlob(data, filename) {
  const url = URL.createObjectURL(data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function reasonLabel(value) {
  return ({ invalid_or_missing_phone: "Missing / invalid phone", opted_out: "Opted out", consent_required: "Consent pending", duplicate_phone: "Duplicate phone", missing_template_variable: "Missing template value" })[value] || sentenceCase(value);
}

export default function Campaigns() {
  const { user } = useAuth();
  const [campaigns, setCampaigns] = useState([]);
  const [step, setStep] = useState(1);
  const [audienceType, setAudienceType] = useState("all");
  const [filters, setFilters] = useState(emptyFilters);
  const [audience, setAudience] = useState(emptyAudience);
  const [templates, setTemplates] = useState([]);
  const [assignees, setAssignees] = useState([]);
  const [templateQuery, setTemplateQuery] = useState("");
  const [templateCategory, setTemplateCategory] = useState("");
  const [templateLanguage, setTemplateLanguage] = useState("");
  const [imageOnly, setImageOnly] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [mapping, setMapping] = useState({});
  const [name, setName] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");
  const [testPhone, setTestPhone] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [imageFile, setImageFile] = useState(null);
  const [campaignId, setCampaignId] = useState(null);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [recipients, setRecipients] = useState([]);
  const [recipientSearch, setRecipientSearch] = useState("");
  const [recipientStatus, setRecipientStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [configuration, setConfiguration] = useState(null);
  const [toast, setToast] = useState(null);

  const audienceFilters = useMemo(() => ({ ...filters, classification: audienceType === "custom" ? "all" : audienceType }), [filters, audienceType]);
  const vars = useMemo(() => variableNumbers(selectedTemplate), [selectedTemplate]);
  const filteredTemplates = useMemo(() => templates.filter((item) => {
    if (templateQuery && !item.name.toLowerCase().includes(templateQuery.toLowerCase())) return false;
    if (templateCategory && item.category !== templateCategory) return false;
    if (templateLanguage && item.language !== templateLanguage) return false;
    if (imageOnly && item.header_type !== "IMAGE") return false;
    return true;
  }), [templates, templateQuery, templateCategory, templateLanguage, imageOnly]);
  const sample = audience.preview.find((item) => !item.reason) || audience.preview[0] || {};
  const renderedPreview = useMemo(() => vars.reduce((body, number) => {
    const config = mapping[number] || {};
    let value = config.field === "fixed" ? config.value : sample[config.field];
    if (!value && config.fallback) value = config.fallback;
    return body.replaceAll(`{{${number}}}`, value || `Missing value ${number}`);
  }, templateText(selectedTemplate, "BODY")), [selectedTemplate, vars, mapping, sample]);

  const loadCampaigns = () => api.get("/campaigns").then(({ data }) => setCampaigns(data));
  const loadAudience = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/campaigns/audience", { params: audienceFilters });
      setAudience(data);
    } catch (error) {
      setToast({ type: "error", message: error.response?.data?.message || "Could not calculate the audience" });
    } finally { setLoading(false); }
  };
  const loadTemplates = async () => {
    setTemplatesLoading(true);
    try {
      const { data } = await api.get("/campaigns/templates");
      setTemplates(data.items || []);
      setConfiguration(data.configuration);
    } catch (error) {
      setToast({ type: "error", message: error.response?.data?.message || "Could not load approved templates" });
    } finally { setTemplatesLoading(false); }
  };
  useEffect(() => { loadCampaigns().catch(() => setToast({ type: "error", message: "Could not load campaigns" })); loadTemplates(); if (can(user, "leads", "assign")) api.get("/leads/assignees").then(({ data }) => setAssignees(data)).catch(() => {}); }, []);
  useEffect(() => { const timer = setTimeout(loadAudience, 250); return () => clearTimeout(timer); }, [audienceFilters]);

  const selectTemplate = (template) => {
    setSelectedTemplate(template);
    const defaults = {};
    variableNumbers(template).forEach((number, index) => { defaults[number] = { field: index === 0 ? "name" : index === 1 ? "service" : "assigned_name", fallback: "" }; });
    setMapping(defaults);
    setImageFile(null);
  };
  const refreshTemplates = async () => {
    setTemplatesLoading(true);
    try {
      await api.post("/campaigns/templates/refresh");
      await loadTemplates();
      setToast({ type: "success", message: "Approved Meta templates synchronized" });
    } catch (error) { setToast({ type: "error", message: error.response?.data?.message || "Template synchronization failed" }); setTemplatesLoading(false); }
  };
  const exportAudience = async () => {
    const { data } = await api.get("/campaigns/audience/export", { params: audienceFilters, responseType: "blob" });
    downloadBlob(data, "whatsapp-audience.csv");
  };
  const payload = () => ({
    name, audience_type: audienceType, audience: audienceCards.find(([key]) => key === audienceType)?.[1], audience_filter: audienceFilters,
    template_name: selectedTemplate?.name, template_language: selectedTemplate?.language, template_category: selectedTemplate?.category,
    template_snapshot: selectedTemplate ? { ...selectedTemplate, components: selectedTemplate.components || [] } : null,
    header_type: selectedTemplate?.header_type, message_body: templateText(selectedTemplate, "BODY"), variable_mapping: { body: mapping },
  });
  const saveDraft = async () => {
    if (!name.trim() || !selectedTemplate) throw new Error("Enter a campaign name and select an approved template");
    const response = campaignId ? await api.put(`/campaigns/${campaignId}`, payload()) : await api.post("/campaigns", payload());
    let id = response.data.id;
    setCampaignId(id);
    if (selectedTemplate.header_type === "IMAGE" && imageFile && !response.data.media_id) {
      const body = new FormData(); body.append("file", imageFile);
      await api.post(`/campaigns/${id}/media`, body);
    }
    await loadCampaigns();
    return id;
  };
  const saveOnly = async () => {
    setLoading(true);
    try { await saveDraft(); setToast({ type: "success", message: "Campaign saved as draft" }); }
    catch (error) { setToast({ type: "error", message: error.response?.data?.message || error.message || "Could not save campaign" }); }
    finally { setLoading(false); }
  };
  const sendTest = async () => {
    setLoading(true);
    try {
      const id = await saveDraft();
      const bodyParams = vars.map((number) => {
        const config = mapping[number] || {};
        return config.field === "fixed" ? config.value : sample[config.field] || config.fallback || "Test";
      });
      await api.post(`/campaigns/${id}/test`, { phone: testPhone, body_params: bodyParams });
      setToast({ type: "success", message: "Test template message accepted by Meta" });
    } catch (error) { setToast({ type: "error", message: error.response?.data?.message || "Test send failed" }); }
    finally { setLoading(false); }
  };
  const launch = async (scheduled = false) => {
    setLoading(true);
    try {
      const id = await saveDraft();
      if (scheduled) await api.post(`/campaigns/${id}/schedule`, { scheduled_at: scheduleAt, confirmed });
      else await api.post(`/campaigns/${id}/launch`, { confirmed });
      setToast({ type: "success", message: scheduled ? "Campaign scheduled" : "Campaign queued for the WhatsApp worker" });
      resetWizard(); await loadCampaigns();
    } catch (error) { setToast({ type: "error", message: error.response?.data?.message || error.message || "Could not launch campaign" }); }
    finally { setLoading(false); }
  };
  const resetWizard = () => { setStep(1); setCampaignId(null); setName(""); setSelectedTemplate(null); setConfirmed(false); setScheduleAt(""); setImageFile(null); };
  const control = async (campaign, action) => {
    try { await api.post(`/campaigns/${campaign.id}/${action}`); await loadCampaigns(); setToast({ type: "success", message: `Campaign ${action}d` }); }
    catch (error) { setToast({ type: "error", message: error.response?.data?.message || `Could not ${action} campaign` }); }
  };
  const loadRecipients = async (campaign = selectedCampaign) => {
    if (!campaign) return;
    const { data } = await api.get(`/campaigns/${campaign.id}/recipients`, { params: { per_page: 100, search: recipientSearch, status: recipientStatus } });
    setRecipients(data.items || []);
  };
  const inspectCampaign = async (campaign) => {
    setSelectedCampaign(campaign);
    setRecipientSearch(""); setRecipientStatus("");
    const { data } = await api.get(`/campaigns/${campaign.id}/recipients`, { params: { per_page: 100 } }); setRecipients(data.items || []);
  };

  const campaignColumns = [
    { label: "Campaign", key: "name", render: (row) => <button className="campaign-link" onClick={() => inspectCampaign(row)}>{row.name}</button> },
    { label: "Template", key: "template_name" }, { label: "Audience", key: "total_count" }, { label: "Sent", key: "sent_count" },
    { label: "Delivered", key: "delivered_count" }, { label: "Read", key: "read_count" }, { label: "Replied", key: "replied_count" },
    { label: "Status", key: "status", render: (row) => <Badge tone={row.status === "completed" ? "teal" : row.status === "failed" ? "red" : "purple"}>{sentenceCase(row.status)}</Badge> },
    { label: "Controls", key: "controls", render: (row) => <div className="row-actions">{["queued", "sending", "scheduled"].includes(row.status) && can(user, "campaigns", "pause") && <button onClick={() => control(row, "pause")}><IconPlayerPause size={15} />Pause</button>}{row.status === "paused" && can(user, "campaigns", "pause") && <button onClick={() => control(row, "resume")}><IconPlayerPlay size={15} />Resume</button>}{!["completed", "cancelled", "sent"].includes(row.status) && can(user, "campaigns", "cancel") && <button onClick={() => control(row, "cancel")}>Cancel</button>}</div> },
  ];
  const recipientColumns = [
    { label: "Lead", key: "recipient_name", render: (row) => <div><strong>{row.recipient_name}</strong><small>{row.recipient_phone}</small></div> },
    { label: "Status", key: "status", render: (row) => <Badge>{sentenceCase(row.status)}</Badge> },
    { label: "Reason / error", key: "skip_reason", render: (row) => reasonLabel(row.skip_reason || row.error_message || "-") },
    { label: "Reply", key: "last_reply_text", render: (row) => row.last_reply_text || "-" },
    { label: "Reply time", key: "last_reply_at", render: (row) => row.last_reply_at ? new Date(row.last_reply_at).toLocaleString("en-IN") : "-" },
  ];

  const totals = campaigns.reduce((sum, campaign) => ({ sent: sum.sent + (campaign.sent_count || 0), delivered: sum.delivered + (campaign.delivered_count || 0), read: sum.read + (campaign.read_count || 0), replied: sum.replied + (campaign.replied_count || 0) }), { sent: 0, delivered: 0, read: 0, replied: 0 });
  return <div className="page campaigns-page campaign-workspace">
    <section className="campaign-hero"><div><span>WHATSAPP CAMPAIGN OPERATIONS</span><h2>Consent-safe outreach with real delivery tracking</h2><p>Build an eligible audience, use an approved Meta template, and track each recipient from queue to reply.</p></div><div className="campaign-live"><IconBrandWhatsapp size={25} /><strong>{configuration?.configured ? "Meta configured" : "Configuration required"}</strong><small>Mass sending is controlled by the backend worker.</small></div></section>
    <div className="campaign-kpis">{[["Sent", totals.sent], ["Delivered", totals.delivered], ["Read", totals.read], ["Replied", totals.replied]].map(([label, value]) => <Card key={label}><span>{label}</span><strong>{value}</strong><small>Actual recipient events</small></Card>)}</div>

    {can(user, "campaigns", "create") && <Card className="campaign-wizard">
      <nav className="wizard-steps" aria-label="Campaign creation steps">{[[1, "Select audience"], [2, "Approved template"], [3, "Review & launch"]].map(([number, label]) => <button key={number} className={step === number ? "active" : step > number ? "done" : ""} onClick={() => number < step && setStep(number)}><i>{step > number ? <IconCheck size={15} /> : number}</i><span>{label}</span></button>)}</nav>
      {step === 1 && <section className="wizard-panel"><header><div><span>STEP 1</span><h3>Select a compliant audience</h3></div><Button className="ghost" onClick={exportAudience} disabled={!can(user, "campaigns", "export")}><IconDownload size={17} />Download audience</Button></header>
        <div className="audience-cards">{audienceCards.map(([key, label, description]) => <button className={audienceType === key ? "active" : ""} onClick={() => setAudienceType(key)} key={key}><i>{key === "hot" ? "🔥" : key === "warm" ? "☀️" : key === "cold" ? "❄️" : key === "custom" ? "⚙️" : "👥"}</i><strong>{label}</strong><span>{description}</span></button>)}</div>
        <div className="campaign-filter-grid"><label><span>Search</span><div className="campaign-search"><IconSearch size={16} /><input value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} placeholder="Name, phone, email" /></div></label><label><span>Status</span><select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">All statuses</option>{["new", "contacted", "qualified", "won", "lost"].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Source</span><select value={filters.source} onChange={(event) => setFilters({ ...filters, source: event.target.value })}><option value="">All sources</option>{["website", "chatbot", "whatsapp", "email", "inperson"].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Service</span><input value={filters.service} onChange={(event) => setFilters({ ...filters, service: event.target.value })} placeholder="Any service" /></label><label><span>Destination</span><input value={filters.destination} onChange={(event) => setFilters({ ...filters, destination: event.target.value })} placeholder="Any destination" /></label><label><span>City</span><input value={filters.city} onChange={(event) => setFilters({ ...filters, city: event.target.value })} placeholder="Any city" /></label><label><span>Assigned staff</span><select value={filters.assigned_to} onChange={(event) => setFilters({ ...filters, assigned_to: event.target.value })}><option value="">All permitted staff</option>{assignees.map((staff) => <option value={staff.id} key={staff.id}>{staff.name}</option>)}</select></label><label><span>Branch</span><input value={filters.branch} onChange={(event) => setFilters({ ...filters, branch: event.target.value })} placeholder="Any branch" /></label><label><span>Created from</span><input type="date" value={filters.created_from} onChange={(event) => setFilters({ ...filters, created_from: event.target.value })} /></label><label><span>Created to</span><input type="date" value={filters.created_to} onChange={(event) => setFilters({ ...filters, created_to: event.target.value })} /></label><label><span>Consent</span><select value={filters.marketing_consent} onChange={(event) => setFilters({ ...filters, marketing_consent: event.target.value })}><option value="">Any</option><option value="granted">Granted</option><option value="pending">Pending</option></select></label></div>
        <div className="audience-summary"><div><strong>{loading ? "…" : audience.total_count}</strong><span>Selected</span></div><div className="eligible"><strong>{loading ? "…" : audience.eligible_count}</strong><span>Eligible WhatsApp</span></div><div className="excluded"><strong>{loading ? "…" : audience.excluded_count}</strong><span>Excluded</span></div>{Object.entries(audience.exclusion_reasons || {}).map(([reason, count]) => <small key={reason}>{reasonLabel(reason)}: <b>{count}</b></small>)}</div>
        <div className="campaign-preview-table"><DataTable columns={[{ label: "Lead", key: "name" }, { label: "Phone", key: "phone" }, { label: "Class", key: "classification", render: (row) => <Badge>{row.classification}</Badge> }, { label: "Service", key: "service" }, { label: "Staff", key: "assigned_name" }, { label: "Eligibility", key: "reason", render: (row) => row.reason ? <span className="campaign-excluded">{reasonLabel(row.reason)}</span> : <span className="campaign-eligible">Eligible</span> }]} data={audience.preview || []} empty={loading ? "Calculating audience…" : "No leads match this audience."} /></div>
        <footer><span>{audience.eligible_count} contacts can continue to template selection.</span><Button disabled={!audience.eligible_count} onClick={() => setStep(2)}>Continue <IconArrowRight size={17} /></Button></footer>
      </section>}

      {step === 2 && <section className="wizard-panel"><header><div><span>STEP 2</span><h3>Choose an approved Meta template</h3></div>{can(user, "campaigns", "manage_templates") && <Button className="ghost" onClick={refreshTemplates} disabled={templatesLoading}><IconRefresh size={17} />{templatesLoading ? "Refreshing…" : "Refresh templates"}</Button>}</header>
        {!configuration?.configured && <div className="campaign-warning"><IconAlertTriangle size={18} />Configure the WhatsApp token and Phone Number ID in Settings or environment variables.</div>}
        <div className="template-workspace"><div className="template-library"><div className="template-filters"><input value={templateQuery} onChange={(event) => setTemplateQuery(event.target.value)} placeholder="Search templates" /><select value={templateCategory} onChange={(event) => setTemplateCategory(event.target.value)}><option value="">All categories</option><option>MARKETING</option><option>UTILITY</option><option>AUTHENTICATION</option></select><select value={templateLanguage} onChange={(event) => setTemplateLanguage(event.target.value)}><option value="">All languages</option>{[...new Set(templates.map((item) => item.language))].map((value) => <option key={value}>{value}</option>)}</select><label><input type="checkbox" checked={imageOnly} onChange={(event) => setImageOnly(event.target.checked)} />Image only</label></div><div className="template-list">{templatesLoading ? <div className="campaign-empty">Loading approved templates…</div> : filteredTemplates.map((template) => <button className={selectedTemplate?.id === template.id ? "active" : ""} onClick={() => selectTemplate(template)} key={template.id}><div><IconTemplate size={18} /><strong>{template.name}</strong><Badge tone="teal">Approved</Badge></div><span>{template.category} · {template.language} · {template.header_type || "TEXT"}</span><p>{template.body_text || "No body preview"}</p></button>)}{!templatesLoading && !filteredTemplates.length && <div className="campaign-empty">No approved templates match these filters. Refresh after Meta approval.</div>}</div></div>
          <div className="whatsapp-preview"><div className="phone-frame"><header><IconBrandWhatsapp size={20} /><div><strong>DigiDARA Technologies</strong><span>WhatsApp Business</span></div></header><main>{selectedTemplate ? <div className="wa-bubble">{selectedTemplate.header_type === "IMAGE" && <div className="wa-image">{imageFile ? <img src={URL.createObjectURL(imageFile)} alt="Campaign header preview" /> : <span>Image header required</span>}</div>}<p>{renderedPreview}</p>{templateText(selectedTemplate, "FOOTER") && <small>{templateText(selectedTemplate, "FOOTER")}</small>}{(selectedTemplate.buttons || []).map((button, index) => <button key={index}>{button.text}</button>)}</div> : <div className="campaign-empty">Select a template to preview the approved message.</div>}</main></div>
            {selectedTemplate && <div className="variable-mapping"><h4>Template variables</h4>{vars.map((number) => <div key={number}><code>{`{{${number}}}`}</code><select value={mapping[number]?.field || ""} onChange={(event) => setMapping({ ...mapping, [number]: { ...mapping[number], field: event.target.value } })}><option value="">Choose CRM field</option>{variableFields.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select>{mapping[number]?.field === "fixed" ? <input value={mapping[number]?.value || ""} onChange={(event) => setMapping({ ...mapping, [number]: { ...mapping[number], value: event.target.value } })} placeholder="Fixed value" /> : <input value={mapping[number]?.fallback || ""} onChange={(event) => setMapping({ ...mapping, [number]: { ...mapping[number], fallback: event.target.value } })} placeholder="Optional fallback" />}</div>)}{selectedTemplate.header_type === "IMAGE" && <label className="image-upload"><span>Approved image header</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setImageFile(event.target.files?.[0] || null)} /><small>JPG, PNG or WEBP. The backend validates and uploads it to Meta.</small></label>}</div>}
          </div></div><footer><Button className="ghost" onClick={() => setStep(1)}><IconArrowLeft size={17} />Back</Button><Button disabled={!selectedTemplate || vars.some((number) => !mapping[number]?.field)} onClick={() => setStep(3)}>Review campaign <IconArrowRight size={17} /></Button></footer>
      </section>}

      {step === 3 && <section className="wizard-panel review-launch"><header><div><span>STEP 3</span><h3>Review and launch</h3></div><Badge tone="teal">Approved template</Badge></header><div className="review-grid"><Card><label><span>Campaign name</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="September course follow-up" /></label><dl><div><dt>Audience</dt><dd>{audienceCards.find(([key]) => key === audienceType)?.[1]}</dd></div><div><dt>Selected</dt><dd>{audience.total_count}</dd></div><div><dt>Eligible</dt><dd>{audience.eligible_count}</dd></div><div><dt>Skipped</dt><dd>{audience.excluded_count}</dd></div><div><dt>Template</dt><dd>{selectedTemplate?.name}</dd></div><div><dt>Language</dt><dd>{selectedTemplate?.language}</dd></div><div><dt>Category</dt><dd>{selectedTemplate?.category}</dd></div><div><dt>Header</dt><dd>{selectedTemplate?.header_type}</dd></div></dl></Card><Card className="final-preview"><span>FINAL WHATSAPP PREVIEW</span>{selectedTemplate?.header_type === "IMAGE" && <div className="review-image">{imageFile ? imageFile.name : "Image is required"}</div>}<p>{renderedPreview}</p><small>{templateText(selectedTemplate, "FOOTER")}</small></Card></div><div className="test-send-row"><label><span>Test recipient</span><input value={testPhone} onChange={(event) => setTestPhone(event.target.value)} placeholder="919876543210" inputMode="tel" /></label><Button className="ghost" onClick={sendTest} disabled={loading || !testPhone}>Send test message</Button><small>Send one approved-template test before enabling the production worker.</small></div><label className="launch-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>I confirm that these contacts are eligible for promotional WhatsApp communication and that the selected Meta template is approved.</span></label><div className="schedule-row"><label><span>Optional schedule</span><input type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} /></label><div><Button className="ghost" onClick={() => setStep(2)}><IconArrowLeft size={17} />Back</Button><Button className="ghost" onClick={saveOnly} disabled={loading}>Save Draft</Button>{can(user, "campaigns", "schedule") && <Button onClick={() => launch(true)} disabled={loading || !confirmed || !scheduleAt}>Schedule campaign</Button>}{can(user, "campaigns", "send") && <Button onClick={() => launch(false)} disabled={loading || !confirmed}><IconSend size={17} />Launch campaign</Button>}</div></div></section>}
    </Card>}

    <Card className="campaign-history"><header><div><span>CAMPAIGN ANALYTICS</span><h3>Real recipient delivery results</h3></div><Button className="ghost" onClick={loadCampaigns}><IconRefresh size={17} />Refresh</Button></header><DataTable columns={campaignColumns} data={campaigns} empty="No campaigns created yet." /></Card>
    {selectedCampaign && <Card className="campaign-detail"><header><div><span>RECIPIENT DETAIL</span><h3>{selectedCampaign.name}</h3></div><div>{can(user, "campaigns", "export") && <Button className="ghost" onClick={async () => { const { data } = await api.get(`/campaigns/${selectedCampaign.id}/export`, { responseType: "blob" }); downloadBlob(data, `campaign-${selectedCampaign.id}.csv`); }}><IconDownload size={17} />Export results</Button>}<button className="campaign-close" onClick={() => setSelectedCampaign(null)}>Close</button></div></header><div className="delivery-funnel">{[["Queued", selectedCampaign.queued_count], ["Sent", selectedCampaign.sent_count], ["Delivered", selectedCampaign.delivered_count], ["Read", selectedCampaign.read_count], ["Replied", selectedCampaign.replied_count]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value || 0}</strong></div>)}</div><div className="recipient-filters"><input value={recipientSearch} onChange={(event) => setRecipientSearch(event.target.value)} placeholder="Search name or phone" /><select value={recipientStatus} onChange={(event) => setRecipientStatus(event.target.value)}><option value="">All delivery states</option>{["queued", "accepted", "sent", "delivered", "read", "replied", "failed", "skipped", "opted_out"].map((value) => <option value={value} key={value}>{sentenceCase(value)}</option>)}</select><Button className="ghost" onClick={() => loadRecipients()}><IconSearch size={16} />Filter</Button></div><DataTable columns={recipientColumns} data={recipients} empty="No recipient records yet." /></Card>}
    <Toast toast={toast} />
  </div>;
}
