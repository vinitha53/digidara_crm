import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { IconAlertTriangle, IconChartBar, IconDownload, IconRefresh, IconTargetArrow } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import api from "../api/client";
import Card from "../components/UI/Card.jsx";
import KpiCard from "../components/UI/KpiCard.jsx";
import DataTable from "../components/shared/DataTable.jsx";

const periods = [{ key: "30", label: "30 days" }, { key: "90", label: "90 days" }, { key: "180", label: "6 months" }, { key: "365", label: "12 months" }, { key: "all", label: "All time" }];
const emptyReport = { period: {}, summary: {}, categories: [], sources: [], loss_reasons: [], trend: [], aging: [], employees: [], actions: [], pipeline: [], conversion_insights: {} };
const tooltipStyle = { background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 10, color: "var(--text)" };

export default function Reports() {
  const [period, setPeriod] = useState("90");
  const [data, setData] = useState(emptyReport);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  const load = () => {
    setLoading(true);
    setError("");
    api.get("/reports/owner-report", { params: { period } }).then(({ data: report }) => setData(report))
      .catch(() => setError("The business report could not be loaded."))
      .finally(() => setLoading(false));
  };
  useEffect(load, [period]);

  const download = () => {
    setExporting(true);
    api.get("/reports/export", { params: { period }, responseType: "blob" }).then(({ data: blob }) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `digidara-business-report-${period}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    }).catch(() => setError("The operational report could not be exported."))
      .finally(() => setExporting(false));
  };

  if (loading && !data.generated_at) return <div className="page reports-page"><Card className="report-state">Preparing the business report...</Card></div>;
  if (error && !data.generated_at) return <div className="page reports-page"><Card className="report-state"><strong>{error}</strong><button className="btn primary" onClick={load}><IconRefresh size={17} /> Try again</button></Card></div>;

  return <div className="page reports-page">
    <section className="report-owner-intro">
      <div><span>BUSINESS OPERATING REPORT</span><h2>Growth quality and execution health</h2><p>Understand which business lines and sources convert, why enquiries are lost, and where the team needs intervention—without revenue noise.</p></div>
      <button className="btn primary report-export" disabled={exporting} onClick={download}><IconDownload size={18} /> {exporting ? "Preparing..." : "Export this view"}</button>
    </section>

    <section className="report-toolbar" aria-label="Report period">
      <div><strong>Reporting period</strong><span>Lead and completed-task performance use this cohort. Current attention metrics remain live.</span></div>
      <div className="report-periods">{periods.map((item) => <button type="button" className={period === item.key ? "active" : ""} onClick={() => setPeriod(item.key)} key={item.key}>{item.label}</button>)}</div>
    </section>

    {error && <div className="report-inline-error">{error} <button onClick={load}>Retry</button></div>}
    <div className="report-kpi-grid">
      <KpiCard label="Leads Added" value={data.summary.leads || 0} sub={data.period.label || "Selected period"} to="/leads" />
      <KpiCard label="Conversion Rate" value={`${data.summary.conversion_rate || 0}%`} sub={`${data.summary.won || 0} won from ${data.summary.leads || 0} leads`} color="teal" to="/leads?status=won" />
      <KpiCard label="Loss Rate" value={`${data.summary.loss_rate || 0}%`} sub={`${data.summary.lost || 0} lost in this cohort`} color="red" to="/leads?status=lost" />
      <KpiCard label="New Customers" value={data.summary.new_customers || 0} sub="Converted customers added in period" color="teal" to="/customers" />
      <KpiCard label="Current Open Leads" value={data.summary.current_open || 0} sub={`${data.summary.hot || 0} hot · ${data.summary.unassigned || 0} unassigned`} color="amber" to="/leads?stage=open" />
      <KpiCard label="Overdue Tasks" value={data.summary.overdue_tasks || 0} sub={`${data.summary.tasks_due_today || 0} additional tasks due today`} color="red" to="/tasks?filter=overdue" />
    </div>

    <OwnerActions actions={data.actions} />

    <div className="report-section-heading"><div><span>PERFORMANCE</span><h2>Demand and conversion movement</h2></div><p>Wins and losses use the current outcome of leads created in the selected period.</p></div>
    <div className="report-chart-grid">
      <Card className="report-chart-card"><h3>Lead movement</h3><p>Monthly acquisition with the wins and losses recorded in each month.</p><ResponsiveContainer width="100%" height={300}><LineChart data={data.trend} margin={{ top: 10, right: 12, left: -18, bottom: 2 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} /><XAxis dataKey="name" tick={{ fill: "var(--text2)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--border)" }} /><YAxis allowDecimals={false} tick={{ fill: "var(--text2)", fontSize: 11 }} tickLine={false} axisLine={false} /><Tooltip contentStyle={tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} /><Line type="monotone" dataKey="leads" name="Leads added" stroke="var(--primary)" strokeWidth={3} /><Line type="monotone" dataKey="won" name="Won" stroke="var(--teal)" strokeWidth={3} /><Line type="monotone" dataKey="lost" name="Lost" stroke="var(--red)" strokeWidth={3} /></LineChart></ResponsiveContainer></Card>
      <Card className="report-chart-card"><h3>Business-line performance</h3><p>Compare course, internship and client-project outcomes.</p><ResponsiveContainer width="100%" height={300}><BarChart data={data.categories} margin={{ top: 10, right: 8, left: -18, bottom: 2 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} /><XAxis dataKey="name" tick={{ fill: "var(--text2)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--border)" }} /><YAxis allowDecimals={false} tick={{ fill: "var(--text2)", fontSize: 11 }} tickLine={false} axisLine={false} /><Tooltip contentStyle={tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} /><Bar dataKey="leads" name="Leads" fill="var(--primary)" radius={[5, 5, 0, 0]} /><Bar dataKey="won" name="Won" fill="var(--teal)" radius={[5, 5, 0, 0]} /><Bar dataKey="lost" name="Lost" fill="var(--red)" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer></Card>
    </div>
    <BusinessLineCards rows={data.categories} />

    <div className="report-section-heading"><div><span>SALES CONVERSION</span><h2>How the team converts assigned leads</h2></div><p>Compare salesperson outcomes, conversion speed and follow-up discipline—not activity volume alone.</p></div>
    <ConversionIntelligence insights={data.conversion_insights} />
    <PipelineReport rows={data.pipeline} />

    <div className="report-section-heading"><div><span>ACQUISITION & LOSS</span><h2>Where quality comes from and where it breaks</h2></div><p>Use conversion—not volume alone—to evaluate lead sources.</p></div>
    <div className="report-insight-grid"><SourceQuality rows={data.sources} /><LossReasons rows={data.loss_reasons} /></div>

    <div className="report-section-heading"><div><span>CURRENT HEALTH</span><h2>Lead aging and customer contact</h2></div><p>These are live operating risks and are not limited by the selected reporting cohort.</p></div>
    <div className="report-health-grid"><Card><div className="report-card-head"><div><h3>Open lead aging</h3><p>Older open enquiries require recovery or a clear outcome.</p></div><strong>{data.summary.stale || 0} stale</strong></div><div className="aging-grid">{data.aging.map((row) => <Link to="/leads?stage=open" key={row.id}><span>{row.name}</span><strong>{row.value}</strong></Link>)}</div></Card><Card className="customer-health-card"><div><span>CUSTOMER RELATIONSHIP RISK</span><strong>{data.summary.customer_contact_overdue || 0}</strong><p>active or follow-up customers have not been contacted for at least seven days.</p></div><Link className="btn" to="/customers?attention=contact_overdue">Review customers</Link></Card></div>

    <div className="report-section-heading"><div><span>SALESPERSON DETAIL</span><h2>Conversion and follow-up accountability</h2></div><p>Creation-to-win days are estimates based on the lead’s last outcome update.</p></div>
    <TeamAccountability rows={data.employees} />
    <footer className="report-generated">Generated from live CRM records {formatGenerated(data.generated_at)} · {data.period.label}</footer>
  </div>;
}

function OwnerActions({ actions = [] }) {
  return <Card className="owner-action-report"><div className="report-card-head"><div><span>PRIORITY ATTENTION</span><h2>Decisions that need action now</h2></div><IconAlertTriangle size={24} /></div><div className="owner-action-list">{actions.map((action) => <Link className={`owner-action-item ${action.priority}`} to={action.to} key={action.id}><i /><div><strong>{action.title}</strong><span>{action.detail}</span></div><b>Review</b></Link>)}</div></Card>;
}

function BusinessLineCards({ rows = [] }) {
  return <div className="business-report-grid">{rows.map((row) => <Link to={`/leads?${row.key === "project" ? "segment=project" : `lead_category=${row.key}`}`} key={row.id}><div><span>{row.name}</span><b>{row.conversion_rate}% conversion</b></div><strong>{row.leads}</strong><small>{row.open} open · {row.won} won · {row.lost} lost</small><div className="report-progress"><i style={{ width: `${Math.min(row.conversion_rate, 100)}%` }} /></div></Link>)}</div>;
}

function ConversionIntelligence({ insights = {} }) {
  const top = insights.top_converter;
  const fastest = insights.fastest_converter;
  const line = insights.best_business_line;
  const cards = [
    { label: "Top converter", value: top?.name || "No wins yet", detail: top ? `${top.leads_won} won · ${top.win_rate}% conversion` : "No assigned lead has converted in this period" },
    { label: "Fastest conversion", value: fastest?.name || "Not available", detail: fastest ? `${fastest.average_days_to_win} average days to win` : "Conversion duration needs a won lead" },
    { label: "Strongest business line", value: line?.name || "Not available", detail: line ? `${line.conversion_rate}% conversion from ${line.leads} leads` : "No lead cohort in this period" },
    { label: "Average time to win", value: insights.average_days_to_win == null ? "Not available" : `${insights.average_days_to_win} days`, detail: "Creation to final won-status update" },
  ];
  return <div className="conversion-intelligence-grid">{cards.map((card) => <Card key={card.label}><span>{card.label}</span><strong>{card.value}</strong><small>{card.detail}</small></Card>)}</div>;
}

function PipelineReport({ rows = [] }) {
  return <Card className="report-funnel-card"><div className="report-card-head"><div><h3>Selected-period lead funnel</h3><p>Current stage concentration of leads created in this reporting period. This is not a historical stage-to-stage transition report.</p></div><IconTargetArrow size={23} /></div><div className="report-funnel">{rows.map((row) => <Link to={`/leads?status=${row.key}`} className={row.key} key={row.id}><span>{row.name}</span><strong>{row.value}</strong><small>{row.share}% of cohort</small><div><i style={{ width: `${Math.min(row.share, 100)}%` }} /></div></Link>)}</div></Card>;
}

function SourceQuality({ rows = [] }) {
  const columns = useMemo(() => [{ label: "Source", key: "name" }, { label: "Leads", key: "leads" }, { label: "Won", key: "won" }, { label: "Lost", key: "lost" }, { label: "Conversion", key: "conversion_rate", render: row => `${row.conversion_rate}%` }], []);
  return <Card className="report-table-card"><div className="report-card-head"><div><h3>Source quality</h3><p>Ranked by conversion rate, then lead volume.</p></div><IconTargetArrow size={23} /></div><div className="report-desktop-table"><DataTable columns={columns} data={rows} empty="No source data in this period." /></div><div className="report-mobile-list">{rows.map((row) => <article key={row.id}><header><strong>{row.name}</strong><b>{row.conversion_rate}%</b></header><span>{row.leads} leads · {row.won} won · {row.lost} lost</span></article>)}</div></Card>;
}

function LossReasons({ rows = [] }) {
  return <Card><div className="report-card-head"><div><h3>Loss reason intelligence</h3><p>Fix the objections and process gaps with the highest share.</p></div><IconChartBar size={23} /></div><div className="report-loss-list">{rows.map((row) => <Link to={`/leads?status=lost&lost_reason=${encodeURIComponent(row.name)}`} key={row.id}><div><strong>{row.name}</strong><span>{row.count} lost lead{row.count === 1 ? "" : "s"}</span></div><b>{row.share}%</b><div><i style={{ width: `${Math.min(row.share, 100)}%` }} /></div></Link>)}{!rows.length && <div className="empty compact-empty">No leads were lost in this period.</div>}</div></Card>;
}

function TeamAccountability({ rows = [] }) {
  const columns = useMemo(() => [{ label: "Employee", key: "name", render: row => <div className="report-person"><strong>{row.name}</strong><span>{row.department}</span></div> }, { label: "Assigned", key: "leads_assigned" }, { label: "Contacted", key: "contacted_leads" }, { label: "Qualified", key: "qualified_leads" }, { label: "Won", key: "leads_won" }, { label: "Lost", key: "leads_lost" }, { label: "Conversion", key: "win_rate", render: row => `${row.win_rate}%` }, { label: "Avg. Days", key: "average_days_to_win", render: row => row.average_days_to_win == null ? "—" : row.average_days_to_win }, { label: "Stale", key: "stale_leads" }, { label: "Never Contacted", key: "never_contacted" }, { label: "Overdue Tasks", key: "overdue_tasks" }], []);
  return <Card className="report-table-card"><div className="report-desktop-table"><DataTable columns={columns} data={rows} empty="No active employee conversion data is available." /></div><div className="report-mobile-list team">{rows.map((row) => <article key={row.id}><header><div><strong>{row.name}</strong><span>{row.department}</span></div><b className={row.overdue_tasks ? "danger-text" : ""}>{row.win_rate}% converted</b></header><dl><div><dt>Assigned</dt><dd>{row.leads_assigned}</dd></div><div><dt>Won</dt><dd>{row.leads_won}</dd></div><div><dt>Lost</dt><dd>{row.leads_lost}</dd></div><div><dt>Avg. days</dt><dd>{row.average_days_to_win ?? "—"}</dd></div><div><dt>Stale</dt><dd>{row.stale_leads}</dd></div><div><dt>Never contacted</dt><dd>{row.never_contacted}</dd></div><div><dt>Overdue tasks</dt><dd>{row.overdue_tasks}</dd></div></dl></article>)}</div></Card>;
}

function formatGenerated(value) {
  if (!value) return "";
  return `on ${new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`;
}
