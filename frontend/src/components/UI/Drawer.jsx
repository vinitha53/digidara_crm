import { IconX } from "@tabler/icons-react";
import { useEffect } from "react";

export default function Drawer({ open, title, children, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    const previous = document.body.style.overflow;
    const close = (event) => { if (event.key === "Escape") onClose(); };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", close);
    return () => { document.body.style.overflow = previous; document.removeEventListener("keydown", close); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header><h2>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close drawer"><IconX size={18} /></button></header>
        {children}
      </aside>
    </div>
  );
}
