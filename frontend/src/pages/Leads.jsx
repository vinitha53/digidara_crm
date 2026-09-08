import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { IconBrandWhatsapp, IconBriefcase, IconColumns3, IconEdit, IconFilter, IconLayoutList, IconMail, IconPlus, IconSchool, IconSend, IconUserCheck } from "@tabler/icons-react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Drawer from "../components/UI/Drawer.jsx";
import Toast from "../components/UI/Toast.jsx";
import DataTable from "../components/shared/DataTable.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";
import { lostReasonOptions } from "../constants/leadOptions.js";
import { sentenceCase } from "../utils/text.js";

const statuses = ["new", "contacted", "qualified", "won", "lost", "closed"];
const KANBAN_INITIAL_RECORDS = 10;
const statusLabels = {
  new: "New",
  contacted: "Contacted",
  qualified: "Qualified",
  won: "Won",
  lost: "Lost",
  closed: "Closed",
  converted: "Converted",
  not_interested: "Not Interested",
};
const categories = [
  { value: "course", label: "Course Lead" },
  { value: "internship", label: "Internship Lead" },
  { value: "business", label: "Client Project Lead" },
];
const durations = ["2 weeks", "4 weeks"];
const sources = [
  { value: "website", label: "Website" },
  { value: "chatbot", label: "Chatbot" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email" },
  { value: "inperson", label: "In Person" },
];
const defaultCourses = ["GenAI Course", "Python Full Stack", "AI Training"];
const defaultInternships = ["AI Internship", "ML / Data Science", "Web Development Internship"];
const defaultBusinessServices = ["AI Product Development", "Digital Marketing", "AI Consulting", "Website Development", "Software Development"];
const emptyLead = {
  lead_category: "course",
  name: "",
  phone: "",
  email: "",
  qualification: "",
  program_duration: "",
  course_name: "",
  internship_name: "",
  business_name: "",
  business_requirement: "",
  deal_value: 0,
  probability: 10,
  expected_close_date: "",
  lost_reason: "",
  lost_reason_detail: "",
  source: "website",
  assigned_to: "",
  notes: "",
};
const emptyAdvanced = {
  search: "",
  source: "",
  lost_reason: "",
  city: "",
  service: "",
  tag: "",
  min_value: "",
  max_value: "",
  expected_from: "",
  expected_to: "",
};
const advancedFilterKeys = Object.keys(emptyAdvanced);
const categoryTabs = [
  { value: "all", label: "All Leads" },
  { value: "academic", label: "Academic" },
  { value: "course", label: "Courses" },
  { value: "internship", label: "Internships" },
  { value: "project", label: "Projects" },
];
const statusTabs = ["all", "open", "new", "contacted", "qualified", "won", "lost", "hot"];

function formatLeadCreatedAt(value) {
  if (!value) return "Not available";
  // Backend timestamps are stored in UTC but serialized without a timezone.
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(date);
}

export default function Leads() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [leads, setLeads] = useState([]);
  const [overview, setOverview] = useState({ total: 0, course: 0, internship: 0, academic: 0, project: 0, statuses: {} });
  const [resultTotal, setResultTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState([]);
  const [syncingSources, setSyncingSources] = useState(false);
  const [duplicates, setDuplicates] = useState([]);
  const [leadTimeline, setLeadTimeline] = useState([]);
  const [followupData, setFollowupData] = useState({ history: [] });
  const [followupDraft, setFollowupDraft] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advanced, setAdvanced] = useState(emptyAdvanced);
  const [savedViews, setSavedViews] = useState([]);
  const [viewName, setViewName] = useState("");
  const [view, setView] = useState("table");
  const [expandedPipelineStages, setExpandedPipelineStages] = useState({});
  const [bulkLostOpen, setBulkLostOpen] = useState(false);
  const [drawer, setDrawer] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [messageOpen, setMessageOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [messageLead, setMessageLead] = useState(null);
  const [messageChannel, setMessageChannel] = useState("WhatsApp");
  const [messageBody, setMessageBody] = useState("");
  const [form, setForm] = useState(emptyLead);
  const [courseOptions, setCourseOptions] = useState(defaultCourses);
  const [internshipOptions, setInternshipOptions] = useState(defaultInternships);
  const [businessServices, setBusinessServices] = useState(defaultBusinessServices);
  const [assignees, setAssignees] = useState([]);
  const [toast, setToast] = useState(null);
  const canAssignLead = can(user, "leads", "assign");
  const categoryFilter = categoryFromSearch(searchParams);
  const filter = statusFromSearch(searchParams);
  const perPage = view === "table" ? 20 : 200;
  const appliedAdvanced = advancedFromSearch(searchParams);
  const appliedFilterCount = advancedFilterKeys.filter((key) => appliedAdvanced[key]).length;
  const filterQueryKey = `${searchParams.toString()}|${view}`;
  const previousFilterQuery = useRef(filterQueryKey);

  const load = () => {
    const params = Object.fromEntries(Object.entries({
      ...appliedAdvanced,
      search: searchParams.get("search") || "",
      status: searchParams.get("status") || "",
      segment: searchParams.get("segment") || "",
      stage: searchParams.get("stage") || "",
      lead_category: searchParams.get("lead_category") || "",
      lost_reason: searchParams.get("lost_reason") || "",
      page,
      per_page: perPage,
    }).filter(([, value]) => value !== "" && value !== null && value !== undefined));
    Promise.all([api.get("/leads", { params }), api.get("/leads/overview")])
      .then(([listResponse, overviewResponse]) => {
        setLeads(listResponse.data.items);
        setResultTotal(listResponse.data.total || 0);
        setOverview(overviewResponse.data);
        setSelectedIds([]);
      })
      .catch(() => setToast({ type: "error", message: "Could not load leads" }));
  };

  useEffect(() => {
    const filtersChanged = previousFilterQuery.current !== filterQueryKey;
    previousFilterQuery.current = filterQueryKey;
    if (filtersChanged && page !== 1) {
      setPage(1);
      return;
    }
    load();
  }, [filterQueryKey, page]);

  useEffect(() => {
    setAdvanced(advancedFromSearch(searchParams));
  }, [searchParams]);

  useEffect(() => {
    setExpandedPipelineStages({});
  }, [filterQueryKey]);

  useEffect(() => {
    api.get("/settings/lead-options")
      .then(({ data }) => {
        setCourseOptions(parseOptions(data.course_name_options, defaultCourses));
        setInternshipOptions(parseOptions(data.internship_name_options, defaultInternships));
        setBusinessServices(parseOptions(data.business_service_options, defaultBusinessServices));
      })
      .catch(() => {
        setCourseOptions(defaultCourses);
        setInternshipOptions(defaultInternships);
        setBusinessServices(defaultBusinessServices);
      });
    api.get("/saved-views", { params: { module: "leads" } })
      .then(({ data }) => {
        setSavedViews(data);
        const def = data.find((item) => item.is_default);
        if (def?.filters && !advancedFilterKeys.some((key) => searchParams.get(key))) {
          applyAdvancedFilters(def.filters);
        }
      })
      .catch(() => setSavedViews([]));
  }, []);

  useEffect(() => {
    if (!canAssignLead) return;
    api.get("/leads/assignees")
      .then(({ data }) => setAssignees(data))
      .catch(() => setToast({ type: "error", message: "Could not load staff list" }));
  }, [canAssignLead]);

  const pipelineMetrics = useMemo(() => statuses.reduce((acc, status) => {
    const rows = leads.filter((lead) => lead.status === status);
    acc[status] = { count: rows.length };
    return acc;
  }, {}), [leads]);

  const set = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  const toggleSelected = (id) => setSelectedIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]);
  const selectedCount = selectedIds.length;
  const setAdvancedField = (key, value) => setAdvanced((old) => ({ ...old, [key]: value }));

  const selectCategory = (value) => {
    const next = new URLSearchParams(searchParams);
    next.delete("segment");
    next.delete("lead_category");
    if (value === "academic" || value === "project") next.set("segment", value);
    if (value === "course" || value === "internship") next.set("lead_category", value);
    setSearchParams(next);
  };

  const selectStatus = (value) => {
    const next = new URLSearchParams(searchParams);
    next.delete("status");
    next.delete("stage");
    if (searchParams.get("tag") === "hot") next.delete("tag");
    if (["new", "contacted", "qualified", "won", "lost"].includes(value)) next.set("status", value);
    if (value === "open") next.set("stage", "open");
    if (value === "hot") { next.set("tag", "hot"); next.set("stage", "open"); }
    setSearchParams(next);
  };

  const applyAdvancedFilters = (filters = advanced) => {
    const next = new URLSearchParams(searchParams);
    advancedFilterKeys.forEach((key) => {
      const value = String(filters?.[key] ?? "").trim();
      if (value) next.set(key, value);
      else next.delete(key);
    });
    setSearchParams(next);
    setAdvanced(advancedFromSearch(next));
  };

  const clearMoreFilters = () => {
    const next = new URLSearchParams(searchParams);
    advancedFilterKeys.forEach((key) => next.delete(key));
    setSearchParams(next);
    setAdvanced(emptyAdvanced);
  };

  const saveView = () => {
    if (!viewName.trim()) {
      setToast({ type: "error", message: "Enter a saved view name" });
      return;
    }
    const filters = Object.fromEntries(advancedFilterKeys
      .map((key) => [key, String(advanced[key] || "").trim()])
      .filter(([, value]) => value));
    api.post("/saved-views", { module: "leads", name: viewName.trim(), filters })
      .then(({ data }) => {
        setSavedViews((items) => [...items, data]);
        setViewName("");
        setToast({ type: "success", message: "Saved view created" });
      })
      .catch(() => setToast({ type: "error", message: "Could not save view" }));
  };

  const applySavedView = (item) => {
    applyAdvancedFilters(item.filters || {});
    setAdvancedOpen(true);
  };

  const openAdd = () => {
    setEditing(null);
    setForm({ ...emptyLead, assigned_to: canAssignLead ? "" : String(user?.id || "") });
    setFormOpen(true);
  };

  const openEdit = (lead) => {
    setEditing(lead);
    setForm({ ...emptyLead, ...lead, assigned_to: String(lead.assigned_to || (canAssignLead ? "" : user?.id || "")) });
    setDrawer(null);
    setFormOpen(true);
  };

  const openMessage = (lead, channel) => {
    const text = defaultMessage(lead);
    setMessageLead(lead);
    setMessageChannel(channel);
    setMessageBody(text);
    setMessageOpen(true);
  };

  const payload = () => {
    const data = { ...form };
    data.deal_value = Number(data.deal_value || 0);
    data.probability = Number(data.probability || 0);
    data.assigned_to = data.assigned_to ? Number(data.assigned_to) : null;
    if (data.status !== "lost") {
      data.lost_reason = "";
      data.lost_reason_detail = "";
    }
    if (data.lead_category === "course") {
      data.service = data.course_name || "Course Enquiry";
      data.program_duration = "";
      data.internship_name = "";
      data.business_name = "";
      data.business_requirement = "";
    }
    if (data.lead_category === "internship") {
      data.service = data.internship_name || "Internship Enquiry";
      data.program_duration = data.program_duration || "2 weeks";
      data.course_name = "";
      data.business_name = "";
      data.business_requirement = "";
    }
    if (data.lead_category === "business") {
      data.service = data.business_requirement || "Business Enquiry";
      data.qualification = "";
      data.program_duration = "";
      data.course_name = "";
      data.internship_name = "";
      data.company = data.business_name;
    }
    return data;
  };

  const save = (e) => {
    e.preventDefault();
    const request = editing ? api.put(`/leads/${editing.id}`, payload()) : api.post("/leads", payload());
    request.then(() => {
      setToast({ type: "success", message: editing ? "Lead updated" : "Lead added and acknowledgement queued" });
      setFormOpen(false);
      load();
    }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Lead save failed" }));
  };

  const sendMessage = (e) => {
    e.preventDefault();
    api.post("/communication/quick-send", {
      recipient_type: "lead",
      recipient_id: messageLead.id,
      channel: messageChannel,
      template_used: `${messageChannel} lead follow-up`,
      message_body: messageBody,
    }).then(() => {
      setToast({ type: "success", message: `${messageChannel} message sent` });
      setMessageOpen(false);
    }).catch(() => setToast({ type: "error", message: `${messageChannel} send failed` }));
  };

  const classify = (lead) => {
    api.post(`/leads/${lead.id}/classify`)
      .then(({ data }) => {
        setLeads(leads.map((x) => x.id === data.id ? data : x));
        if (drawer?.id === data.id) setDrawer(data);
        setToast({ type: "success", message: "Lead classified" });
      })
      .catch(() => setToast({ type: "error", message: "AI classification failed" }));
  };

  const scoreAll = () => {
    api.post("/leads/score-all")
      .then(({ data }) => {
        setToast({ type: "success", message: `${data.updated} leads scored` });
        load();
      })
      .catch(() => setToast({ type: "error", message: "Bulk AI scoring failed" }));
  };

  const openLead = (lead) => {
    setDrawer(lead);
    api.get(`/leads/${lead.id}/timeline`)
      .then(({ data }) => setLeadTimeline(data))
      .catch(() => setLeadTimeline([]));
    loadFollowups(lead.id);
  };

  const loadFollowups = (leadId) => {
    api.get(`/ai-followups/lead/${leadId}`)
      .then(({ data }) => {
        setFollowupData(data);
        const latest = data.history?.find((item) => item.status === "generated");
        setFollowupDraft(latest?.edited_message || latest?.generated_message || "");
      })
      .catch(() => setFollowupData({ history: [] }));
  };

  const moveLeadStatus = (lead, status) => {
    if (!can(user, "leads", "update") || lead.status === status) return;
    if (status === "lost") {
      openEdit({ ...lead, status: "lost", lost_reason: "", lost_reason_detail: "" });
      setToast({ type: "info", message: "Choose why this lead was lost before saving." });
      return;
    }
    const body = { status };
    if (status === "won") body.probability = 100;
    api.put(`/leads/${lead.id}`, body)
      .then(({ data }) => {
        setLeads(leads.map((item) => item.id === data.id ? data : item));
        setDrawer((old) => old?.id === data.id ? data : old);
        setToast({ type: "success", message: `Moved to ${statusLabels[status]}` });
      })
      .catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Pipeline update failed" }));
  };

  const remove = (lead) => {
    api.delete(`/leads/${lead.id}`).then(() => {
      setToast({ type: "success", message: "Lead deleted" });
      setDrawer(null);
      load();
    }).catch(() => setToast({ type: "error", message: "Delete failed" }));
  };

  const bulk = (action, value, lostReason = "") => {
    if (!selectedIds.length) return;
    api.post("/leads/bulk", { ids: selectedIds, action, value, lost_reason: lostReason })
      .then(({ data }) => {
        setToast({ type: "success", message: `${data.updated} leads updated` });
        setBulkLostOpen(false);
        load();
      })
      .catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Bulk action failed" }));
  };

  const syncConnectedSources = () => {
    setSyncingSources(true);
    Promise.allSettled([
      api.post("/communication/sync-whatsapp-leads"),
      api.post("/external-sources/sync-website-leads"),
    ]).then((results) => {
      const completed = results.filter((result) => result.status === "fulfilled");
      if (!completed.length) throw new Error("No connected source could be reached");
      const totals = completed.reduce((summary, result) => ({
        created: summary.created + Number(result.value.data.created || 0),
        updated: summary.updated + Number(result.value.data.updated || 0),
      }), { created: 0, updated: 0 });
      setToast({ type: "success", message: `${totals.created} new and ${totals.updated} updated leads synchronized` });
      load();
    }).catch(() => setToast({ type: "error", message: "Connected lead sources are unavailable" }))
      .finally(() => setSyncingSources(false));
  };

  const findDuplicates = () => {
    api.get("/leads/duplicates")
      .then(({ data }) => {
        setDuplicates(data);
        setToast({ type: data.length ? "success" : "success", message: data.length ? `${data.length} duplicate groups found` : "No duplicates found" });
      })
      .catch(() => setToast({ type: "error", message: "Duplicate check failed" }));
  };

  const generateFollowup = () => {
    api.post(`/ai-followups/lead/${drawer.id}/generate`)
      .then(({ data }) => {
        setFollowupDraft(data.generated_message || "");
        loadFollowups(drawer.id);
        setToast({ type: "success", message: "AI follow-up generated" });
      })
      .catch(() => setToast({ type: "error", message: "AI follow-up generation failed" }));
  };

  const sendFollowup = () => {
    const latest = followupData.history?.find((item) => item.status === "generated");
    if (!latest) return;
    api.post(`/ai-followups/history/${latest.id}/send`, { message: followupDraft })
      .then(() => {
        loadFollowups(drawer.id);
        setToast({ type: "success", message: "AI follow-up sent" });
      })
      .catch(() => setToast({ type: "error", message: "AI follow-up send failed" }));
  };

  const pauseFollowup = () => {
    api.post(`/ai-followups/lead/${drawer.id}/pause`, { reason: "Paused from lead details" })
      .then(({ data }) => {
        setDrawer(data);
        loadFollowups(data.id);
        setToast({ type: "success", message: "AI follow-up paused" });
      });
  };

  const resumeFollowup = () => {
    api.post(`/ai-followups/lead/${drawer.id}/resume`)
      .then(({ data }) => {
        setDrawer(data);
        loadFollowups(data.id);
        setToast({ type: "success", message: "AI follow-up resumed" });
      });
  };

  const markManualFollowup = () => {
    api.post(`/ai-followups/lead/${drawer.id}/manual`, { note: "Manual follow-up completed", outcome: "manual_followup" })
      .then(() => {
        loadFollowups(drawer.id);
        setToast({ type: "success", message: "Manual follow-up marked" });
      });
  };

  const columns = [
    { label: "", key: "select", render: (r) => <input type="checkbox" aria-label={`Select ${r.name}`} checked={selectedIds.includes(r.id)} onChange={(e) => { e.stopPropagation(); toggleSelected(r.id); }} onClick={(e) => e.stopPropagation()} /> },
    { label: "Lead", key: "name", render: (r) => <><strong>{r.name}</strong><small>{r.email || "No email"} - {r.phone}</small></> },
    { label: "Category", key: "lead_category", render: (r) => <Badge tone={r.lead_category === "business" ? "teal" : r.lead_category === "internship" ? "amber" : "purple"}>{categoryLabel(r.lead_category)}</Badge> },
    { label: "Interest", key: "service", render: (r) => interestName(r) },
    { label: "Source", key: "source", render: (r) => sourceLabel(r.source) },
    { label: "Assigned Staff", key: "assigned_name", render: (r) => r.assigned_name || "Unassigned" },
    { label: "Date and Time", key: "created_at", render: (r) => <time dateTime={r.created_at}>{formatLeadCreatedAt(r.created_at)}</time> },
    { label: "Priority", key: "tag", render: (r) => <Badge tone={r.tag === "hot" ? "red" : r.tag === "warm" ? "amber" : "purple"}>{r.tag}</Badge> },
    { label: "Stage", key: "status", render: (r) => <Badge tone={r.status === "won" ? "teal" : r.status === "lost" ? "red" : "purple"}>{statusLabels[r.status] || r.status}</Badge> },
    { label: "Actions", key: "actions", render: (r) => <div className="row-actions icon-actions">
      {can(user, "leads", "update") && <button title="Edit lead" onClick={(e) => { e.stopPropagation(); openEdit(r); }}><IconEdit size={16} /></button>}
      {can(user, "communication", "send") && <button title="Send WhatsApp" onClick={(e) => { e.stopPropagation(); openMessage(r, "WhatsApp"); }}><IconBrandWhatsapp size={16} /></button>}
      {can(user, "communication", "send") && <button title="Send Email" onClick={(e) => { e.stopPropagation(); openMessage(r, "Email"); }}><IconMail size={16} /></button>}
    </div> },
  ];
  const totalPages = Math.max(1, Math.ceil(resultTotal / perPage));
  const categoryCount = (value) => value === "all" ? overview.total : overview[value] || 0;

  return (
    <div className="page leads-page">
      <section className="lead-workspace-head">
        <div><span>Lead workspace</span><h2>Course, internship and project enquiries</h2><p>Move every enquiry from first contact to a clear outcome.</p></div>
        <div className="lead-workspace-total"><strong>{overview.total}</strong><span>Total leads</span></div>
        {can(user, "leads", "create") && <Button onClick={openAdd}><IconPlus size={17} />Add lead</Button>}
      </section>

      <nav className="lead-segment-tabs" aria-label="Lead category">
        {categoryTabs.map((tab) => <button type="button" className={categoryFilter === tab.value ? "active" : ""} onClick={() => selectCategory(tab.value)} key={tab.value}>{categoryTabIcon(tab.value)}<span>{tab.label}</span><b>{categoryCount(tab.value)}</b></button>)}
      </nav>

      <section className="lead-control-bar">
        <div className="lead-status-tabs" aria-label="Lead status">
          {statusTabs.map((value) => <button type="button" className={filter === value ? "active" : ""} onClick={() => selectStatus(value)} key={value}>{value === "all" ? "All stages" : value}</button>)}
        </div>
        <div className="lead-view-actions">
          <button type="button" className={view === "table" ? "active" : ""} onClick={() => setView("table")}><IconLayoutList size={16} />Table</button>
          <button type="button" className={view === "pipeline" ? "active" : ""} onClick={() => setView("pipeline")}><IconColumns3 size={16} />Pipeline</button>
          <button type="button" className={advancedOpen ? "active" : ""} onClick={() => setAdvancedOpen((value) => !value)}><IconFilter size={16} />Filters{appliedFilterCount > 0 && <b className="filter-count">{appliedFilterCount}</b>}</button>
        </div>
      </section>

      <div className="lead-utility-actions">
        {can(user, "leads", "create") && <button type="button" onClick={syncConnectedSources} disabled={syncingSources}>{syncingSources ? "Synchronizing..." : "Sync connected sources"}</button>}
        <button type="button" onClick={findDuplicates}>Find duplicates</button>
        {can(user, "leads", "classify") && <button type="button" onClick={scoreAll}>AI rescore</button>}
      </div>

      {selectedCount > 0 && <Card className="lead-bulk-bar">
        <strong>{selectedCount} lead{selectedCount === 1 ? "" : "s"} selected</strong>
        <select onChange={(e) => { if (e.target.value === "lost") setBulkLostOpen(true); else if (e.target.value) bulk("status", e.target.value); e.target.value = ""; }} defaultValue=""><option value="">Change stage</option>{statuses.map((x) => <option key={x} value={x}>{statusLabels[x]}</option>)}</select>
        {bulkLostOpen && <select aria-label="Why Lost category for selected leads" defaultValue="" onChange={(e) => e.target.value && bulk("status", "lost", e.target.value)}><option value="">Choose why lost</option>{lostReasonOptions.filter((reason) => reason !== "Other").map((reason) => <option value={reason} key={reason}>{reason}</option>)}</select>}
        <select onChange={(e) => e.target.value && bulk("tag", e.target.value)} defaultValue=""><option value="">Change priority</option>{["new", "hot", "warm", "cold"].map((x) => <option key={x}>{sentenceCase(x)}</option>)}</select>
        {canAssignLead && <select onChange={(e) => e.target.value && bulk("assign", e.target.value)} defaultValue=""><option value="">Assign staff</option>{assignees.map((staff) => <option value={staff.id} key={staff.id}>{staff.name}</option>)}</select>}
        {can(user, "leads", "delete") && <button className="danger-btn" onClick={() => bulk("delete")}>Delete selected</button>}
      </Card>}

      {!!duplicates.length && <Card className="duplicate-list"><div className="card-head"><div><h2>Possible duplicates</h2><small>Review leads sharing the same phone or email.</small></div><button className="ghost-action compact" onClick={() => setDuplicates([])}>Close</button></div>{duplicates.map((group) => <div key={group.match}><strong>{group.match}</strong><span>{group.leads.map((lead) => lead.name).join(", ")}</span></div>)}</Card>}

      {advancedOpen && <Card className="filter-panel">
        <div className="filter-head">
          <div>
            <h2>Filter leads</h2>
            <span>Combine filters, then apply them together.</span>
          </div>
          <button type="button" className="ghost-action compact" onClick={clearMoreFilters} disabled={!appliedFilterCount && !advancedFilterKeys.some((key) => advanced[key])}>Clear filters</button>
        </div>
        <div className="lead-filter-grid">
          <label className="field filter-search"><span>Search</span><input value={advanced.search} onChange={(e) => setAdvancedField("search", e.target.value)} placeholder="Name, phone or email" /></label>
          <label className="field"><span>Source</span><select value={advanced.source} onChange={(e) => setAdvancedField("source", e.target.value)}><option value="">All sources</option>{sources.map((x) => <option value={x.value} key={x.value}>{x.label}</option>)}</select></label>
          <label className="field"><span>Priority</span><select value={advanced.tag} onChange={(e) => setAdvancedField("tag", e.target.value)}><option value="">All priorities</option>{["new", "hot", "warm", "cold"].map((value) => <option value={value} key={value}>{sentenceCase(value)}</option>)}</select></label>
          <label className="field"><span>Why Lost</span><select value={advanced.lost_reason} onChange={(e) => setAdvancedField("lost_reason", e.target.value)}><option value="">All loss categories</option>{lostReasonOptions.map((reason) => <option value={reason} key={reason}>{reason}</option>)}</select></label>
          <label className="field"><span>City</span><input value={advanced.city} onChange={(e) => setAdvancedField("city", e.target.value)} placeholder="Any city" /></label>
          <label className="field"><span>Course, internship or service</span><input value={advanced.service} onChange={(e) => setAdvancedField("service", e.target.value)} placeholder="Any interest" /></label>
          <label className="field"><span>Minimum deal value</span><input type="number" min="0" value={advanced.min_value} onChange={(e) => setAdvancedField("min_value", e.target.value)} placeholder="No minimum" /></label>
          <label className="field"><span>Maximum deal value</span><input type="number" min="0" value={advanced.max_value} onChange={(e) => setAdvancedField("max_value", e.target.value)} placeholder="No maximum" /></label>
          <label className="field"><span>Expected close from</span><input type="date" value={advanced.expected_from} onChange={(e) => setAdvancedField("expected_from", e.target.value)} /></label>
          <label className="field"><span>Expected close to</span><input type="date" value={advanced.expected_to} onChange={(e) => setAdvancedField("expected_to", e.target.value)} /></label>
        </div>
        <div className="filter-apply-row">
          <span>{appliedFilterCount ? `${appliedFilterCount} filter${appliedFilterCount === 1 ? "" : "s"} applied` : "No additional filters applied"}</span>
          <Button onClick={() => applyAdvancedFilters()}>Apply filters</Button>
        </div>
        <div className="saved-view-row">
          <input value={viewName} onChange={(e) => setViewName(e.target.value)} placeholder="Saved view name" />
          <Button onClick={saveView}>Save View</Button>
          {savedViews.map((item) => <button type="button" className="saved-chip" key={item.id} onClick={() => applySavedView(item)}>{item.name}</button>)}
        </div>
      </Card>}

      {view === "table" ? (
        <section className="lead-results">
          <div className="lead-results-head"><div><strong>{resultTotal} matching lead{resultTotal === 1 ? "" : "s"}</strong><span>{categoryTabs.find((item) => item.value === categoryFilter)?.label || "All Leads"} · {filter === "all" ? "All stages" : filter}</span></div><small>Page {page} of {totalPages}</small></div>
          <div className="desktop-lead-table"><DataTable columns={columns} data={leads} onRow={openLead} empty="No leads match these filters." /></div>
          <div className="mobile-lead-list">{leads.map((lead) => <article className="mobile-lead-card" onClick={() => openLead(lead)} key={lead.id}><header><div><strong>{lead.name}</strong><span>{interestName(lead)}</span></div><Badge tone={lead.status === "won" ? "teal" : lead.status === "lost" ? "red" : "purple"}>{statusLabels[lead.status] || lead.status}</Badge></header><div className="mobile-lead-badges"><Badge tone={lead.lead_category === "business" ? "teal" : lead.lead_category === "internship" ? "amber" : "purple"}>{categoryLabel(lead.lead_category)}</Badge><Badge tone={lead.tag === "hot" ? "red" : lead.tag === "warm" ? "amber" : "purple"}>{lead.tag}</Badge></div><dl><div><dt>Phone</dt><dd>{lead.phone}</dd></div><div><dt>Source</dt><dd>{sourceLabel(lead.source)}</dd></div><div><dt>Assigned Staff</dt><dd>{lead.assigned_name || "Unassigned"}</dd></div><div><dt>Date and Time</dt><dd><time dateTime={lead.created_at}>{formatLeadCreatedAt(lead.created_at)}</time></dd></div></dl><footer><label onClick={(event) => event.stopPropagation()}><input type="checkbox" checked={selectedIds.includes(lead.id)} onChange={() => toggleSelected(lead.id)} />Select</label><div className="row-actions icon-actions">{can(user, "leads", "update") && <button title="Edit lead" onClick={(event) => { event.stopPropagation(); openEdit(lead); }}><IconEdit size={16} /></button>}{can(user, "communication", "send") && <button title="Send WhatsApp" onClick={(event) => { event.stopPropagation(); openMessage(lead, "WhatsApp"); }}><IconBrandWhatsapp size={16} /></button>}</div></footer></article>)}{!leads.length && <div className="empty">No leads match these filters.</div>}</div>
          {totalPages > 1 && <div className="lead-pagination"><button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>{(page - 1) * perPage + 1}-{Math.min(page * perPage, resultTotal)} of {resultTotal}</span><button type="button" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>Next</button></div>}
        </section>
      ) : (
        <div className="pipeline-board">
          {statuses.map((status) => {
            const stageLeads = leads.filter((lead) => lead.status === status);
            const isExpanded = Boolean(expandedPipelineStages[status]);
            const visibleLeads = isExpanded ? stageLeads : stageLeads.slice(0, KANBAN_INITIAL_RECORDS);
            const remainingCount = stageLeads.length - visibleLeads.length;

            return <section
            className="pipeline-column"
            key={status}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              const id = Number(event.dataTransfer.getData("lead/id"));
              const lead = leads.find((item) => item.id === id);
              if (lead) moveLeadStatus(lead, status);
            }}
          >
            <div className="pipeline-head">
              <div>
                <strong>{statusLabels[status]}</strong>
                <span>{pipelineMetrics[status]?.count || 0} leads</span>
              </div>
              <Badge tone={status === "won" ? "teal" : status === "lost" ? "red" : "purple"}>{pipelineMetrics[status]?.count || 0}</Badge>
            </div>
            {visibleLeads.map((lead) => <article
              className="kanban-card deal-card"
              draggable={can(user, "leads", "update")}
              key={lead.id}
              onClick={() => openLead(lead)}
              onDragStart={(event) => event.dataTransfer.setData("lead/id", String(lead.id))}
            >
              <div className="deal-card-head">
                <strong>{lead.name}</strong>
                <Badge tone={lead.tag === "hot" ? "red" : lead.tag === "warm" ? "amber" : "purple"}>{lead.tag}</Badge>
              </div>
              <span>{interestName(lead)}</span>
              <div className="pipeline-card-meta"><Badge tone={lead.lead_category === "business" ? "teal" : lead.lead_category === "internship" ? "amber" : "purple"}>{categoryLabel(lead.lead_category)}</Badge><small>{sourceLabel(lead.source)}</small></div>
              <small>{lead.phone} · {lead.assigned_name || "Unassigned"}</small>
              <small className="lead-created-time">Date and Time: <time dateTime={lead.created_at}>{formatLeadCreatedAt(lead.created_at)}</time></small>
              {lead.status === "lost" && <small>Reason: {lead.lost_reason || "Not specified"}</small>}
            </article>)}
            {!stageLeads.length && <div className="pipeline-empty">No leads in this stage</div>}
            {remainingCount > 0 && <button
              type="button"
              className="pipeline-show-more"
              onClick={() => setExpandedPipelineStages((current) => ({ ...current, [status]: true }))}
              aria-label={`Show ${remainingCount} more ${statusLabels[status]} leads`}
            >
              <span>Show More</span>
              <small>{remainingCount} more lead{remainingCount === 1 ? "" : "s"}</small>
            </button>}
          </section>;
          })}
        </div>
      )}

      <Drawer open={formOpen} title={editing ? "Edit Lead" : "Add Lead"} onClose={() => setFormOpen(false)}>
        <LeadForm form={form} set={set} save={save} editing={editing} onCancel={() => setFormOpen(false)} courseOptions={courseOptions} internshipOptions={internshipOptions} businessServices={businessServices} canConvert={can(user, "leads", "convert")} canAssign={canAssignLead} assignees={assignees} />
      </Drawer>

      <Drawer open={messageOpen} title={`Send ${messageChannel}`} onClose={() => setMessageOpen(false)}>
        {messageLead && <form className="lead-form" onSubmit={sendMessage}>
          <div className={`message-hero ${messageChannel === "WhatsApp" ? "whatsapp" : "email"}`}>
            <div className="message-icon">{messageChannel === "WhatsApp" ? <IconBrandWhatsapp size={22} /> : <IconMail size={22} />}</div>
            <div>
              <strong>{messageChannel} Composer</strong>
              <span>{messageLead.name} - {messageChannel === "Email" ? messageLead.email || "No email available" : messageLead.phone}</span>
            </div>
          </div>
          <label className="field wide"><span>Message Body</span><textarea className="message-box" value={messageBody} onChange={(e) => setMessageBody(e.target.value)} required /></label>
          <div className="composer-actions">
            <button type="button" className="ghost-action" onClick={() => setMessageOpen(false)}>Cancel</button>
            <Button><IconSend size={16} />Send {messageChannel}</Button>
          </div>
        </form>}
      </Drawer>

      <Drawer open={drawer} title={drawer?.name} onClose={() => setDrawer(null)}>
        {drawer && <div className="detail">
          <Badge tone={drawer.lead_category === "business" ? "teal" : "purple"}>{categoryLabel(drawer.lead_category)}</Badge>
          <p><strong>Phone:</strong> {drawer.phone}</p>
          <p><strong>Gmail:</strong> {drawer.email || "-"}</p>
          <p><strong>Interest:</strong> {interestName(drawer)}</p>
          <p><strong>Source:</strong> {sourceLabel(drawer.source)}</p>
          <p><strong>Assigned Staff:</strong> {drawer.assigned_name || "Unassigned"}</p>
          {drawer.status === "lost" && <p><strong>Why Lost:</strong> {drawer.lost_reason || "-"}</p>}
          {drawer.status === "lost" && drawer.lost_reason_detail && <p><strong>Loss Details:</strong> {drawer.lost_reason_detail}</p>}
          {drawer.lead_category !== "business" && <p><strong>Qualification:</strong> {drawer.qualification || "-"}</p>}
          {drawer.lead_category === "internship" && <p><strong>Internship Duration:</strong> {drawer.program_duration || "-"}</p>}
          {drawer.lead_category === "business" && <p><strong>Client / Company:</strong> {drawer.business_name || drawer.company || "-"}</p>}
          <p><strong>Notes:</strong> {drawer.notes || "-"}</p>
          <Badge tone="teal">AI {drawer.ai_score || "not scored"}</Badge>
          <p>{drawer.ai_reason}</p>
          {drawer.ai_score_factors && <p><strong>Score Factors:</strong> {drawer.ai_score_factors}</p>}
          {drawer.ai_next_best_action && <p><strong>Next Best Action:</strong> {drawer.ai_next_best_action}</p>}
          {drawer.ai_scored_at && <p><strong>Scored At:</strong> {drawer.ai_scored_at.slice(0, 16).replace("T", " ")}</p>}
          <div className="drawer-actions">
            {can(user, "leads", "update") && <Button onClick={() => openEdit(drawer)}>Edit Lead</Button>}
            {can(user, "communication", "send") && <Button onClick={() => openMessage(drawer, "WhatsApp")}>WhatsApp</Button>}
            {can(user, "communication", "send") && <Button onClick={() => openMessage(drawer, "Email")}>Email</Button>}
            {can(user, "leads", "classify") && <Button onClick={() => classify(drawer)}>AI Classify</Button>}
            {can(user, "leads", "delete") && <button className="danger-btn" onClick={() => remove(drawer)}>Delete</button>}
          </div>
          <div className="customer-section relation-list">
            <h3>AI follow-up automation</h3>
            <div className="customer-facts">
              <div><span>Status</span><strong>{drawer.ai_followup_enabled ? "Active" : "Paused"}</strong></div>
              <div><span>Temperature</span><strong>{sentenceCase(drawer.tag, "-")}</strong></div>
              <div><span>Last Follow-up</span><strong>{drawer.ai_last_followup_at?.slice(0, 10) || "-"}</strong></div>
              <div><span>Next Follow-up</span><strong>{drawer.ai_next_followup_at?.slice(0, 10) || "-"}</strong></div>
              <div><span>Sent</span><strong>{drawer.ai_followup_count || 0}</strong></div>
              <div><span>Engagement</span><strong>{drawer.ai_engagement_score || 0}%</strong></div>
            </div>
            <label className="field wide"><span>Generated Message Preview</span><textarea value={followupDraft} onChange={(e) => setFollowupDraft(e.target.value)} placeholder="Generate a message to preview and edit before sending." /></label>
            <div className="drawer-actions">
              {can(user, "leads", "update") && <Button onClick={generateFollowup}>Regenerate Message</Button>}
              {can(user, "communication", "send") && <Button onClick={sendFollowup} disabled={!followupDraft}>Send Now</Button>}
              {can(user, "leads", "update") && (drawer.ai_followup_enabled ? <button className="danger-btn" onClick={pauseFollowup}>Pause Automation</button> : <Button onClick={resumeFollowup}>Resume Automation</Button>)}
              {can(user, "leads", "update") && <button className="ghost-action" onClick={markManualFollowup}>Mark Manual Follow-up</button>}
            </div>
            {(followupData.history || []).slice(0, 6).map((item) => <div key={item.id}>
              <strong>{sentenceCase(item.status)} - {sentenceCase(item.delivery_status)}</strong>
              <span>{item.sent_at || item.created_at}</span>
              <p>{item.edited_message || item.generated_message || item.skip_reason || "-"}</p>
            </div>)}
          </div>
          <div className="customer-section timeline-list">
            <h3>Lead timeline</h3>
            {leadTimeline.map((item, index) => <div key={`${item.kind}-${index}`}><Badge>{item.kind}</Badge><strong>{item.title}</strong><span>{item.timestamp || "-"}</span><p>{item.body || "-"}</p></div>)}
            {!leadTimeline.length && <div className="empty compact-empty">No timeline yet.</div>}
          </div>
        </div>}
      </Drawer>

      <Toast toast={toast} />
    </div>
  );
}

function LeadForm({ form, set, save, editing, onCancel, courseOptions, internshipOptions, businessServices, canConvert, canAssign, assignees }) {
  const isBusiness = form.lead_category === "business";
  const visibleCategories = editing ? categories.filter((item) => item.value === form.lead_category) : categories;
  return (
    <form className="lead-form" onSubmit={save}>
      <div className="lead-form-banner">
        <div className="lead-form-icon">{iconFor(form.lead_category)}</div>
        <div>
          <strong>{editing ? "Update Lead Profile" : "Create New Lead"}</strong>
          <span>Capture accurate details and notes. AI assigns the hot, warm or cold priority after saving.</span>
        </div>
      </div>

      <div className="category-picker">
        {visibleCategories.map((item) => <button type="button" className={form.lead_category === item.value ? "active" : ""} key={item.value} onClick={() => !editing && set("lead_category", item.value)}>{iconFor(item.value)}<span>{item.label}</span></button>)}
      </div>

      <div className="form-section wide">
        <h3>Contact information</h3>
        <div className="lead-form-grid">
          <label className="field"><span>Name</span><input value={form.name || ""} onChange={(e) => set("name", e.target.value)} required /></label>
          <label className="field"><span>Phone Number</span><input value={form.phone || ""} onChange={(e) => set("phone", e.target.value)} required /></label>
          <label className="field wide"><span>Gmail</span><input type="email" value={form.email || ""} onChange={(e) => set("email", e.target.value)} /></label>
        </div>
      </div>

      <div className="form-section wide">
        <h3>{isBusiness ? "Client Project Details" : "Course / Internship Details"}</h3>
        <div className="lead-form-grid">
          {!isBusiness && <label className="field"><span>Qualification</span><input value={form.qualification || ""} onChange={(e) => set("qualification", e.target.value)} required /></label>}
          {form.lead_category === "internship" && <label className="field"><span>Internship Duration</span><select value={form.program_duration || "2 weeks"} onChange={(e) => set("program_duration", e.target.value)}>{durations.map((x) => <option key={x}>{x}</option>)}</select></label>}
          {form.lead_category === "course" && <label className="field wide"><span>Course Name</span><select value={form.course_name || ""} onChange={(e) => set("course_name", e.target.value)} required><option value="">Select course</option>{courseOptions.map((course) => <option value={course} key={course}>{course}</option>)}</select></label>}
          {form.lead_category === "internship" && <label className="field wide"><span>Internship Name</span><select value={form.internship_name || ""} onChange={(e) => set("internship_name", e.target.value)} required><option value="">Select internship</option>{internshipOptions.map((internship) => <option value={internship} key={internship}>{internship}</option>)}</select></label>}
          {isBusiness && <label className="field wide"><span>Client / Company Name</span><input value={form.business_name || ""} onChange={(e) => set("business_name", e.target.value)} required /></label>}
          {isBusiness && <label className="field wide"><span>Services</span><select value={form.business_requirement || ""} onChange={(e) => set("business_requirement", e.target.value)} required><option value="">Select service</option>{businessServices.map((service) => <option value={service} key={service}>{service}</option>)}</select></label>}
        </div>
      </div>

      <div className="form-section wide">
        <h3>Lead stage</h3>
        <div className="lead-form-grid">
          <label className="field"><span>Status</span><select value={form.status || "new"} onChange={(e) => set("status", e.target.value)}><option value="new">New</option><option value="contacted">Contacted</option><option value="qualified">Qualified</option>{canConvert && <option value="won">Won</option>}<option value="lost">Lost</option><option value="closed">Closed</option><option value="not_interested">Not Interested</option></select></label>
          <label className="field"><span>Source</span><select value={form.source || "website"} onChange={(e) => set("source", e.target.value)}>{sources.map((x) => <option value={x.value} key={x.value}>{x.label}</option>)}</select></label>
          {canAssign && <label className="field"><span>Assigned Staff</span><select value={form.assigned_to || ""} onChange={(e) => set("assigned_to", e.target.value)} required><option value="">Select staff member</option>{assignees.map((staff) => <option value={staff.id} key={staff.id}>{staff.name}{staff.department ? ` - ${staff.department}` : ""}</option>)}</select></label>}
          {(form.status || "new") === "lost" && <label className="field wide"><span>Why Lost</span><select value={form.lost_reason || ""} onChange={(e) => { set("lost_reason", e.target.value); if (e.target.value !== "Other") set("lost_reason_detail", ""); }} required><option value="">Choose a loss category</option>{lostReasonOptions.map((reason) => <option value={reason} key={reason}>{reason}</option>)}</select></label>}
          {(form.status || "new") === "lost" && form.lost_reason === "Other" && <label className="field wide"><span>Why Lost Details</span><textarea value={form.lost_reason_detail || ""} onChange={(e) => set("lost_reason_detail", e.target.value)} placeholder="Briefly explain why this lead was lost" required /></label>}
          <label className="field wide"><span>Notes</span><textarea value={form.notes || ""} onChange={(e) => set("notes", e.target.value)} /></label>
        </div>
      </div>

      <div className="composer-actions wide">
        <button type="button" className="ghost-action" onClick={onCancel}>Cancel</button>
        <Button>{editing ? "Update Lead" : "Add Lead and Send Message"}</Button>
      </div>
    </form>
  );
}

function categoryLabel(value) {
  return categories.find((x) => x.value === value)?.label || "Course Lead";
}

function categoryFromSearch(searchParams) {
  const category = searchParams.get("lead_category");
  const segment = searchParams.get("segment");
  if (category === "course" || category === "internship") return category;
  if (segment === "academic" || segment === "project") return segment;
  return "all";
}

function statusFromSearch(searchParams) {
  if (searchParams.get("tag") === "hot" && searchParams.get("stage") === "open") return "hot";
  if (searchParams.get("stage") === "open") return "open";
  const status = searchParams.get("status");
  return statusTabs.includes(status) ? status : "all";
}

function advancedFromSearch(searchParams) {
  return Object.fromEntries(advancedFilterKeys.map((key) => [key, searchParams.get(key) || ""]));
}

function categoryTabIcon(value) {
  if (value === "project") return <IconBriefcase size={19} />;
  if (value === "internship") return <IconUserCheck size={19} />;
  if (value === "course" || value === "academic") return <IconSchool size={19} />;
  return <IconLayoutList size={19} />;
}

function sourceLabel(value) {
  return sources.find((item) => item.value === value)?.label || "Unknown";
}

function parseOptions(value, fallback) {
  const items = String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items : fallback;
}

function interestName(lead) {
  return lead.course_name || lead.internship_name || lead.business_requirement || lead.service || "-";
}

function defaultMessage(lead) {
  if (lead.lead_category === "course") return `Hi ${lead.name}, thank you for your interest in ${interestName(lead)}. Our Digidara team will share the course details shortly.`;
  if (lead.lead_category === "internship") return `Hi ${lead.name}, thank you for your interest in the ${lead.program_duration || ""} ${interestName(lead)} internship. Our team will guide you with the next steps.`;
  return `Hi ${lead.name}, thank you for contacting Digidara Technologies about ${interestName(lead)}. Our business team will reach out shortly.`;
}

function iconFor(category) {
  if (category === "internship") return <IconUserCheck size={18} />;
  if (category === "business") return <IconBriefcase size={18} />;
  return <IconSchool size={18} />;
}
