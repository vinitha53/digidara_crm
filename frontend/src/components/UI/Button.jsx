import { Children } from "react";
import { sentenceCase } from "../../utils/text.js";

export default function Button({ children, variant = "primary", ...props }) {
  const label = Children.map(children, (child) => typeof child === "string" ? sentenceCase(child) : child);
  return <button className={`btn ${variant}`} {...props}>{label}</button>;
}
