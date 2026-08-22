import { useEffect, useMemo, useState } from "react";
import { IconEdit, IconEye, IconEyeOff, IconShield, IconTrash, IconUserCheck, IconUserOff, IconUserPlus, IconUsers } from "@tabler/icons-react";
import api from "../api/client";
import Badge from "../components/UI/Badge.jsx";
import Button from "../components/UI/Button.jsx";
import Card from "../components/UI/Card.jsx";
import Modal from "../components/UI/Modal.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { can } from "../permissions.js";

const emptyEmployee = { name: "", phone: "", email: "", password: "", confirm_password: "", branch: "Coimbatore", department: "sales", role: "staff" };
const emptyRole = { key: "", label: "", description: "", template: "staff", permissions: {} };
const departments = ["sales", "marketing", "support", "management", "training", "operations"];
const branches = ["Coimbatore", "Chennai", "Bengaluru", "Remote"];

export default function Employees() {
  const { user } = useAuth();
  const [tab, setTab] = useState("team");
  const [items, setItems] = useState([]);
  const [roleData, setRoleData] = useState({ roles: [], pages: [] });
  const [form, setForm] = useState(emptyEmployee);
  const [roleForm, setRoleForm] = useState(emptyRole);
  const [editing, setEditing] = useState(null);
  const [showRoleForm, setShowRoleForm] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [createdLoginId, setCreatedLoginId] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const load = () => Promise.all([api.get("/employees"), api.get("/employees/roles")]).then(([employees, roles]) => {
    setItems(employees.data);
    setRoleData(roles.data);
    setForm((current) => ({ ...current, role: roles.data.roles.find((role) => role.key === current.role && role.is_active)?.key || roles.data.roles.find((role) => role.key === "staff")?.key || "staff" }));
  });
  useEffect(() => { load().catch(() => setToast({ type: "error", message: "Could not load CRM users and roles." })); }, []);

  const activeRoles = roleData.roles.filter((role) => role.is_active);
  const editingSelf = editing?.id === user?.id;
  const summary = useMemo(() => ({ active: items.filter((item) => item.is_active).length, inactive: items.filter((item) => !item.is_active).length, customRoles: roleData.roles.filter((role) => !role.is_system).length }), [items, roleData.roles]);
  const isAdministrator = user?.permission_role === "admin" || user?.role === "admin";
  const assignableRoles = isAdministrator ? activeRoles : activeRoles.filter((role) => role.key === "staff");
  const tabs = ["team", ...(can(user, "employees", "create") ? ["add employee"] : []), ...(isAdministrator ? ["roles"] : [])];

  const saveEmployee = (event) => {
    event.preventDefault();
    if (form.password !== form.confirm_password) return setToast({ type: "error", message: "Passwords must match." });
    setSaving(true);
    api.post("/employees", form).then(({ data }) => {
      setCreatedLoginId(data.login_id || "");
      setToast({ type: "success", message: `${data.name} can now sign in with ${data.login_id}.` });
      setForm({ ...emptyEmployee, role: activeRoles.find((role) => role.key === "staff")?.key || activeRoles[0]?.key || "staff" });
      setTab("team");
      return load();
    }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Employee could not be added." }))
      .finally(() => setSaving(false));
  };

  const saveEdit = (event) => {
    event.preventDefault();
    setSaving(true);
    api.put(`/employees/${editing.id}`, editing).then(() => {
      setToast({ type: "success", message: "Employee access updated." });
      setEditing(null);
      return load();
    }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Employee could not be updated." }))
      .finally(() => setSaving(false));
  };

  const deleteEmployee = (employee) => {
    if (!window.confirm(`Remove CRM access for ${employee.name}? They will no longer be able to sign in.`)) return;
    api.delete(`/employees/${employee.id}`).then(({ data }) => {
      setToast({ type: "success", message: data?.message || "Employee access removed." });
      return load();
    }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Employee could not be removed." }));
  };

  const startRole = (role = null) => {
    const template = role || roleData.roles.find((item) => item.key === "staff") || roleData.roles[0];
    setRoleForm(role ? { key: role.key, label: role.label, description: role.description || "", template: role.key, permissions: structuredClone(role.permissions || {}) } : { ...emptyRole, template: template?.key || "staff", permissions: structuredClone(template?.permissions || {}) });
    setShowRoleForm(true);
  };
  const applyTemplate = (key) => {
    const template = roleData.roles.find((role) => role.key === key);
    setRoleForm((current) => ({ ...current, template: key, permissions: structuredClone(template?.permissions || {}) }));
  };
  const setRolePermission = (page, action, allowed) => setRoleForm((current) => ({ ...current, permissions: { ...current.permissions, [page]: { ...(current.permissions[page] || {}), [action]: allowed } } }));
  const saveRole = (event) => {
    event.preventDefault();
    setSaving(true);
    const request = roleForm.key ? api.put(`/employees/roles/${roleForm.key}`, roleForm.key === "admin" || roleForm.key === "staff" ? { permissions: roleForm.permissions } : roleForm) : api.post("/employees/roles", roleForm);
    request.then(() => {
      setToast({ type: "success", message: roleForm.key ? "Role permissions updated." : "New CRM role created." });
      setShowRoleForm(false);
      setRoleForm(emptyRole);
      return load();
    }).catch((error) => setToast({ type: "error", message: error.response?.data?.message || "Role could not be saved." }))
      .finally(() => setSaving(false));
  };

  return <div className="page employees-page">
    <section className="employee-access-intro"><div><span>CRM ACCESS MANAGEMENT</span><h2>People, roles and permissions</h2><p>Control who can sign in, what each role can see, and who owns daily CRM execution.</p></div><div className="employee-access-count"><strong>{summary.active}</strong><span>active CRM users</span></div></section>
    <div className="employee-summary-grid"><Card><IconUsers /><span>Total users</span><strong>{items.length}</strong></Card><Card><IconUserCheck /><span>Active access</span><strong>{summary.active}</strong></Card><Card><IconUserOff /><span>Inactive access</span><strong>{summary.inactive}</strong></Card><Card><IconShield /><span>Custom roles</span><strong>{summary.customRoles}</strong></Card></div>
    <div className="employee-tabs">{tabs.map((name) => <button type="button" className={tab === name ? "active" : ""} onClick={() => setTab(name)} key={name}>{name}</button>)}</div>

    {createdLoginId && <div className="notice employee-login-id"><strong>Login ID created</strong><span>{createdLoginId}</span><button onClick={() => setCreatedLoginId("")}>Dismiss</button></div>}

    {tab === "team" && <TeamGrid items={items} canEdit={can(user, "employees", "update")} canDelete={can(user, "employees", "delete")} currentUserId={user?.id} onEdit={setEditing} onDelete={deleteEmployee} />}
    {tab === "add employee" && can(user, "employees", "create") && <Card className="employee-create-card"><div className="employee-form-head"><div className="employee-form-icon"><IconUserPlus /></div><div><span>NEW CRM USER</span><h2>Create employee access</h2><p>The employee receives a unique login ID and the permissions of the selected role.</p></div></div><EmployeeForm form={form} setForm={setForm} roles={assignableRoles} showPassword={showPassword} setShowPassword={setShowPassword} showConfirm={showConfirm} setShowConfirm={setShowConfirm} onSubmit={saveEmployee} saving={saving} /></Card>}
    {tab === "roles" && isAdministrator && <RolesWorkspace roles={roleData.roles} onCreate={() => startRole()} onConfigure={startRole} />}

    <Modal open={Boolean(editing)} title="Edit CRM user" onClose={() => setEditing(null)}>{editing && <form className="employee-edit-form" onSubmit={saveEdit}><div className="employee-edit-person"><div className="avatar big" style={{ background: editing.avatar_color }}>{editing.avatar_initials}</div><div><strong>{editing.name}</strong><span>{editing.login_id} · {editing.email}</span></div></div><label className="field"><span>Name</span><input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} required /></label><label className="field"><span>Phone</span><input value={editing.phone || ""} onChange={(e) => setEditing({ ...editing, phone: e.target.value })} required /></label><label className="field"><span>Role</span><select disabled={editingSelf || !isAdministrator} value={editing.role_key} onChange={(e) => setEditing({ ...editing, role: e.target.value, role_key: e.target.value })}>{activeRoles.map((role) => <option value={role.key} key={role.key}>{role.label}</option>)}</select>{(editingSelf || !isAdministrator) && <small>{editingSelf ? "Your own role is protected." : "Only an administrator can change roles."}</small>}</label><label className="field"><span>Department</span><select value={editing.department || "sales"} onChange={(e) => setEditing({ ...editing, department: e.target.value })}>{departments.map((value) => <option key={value}>{value}</option>)}</select></label><label className="field"><span>Branch</span><select value={editing.branch || "Coimbatore"} onChange={(e) => setEditing({ ...editing, branch: e.target.value })}>{branches.map((value) => <option key={value}>{value}</option>)}</select></label><label className="employee-active-control"><input type="checkbox" disabled={editingSelf} checked={Boolean(editing.is_active)} onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} /><span><strong>CRM access active</strong><small>{editingSelf ? "Your own access is protected." : "Inactive users cannot sign in."}</small></span></label><div className="employee-modal-actions"><Button variant="ghost" type="button" onClick={() => setEditing(null)}>Cancel</Button><Button disabled={saving}>{saving ? "Saving..." : "Save user"}</Button></div></form>}</Modal>

    <Modal open={showRoleForm} title={roleForm.key ? `Configure ${roleForm.label}` : "Create CRM role"} onClose={() => setShowRoleForm(false)}><RoleForm form={roleForm} pages={roleData.pages} roles={roleData.roles} setForm={setRoleForm} setPermission={setRolePermission} applyTemplate={applyTemplate} onSubmit={saveRole} onClose={() => setShowRoleForm(false)} saving={saving} /></Modal>
    <Toast toast={toast} />
  </div>;
}

function TeamGrid({ items, canEdit, canDelete, currentUserId, onEdit, onDelete }) {
  return <div className="employee-grid access-grid">{items.map((employee) => <Card className={`employee-access-card ${employee.is_active ? "" : "inactive"}`} key={employee.id}><header><div className="avatar big" style={{ background: employee.avatar_color }}>{employee.avatar_initials}</div><div><strong>{employee.name}</strong><span>{employee.login_id}</span></div><Badge tone={employee.is_active ? "teal" : "red"}>{employee.is_active ? "Active" : "Inactive"}</Badge></header><div className="employee-role-line"><IconShield size={16} /><strong>{employee.role_label}</strong><span>{employee.department || "No department"}</span></div><dl><div><dt>Email</dt><dd>{employee.email}</dd></div><div><dt>Phone</dt><dd>{employee.phone || "—"}</dd></div><div><dt>Branch</dt><dd>{employee.branch || "—"}</dd></div><div><dt>Last login</dt><dd>{employee.last_login ? new Date(employee.last_login).toLocaleDateString() : "Never"}</dd></div></dl>{(canEdit || canDelete) && <footer>{canEdit && <button className="btn ghost" onClick={() => onEdit({ ...employee, role: employee.role_key })}><IconEdit size={16} /> Edit access</button>}{canDelete && <button className="danger-btn" disabled={employee.id === currentUserId} title={employee.id === currentUserId ? "You cannot remove your own access." : "Remove CRM access"} onClick={() => onDelete(employee)}><IconTrash size={16} /> Delete</button>}</footer>}</Card>)}{!items.length && <div className="empty">No CRM users have been added.</div>}</div>;
}

function EmployeeForm({ form, setForm, roles, showPassword, setShowPassword, showConfirm, setShowConfirm, onSubmit, saving }) {
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  return <form className="employee-access-form" onSubmit={onSubmit}><label className="field"><span>Full name*</span><input value={form.name} onChange={(e) => set("name", e.target.value)} required /></label><label className="field"><span>Phone number*</span><input value={form.phone} onChange={(e) => set("phone", e.target.value)} required /></label><label className="field"><span>Email address*</span><input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} required /></label><label className="field"><span>CRM role*</span><select value={form.role} onChange={(e) => set("role", e.target.value)} required>{roles.map((role) => <option value={role.key} key={role.key}>{role.label}</option>)}</select><small>Role controls every page and action this employee may use.</small></label><label className="field"><span>Department*</span><select value={form.department} onChange={(e) => set("department", e.target.value)}>{departments.map((value) => <option key={value}>{value}</option>)}</select></label><label className="field"><span>Branch*</span><select value={form.branch} onChange={(e) => set("branch", e.target.value)}>{branches.map((value) => <option key={value}>{value}</option>)}</select></label><label className="field password-field"><span>Password*</span><input type={showPassword ? "text" : "password"} minLength={8} value={form.password} onChange={(e) => set("password", e.target.value)} required /><button type="button" onClick={() => setShowPassword((value) => !value)}>{showPassword ? <IconEyeOff size={18} /> : <IconEye size={18} />}</button></label><label className="field password-field"><span>Confirm password*</span><input type={showConfirm ? "text" : "password"} minLength={8} value={form.confirm_password} onChange={(e) => set("confirm_password", e.target.value)} required /><button type="button" onClick={() => setShowConfirm((value) => !value)}>{showConfirm ? <IconEyeOff size={18} /> : <IconEye size={18} />}</button></label><div className="employee-create-action"><Button disabled={saving}>{saving ? "Creating access..." : "Create employee access"}</Button></div></form>;
}

function RolesWorkspace({ roles, onCreate, onConfigure }) {
  return <><div className="role-workspace-head"><div><span>ROLE LIBRARY</span><h2>Reusable CRM access roles</h2><p>Create a role once, configure its permissions, then assign it to any employee.</p></div><Button onClick={onCreate}>+ New role</Button></div><div className="role-card-grid">{roles.map((role) => <Card className={`role-card ${role.is_active ? "" : "inactive"}`} key={role.key}><header><div className="role-icon"><IconShield /></div><Badge tone={role.is_system ? "teal" : role.is_active ? "purple" : "red"}>{role.is_system ? "System" : role.is_active ? "Custom" : "Inactive"}</Badge></header><h3>{role.label}</h3><p>{role.description || "Custom CRM access role"}</p><div className="role-users"><strong>{role.active_user_count}</strong><span>active users · {role.user_count} total</span></div><small>{countAllowed(role.permissions)} allowed activities</small><button className="btn ghost" onClick={() => onConfigure(role)}>Configure permissions</button></Card>)}</div></>;
}

function RoleForm({ form, pages, roles, setForm, setPermission, applyTemplate, onSubmit, onClose, saving }) {
  const system = form.key === "admin" || form.key === "staff";
  return <form className="role-form" onSubmit={onSubmit}>{!system && <div className="role-basics"><label className="field"><span>Role name*</span><input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Example: Sales Manager" required /></label><label className="field"><span>Start from</span><select value={form.template} onChange={(e) => applyTemplate(e.target.value)}>{roles.filter((role) => role.is_active).map((role) => <option value={role.key} key={role.key}>{role.label}</option>)}</select></label><label className="field wide"><span>Description</span><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="What this role is responsible for" /></label></div>}<div className="role-permission-note"><IconShield size={18} /><span><strong>Set least-privilege access</strong><small>Enable only the pages and actions needed for this role.</small></span></div><div className="role-permission-list">{pages.map((page) => <section key={page.key}><header><strong>{page.label}</strong><button type="button" onClick={() => page.actions.forEach((action) => setPermission(page.key, action, true))}>Allow all</button></header><div>{page.actions.map((action) => <label key={action}><input type="checkbox" checked={Boolean(form.permissions?.[page.key]?.[action])} onChange={(e) => setPermission(page.key, action, e.target.checked)} /><span>{action.replaceAll("_", " ")}</span></label>)}</div></section>)}</div><div className="employee-modal-actions"><Button variant="ghost" type="button" onClick={onClose}>Cancel</Button><Button disabled={saving}>{saving ? "Saving role..." : form.key ? "Save permissions" : "Create role"}</Button></div></form>;
}

function countAllowed(permissions = {}) {
  return Object.values(permissions).reduce((total, page) => total + Object.values(page || {}).filter(Boolean).length, 0);
}
