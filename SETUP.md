# UK Bin Cal — Setup Guide

## 1. Fork / create the repo

Create a public GitHub repo named `bin-cal` (or any name — it becomes part of the calendar URL).

Enable **GitHub Pages** from repo Settings → Pages → Source: `main` branch, `/ (root)`.

## 2. Update CONFIG in app.js

Edit `app.js` and set:

```js
const CONFIG = {
  WORKER_URL:   "https://bin-cal-proxy.YOUR-SUBDOMAIN.workers.dev",
  GITHUB_OWNER: "your-github-username",
  GITHUB_REPO:  "bin-cal",
};
```

## 3. Create a GitHub Personal Access Token

Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens.

Create a token with:
- **Repository access**: your `bin-cal` repo only
- **Permissions**: `Actions: Read and Write`, `Contents: Read and Write`

Copy the token — you'll use it in step 4.

## 4. Deploy the Cloudflare Worker

Install Wrangler if you don't have it:
```bash
npm install -g wrangler
wrangler login
```

Create the KV namespace:
```bash
wrangler kv:namespace create RATE_LIMIT_KV
```

Copy the namespace ID it prints and update `worker/wrangler.toml`.

Set secrets:
```bash
wrangler secret put GITHUB_TOKEN   # paste your PAT
wrangler secret put GITHUB_OWNER   # your GitHub username
wrangler secret put GITHUB_REPO    # bin-cal
```

Deploy:
```bash
cd worker
wrangler deploy
```

Copy the Worker URL (e.g. `https://bin-cal-proxy.yourname.workers.dev`) and set it as `WORKER_URL` in `app.js`.

## 5. Push to GitHub

```bash
git init
git remote add origin https://github.com/YOUR_USERNAME/bin-cal.git
git add .
git commit -m "Initial commit"
git push -u origin main
```

## 6. Test it

Visit `https://YOUR_USERNAME.github.io/bin-cal/` and submit a test address.

The first request triggers the `first-request.yml` workflow. Watch it complete in the Actions tab
(~60–90 seconds), then check the waiting page auto-advances to the success page.

## Updating councils.json

Run locally whenever you want to refresh the council list:
```bash
git clone --depth=1 https://github.com/mampfes/hacs_waste_collection_schedule.git /tmp/wcs
python3 scripts/generate_councils.py
```

Or let the weekly `update-package.yml` Action handle it automatically.

## Calendar URLs

Calendars are served at:
```
https://YOUR_USERNAME.github.io/bin-cal/calendars/{8-char-hash}.ics
```

The hash is a deterministic SHA-256 of `council_id|POSTCODE|door_num[|uprn]`,
so the same address always produces the same URL regardless of who submits it.
