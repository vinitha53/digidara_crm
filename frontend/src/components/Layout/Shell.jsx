import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import Sidebar from "./Sidebar.jsx";
import Topbar from "./Topbar.jsx";

export default function Shell({ children }) {
  const [navigationOpen, setNavigationOpen] = useState(false);
  const location = useLocation();

  useEffect(() => { setNavigationOpen(false); }, [location.pathname]);
  useEffect(() => {
    if (!navigationOpen) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const close = (event) => { if (event.key === "Escape") setNavigationOpen(false); };
    document.addEventListener("keydown", close);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", close);
    };
  }, [navigationOpen]);

  return <div className={`shell ${navigationOpen ? "navigation-open" : ""}`}>
    <Sidebar open={navigationOpen} onClose={() => setNavigationOpen(false)} />
    <button className="sidebar-backdrop" type="button" aria-label="Close navigation" onClick={() => setNavigationOpen(false)} />
    <main><Topbar navigationOpen={navigationOpen} onMenuClick={() => setNavigationOpen(true)} /><div className="content">{children}</div></main>
  </div>;
}
