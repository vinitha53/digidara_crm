export default function ActivityFeed({ items = [] }) {
  return <div className="feed">{items.map((x) => <div className="feed-row" key={x.id}><strong>{x.actor}</strong><span>{x.action.replaceAll("_", " ")} - {x.entity_name}</span><small>{new Date(x.created_at).toLocaleString("en-IN")}</small></div>)}</div>;
}
