const ACRONYMS = new Set(["AI", "API", "CRM", "CSV", "GST", "ID", "OTP", "UI", "URL", "UX"]);

/**
 * Converts database-style labels to readable sentence case without changing
 * intentional casing in product names and acronyms such as WhatsApp or CRM.
 */
export function sentenceCase(value, fallback = "") {
  if (value === null || value === undefined || value === "") return fallback;
  const text = String(value).replaceAll("_", " ").trim();
  if (!text) return fallback;

  return text.split(/\s+/).map((word, index) => {
    const letters = word.replace(/[^A-Za-z0-9]/g, "");
    const isAcronym = ACRONYMS.has(letters.toLocaleUpperCase());
    const hasIntentionalInnerCapital = /[a-z][A-Z]/.test(letters);
    if (isAcronym) return word.replace(letters, letters.toLocaleUpperCase());
    if (hasIntentionalInnerCapital) return word;
    const lower = word.toLocaleLowerCase();
    return index === 0 ? lower.charAt(0).toLocaleUpperCase() + lower.slice(1) : lower;
  }).join(" ");
}
