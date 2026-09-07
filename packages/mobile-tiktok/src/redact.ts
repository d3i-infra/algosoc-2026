export const EMAIL_PATTERN = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function redactEmails(text: string): string {
  return text.replace(EMAIL_PATTERN, "[email]");
}

export function redactUsername(text: string, username: string): string {
  if (!username) return text;
  const re = new RegExp("(^|[^\\p{L}\\p{N}_])(" + escapeRegExp(username) + ")(?![\\p{L}\\p{N}_])", "giu");
  return text.replace(re, "$1[user]");
}

export function redactText(text: string, username: string | null): string {
  const t = redactEmails(text);
  return username ? redactUsername(t, username) : t;
}
