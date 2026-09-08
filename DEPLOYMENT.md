# Deployment

VidLingo runs in two places at once, on deliberately different stacks:

| | **Render** | **AWS Lightsail** |
|---|---|---|
| URL | `vidlingo.onrender.com` | `vidlingo.dev` |
| Model | PaaS — hand it a `Dockerfile`, it builds and runs the container | VPS — a bare Ubuntu machine; everything below the app is mine |
| Runtime | the image built from `Dockerfile` | a Python venv supervised by systemd |
| TLS | issued and renewed by the platform | nginx + certbot (Let's Encrypt) |
| Web server | none — the container is reached directly | nginx as reverse proxy |
| Deploy | automatic on push to `main` | manual (see §12) |
| Cost | free tier | USD $5/mo |
| Database | the same external Neon Postgres | the same external Neon Postgres |

Neither is a fallback for the other. **Render proves the image is portable;
Lightsail proves the thing can be run without a platform doing it.** The
interesting engineering is in the second column, so that is what this document
is mostly about.

---

## 1. What actually runs on the VPS

```
                 Cloudflare DNS (A record, proxy off)
                              |
                              v
                    13.237.105.207   <- Lightsail static IP
        +-------------------------------------------+
        |  Lightsail firewall: 22, 80, 443 only     |
        +---------------------+---------------------+
                              v
                    nginx  :80 -> 301 -> :443
                       |  TLS terminates here
                       |  proxy_pass
                       v
                    uvicorn 127.0.0.1:8000     <- systemd unit `vidlingo`
                       |  FastAPI serves /api and web/dist
                       v
                    Neon Postgres (external, TLS)
```

Two properties of this shape are worth naming, because both were choices:

**uvicorn binds `127.0.0.1`, not `0.0.0.0`.** The application is unreachable
from the internet by construction — the only way in is through nginx. If the
firewall were ever misconfigured, port 8000 still would not answer.

**nginx serves no files.** It is a pure reverse proxy. The built client is
served by FastAPI out of `STATIC_DIR`, exactly as it is inside the Docker image
on Render. See §8, since this is the opposite of the conventional
`nginx -> dist/` arrangement.

---

## 2. The instance

AWS Lightsail, region **Sydney (`ap-southeast-2a`)** — chosen for latency to
Canberra, and because the audience for this deployment is in Australia.

Lightsail rather than plain EC2 **for cost predictability, not for simplicity.**
EC2 bills egress per gigabyte, which is the classic way a personal project
produces a surprise bill. A Lightsail plan bundles 1–2 TB of transfer into a
fixed monthly price, so the worst case is knowable in advance. The tradeoff is
real: no VPC-level control, no autoscaling, no load balancer without paying for
one. For a single-process app, that is not a cost worth paying.

Plan: **$5/mo, 512 MB RAM, 2 vCPU, dual-stack.**

**Dual-stack, not the cheaper IPv6-only option.** IPv6-only would have saved a
dollar and broken CI: GitHub-hosted Actions runners have no IPv6 connectivity,
so the keepalive workflow — and any future deploy job — could not reach the box
at all. That failure would have been silent and baffling.

---

## 3. Networking

**Static IP.** An instance's default public IP is dynamic and changes when the
instance is stopped and started, so a DNS record pointing at it would silently
rot. Lightsail static IPs are free *while attached* to a running instance, and
billed only if left dangling.

**Firewall.** Lightsail has its own edge firewall, configured in the console:

| Port | Why |
|---|---|
| 22 | SSH |
| 80 | HTTP → HTTPS redirect **and** Let's Encrypt's HTTP-01 renewal challenge |
| 443 | HTTPS |

Port 80 looks redundant once everything redirects to 443. **It is not — closing
it breaks certificate renewal about 60 days later**, which is exactly the kind of
delayed failure that is hard to trace back to its cause.

There is deliberately **no `ufw` on the host**. Two firewalls enforcing one
policy is two places to forget, and the failure mode — locking yourself out of
SSH — is worse than the risk being mitigated. One firewall, at the edge.

---

## 4. Getting on the box

```bash
ssh -i ~/.ssh/id_ed25519_lightsail ubuntu@13.237.105.207
```

The keypair was generated locally with `ssh-keygen -t ed25519` and only the
**public** half uploaded to Lightsail. The private key never leaves the laptop —
which is the point, and is not true of Lightsail's "create a key for me" flow,
where the private key is generated on their side and downloaded.

ed25519 rather than RSA: shorter, faster, and no key-size decision to get wrong.

---

## 5. First-boot setup

### Swap — the non-obvious prerequisite

```bash
sudo fallocate -l 2G /swapfile      # allocate a 2 GB file
sudo chmod 600 /swapfile            # only root may read it: it will hold process memory
sudo mkswap /swapfile               # write swap-format headers into it
sudo swapon /swapfile               # activate it now
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # ...and on every future boot
```

512 MB of RAM is not enough to `pip install` a dependency tree of this size.
Without swap those commands do not fail with a useful message — **the kernel's
OOM killer terminates the process**, and what you see is a build that dies with
no explanation at all.

The `/etc/fstab` line is the part that gets forgotten. Without it the swap file
exists but is inactive after the next reboot, and the problem returns weeks
later looking like something new.

### Application user and code

```bash
sudo apt update && sudo apt install -y python3-venv nginx git
git clone https://github.com/shaw4dev/vidlingo.git ~/vidlingo
cd ~/vidlingo/backend
python3 -m venv .venv
./.venv/bin/pip install ".[llm]"
```

`python3 -m venv .venv` creates an isolated interpreter environment, so the
app's dependencies never mix with the ones Ubuntu itself needs. On a current
Ubuntu a system-wide `pip install` is refused outright for exactly that reason.

`.[llm]` installs the project from `backend/pyproject.toml` **plus** the `llm`
extra, which pulls in the `anthropic` client used for the word card's Chinese
gloss.

### The client bundle

`web/dist` is built **on the laptop** and copied up:

```bash
cd web && npm run build
scp -i ~/.ssh/id_ed25519_lightsail -r dist/* \
    ubuntu@13.237.105.207:~/vidlingo/backend/static/
```

Building on the server would need Node, several hundred MB of `node_modules`,
and more RAM than the box has. The build is deterministic and its output is
static, so there is no reason for it to happen there.

---

## 6. Configuration and secrets

`/etc/vidlingo.env`, mode `600`, owned by `ubuntu`:

```ini
DATABASE_URL=postgresql://...      # external Neon Postgres
SECRET_KEY=...                     # JWT signing
STATIC_DIR=/home/ubuntu/vidlingo/backend/static
YOUTUBE_API_KEY=...
ANTHROPIC_API_KEY=...
ANTHROPIC_BASE_URL=...
TRANSLATE_MODEL=...
```

**It lives in `/etc`, outside the git working tree, on purpose.** A secrets file
inside `~/vidlingo` is one `git add -A` away from being committed. Putting it
where git cannot reach makes that mistake impossible rather than merely
discouraged.

Mode `600` is owner-read-only: no other account on the machine can read it.

---

## 7. systemd — the process supervisor

`/etc/systemd/system/vidlingo.service`:

```ini
[Unit]
Description=VidLingo API
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=ubuntu
WorkingDirectory=/home/ubuntu/vidlingo/backend
EnvironmentFile=/etc/vidlingo.env
ExecStart=/home/ubuntu/vidlingo/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Line by line, because every one of these is load-bearing:

| Directive | What it does |
|---|---|
| `After=` / `Wants=network-online.target` | Do not start until the network is actually up. `After` orders it; `Wants` pulls the target in. Without both, a reboot can start the app before it can resolve the database host. |
| `Type=exec` | The process systemd launches *is* the service — it does not fork into the background. |
| `User=ubuntu` | Runs unprivileged. Nothing here needs root. |
| `EnvironmentFile=` | Loads the secrets. They are never in the unit file, which is world-readable. |
| `ExecStart=` | Absolute path into the venv's uvicorn — systemd has no shell and no `PATH` worth relying on. |
| `Restart=always` + `RestartSec=3` | Crash, OOM kill or unhandled exception → restarted three seconds later. This is the entire high-availability story, and on one machine it is most of the value. |
| `NoNewPrivileges=true` | The process can never gain privileges, even through a setuid binary. |
| `PrivateTmp=true` | Gets its own `/tmp`, invisible to other processes. |
| `WantedBy=multi-user.target` | What `enable` hooks into — this is what makes it start on boot. |

```bash
sudo systemctl daemon-reload           # re-read unit files after any edit
sudo systemctl enable --now vidlingo   # start it now AND on every boot
journalctl -u vidlingo -f              # follow its logs
```

`enable` and `start` are different things, and forgetting `enable` is the
classic mistake: everything works until the first reboot.

---

## 8. nginx — reverse proxy, not file server

`/etc/nginx/sites-available/vidlingo`, before certbot rewrote it:

```nginx
server {
    listen 80;
    server_name vidlingo.dev www.vidlingo.dev;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

The four `proxy_set_header` lines exist because, from uvicorn's point of view,
every request now arrives from `127.0.0.1` over plain HTTP. Without them the app
cannot know the real client IP, the real hostname, or that the user is on HTTPS
— which matters the moment anything generates an absolute URL or a `Secure`
cookie.

`proxy_read_timeout 120s` covers the slow path: a word lookup that misses the
cache can trigger a dictionary fetch plus an LLM call.

```bash
sudo ln -s /etc/nginx/sites-available/vidlingo /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default   # otherwise it wins on port 80
sudo nginx -t                              # validate the config BEFORE applying it
sudo systemctl reload nginx                # reload, not restart: no dropped connections
```

`nginx -t` before every reload is not optional discipline. A syntax error in a
`restart` takes the site down; a failed `reload` leaves the old config serving.

### Why nginx serves no files

The conventional layout is nginx serving `dist/` directly and proxying only
`/api`. This app does the opposite: FastAPI serves the built client itself
(`backend/app/main.py`, `_mount_client`).

That is **reverse-derived from Render's free tier**, which runs one service. One
service means one origin for both halves, which means the browser never makes a
cross-origin request and **CORS never enters the picture at all** (ADR-002).
That is a real simplification, not a workaround.

The cost is equally real and worth stating plainly: about 30 lines of
hand-written Python to do the SPA deep-link fallback that nginx does in one
`try_files` line, and no easy way to put a CDN in front of the assets.

The VPS keeps the same arrangement **specifically so the two deployments do not
diverge.** Two environments serving files by different mechanisms produce bugs
that reproduce in exactly one of them, and never locally.

---

## 9. DNS

`vidlingo.dev`, registered through Cloudflare:

| Type | Name | Value | Proxy |
|---|---|---|---|
| A | `@` | `13.237.105.207` | DNS only |
| A | `www` | `13.237.105.207` | DNS only |

DNS is the phone book: it maps the name a human types to the address a packet
needs. Nothing more — it plays no part in the request itself.

**Proxy deliberately off (grey cloud).** Cloudflare's orange-cloud proxy would
terminate TLS at their edge, which means certbot's HTTP-01 challenge cannot
reach the origin and the certificate stops renewing. Running my own TLS is the
point of this deployment, so the proxy stays off.

`.dev` is worth knowing about: **the whole TLD is on the browsers' HSTS preload
list.** Chrome, Firefox, Safari and Edge refuse to make a plaintext HTTP request
to any `.dev` name, whatever the server says. HTTPS was mandatory here before a
line of nginx was written.

---

## 10. TLS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d vidlingo.dev -d www.vidlingo.dev
```

What certbot does: proves to Let's Encrypt that this machine controls the
domain, then installs the certificate it gets back. The proof is the **HTTP-01
challenge** — the CA names a random token, certbot serves it at
`http://vidlingo.dev/.well-known/acme-challenge/<token>` over port 80, and the
CA fetches it. Only whoever the DNS actually points at can answer, which is
exactly the thing being proven.

The `--nginx` plugin then edits the config in place: adds the `listen 443 ssl`
block, wires in the certificate paths, and converts the port-80 server into a
301 redirect.

Let's Encrypt certificates last **90 days** — short on purpose, to force
automation. Installing certbot creates a systemd timer that runs twice a day and
renews anything within 30 days of expiry:

```bash
systemctl list-timers | grep certbot   # confirm the timer exists
sudo certbot renew --dry-run           # rehearse a real renewal
```

The dry run is the step that matters. It exercises the entire challenge path
without consuming rate limit, so a broken renewal surfaces now rather than in
two months.

---

## 11. Security response headers

TLS protects data in transit. It says nothing about what the browser is allowed
to do once the page has loaded. That is what these are for:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options    "nosniff" always;
add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
add_header X-Frame-Options           "DENY" always;

add_header Content-Security-Policy
    "default-src 'self'; img-src 'self' data: https://i.ytimg.com; frame-src https://www.youtube.com https://www.youtube-nocookie.com; script-src 'self' https://www.youtube.com; style-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:; base-uri 'self'; form-action 'self'" always;
```

| Header | What it buys |
|---|---|
| **HSTS** | Closes the window where the *first* request goes out in plaintext and can be stripped. Largely redundant here because `.dev` is TLD-preloaded — but free. |
| **nosniff** | Stops the browser second-guessing `Content-Type` and executing a file the server labelled as something else. |
| **Referrer-Policy** | Relevant specifically because the page embeds a YouTube iframe: without it the full URL of every page is handed to Google. |
| **X-Frame-Options** | Clickjacking — nobody else may put this site in a frame. |
| **CSP** | The second line of defence: if an XSS did land, injected script has no origin it is permitted to load from. |

Two things learned while building the CSP:

**`script-src 'self'` alone breaks the app.** `web/src/lib/youtube.ts:64`
injects `https://www.youtube.com/iframe_api` into the parent document, so the
Reader page white-screens unless that origin is whitelisted. Found by grepping
the source rather than trusting a console that showed nothing — the policy was
in `Report-Only` mode at the time, which is precisely what that mode is for.

**`add_header` does not inherit in nginx.** A single `add_header` inside a
`location` block silently discards *every* server-level header. The `always`
flag is separately required, or none of them apply to error responses.

**And a third: `nginx -t` does not tell you what is running.** The headers were
written into the config and then appeared to do nothing — no HSTS, no CSP, no
`nosniff` in the response, while `nginx -t` reported the config valid. The
config *file* was valid; the running process had never read it. Comparing two
timestamps found it:

```
nginx worker started:  Sep  8 06:09:06     <- last reload
config file mtime:     Sep  8 06:45:42     <- the edit
```

The edit was 36 minutes newer than the process using it. `nginx -t` validates
what is on disk; only `systemctl reload nginx` makes it live. **A config change
is not applied until the workers restart** — which is what the worker start time
is for.

Verified in a browser after enforcing, not just with `curl`: a CSP violation is
only observable where the policy is enforced. Library thumbnails
(`i.ytimg.com`), the Reader's player (`iframe_api` script + the iframe itself),
and the word card all work, with an empty console.

---

## 12. Shipping an update

```bash
# laptop
cd web && npm run build
scp -i ~/.ssh/id_ed25519_lightsail -r dist/* ubuntu@13.237.105.207:~/vidlingo/backend/static/

# box
cd ~/vidlingo && git pull
./backend/.venv/bin/pip install -e backend                        # only if dependencies changed
cd backend && ./.venv/bin/alembic upgrade head                    # only if migrations changed
sudo systemctl restart vidlingo
```

This is manual, and that is the honest state of it. The obvious next step is a
GitHub Actions job that builds `web/dist` and rsyncs it — the runner already
builds the client for CI, so the artifact exists.

Render, by contrast, redeploys on push to `main` with no action at all. **That
contrast is the whole argument for PaaS**, and running both makes it concrete
rather than theoretical.

---

## 13. Problems hit, and what they turned out to be

**SSH connected to nothing — `connect to host 13.237.105.207 port 22:
Connection timed out`.** The distinction that matters: *timed out* means packets
are being dropped somewhere on the path; *connection refused* would mean they
arrived and sshd said no. So the server was almost certainly healthy. It was the
mobile hotspot — the carrier blocks outbound TCP 22. Worked around at the time
with Lightsail's browser SSH, which tunnels over 443, and confirmed later when
the identical command succeeded on WiFi.

**Intermittent 500s from every database endpoint, after quiet periods.** Neon
suspends its compute when idle and closes every connection with it. SQLAlchemy's
pool has no way to notice, so it hands the next request a dead socket. Fixed
with `pool_pre_ping=True` and `pool_recycle=300` in
`backend/app/db/session.py`. **Invisible locally and in CI, because both run
SQLite** — which has no server to lose. A bug whose shape is set by the
environment rather than by the code.

**The $3.50 Lightsail plan no longer exists.** Planning assumed a price tier
that had been retired; the real floor is $5. Half a year is about A$46, not the
A$32 budgeted. Recorded as the ordinary case of documentation ageing out.

---

## 14. The corpus

The library does not travel with the code. Re-running ingest against a fresh
database would re-fetch every caption, and YouTube rate-limits that endpoint by
IP. `LessonPackage` is already the interchange format, so the corpus moves as
validated JSON through the same ingestion path the pipeline uses:

```bash
cd backend
python -m app.content.packages export --out ../content/packages
DATABASE_URL=<target> python -m app.content.packages load ../content/packages
```

The round trip is exact and tested — same rows, same IDs. Clips are regenerated
rather than exported, so a re-import picks up the current windowing strategy.

Both deployments point at the same Neon database, so this ran once.

---

## 15. Open items

- [ ] Confirm domain auto-renewal is enabled in Cloudflare — an expired domain is
      the one failure here that arrives with no warning and no alert
- [ ] Automate the client build and upload instead of `scp` by hand
- [ ] Rotate the Neon password and update it in both Render's dashboard and
      `/etc/vidlingo.env`
