import { useEffect, useState } from "react";

export default function Toast({ toast, duration = 3000 }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!toast) {
      setVisible(false);
      return undefined;
    }

    setVisible(true);
    const timer = window.setTimeout(() => setVisible(false), duration);
    return () => window.clearTimeout(timer);
  }, [toast, duration]);

  if (!toast || !visible) return null;
  return <div className={`toast ${toast.type || "info"}`}>{toast.message}</div>;
}
