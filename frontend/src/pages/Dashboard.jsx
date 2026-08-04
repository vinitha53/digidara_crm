import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import api from "../api/client";
import Card from "../components/UI/Card.jsx";
import KpiCard from "../components/UI/KpiCard.jsx";

export default function Dashboard() {
  const [data, setData] = useState({ owner: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    setError("");
    Promise.all([
      api.post("/communication/sync-whatsapp-leads").catch(() => null),
      api.post("/external-sources/sync-website-leads").catch(() => null),
    ])
      .then(() => api.get("/reports/owner-overview"))
      .then(({ data: owner }) => setData({ owner }))
      .catch(() => setError("Dashboard data could not be loaded."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading) return <div className="page dashboard-page"><Card className="dashboard-state">Loading business insights...</Card></div>;
  if (error) return <div className="page dashboard-page"><Card className="dashboard-state"><strong>{error}</strong><button className="btn primary" onClick={load}>Try again</button></Card></div>;

  return <div className="page dashboard-page">
    <section className="dashboard-intro">
      <div><span>BUSINESS LEAD OVERVIEW</span><h2>Courses, internships and client projects</h2><p>Monitor enquiry volume, conversion, source quality and loss patterns without revenue noise.</p></div>
      <div className="dashboard-open"><strong>{data.owner.open_leads || 0}</strong><span>Open leads need progression</span></div>
    </section>
    <div className="owner-kpi-grid">
      <KpiCard label="Total Leads" value={data.owner.total_leads || 0} sub="All course, internship and project enquiries" to="/leads" />
      <KpiCard label="Academic Leads" value={data.owner.academic_leads || 0} sub="Courses and internships combined" color="teal" to="/leads?segment=academic" />
      <KpiCard label="Project Leads" value={data.owner.project_leads || 0} sub="Client project enquiries" color="amber" to="/leads?segment=project" />
      <KpiCard label="Lead Lost" value={data.owner.lost_leads || 0} sub={`${data.owner.loss_rate || 0}% of all leads`} color="red" to="/leads?status=lost" />
      <KpiCard label="Academic Lost" value={data.owner.academic_lost || 0} sub={`${data.owner.academic_loss_rate || 0}% of academic leads`} color="red" to="/leads?status=lost&segment=academic" />
      <KpiCard label="Project Lost" value={data.owner.project_lost || 0} sub={`${data.owner.project_loss_rate || 0}% of project leads`} color="red" to="/leads?status=lost&segment=project" />
    </div>
    <div className="dashboard-section-heading"><div><span>CONVERSION & PIPELINE</span><h2>From enquiry to won customer</h2></div><p>Conversion rate = won leads divided by total leads.</p></div>
    <div className="owner-kpi-grid">
      <KpiCard label="Conversion Rate" value={`${data.owner.conversion_rate || 0}%`} sub={`${data.owner.won_leads || 0} of ${data.owner.total_leads || 0} leads won`} color="teal" to="/leads?status=won" />
      <KpiCard label="Academic Conversion" value={`${data.owner.academic_conversion_rate || 0}%`} sub={`${data.owner.academic_won || 0} academic leads won`} color="teal" to="/leads?status=won&segment=academic" />
      <KpiCard label="Project Conversion" value={`${data.owner.project_conversion_rate || 0}%`} sub={`${data.owner.project_won || 0} project leads won`} color="teal" to="/leads?status=won&segment=project" />
      <KpiCard label="Won Leads" value={data.owner.won_leads || 0} sub="Successfully converted to customers" color="teal" to="/leads?status=won" />
      <KpiCard label="Open Leads" value={data.owner.open_leads || 0} sub="New, contacted and qualified" color="amber" to="/leads?stage=open" />
      <KpiCard label="Hot Open Leads" value={data.owner.hot_leads || 0} sub="Priority opportunities to contact" color="red" to="/leads?tag=hot&stage=open" />
    </div>
    <div className="grid dashboard-charts"><CategoryPerformance data={data.owner.category_performance || []} /><ConversionByLine data={data.owner.category_performance || []} /><LeadTrend className="wide" data={data.owner.monthly_trend || []} /></div>
    <div className="dashboard-section-heading"><div><span>BUSINESS DECISION INSIGHTS</span><h2>Where growth comes from and where leads are lost</h2></div><p>Use source quality and loss patterns to guide marketing and sales decisions.</p></div>
    <div className="grid dashboard-insights"><SourcePerformance data={data.owner.source_performance || []} /><LossIntelligence data={data.owner.loss_reasons || []} /></div>
    <PipelineSnapshot data={data.owner.pipeline_snapshot || []} />
  </div>;
}

const tooltipStyle = { background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 10, color: "var(--text)" };

function CategoryPerformance({ data }) {
  return <Card className="dashboard-chart-card"><h2>Lead Performance by Business Line</h2><p className="chart-note">Compare the complete lead pool with open, won and lost outcomes.</p><ResponsiveContainer width="100%" height={300}><BarChart data={data} margin={{ top: 12, right: 8, left: -14, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} /><XAxis dataKey="name" tick={{ fill: "var(--text2)", fontSize: 12 }} axisLine={{ stroke: "var(--border-strong)" }} tickLine={false} /><YAxis allowDecimals={false} tick={{ fill: "var(--text2)", fontSize: 12 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} labelStyle={{ color: "var(--ink)", fontWeight: 800 }} /><Legend wrapperStyle={{ color: "var(--text2)", fontSize: 12 }} /><Bar dataKey="total" name="Total" fill="var(--primary)" radius={[5, 5, 0, 0]} /><Bar dataKey="open" name="Open" fill="var(--gold)" radius={[5, 5, 0, 0]} /><Bar dataKey="won" name="Won" fill="var(--teal)" radius={[5, 5, 0, 0]} /><Bar dataKey="lost" name="Lost" fill="var(--red)" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer></Card>;
}

function ConversionByLine({ data }) {
  return <Card className="dashboard-chart-card"><h2>Conversion Rate by Business Line</h2><p className="chart-note">Identify which offering converts enquiries most effectively.</p><ResponsiveContainer width="100%" height={300}><BarChart data={data} layout="vertical" margin={{ top: 12, right: 48, left: 8, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} /><XAxis type="number" domain={[0, 100]} tickFormatter={(value) => `${value}%`} tick={{ fill: "var(--text2)", fontSize: 12 }} axisLine={{ stroke: "var(--border-strong)" }} tickLine={false} /><YAxis type="category" dataKey="name" width={105} tick={{ fill: "var(--text2)", fontSize: 12 }} axisLine={false} tickLine={false} /><Tooltip formatter={(value) => [`${value}%`, "Conversion Rate"]} contentStyle={tooltipStyle} labelStyle={{ color: "var(--ink)", fontWeight: 800 }} /><Bar dataKey="conversion_rate" name="Conversion Rate" fill="var(--teal)" radius={[0, 6, 6, 0]}><LabelList dataKey="conversion_rate" position="right" formatter={(value) => `${value}%`} fill="var(--text)" fontSize={12} fontWeight={800} /></Bar></BarChart></ResponsiveContainer></Card>;
}

function LeadTrend({ data, className = "" }) {
  return <Card className={`dashboard-chart-card ${className}`}><h2>Six-Month Lead Movement</h2><p className="chart-note">See whether new enquiries are growing and how wins compare with losses.</p><ResponsiveContainer width="100%" height={300}><LineChart data={data} margin={{ top: 12, right: 12, left: -14, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} /><XAxis dataKey="name" tick={{ fill: "var(--text2)", fontSize: 12 }} axisLine={{ stroke: "var(--border-strong)" }} tickLine={false} /><YAxis allowDecimals={false} tick={{ fill: "var(--text2)", fontSize: 12 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} labelStyle={{ color: "var(--ink)", fontWeight: 800 }} /><Legend wrapperStyle={{ color: "var(--text2)", fontSize: 12 }} /><Line type="monotone" dataKey="leads" name="Leads Added" stroke="var(--primary)" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} /><Line type="monotone" dataKey="won" name="Won" stroke="var(--teal)" strokeWidth={3} dot={{ r: 4 }} /><Line type="monotone" dataKey="lost" name="Lost" stroke="var(--red)" strokeWidth={3} dot={{ r: 4 }} /></LineChart></ResponsiveContainer></Card>;
}

function SourcePerformance({ data }) {
  return <Card className="owner-insight-card"><h2>Lead Source Effectiveness</h2><p className="chart-note">Compare lead volume, wins and conversion quality by acquisition channel.</p><div className="insight-table-head"><span>Source</span><span>Leads</span><span>Won</span><span>Conversion</span></div><div className="insight-list">{data.map((item) => <Link className="insight-row" to={`/leads?source=${encodeURIComponent(item.key)}`} key={item.key}><strong>{sourceLabel(item.key)}</strong><span>{item.leads}</span><span>{item.won}</span><div className="insight-rate"><b>{item.conversion_rate}%</b><div><i style={{ width: `${Math.min(item.conversion_rate, 100)}%` }} /></div></div></Link>)}{!data.length && <div className="insight-empty">No lead-source data available yet.</div>}</div></Card>;
}

function LossIntelligence({ data }) {
  return <Card className="owner-insight-card"><h2>Why Leads Are Lost</h2><p className="chart-note">Prioritize the objections and process gaps causing the most losses.</p><div className="loss-list">{data.map((item) => <Link className="loss-row" to={`/leads?status=lost&lost_reason=${encodeURIComponent(item.name)}`} key={item.name}><div><strong>{item.name}</strong><span>{item.count} lead{item.count === 1 ? "" : "s"}</span></div><b>{item.share}%</b><div className="loss-bar"><i style={{ width: `${Math.min(item.share, 100)}%` }} /></div></Link>)}{!data.length && <div className="insight-empty">No lost leads recorded. That is a healthy signal.</div>}</div></Card>;
}

function PipelineSnapshot({ data }) {
  return <Card className="pipeline-snapshot-card"><div className="pipeline-snapshot-head"><div><h2>Current Lead Pipeline</h2><p>See where the active portfolio is concentrated and drill into any stage.</p></div><Link to="/leads">View all leads</Link></div><div className="pipeline-snapshot">{data.map((item) => <Link className={`pipeline-stage ${item.key}`} to={`/leads?status=${item.key}`} key={item.key}><span>{item.name}</span><strong>{item.value}</strong><small>{item.share}% of tracked pipeline</small><div><i style={{ width: `${Math.min(item.share, 100)}%` }} /></div></Link>)}</div></Card>;
}

function sourceLabel(value) {
  return ({ website: "Website", chatbot: "Chatbot", whatsapp: "WhatsApp", email: "Email", inperson: "In Person" })[value] || value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
