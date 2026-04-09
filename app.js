/**
 * Shared JS for UK Bin Cal
 *
 * CONFIG — update these before deploying:
 *   WORKER_URL:   Your Cloudflare Worker URL
 *   GITHUB_OWNER: Your GitHub username
 *   GITHUB_REPO:  Repository name
 */
const CONFIG = {
  WORKER_URL:   "https://bin-cal-proxy.nick-c79.workers.dev",
  GITHUB_OWNER: "elyobelyob",
  GITHUB_REPO:  "bin-cal",
};

// ── Hash generation ────────────────────────────────────────────────────────

/**
 * Compute an 8-char hex hash from the normalized address string.
 * Hash input: "council_id|postcode_normalised|door_num_normalised[|uprn]"
 */
async function computeHash(councilId, args) {
  const postcode  = (args.postcode  || "").toUpperCase().replace(/\s+/g, "");
  const doorNum   = String(args.door_num || args.house_number || args.house_no || args.number || "")
                      .trim().toLowerCase();
  const uprn      = String(args.uprn || "").trim();

  const parts = [councilId, postcode, doorNum];
  if (uprn) parts.push(uprn);

  const raw = parts.join("|");
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(raw));
  const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
  return hex.slice(0, 8);
}

// ── ICS URL ────────────────────────────────────────────────────────────────

function icsUrl(hash) {
  return `https://${CONFIG.GITHUB_OWNER}.github.io/${CONFIG.GITHUB_REPO}/calendars/${hash}.ics`;
}

// ── Poll for ICS ───────────────────────────────────────────────────────────

/**
 * Poll the expected ICS URL every 5 seconds until it returns 200.
 * Calls onReady(url) when found, onTimeout() after maxSeconds.
 */
function pollForIcs(hash, onReady, onTimeout, maxSeconds = 300) {
  const url = icsUrl(hash);
  const deadline = Date.now() + maxSeconds * 1000;

  const interval = setInterval(async () => {
    try {
      const res = await fetch(url, { method: "HEAD", cache: "no-store" });
      if (res.ok) {
        clearInterval(interval);
        onReady(url);
      }
    } catch { /* network error — keep polling */ }

    if (Date.now() > deadline) {
      clearInterval(interval);
      onTimeout();
    }
  }, 5000);
}
