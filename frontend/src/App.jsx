import { Navigate, Route, Routes } from "react-router-dom";
import { Component, Suspense, lazy } from "react";
import Shell from "./components/Layout/Shell.jsx";
import { useAuth } from "./context/AuthContext.jsx";
import { can } from "./permissions.js";

const AIChat = lazy(() => import("./pages/AIChat.jsx"));
const AIFollowups = lazy(() => import("./pages/AIFollowups.jsx"));
const Calendar = lazy(() => import("./pages/Calendar.jsx"));
const Campaigns = lazy(() => import("./pages/Campaigns.jsx"));
const Communication = lazy(() => import("./pages/Communication.jsx"));
const Customers = lazy(() => import("./pages/Customers.jsx"));
const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const Employees = lazy(() => import("./pages/Employees.jsx"));
const Leads = lazy(() => import("./pages/Leads.jsx"));
const Login = lazy(() => import("./pages/Login.jsx"));
const Reports = lazy(() => import("./pages/Reports.jsx"));
const Settings = lazy(() => import("./pages/Settings.jsx"));
const Tasks = lazy(() => import("./pages/Tasks.jsx"));
const Workflows = lazy(() => import("./pages/Workflows.jsx"));
const WhatsAppMessages = lazy(() => import("./pages/WhatsAppMessages.jsx"));

function PrivateRoute({ children, page }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="boot">Loading Digidara CRM...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (page && !can(user, page)) return <Shell><div className="empty">403 - Permission required for this page.</div></Shell>;
  return <Shell>{children}</Shell>;
}

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app-error">
          <div>
            <strong>Digidara CRM could not load this screen.</strong>
            <span>Clear the browser cache or sign in again. The app is still running.</span>
            <button onClick={() => {
              localStorage.removeItem("access_token");
              localStorage.removeItem("refresh_token");
              localStorage.removeItem("user");
              location.href = "/login";
            }}>Return to login</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <AppErrorBoundary>
      <Suspense fallback={<div className="boot">Loading Digidara CRM...</div>}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<PrivateRoute page="dashboard"><Dashboard /></PrivateRoute>} />
          <Route path="/leads" element={<PrivateRoute page="leads"><Leads /></PrivateRoute>} />
          <Route path="/customers" element={<PrivateRoute page="customers"><Customers /></PrivateRoute>} />
          <Route path="/tasks" element={<PrivateRoute page="tasks"><Tasks /></PrivateRoute>} />
          <Route path="/calendar" element={<PrivateRoute page="calendar"><Calendar /></PrivateRoute>} />
          <Route path="/ai-chat" element={<PrivateRoute page="ai_chat"><AIChat /></PrivateRoute>} />
          <Route path="/ai-copilot" element={<Navigate to="/ai-chat" replace />} />
          <Route path="/ai-followups" element={<PrivateRoute page="ai_followups"><AIFollowups /></PrivateRoute>} />
          <Route path="/workflows" element={<PrivateRoute page="workflows"><Workflows /></PrivateRoute>} />
          <Route path="/notifications" element={<Navigate to="/dashboard" replace />} />
          <Route path="/campaigns" element={<PrivateRoute page="campaigns"><Campaigns /></PrivateRoute>} />
          <Route path="/communication" element={<PrivateRoute page="communication"><Communication /></PrivateRoute>} />
          <Route path="/communication/whatsapp" element={<PrivateRoute page="whatsapp_messages"><WhatsAppMessages /></PrivateRoute>} />
          <Route path="/reports" element={<PrivateRoute page="reports"><Reports /></PrivateRoute>} />
          <Route path="/employees" element={<PrivateRoute page="employees"><Employees /></PrivateRoute>} />
          <Route path="/settings" element={<PrivateRoute page="settings"><Settings /></PrivateRoute>} />
        </Routes>
      </Suspense>
    </AppErrorBoundary>
  );
}
