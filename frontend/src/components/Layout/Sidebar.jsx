import { IconBrandWhatsapp, IconBriefcase, IconCalendar, IconChartBar, IconChecklist, IconGitBranch, IconLayoutDashboard, IconLogout, IconMessage, IconRobot, IconRocket, IconSettings, IconTargetArrow, IconUsers, IconX } from "@tabler/icons-react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { can, roleLabel } from "../../permissions.js";

const items = [
  ["MAIN", "Dashboard", "/dashboard", IconLayoutDashboard, "dashboard"],
  ["MANAGEMENT", "Leads", "/leads", IconTargetArrow, "leads"],
  ["MANAGEMENT", "Customers", "/customers", IconBriefcase, "customers"],
  ["MANAGEMENT", "Tasks", "/tasks", IconChecklist, "tasks"],
  ["MANAGEMENT", "Calendar", "/calendar", IconCalendar, "calendar"],
  ["MANAGEMENT", "Communication", "/communication", IconMessage, "communication"],
  ["MANAGEMENT", "WhatsApp Message", "/communication/whatsapp", IconBrandWhatsapp, "whatsapp_messages"],
  ["INTELLIGENCE", "AI Chat", "/ai-chat", IconRobot, "ai_chat"],
  ["ADMIN", "AI Follow-ups", "/ai-followups", IconMessage, "ai_followups"],
  ["ADMIN", "Workflows", "/workflows", IconGitBranch, "workflows"],
  ["ADMIN", "Campaigns", "/campaigns", IconRocket, "campaigns"],
  ["ADMIN", "Reports", "/reports", IconChartBar, "reports"],
  ["ADMIN", "Employees", "/employees", IconUsers, "employees"],
  ["ADMIN", "Settings", "/settings", IconSettings, "settings"],
];

export default function Sidebar({ open = false, onClose }) {
  const { user, logout } = useAuth();
  let section = "";
  return (
    <aside id="crm-navigation" className={`sidebar ${open ? "open" : ""}`} aria-label="CRM navigation">
      <div className="brand"><div className="logo company-logo"><img src={`${import.meta.env.BASE_URL}assets/digidara-company-logo.png`} alt="" /></div><div><strong>Digidara CRM</strong><span>Digidara Technologies Pvt Ltd</span></div><button className="icon-btn sidebar-close" type="button" onClick={onClose} aria-label="Close CRM navigation"><IconX size={19} /></button></div>
      <div className="sidebar-pulse"><strong>CRM Command Center</strong><span>Leads, customers, campaigns, tasks and client growth</span></div>
      <nav>{items.filter((x) => can(user, x[4])).map(([group, label, href, Icon]) => {
        const head = group !== section; section = group;
        return <div key={href}>{head && <p className="nav-head">{group}</p>}<NavLink to={href}><Icon size={18} />{label}</NavLink></div>;
      })}</nav>
      <footer><div className="avatar" style={{ background: user.avatar_color }}>{user.avatar_initials}</div><div><strong>{user.name}</strong><span>{user.role_label || roleLabel(user.permission_role || user.role)}</span></div><button className="icon-btn" onClick={logout} title="Logout"><IconLogout size={18} /></button></footer>
    </aside>
  );
}
