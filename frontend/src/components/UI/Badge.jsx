export default function Badge({ children, tone = "purple" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
