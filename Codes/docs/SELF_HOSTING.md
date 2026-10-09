# Self-hosting NemoTwins

Live demo: **https://nemotwins.koushikdeb.com**: "Start a private demo" (one click, a fresh private
session), or the shared jury login `TestUser` / `TestUser11`.

```
browser ──HTTPS (Let's Encrypt via Caddy)──▶ Caddy
                                              ├─ /            → static React build  (/home/Debz/Host/nemotwins/web)
                                              └─ /api/*       → uvicorn 127.0.0.1:8150 (FastAPI, 1 worker)
FastAPI ──HTTPS──▶ Nebius Token Factory (Nemotron 3 Super / Nano, Gemma 3 vision) · Tavily search (topic queries)
        ──local──▶ PostgreSQL 16 (database nemotwins_prod)
```

## Install / update

```bash
cd Codes
deploy/selfhost/install.sh                 # backend + artefacts + reports -> $TARGET/backend, web build -> $TARGET/web
$TARGET/run.sh                             # (re)start the API on 127.0.0.1:8150 and wait for /api/health
```

`TARGET` defaults to `/home/Debz/Host/nemotwins`. The first install creates `$TARGET/.env` from
`deploy/selfhost/env.example` (chmod 600): fill in `TOKENFACTORY_2009_API_KEY`, `TAVILY_API_KEY`
(optional), a random `JWT_SECRET` and `DATABASE_URL`. Secrets never enter the repository or the web build.

Python packages come from one interpreter (`pip install -r backend/requirements.lock`); `run.sh` uses
`python3.12` with `PYTHONPATH` pinned to the installed copy.

## Web server

Append `deploy/selfhost/Caddyfile.snippet` to the Caddyfile, then:

```bash
caddy validate --config <Caddyfile> --adapter caddyfile
caddy reload   --config <Caddyfile> --adapter caddyfile
```

The block sets HSTS and security headers, caches fingerprinted `/assets/*`, limits uploads to 15 MB,
proxies `/api/*` to port 8150 and serves the SPA with an `index.html` fallback. DNS: an A record
`nemotwins` → the server's public IP; Caddy obtains the certificate automatically.

## Keeping it running

Cron (same pattern as the other apps on the host):

```
@reboot sleep 55 && /home/Debz/Host/nemotwins/autostart.sh  # NemoTwins
*/5 * * * * /home/Debz/Host/nemotwins/autostart.sh  # NemoTwins watchdog
```

`autostart.sh` starts the API only when nothing listens on port 8150. Logs: `$TARGET/logs/api.log`
(no conversation text: the audit log stores lengths and hashes, and the guardrails library's message
logging is capped), Caddy access log `/var/log/caddy/nemotwins.log`.

## Checks

```bash
curl -s https://nemotwins.koushikdeb.com/api/health      # process + configured model
curl -s https://nemotwins.koushikdeb.com/api/ready       # database reachable and twin warm
deploy/nebius/smoke.sh https://nemotwins.koushikdeb.com  # health, capabilities, SPA, login, one Spanish chat turn
```

## Public-demo bounds

Login required for every model-backed endpoint. "Start a private demo" creates a throw-away user per
visitor (`POST /api/auth/demo`), so judges never see each other's readings, meals or replay clocks; at most
`RATE_DEMO_SESSION_PER_HOUR=6` per client address and `DEMO_SESSIONS_PER_DAY=500`, and demo users older than
`DEMO_SESSION_TTL_HOURS=24` are deleted with their data. Per-user rate limits (`RATE_CHAT_PER_MIN=20`), at most
4 concurrent model requests, ≤ 6 tool steps per turn, a local daily token quota, 15 MB upload limit. The
developer integration page is off for the public account (`ADMIN_USERS` empty).

## Rollback

`$TARGET/stop.sh`, re-run `install.sh` from the previous git revision, `run.sh`. Remove the Caddy block
between `# >>> nemotwins` and `# <<< nemotwins` and reload Caddy to take the site offline.
