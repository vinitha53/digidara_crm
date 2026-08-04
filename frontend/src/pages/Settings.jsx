import { useEffect, useMemo, useState } from "react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const TABS = [
  ["integrations", "Company & Integrations", "Identity and delivery channels"],
  ["options", "Lead Options", "Course, internship and project lists"],
  ["ai_followups", "AI Follow-ups", "Cadence, timing and safeguards"],
  ["permissions", "Permissions", "Role-based page and action access"],
];

export default function Settings() {
  const { user } = useAuth();
  const [tab, setTab] = useState("integrations");
  const [form, setForm] = useState({});
  const [integrations, setIntegrations] = useState({});
  const [integrationDraft, setIntegrationDraft] = useState({});
  const [permissionConfig, setPermissionConfig] = useState({ roles: [], pages: [], permissions: {} });
  const [selectedRole, setSelectedRole] = useState("staff");
  const [newOption, setNewOption] = useState({ courses: "", internships: "", services: "" });
  const [saving, setSaving] = useState("");
  const [toast, setToast] = useState(null);
  const mayUpdate = can(user, "settings", "update");
  const mayManage = can(user, "settings", "manage");

  const load = async () => {
    try {
      const requests = [api.get("/settings/company"), api.get("/settings/integrations")];
      if (mayManage) requests.push(api.get("/settings/permissions"));
      const [company, integrationStatus, permissions] = await Promise.all(requests);
      setForm(company.data);
      setIntegrations(integrationStatus.data);
      setIntegrationDraft({
        whatsapp_phone_number_id: integrationStatus.data.whatsapp?.phone_number_id || "",
        whatsapp_api_token: "",
        gmail_address: integrationStatus.data.gmail?.address || "",
        gmail_app_password: "",
        google_review_url: integrationStatus.data.google_reviews?.url || "",
        google_review_place_id: integrationStatus.data.google_reviews?.place_id || "",
        google_review_api_key: "",
      });
      if (permissions) {
        setPermissionConfig(permissions.data);
        const roles = permissions.data.roles || [];
        if (!roles.some((role) => role.key === selectedRole)) {
          setSelectedRole(roles.find((role) => role.key === "staff")?.key || roles[0]?.key || "");
        }
      }
    } catch (error) {
      notifyError(error, "Could not load settings", setToast);
    }
  };

  useEffect(() => { load(); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  const setIntegration = (key, value) => setIntegrationDraft((old) => ({ ...old, [key]: value }));
  const saveCompany = () => saveCompanyFields("company", ["company_name", "tagline", "website", "email", "phone", "city", "gst_number"], "Company profile saved");
  const saveOptions = () => saveCompanyFields("options", ["course_name_options", "internship_name_options", "business_service_options"], "Lead options saved");
  const saveAI = () => saveCompanyFields("ai", [
    "ai_followups_enabled", "ai_followup_hot_interval_days", "ai_followup_warm_interval_days",
    "ai_followup_cold_interval_days", "ai_followup_business_hours", "ai_followup_working_days",
    "ai_followup_max_count", "ai_followup_stop_after_no_response", "ai_followup_preferred_channel",
    "ai_followup_llm_model",
  ], "AI follow-up policy saved");

  async function saveCompanyFields(key, fields, message) {
    setSaving(key);
    try {
      const payload = Object.fromEntries(fields.map((field) => [field, form[field]]));
      const { data } = await api.put("/settings/company", payload);
      setForm((old) => ({ ...old, ...data }));
      setToast({ type: "success", message });
    } catch (error) {
      notifyError(error, "Settings save failed", setToast);
    } finally {
      setSaving("");
    }
  }

  async function saveIntegration(provider) {
    const fields = {
      whatsapp: ["whatsapp_phone_number_id", "whatsapp_api_token"],
      gmail: ["gmail_address", "gmail_app_password"],
      google_reviews: ["google_review_url", "google_review_place_id", "google_review_api_key"],
    }[provider];
    setSaving(provider);
    try {
      const payload = { provider };
      fields.forEach((field) => { payload[field] = integrationDraft[field] || ""; });
      const { data } = await api.put("/settings/integrations", payload);
      setIntegrations(data);
      setIntegrationDraft((old) => ({
        ...old,
        whatsapp_api_token: "",
        gmail_app_password: "",
        google_review_api_key: "",
      }));
      setToast({ type: "success", message: `${integrationName(provider)} configuration saved` });
    } catch (error) {
      notifyError(error, "Integration save failed", setToast);
    } finally {
      setSaving("");
    }
  }

  const courses = parseOptions(form.course_name_options);
  const internships = parseOptions(form.internship_name_options);
  const services = parseOptions(form.business_service_options);
  const optionConfig = {
    courses: { title: "Courses", hint: "Academic programmes offered to learners", field: "course_name_options", placeholder: "Example: Data Analytics", items: courses },
    internships: { title: "Internships", hint: "Practical training tracks", field: "internship_name_options", placeholder: "Example: UI/UX Internship", items: internships },
    services: { title: "Client Projects", hint: "Services available to business clients", field: "business_service_options", placeholder: "Example: Mobile App Development", items: services },
  };
  const addOption = (key, event) => {
    event.preventDefault();
    const config = optionConfig[key];
    const value = newOption[key].trim();
    if (!value) return;
    if (config.items.some((item) => item.toLowerCase() === value.toLowerCase())) {
      setToast({ type: "error", message: "That option already exists" });
      return;
    }
    set(config.field, [...config.items, value].join("\n"));
    setNewOption((old) => ({ ...old, [key]: "" }));
  };
  const removeOption = (key, value) => {
    const config = optionConfig[key];
    if (config.items.length === 1) {
      setToast({ type: "error", message: "Keep at least one option in each business line" });
      return;
    }
    set(config.field, config.items.filter((item) => item !== value).join("\n"));
  };

  const selectedRoleInfo = permissionConfig.roles.find((role) => role.key === selectedRole);
  const rolePermissions = permissionConfig.permissions?.[selectedRole] || {};
  const isAdminRole = selectedRole === "admin";
  const enabledPages = useMemo(
    () => permissionConfig.pages.filter((page) => rolePermissions?.[page.key]?.view).length,
    [permissionConfig.pages, rolePermissions],
  );

  const setPermission = (pageKey, action, checked) => {
    if (isAdminRole) return;
    setPermissionConfig((old) => {
      const page = { ...(old.permissions?.[selectedRole]?.[pageKey] || {}) };
      if (action === "view") {
        Object.keys(page).forEach((key) => { page[key] = checked ? page[key] : false; });
        page.view = checked;
      } else {
        page[action] = checked;
        if (checked) page.view = true;
      }
      return {
        ...old,
        permissions: {
          ...old.permissions,
          [selectedRole]: { ...(old.permissions?.[selectedRole] || {}), [pageKey]: page },
        },
      };
    });
  };

  const savePermissions = async () => {
    if (!selectedRole || isAdminRole) return;
    setSaving("permissions");
    try {
      const { data } = await api.put(`/settings/permissions/${selectedRole}`, { permissions: rolePermissions });
      setPermissionConfig(data);
      setToast({ type: "success", message: `${selectedRoleInfo?.label || "Role"} permissions saved` });
    } catch (error) {
      notifyError(error, "Permissions save failed", setToast);
    } finally {
      setSaving("");
    }
  };

  const visibleTabs = TABS.filter(([key]) => key !== "permissions" || mayManage);
  const [startTime = "09:00", endTime = "18:00"] = String(form.ai_followup_business_hours || "09:00-18:00").split("-");
  const workingDays = String(form.ai_followup_working_days || "").split(",");

  return (
    <div className="page settings-page">
      <section className="settings-hero">
        <div>
          <span className="eyebrow">ADMIN CONTROL CENTER</span>
          <h2>CRM Settings</h2>
          <p>Manage business choices, connected channels, automation rules and employee access from one place.</p>
        </div>
        <div className="settings-health">
          <StatusPill good={integrations.whatsapp?.configured} label="WhatsApp" />
          <StatusPill good={integrations.gmail?.configured} label="Gmail" />
          <StatusPill good={form.ai_followups_enabled} label="AI follow-ups" />
        </div>
      </section>

      <nav className="settings-nav" aria-label="Settings sections">
        {visibleTabs.map(([key, label, description]) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            <strong>{label}</strong><span>{description}</span>
          </button>
        ))}
      </nav>

      {tab === "integrations" && (
        <div className="settings-stack">
          <Card>
            <SettingsHead title="Company Profile" description="Core identity used in CRM communication and reports." action={mayUpdate && <Button disabled={saving === "company"} onClick={saveCompany}>{saving === "company" ? "Saving..." : "Save Profile"}</Button>} />
            <div className="settings-form profile-form">
              <Field label="Company name"><input value={form.company_name || ""} onChange={(e) => set("company_name", e.target.value)} /></Field>
              <Field label="Company email"><input type="email" value={form.email || ""} onChange={(e) => set("email", e.target.value)} /></Field>
              <Field label="Phone"><input value={form.phone || ""} onChange={(e) => set("phone", e.target.value)} /></Field>
              <Field label="Website"><input value={form.website || ""} onChange={(e) => set("website", e.target.value)} /></Field>
              <Field label="City"><input value={form.city || ""} onChange={(e) => set("city", e.target.value)} /></Field>
              <Field label="GST number"><input value={form.gst_number || ""} onChange={(e) => set("gst_number", e.target.value)} /></Field>
              <Field label="Short tagline" wide><input value={form.tagline || ""} onChange={(e) => set("tagline", e.target.value)} placeholder="How your team describes the business" /></Field>
            </div>
          </Card>

          <div className="integration-grid">
            <IntegrationCard title="WhatsApp Business" description="Lead and customer messaging through Meta." state={integrations.whatsapp} saving={saving === "whatsapp"} onSave={() => saveIntegration("whatsapp")} canSave={mayUpdate}>
              <Field label="Meta phone number ID"><input value={integrationDraft.whatsapp_phone_number_id || ""} onChange={(e) => setIntegration("whatsapp_phone_number_id", e.target.value.trim())} placeholder="123456789012345" /></Field>
              <SecretField label="Access token" configured={integrations.whatsapp?.secret_configured} value={integrationDraft.whatsapp_api_token} onChange={(value) => setIntegration("whatsapp_api_token", value)} />
            </IntegrationCard>
            <IntegrationCard title="Gmail" description="Email follow-ups from the company inbox." state={integrations.gmail} saving={saving === "gmail"} onSave={() => saveIntegration("gmail")} canSave={mayUpdate}>
              <Field label="Sender Gmail address"><input type="email" value={integrationDraft.gmail_address || ""} onChange={(e) => setIntegration("gmail_address", e.target.value.trim())} placeholder="team@gmail.com" /></Field>
              <SecretField label="Google app password" configured={integrations.gmail?.secret_configured} value={integrationDraft.gmail_app_password} onChange={(value) => setIntegration("gmail_app_password", value)} />
            </IntegrationCard>
            <IntegrationCard title="Google Reviews" description="Review requests and customer feedback sync." state={integrations.google_reviews} saving={saving === "google_reviews"} onSave={() => saveIntegration("google_reviews")} canSave={mayUpdate}>
              <Field label="Review URL"><input value={integrationDraft.google_review_url || ""} onChange={(e) => setIntegration("google_review_url", e.target.value.trim())} placeholder="https://g.page/.../review" /></Field>
              <Field label="Google place ID"><input value={integrationDraft.google_review_place_id || ""} onChange={(e) => setIntegration("google_review_place_id", e.target.value.trim())} placeholder="ChIJ..." /></Field>
              <SecretField label="Places API key" configured={integrations.google_reviews?.secret_configured} value={integrationDraft.google_review_api_key} onChange={(value) => setIntegration("google_review_api_key", value)} />
            </IntegrationCard>
          </div>
        </div>
      )}

      {tab === "options" && (
        <Card>
          <SettingsHead title="Lead Options" description="Keep only the choices your team actually sells. These lists feed lead forms and business reporting." action={mayUpdate && <Button disabled={saving === "options"} onClick={saveOptions}>{saving === "options" ? "Saving..." : "Save All Options"}</Button>} />
          <div className="lead-option-grid">
            {Object.entries(optionConfig).map(([key, config]) => (
              <section className="option-editor" key={key}>
                <div className="option-editor-head"><div><h3>{config.title}</h3><p>{config.hint}</p></div><Badge tone="teal">{config.items.length}</Badge></div>
                <form className="option-add" onSubmit={(event) => addOption(key, event)}>
                  <input disabled={!mayUpdate} placeholder={config.placeholder} value={newOption[key]} onChange={(e) => setNewOption((old) => ({ ...old, [key]: e.target.value }))} />
                  {mayUpdate && <Button>Add</Button>}
                </form>
                <div className="option-list">
                  {config.items.map((item) => <div key={item}><span>{item}</span>{mayUpdate && <button type="button" aria-label={`Remove ${item}`} onClick={() => removeOption(key, item)}>×</button>}</div>)}
                </div>
              </section>
            ))}
          </div>
        </Card>
      )}

      {tab === "ai_followups" && (
        <Card>
          <SettingsHead title="AI Follow-up Policy" description="Control when automation runs, how often it contacts leads, and when it must stop." action={mayUpdate && <Button disabled={saving === "ai"} onClick={saveAI}>{saving === "ai" ? "Saving..." : "Save Policy"}</Button>} />
          <label className={`automation-switch ${form.ai_followups_enabled ? "on" : ""}`}>
            <input type="checkbox" checked={Boolean(form.ai_followups_enabled)} onChange={(e) => set("ai_followups_enabled", e.target.checked)} />
            <span><strong>{form.ai_followups_enabled ? "Automation enabled" : "Automation paused"}</strong><small>Existing lead follow-up data stays available when paused.</small></span>
          </label>
          <div className="ai-settings-grid">
            <section className="settings-subcard">
              <h3>Lead cadence</h3><p>Days between follow-ups by lead temperature.</p>
              <div className="cadence-grid">
                <NumberField label="Hot" value={form.ai_followup_hot_interval_days ?? 2} onChange={(value) => set("ai_followup_hot_interval_days", value)} />
                <NumberField label="Warm" value={form.ai_followup_warm_interval_days ?? 4} onChange={(value) => set("ai_followup_warm_interval_days", value)} />
                <NumberField label="Cold" value={form.ai_followup_cold_interval_days ?? 5} onChange={(value) => set("ai_followup_cold_interval_days", value)} />
              </div>
            </section>
            <section className="settings-subcard">
              <h3>Operating window</h3><p>Messages are scheduled only during this local business window.</p>
              <div className="time-grid">
                <Field label="Start"><input type="time" value={startTime} onChange={(e) => set("ai_followup_business_hours", `${e.target.value}-${endTime}`)} /></Field>
                <Field label="End"><input type="time" value={endTime} onChange={(e) => set("ai_followup_business_hours", `${startTime}-${e.target.value}`)} /></Field>
              </div>
              <div className="day-picker">{DAYS.map((day) => <label key={day} className={workingDays.includes(day) ? "selected" : ""}><input type="checkbox" checked={workingDays.includes(day)} onChange={(e) => set("ai_followup_working_days", toggleDay(workingDays, day, e.target.checked).join(","))} /><span>{day}</span></label>)}</div>
            </section>
            <section className="settings-subcard">
              <h3>Safety limits</h3><p>Prevent excessive outreach to unresponsive leads.</p>
              <div className="time-grid">
                <NumberField label="Maximum follow-ups" min={0} max={50} unit="times" value={form.ai_followup_max_count ?? 6} onChange={(value) => set("ai_followup_max_count", value)} />
                <NumberField label="Stop after no response" min={0} max={50} unit="times" value={form.ai_followup_stop_after_no_response ?? 4} onChange={(value) => set("ai_followup_stop_after_no_response", value)} />
              </div>
            </section>
            <section className="settings-subcard">
              <h3>Delivery and AI</h3><p>Use a configured channel and the approved generation model.</p>
              <div className="settings-form compact">
                <Field label="Preferred channel"><select value={form.ai_followup_preferred_channel || "WhatsApp"} onChange={(e) => set("ai_followup_preferred_channel", e.target.value)}><option>WhatsApp</option><option>Email</option></select></Field>
                <Field label="AI model"><input value={form.ai_followup_llm_model || "llama3-8b-8192"} onChange={(e) => set("ai_followup_llm_model", e.target.value)} /></Field>
              </div>
            </section>
          </div>
        </Card>
      )}

      {tab === "permissions" && mayManage && (
        <div className="permission-workspace">
          <aside className="role-selector">
            <div><span className="eyebrow">ACCESS ROLES</span><h3>Choose a role</h3><p>Permissions apply to every active user assigned to that role.</p></div>
            <div className="role-selector-list">
              {permissionConfig.roles.map((role) => (
                <button key={role.key} className={selectedRole === role.key ? "active" : ""} onClick={() => setSelectedRole(role.key)}>
                  <span><strong>{role.label}</strong><small>{role.user_count || 0} user{role.user_count === 1 ? "" : "s"}</small></span>
                  <Badge tone={role.key === "admin" ? "teal" : role.is_active ? "amber" : "red"}>{role.key === "admin" ? "Protected" : role.is_active ? "Active" : "Inactive"}</Badge>
                </button>
              ))}
            </div>
          </aside>
          <Card className="permission-editor">
            <SettingsHead
              title={selectedRoleInfo?.label || "Role permissions"}
              description={isAdminRole ? "Administrator access is protected and always includes every page and action." : selectedRoleInfo?.description || "Choose the pages and actions available to this role."}
              action={!isAdminRole && <Button disabled={saving === "permissions"} onClick={savePermissions}>{saving === "permissions" ? "Saving..." : "Save Role Access"}</Button>}
            />
            <div className="permission-summary">
              <span><strong>{enabledPages}</strong> of {permissionConfig.pages.length} pages enabled</span>
              <span><strong>{selectedRoleInfo?.user_count || 0}</strong> assigned users</span>
              {selectedRoleInfo?.permissions_updated_at && <span>Updated {formatDate(selectedRoleInfo.permissions_updated_at)}</span>}
            </div>
            {isAdminRole && <div className="protected-note"><strong>Administrator protection is active.</strong><span>Administrator permissions cannot be reduced from this screen or through the API.</span></div>}
            <div className="permission-page-list">
              {permissionConfig.pages.map((page) => {
                const pageAccess = rolePermissions?.[page.key] || {};
                const enabled = Boolean(pageAccess.view);
                return (
                  <section key={page.key} className={`permission-page ${enabled ? "enabled" : ""}`}>
                    <div className="permission-page-main">
                      <div><strong>{page.label}</strong><span>{pageDescription(page.key)}</span></div>
                      <label className="page-access-toggle"><input type="checkbox" disabled={isAdminRole} checked={enabled} onChange={(e) => setPermission(page.key, "view", e.target.checked)} /><span>{enabled ? "Page enabled" : "No page access"}</span></label>
                    </div>
                    <div className="permission-actions">
                      {page.actions.filter((action) => action !== "view").map((action) => (
                        <label key={action} className={pageAccess[action] ? "checked" : ""}>
                          <input type="checkbox" disabled={isAdminRole || !enabled} checked={Boolean(pageAccess[action])} onChange={(e) => setPermission(page.key, action, e.target.checked)} />
                          <span>{actionLabel(action)}</span>
                        </label>
                      ))}
                      {page.actions.length === 1 && <small>View-only page</small>}
                    </div>
                  </section>
                );
              })}
            </div>
          </Card>
        </div>
      )}

      <Toast toast={toast} />
    </div>
  );
}

function SettingsHead({ title, description, action }) {
  return <div className="settings-header"><div><h2>{title}</h2><p>{description}</p></div>{action}</div>;
}

function Field({ label, children, wide = false }) {
  return <label className={`field ${wide ? "wide" : ""}`}><span>{label}</span>{children}</label>;
}

function SecretField({ label, configured, value, onChange }) {
  return <Field label={label}><input type="password" value={value || ""} onChange={(e) => onChange(e.target.value)} placeholder={configured ? "Configured — enter only to replace" : "Enter credential"} autoComplete="new-password" /></Field>;
}

function NumberField({ label, value, onChange, min = 1, max = 90, unit = "days" }) {
  return <Field label={label}><div className="number-with-unit"><input type="number" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} /><span>{unit}</span></div></Field>;
}

function IntegrationCard({ title, description, state, saving, onSave, canSave, children }) {
  return (
    <Card className="integration-card">
      <div className="integration-head"><div><h2>{title}</h2><p>{description}</p></div><Badge tone={state?.configured ? "teal" : "amber"}>{state?.configured ? "Configured" : "Setup needed"}</Badge></div>
      <div className="settings-form compact">{children}</div>
      {canSave && <Button disabled={saving} onClick={onSave}>{saving ? "Saving..." : "Save Configuration"}</Button>}
      <small className="credential-note">Credentials are stored securely and are never shown again after saving.</small>
    </Card>
  );
}

function StatusPill({ good, label }) {
  return <span className={good ? "good" : ""}><i />{label}: {good ? "On" : "Off"}</span>;
}

function parseOptions(value) {
  return String(value || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function toggleDay(current, day, checked) {
  const next = checked ? [...current, day] : current.filter((item) => item !== day);
  return DAYS.filter((item) => next.includes(item));
}

function notifyError(error, fallback, setter) {
  setter({ type: "error", message: error?.response?.data?.message || fallback });
}

function integrationName(provider) {
  return { whatsapp: "WhatsApp", gmail: "Gmail", google_reviews: "Google Reviews" }[provider] || provider;
}

function formatDate(value) {
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function actionLabel(action) {
  return ({ create: "Create", update: "Edit", delete: "Delete", assign: "Assign", convert: "Convert", classify: "AI classify", complete: "Complete", send: "Send", schedule: "Schedule", export: "Export", manage: "Manage access", generate: "Generate", run: "Run automation", ask: "Ask AI", send_review: "Send review", sync_review: "Sync review" })[action] || action.replaceAll("_", " ");
}

function pageDescription(key) {
  return ({
    dashboard: "Business and operational summaries", leads: "Course, internship and project enquiries", customers: "Converted customer records", tasks: "Assigned employee work", notifications: "Topbar bell notifications", calendar: "Task due dates and schedules", ai_chat: "Questions against live CRM data", ai_followups: "Automated lead follow-up workspace", workflows: "Automation rules", campaigns: "Bulk outreach campaigns", communication: "Single and bulk customer WhatsApp", whatsapp_messages: "WhatsApp conversation history", reports: "Business reports and exports", employees: "Users, roles and employment access", settings: "Company, integrations and access controls",
  })[key] || "CRM workspace access";
}
