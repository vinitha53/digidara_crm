import { useEffect, useRef, useState } from "react";
import { IconEye, IconEyeOff, IconMoon, IconSun } from "@tabler/icons-react";
import { useNavigate } from "react-router-dom";
import Button from "../components/UI/Button.jsx";
import Toast from "../components/UI/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";

export default function Login() {
  const [theme, setTheme] = useState(() => localStorage.getItem("crm_theme") || "light");
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("crm_theme", theme); }, [theme]);
  const [form, setForm] = useState({ email: "", password: "" });
  const [loginType, setLoginType] = useState("admin");
  const [credentialsEditable, setCredentialsEditable] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [challenge, setChallenge] = useState(null);
  const [otp, setOtp] = useState("");
  const [resendIn, setResendIn] = useState(0);
  const [toast, setToast] = useState(null);
  const [loading, setLoading] = useState(false);
  const requestInFlight = useRef(false);
  const { login, verifyOtp, resendOtp } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (resendIn <= 0) return undefined;
    const timer = window.setInterval(() => setResendIn((seconds) => Math.max(0, seconds - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [resendIn]);
  async function submit(e) {
    e.preventDefault();
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setLoading(true);
    try {
      if (challenge) {
        await verifyOtp(challenge.challenge_id, otp);
        navigate("/dashboard");
      } else {
        const result = await login(form.email, form.password);
        if (result.otp_required) {
          setChallenge(result);
          setResendIn(result.resend_in || 0);
          setToast({ type: "success", message: `OTP sent to ${result.phone_hint}` });
        } else {
          navigate("/dashboard");
        }
      }
    } catch (error) {
      const data = error.response?.data;
      if (data?.challenge_id) {
        setChallenge(data);
        setResendIn(data.resend_in || 0);
      }
      setToast({ type: "error", message: data?.message || "Unable to sign in. Please try again." });
    } finally {
      requestInFlight.current = false;
      setLoading(false);
    }
  }
  async function resend() {
    if (!challenge || resendIn > 0 || requestInFlight.current) return;
    requestInFlight.current = true;
    setLoading(true);
    try {
      const result = await resendOtp(challenge.challenge_id);
      setChallenge(result);
      setResendIn(result.resend_in || 0);
      setOtp("");
      setToast({ type: "success", message: "A new OTP was sent." });
    } catch (error) {
      const data = error.response?.data;
      if (data?.challenge_id) {
        setChallenge(data);
        setResendIn(data.resend_in || 0);
      }
      setToast({ type: "error", message: data?.message || "Unable to resend OTP." });
    } finally {
      requestInFlight.current = false;
      setLoading(false);
    }
  }
  function backToLogin() {
    setChallenge(null);
    setOtp("");
    setResendIn(0);
    setToast(null);
    setForm((current) => ({ ...current, password: "" }));
    setShowPassword(false);
  }
  function chooseLoginType(type) {
    setLoginType(type);
    setForm({ email: "", password: "" });
    setShowPassword(false);
    setCredentialsEditable(false);
  }
  return <div className="login-page"><button className="login-theme" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}{theme === "dark" ? "Light" : "Dark"}</button><section><div className="login-mark company-logo"><img src={`${import.meta.env.BASE_URL}assets/digidara-company-logo.png`} alt="Digidara Technologies" /></div><h1>DigiDARA CRM</h1><p>The operating system for course enquiries, internships, client projects and team execution.</p>{["Live business overview", "Lead and customer management", "Tasks, campaigns and communication", "Database-connected AI Chat"].map((x) => <span key={x}>{x}</span>)}</section><form onSubmit={submit} className="login-card" autoComplete="off"><small>SECURE WORKSPACE</small><h2>{challenge ? "Verify your login" : "Welcome back"}</h2><p>{challenge ? `Enter the 6-digit OTP sent to WhatsApp number ${challenge.phone_hint}.` : "Sign in to continue to your CRM."}</p>{challenge ? <><label>One-time password<input className="otp-input" inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]{6}" value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))} required autoFocus /></label><Button disabled={loading || otp.length !== 6}>{loading ? "Verifying..." : "Verify and sign in"}</Button><div className="otp-actions"><button type="button" onClick={backToLogin}>Back to login</button><button type="button" onClick={resend} disabled={loading || resendIn > 0}>{resendIn > 0 ? `Resend in ${resendIn}s` : "Resend OTP"}</button></div></> : <><div className="seg"><button type="button" aria-pressed={loginType === "admin"} onClick={() => chooseLoginType("admin")}>Admin Login</button><button type="button" aria-pressed={loginType === "staff"} onClick={() => chooseLoginType("staff")}>Staff Login</button></div><label>Email or login ID<input autoComplete="off" readOnly={!credentialsEditable} value={form.email} onFocus={() => setCredentialsEditable(true)} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label><label>Password<div className="password-input"><input type={showPassword ? "text" : "password"} autoComplete="new-password" readOnly={!credentialsEditable} value={form.password} onFocus={() => setCredentialsEditable(true)} onChange={(e) => setForm({ ...form, password: e.target.value })} required /><button type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} title={showPassword ? "Hide password" : "Show password"}>{showPassword ? <IconEyeOff size={20} /> : <IconEye size={20} />}</button></div></label><Button disabled={loading}>{loading ? "Sending OTP..." : "Continue securely"}</Button></>}</form><Toast toast={toast} /></div>;
}
