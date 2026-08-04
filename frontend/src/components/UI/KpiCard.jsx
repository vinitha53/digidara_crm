import Card from "./Card.jsx";
import { IconAlertTriangle, IconBell, IconBriefcase, IconChartBar, IconChevronRight, IconClipboardCheck, IconSchool, IconTargetArrow, IconUsers } from "@tabler/icons-react";
import { Link } from "react-router-dom";

export default function KpiCard({ label, value, sub, color = "purple", to, onClick }) {
  const MetricIcon = iconFor(label);
  const content = <><div className="kpi-icon" aria-hidden="true"><MetricIcon size={23} stroke={1.8} /></div><span>{label}</span><strong>{value}</strong><small>{sub}</small>{to && <IconChevronRight className="kpi-arrow" size={18} />}</>;
  if (onClick) return <button type="button" className={`card kpi clickable kpi-button ${color}`} onClick={onClick}>{content}</button>;
  return to ? <Link className={`card kpi clickable ${color}`} to={to}>{content}</Link> : <Card className={`kpi ${color}`}>{content}</Card>;
}

function iconFor(label = "") {
  const text = label.toLowerCase();
  if (text.includes("customer")) return IconUsers;
  if (text.includes("lost") || text.includes("alert") || text.includes("attention") || text.includes("overdue")) return IconAlertTriangle;
  if (text.includes("academic") || text.includes("course") || text.includes("internship")) return IconSchool;
  if (text.includes("project") || text.includes("business")) return IconBriefcase;
  if (text.includes("task") || text.includes("follow-up") || text.includes("review")) return IconClipboardCheck;
  if (text.includes("notification") || text.includes("unread")) return IconBell;
  if (text.includes("conversion") || text.includes("won") || text.includes("lead")) return IconTargetArrow;
  return IconChartBar;
}
