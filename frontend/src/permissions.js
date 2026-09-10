export const pageActions = {
  dashboard: ["view"],
  leads: ["view", "create", "update", "delete", "assign", "convert", "classify"],
  customers: ["view", "create", "update", "delete", "send_review", "sync_review"],
  tasks: ["view", "create", "update", "delete", "assign", "complete"],
  notifications: ["view", "update"],
  calendar: ["view", "schedule"],
  ai_chat: ["view", "ask"],
  ai_followups: ["view", "generate", "send", "run"],
  campaigns: ["view", "create", "update", "send", "schedule", "pause", "cancel", "export", "manage_templates"],
  communication: ["view", "send"],
  whatsapp_messages: ["view"],
  reports: ["view", "export"],
  employees: ["view", "create", "update", "delete"],
  settings: ["view", "update", "manage"],
};

export function can(user, page, action = "view") {
  if (page === "whatsapp_messages" && action === "view") {
    return Boolean(user?.permissions?.whatsapp_messages?.view || user?.permissions?.communication?.view);
  }
  return Boolean(user?.permissions?.[page]?.[action]);
}

export function roleLabel(role) {
  if (role === "admin") return "Administrator";
  if (role === "staff" || role === "employee") return "Staff";
  return String(role || "Staff").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
