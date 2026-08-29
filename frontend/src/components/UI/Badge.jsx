import { sentenceCase } from "../../utils/text.js";

export default function Badge({ children, tone = "purple" }) {
  const label = typeof children === "string" ? sentenceCase(children) : children;
  return <span className={`badge ${tone}`}>{label}</span>;
}
