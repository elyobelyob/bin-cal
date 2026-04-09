/**
 * Cloudflare Worker — bin-cal form proxy
 *
 * Responsibilities:
 *  1. CORS headers so GitHub Pages can POST to this worker
 *  2. Rate-limit to 1 submission per IP per hour (via KV)
 *  3. Honeypot field check
 *  4. Forward workflow_dispatch to GitHub Actions API (with secret token)
 *
 * Environment variables (set in Cloudflare dashboard → Worker → Settings → Variables):
 *   GITHUB_TOKEN   — PAT with repo + workflow scope (keep as secret)
 *   GITHUB_OWNER   — your GitHub username
 *   GITHUB_REPO    — repository name (e.g. bin-cal)
 *
 * KV namespace binding (set in wrangler.toml or dashboard):
 *   RATE_LIMIT_KV  — bound KV namespace for IP rate limiting
 */

const RATE_LIMIT_SECONDS = 60; // 1 minute

const ALLOWED_ORIGIN_PATTERN = /^https:\/\/[a-z0-9-]+\.github\.io$/;

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    // CORS preflight
    if (request.method === "OPTIONS") {
      return corsResponse(null, 204, origin);
    }

    if (request.method !== "POST") {
      return corsResponse(JSON.stringify({ error: "Method not allowed" }), 405, origin);
    }

    // Validate origin
    if (!ALLOWED_ORIGIN_PATTERN.test(origin)) {
      return corsResponse(JSON.stringify({ error: "Forbidden" }), 403, origin);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return corsResponse(JSON.stringify({ error: "Invalid JSON" }), 400, origin);
    }

    // Honeypot check — a hidden field "website" must be empty
    if (body.website) {
      // Bot filled the honeypot — silently accept but do nothing
      return corsResponse(JSON.stringify({ ok: true }), 200, origin);
    }

    // Rate limiting by IP
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const rateLimitKey = `rl:${ip}`;

    if (env.RATE_LIMIT_KV) {
      const existing = await env.RATE_LIMIT_KV.get(rateLimitKey);
      if (existing) {
        return corsResponse(
          JSON.stringify({ error: "Too many requests. Please wait a minute before submitting again." }),
          429,
          origin
        );
      }
      await env.RATE_LIMIT_KV.put(rateLimitKey, "1", { expirationTtl: RATE_LIMIT_SECONDS });
    }

    // Validate required fields
    const { hash, council_id, council_title, args_json } = body;
    if (!hash || !council_id || !council_title || !args_json) {
      return corsResponse(JSON.stringify({ error: "Missing required fields" }), 400, origin);
    }

    // Validate hash format (8 hex chars)
    if (!/^[0-9a-f]{8}$/.test(hash)) {
      return corsResponse(JSON.stringify({ error: "Invalid hash" }), 400, origin);
    }

    // Validate council_id (module name: lowercase letters, digits, underscores only)
    if (!/^[a-z0-9_]{1,64}$/.test(council_id)) {
      return corsResponse(JSON.stringify({ error: "Invalid council_id" }), 400, origin);
    }

    // Validate council_title (printable text, reasonable length)
    if (typeof council_title !== "string" || council_title.length < 1 || council_title.length > 128) {
      return corsResponse(JSON.stringify({ error: "Invalid council_title" }), 400, origin);
    }

    // Validate args_json is valid JSON object with string/boolean values only
    let parsedArgs;
    try {
      parsedArgs = JSON.parse(args_json);
      if (typeof parsedArgs !== "object" || Array.isArray(parsedArgs) || parsedArgs === null) {
        throw new Error("args must be a JSON object");
      }
      for (const [k, v] of Object.entries(parsedArgs)) {
        if (!/^[a-z_]{1,32}$/.test(k)) throw new Error(`Invalid arg key: ${k}`);
        if (typeof v !== "string" && typeof v !== "boolean") throw new Error(`Invalid arg value type for ${k}`);
        if (typeof v === "string" && v.length > 256) throw new Error(`Arg value too long: ${k}`);
      }
    } catch (e) {
      return corsResponse(JSON.stringify({ error: `Invalid args_json: ${e.message}` }), 400, origin);
    }

    // Trigger GitHub Actions workflow_dispatch
    const ghUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/first-request.yml/dispatches`;

    const ghResponse = await fetch(ghUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bin-cal-worker",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          hash,
          council_id,
          council_title,
          args_json,
        },
      }),
    });

    if (ghResponse.status === 204) {
      return corsResponse(JSON.stringify({ ok: true }), 200, origin);
    }

    const errText = await ghResponse.text();
    console.error("GitHub API error:", ghResponse.status, errText);
    return corsResponse(
      JSON.stringify({ error: "Failed to trigger workflow. Please try again." }),
      502,
      origin
    );
  },
};

function corsResponse(body, status, origin) {
  const headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
  return new Response(body, { status, headers });
}
