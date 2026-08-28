# CareerCompass — No-Card, $0-Cloud Deployment Plan

**Revised:** 2026-08-27
**Target:** the full stack (Spring Boot API + FastAPI AI service + React SPA + MySQL + PostgreSQL
+ OpenRouter) running publicly at `https://careercompass.duckdns.org` without supplying a credit
card to a cloud-compute or LLM provider.

> **What “$0” means here:** the existing Linux computer and internet connection host the system;
> DuckDNS, Let's Encrypt and OpenRouter's free-model router have no usage charge within their
> limits. Electricity, internet service and hardware are still real costs. This is a public demo
> deployment, not a free highly-available production platform.

This replaces the earlier draft. That version assumed a spread of managed free tiers and listed
two large refactors as blockers. Both assumptions were wrong for this system, and the corrections
save real work:

| Earlier plan said | Actually |
|---|---|
| Refactor `FileStorageService` to S3/R2 before deploying | **Not needed.** Uploads only break on ephemeral or multi-instance hosting. On one host with a Docker volume, local disk is correct and durable. Deferred to the scaling section. |
| Point the AI service at Groq/Gemini instead of Ollama | **No longer needed.** `llm.py` now supports OpenRouter directly over REST. `openrouter/free` needs no purchased credits, but is limited and best suited to a demo. |
| Managed MySQL (Aiven) + managed Postgres (Neon) | **Not needed.** Both databases run locally, avoid more accounts/cards, and remain under one backup boundary. |
| Frontend on Vercel | **Works, but same-origin is better.** Serving the SPA from the same host as the API removes CORS from the picture entirely. |

---

## 1. Architecture

The existing Linux computer runs every container. The home router forwards TCP 80/443 to that
computer, DuckDNS tracks the changing public IP, and Caddy terminates TLS. OpenRouter supplies
limited hosted inference so the host does not need to run a local language model.

```
                    Internet
                       │  443/80
              ┌────────▼────────┐
              │      Caddy      │  automatic Let's Encrypt TLS
              │  (only public   │
              │    listener)    │
              └───┬─────────┬───┘
      /api/*      │         │   everything else
  /actuator/health│         │
      /v3/api-docs│         │
                  ▼         ▼
          ┌──────────┐   ┌──────────┐
          │ backend  │   │ frontend │  nginx serving the built SPA
          │ :8080    │   │ :80      │
          └────┬─────┘   └──────────┘
               │ private Docker network only
      ┌────────┴─────────┐
      ▼                  ▼
 ┌────────┐        ┌──────────┐ ── outbound HTTPS ──► OpenRouter free router
 │ mysql  │        │ai-service│
 │ :3306  │        │  :8000   │
 └────────┘        └────┬─────┘
                       ▼
                  ┌──────────┐
                  │ postgres │
                  │  :5432   │
                  └──────────┘
```

**Nothing except Caddy publishes a port.** The AI service and both databases are reachable only on
the private Docker network. That matters: the AI service holds parsed transcripts and quiz answer
keys, and its only authentication is a shared bearer token. The AI service sends quiz prompts and
ambiguous skill phrases to OpenRouter; it does not send database credentials or whole database
rows. Requests deny provider data collection by default and fail if no compatible route remains.

### Why one host

Because the user does not want the card verification required by Oracle and Google. Hosting on the
existing computer removes that signup requirement. The trade is router configuration, dependence
on home power/internet, no availability guarantee, and backups you own. Sections 8, 11 and 12
cover those limits.

---

## 2. Cost

| Component | Provider | Free allowance | Cost |
|---|---|---|---|
| Compute | existing Linux computer | already owned; runs continuously | $0 cloud bill |
| DNS + subdomain | DuckDNS | free dynamic-DNS hostname | $0 |
| TLS certificates | Let's Encrypt via Caddy | automatically issued and renewed | $0 |
| MySQL 8.4 | self-hosted on the Linux computer | — | $0 |
| PostgreSQL 16 | self-hosted on the Linux computer | — | $0 |
| LLM inference | OpenRouter `openrouter/free` | 50 free-model requests/day without purchased credits | $0 within quota |
| Container registry | none (build on the Linux computer) | — | $0 |
| **Total** | | | **$0 / month** |

The OpenRouter figures were checked on 2026-08-27 against its
[free-router documentation](https://openrouter.ai/docs/guides/routing/routers/free) and
[FAQ](https://openrouter.ai/docs/faq). With no purchased credits the documented shared limit is 50
free-model requests per day. Availability, latency and the selected model can vary. Do not add
credits or enable automatic top-up if the hard $0 boundary matters.

### Resource budget on the host

| Service | RAM | Notes |
|---|---|---|
| MySQL 8.4 | ~0.75 GB | 384 MB InnoDB buffer pool plus server overhead |
| PostgreSQL 16 | ~0.5 GB | |
| Backend (JVM) | ~1.8 GB | heap pinned at 1.5 GB |
| AI service | ~2 GB | taxonomy + course index held in memory |
| Caddy + nginx | ~0.1 GB | |
| Docker/OS/build headroom | ~3–5 GB | swap absorbs temporary build spikes, not steady load |
| **Steady application use** | **~5 GB** | 12 GB RAM recommended; 8 GB is a tight minimum |

Images measured in this tree: backend 536 MB and AI service 735 MB. The production frontend should
be far smaller than today's 644 MB development image because it contains only nginx and `dist/`.
Allow at least 30 GB of free disk initially and monitor it. Phase 9 adds log limits and Phase 8
prevents local backups growing forever.

---

## 3. The blockers — what must exist before you can deploy

These are the actual gaps. Everything in Phases 3–5 is written out in full, so this section is a
checklist, not research.

| # | Blocker | Why it stops a deploy | Fixed in |
|---|---|---|---|
| B1 | `frontend/Dockerfile` runs `npm run dev` | It is explicitly a dev image. Vite's dev server is not a production server: no asset hashing strategy for caching, no compression, single-threaded, and it exposes source. | Phase 3.1 |
| B2 | No `docker-compose.prod.yml` | The only compose file is the dev stack: H2, seeded demo accounts, published ports on every service, `use-mock` togglable. | Phase 3.3 |
| B3 | `ai-service` uses `network_mode: host` and the backend reaches it at hardcoded `172.18.0.1:8000` | That IP is assigned by Docker and varies by host and network creation order. It will not resolve on a fresh host. | Phase 3.3 (service DNS) |
| B4 | No TLS, no domain | JWTs over plain HTTP are readable in transit. | Phase 2 + 3.4 |
| B5 | Local `qwen3:8b` is too resource-heavy for ordinary home hosting | `llm.py` now has a tested OpenRouter provider and free-router mode. | Phase 4 + 6 |
| B8 | Home connection may use CGNAT or block inbound 80/443 | DuckDNS alone does not open the router. Public IPv4, NAT forwarding and firewall checks are mandatory. | Phase 1 + 2 |
| B6 | Dev compose publishes Postgres, Adminer, and the AI service | Adminer on a public IP is a database console for anyone who finds it. | Phase 3.3 (nothing but Caddy publishes) |
| B7 | Secrets have dev defaults in `compose.yaml` | `JWT_SECRET` now has **no** fallback in `application.yml`, so the app refuses to start without it — good, but you must supply one. | Phase 4 |

**Already handled in the current tree** (do not redo):

- `JWT_SECRET` is required with a 32-char minimum, validated at startup.
- `CORS_ALLOWED_ORIGINS` is configurable (and unnecessary if you follow this plan — same origin).
- `/actuator/health` exists with liveness/readiness probes; only `health` and `info` are exposed.
- Login rate limiting (10 failures → 15-minute lockout, per IP per actor route).
- Unhandled exceptions are logged.
- Production quiz timeout raised to 90 s.
- OpenRouter provider supports strict JSON Schema, privacy filtering, rate-limit handling and no SDK.
- Flyway owns the backend schema through V6; the AI service has its own checksum-validated runner.

---

## 4. Prerequisites

1. **Linux host** — preferably 4 CPU threads, 12 GB RAM and 30+ GB free disk. It must remain powered
   on and connected whenever the site should be available.
2. **Router administration access** — needed to reserve the host's LAN address and forward TCP
   ports 80 and 443.
3. **Public IPv4 without CGNAT** — Phase 1 shows how to check. DuckDNS cannot bypass CGNAT.
4. **DuckDNS domain** — already created: `careercompass.duckdns.org`.
5. **OpenRouter API key** — create a new key at https://openrouter.ai/settings/keys. No credit
   purchase is needed for `openrouter/free`. Treat every key pasted into chat as exposed and revoke
   it before deployment.

---

## Phase 1 — Prepare the home host and network

### 1.1 Confirm that inbound hosting is possible

Find the public IPv4 seen by the internet:

```bash
curl -4 https://api.ipify.org; echo
```

Open the router's administration page and find its **WAN/Internet IPv4**. It must equal the address
printed above. If the router shows `10.x.x.x`, `172.16–31.x.x`, `192.168.x.x`, or
`100.64–127.x.x`, the ISP is using CGNAT and ordinary port forwarding will not work. Ask the ISP
for a public IPv4. If it will not provide one for free, this exact DuckDNS design has no reliable
no-card public-hosting path; a tunnel with a different hostname is required.

### 1.2 Reserve the host's LAN address and forward ports

1. Find the host address with `hostname -I` (for example `192.168.1.50`).
2. In the router, create a DHCP reservation for that address using the host's network-card MAC.
3. Add TCP port forwards:

| Public port | Protocol | Destination |
|---|---|---|
| 80 | TCP | `HOST_LAN_IP:80` |
| 443 | TCP | `HOST_LAN_IP:443` |

Do not forward 3306, 5432, 8000, 8080 or 8081. Test public reachability from mobile data, not from
the same Wi-Fi; some routers do not support NAT loopback.

### 1.3 Host firewall

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status
```

If UFW is currently inactive, enabling it can lock out SSH. Allow SSH from the LAN before running
`sudo ufw enable`, or leave firewall activation to the machine's administrator.

### Install Docker

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER" && newgrp docker
docker --version && docker compose version
```

### Add swap

If the host has less than 16 GB RAM, 4 GB of swap reduces the chance that a container build triggers
the OOM killer. Skip creation if `swapon --show` already lists adequate swap.

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Phase 2 — DNS

The domain already exists: `careercompass.duckdns.org`. The IP shown in DuckDNS during planning was
`92.253.28.211`, but it is dynamic and must never be treated as permanent. The token pasted during
planning is a credential; rotate it in DuckDNS before continuing.

Store the replacement token outside the repository and shell history:

```bash
install -m 700 -d "$HOME/.config/duckdns"
install -m 600 /dev/null "$HOME/.config/duckdns/careercompass.env"
nano "$HOME/.config/duckdns/careercompass.env"
```

Put only these two lines in that file:

```dotenv
DUCKDNS_DOMAIN=careercompass
DUCKDNS_TOKEN=PASTE_THE_NEW_DUCKDNS_TOKEN
```

Test an update. An empty `ip=` makes DuckDNS use the request's public IPv4:

```bash
set -a; . "$HOME/.config/duckdns/careercompass.env"; set +a
curl -fsS "https://www.duckdns.org/update?domains=$DUCKDNS_DOMAIN&token=$DUCKDNS_TOKEN&ip="
# expect: OK
```

Keep it current after any IP change without placing the token in crontab:

```bash
(crontab -l 2>/dev/null; echo '*/5 * * * * set -a; . "$HOME/.config/duckdns/careercompass.env"; curl -fsS "https://www.duckdns.org/update?domains=$DUCKDNS_DOMAIN&token=$DUCKDNS_TOKEN&ip=" >/dev/null') | crontab -
```

Verify before continuing — Caddy cannot get a certificate until this resolves:

```bash
dig +short careercompass.duckdns.org    # must print YOUR_PUBLIC_IP
```

---

## Phase 3 — Files to add to the repo

Four new files. Create and commit them before launching the home-hosted stack.

### 3.1 `frontend/Dockerfile.prod`

```dockerfile
# Production image: a static bundle behind nginx. The default Dockerfile in this
# directory deliberately runs Vite's dev server and must not be used here.
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Baked in at build time, not read at runtime — Vite inlines import.meta.env into
# the bundle. An EMPTY value is intentional and load-bearing: api/client.ts reads
#   import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'
# and `??` only falls back on null/undefined, so an empty string leaves BASE_URL
# as "" and every request goes to a relative /api/... path — same origin as the
# page, which is exactly what the Caddy routing below gives us. No CORS involved.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### 3.2 `frontend/nginx.conf`

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # React Router owns the URL space. Without this fallback a refresh on
    # /dashboard or a pasted /content/learning-outcomes/14/review is a 404,
    # because no file of that name exists.
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Vite fingerprints asset filenames, so they can be cached hard and forever.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # index.html must NOT be cached, or a browser keeps loading the old bundle
    # after a deploy and requests asset hashes that no longer exist.
    location = /index.html {
        add_header Cache-Control "no-cache, must-revalidate";
    }

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;
}
```

### 3.3 `docker-compose.prod.yml`

```yaml
# Production stack. Differences from the dev compose.yaml that matter:
#   - MySQL, not H2, and the prod Spring profile (no demo seed data)
#   - service DNS instead of network_mode: host and a hardcoded 172.18.0.1
#   - ONLY Caddy publishes ports; databases and the AI service are private
#   - hosted OpenRouter instead of a CPU-bound local Ollama container
#   - no Adminer
#   - every secret comes from .env with no fallback

name: careercompass

services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    environment:
      # Caddy expands {$PUBLIC_HOST} from its own container environment; merely
      # putting the value in Compose's .env file is not enough.
      PUBLIC_HOST: ${PUBLIC_HOST:?set PUBLIC_HOST in .env}
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data      # certificates — losing this re-issues from Let's Encrypt
      - caddy_config:/config
    depends_on:
      - frontend
      - backend

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
      args:
        # Empty on purpose — same-origin relative API calls. See Dockerfile.prod.
        VITE_API_BASE_URL: ""
    restart: unless-stopped
    expose:
      - "80"

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      SPRING_PROFILES_ACTIVE: prod
      # Pin the heap so the host keeps room for Python and both databases.
      JAVA_TOOL_OPTIONS: "-Xmx1536m -Xms256m"
      DB_URL: "jdbc:mysql://mysql:3306/careercompass?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
      DB_USERNAME: careercompass
      DB_PASSWORD: ${MYSQL_PASSWORD:?set MYSQL_PASSWORD in .env}
      JWT_SECRET: ${JWT_SECRET:?set JWT_SECRET in .env}
      AI_SERVICE_BASE_URL: http://ai-service:8000
      AI_SERVICE_TOKEN: ${AI_SERVICE_TOKEN:?set AI_SERVICE_TOKEN in .env}
      # Same origin behind Caddy, so this is belt-and-braces rather than required.
      CORS_ALLOWED_ORIGINS: https://${PUBLIC_HOST:?set PUBLIC_HOST in .env}
      LEARNING_OUTCOMES_DIR: /app/uploads/learning-outcomes
    volumes:
      - learning_outcomes:/app/uploads/learning-outcomes
    expose:
      - "8080"
    depends_on:
      mysql:
        condition: service_healthy
      ai-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8080/actuator/health"]
      interval: 15s
      timeout: 5s
      retries: 10
      start_period: 90s

  ai-service:
    build:
      context: ./ai-service
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      CC_DATA_DIR: /app/data
      CC_SERVICE_TOKEN: ${AI_SERVICE_TOKEN:?set AI_SERVICE_TOKEN in .env}
      CC_DB_HOST: postgres
      CC_DB_PORT: "5432"
      CC_DB_NAME: careercompass_ai
      CC_DB_USER: careercompass
      CC_DB_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      # Migrations are applied as an explicit step (Phase 5), not silently at boot.
      CC_DB_AUTO_MIGRATE: "0"
      # Semantic retrieval needs sentence-transformers (a multi-GB download that
      # is not installed in this image). Lexical is the tested path.
      CC_EMBEDDING_BACKEND: lexical
      CC_RERANKER: lexical
      # OpenRouter avoids running a local language model on the home host.
      CC_MATCH_LLM: ${CC_MATCH_LLM:-1}
      CC_MATCH_LLM_PROVIDER: openrouter
      CC_MATCH_MODEL: ${CC_MATCH_MODEL:-openrouter/free}
      # Blank is valid only with CC_MATCH_LLM=0. Keeping interpolation optional
      # preserves the documented no-LLM/privacy fallback.
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:-}
      CC_OPENROUTER_TIMEOUT: "60"
      CC_OPENROUTER_SITE_URL: https://${PUBLIC_HOST:?set PUBLIC_HOST in .env}
      # Fail closed: use only routes OpenRouter marks as not collecting data.
      # This may reduce free-model availability.
      CC_OPENROUTER_DATA_COLLECTION: deny
      # 1 = also count the 96 synthetic course maps, labelled as such on screen.
      # Set 0 for a deployment that must only ever reflect real extracted syllabi
      # — expect student coverage to drop sharply. Read Section 11 first.
      CC_INCLUDE_MOCK_COURSES: ${CC_INCLUDE_MOCK_COURSES:-1}
    expose:
      - "8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=5).close()
      interval: 15s
      timeout: 10s
      retries: 12
      # A cold start assembles the matcher index from the taxonomy.
      start_period: 5m

  mysql:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?set MYSQL_ROOT_PASSWORD in .env}
      MYSQL_DATABASE: careercompass
      MYSQL_USER: careercompass
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?set MYSQL_PASSWORD in .env}
    command: --innodb-buffer-pool-size=384M
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-u", "root", "-p${MYSQL_ROOT_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 20
      start_period: 60s

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: careercompass_ai
      POSTGRES_USER: careercompass
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U careercompass -d careercompass_ai"]
      interval: 10s
      timeout: 5s
      retries: 20

volumes:
  caddy_data:
  caddy_config:
  mysql_data:
  postgres_data:
  learning_outcomes:
```

### 3.4 `Caddyfile`

```caddy
# Caddy obtains and renews Let's Encrypt certificates automatically. The only
# requirement is that this hostname already resolves to this machine (Phase 2)
# and that ports 80 and 443 are reachable (Phase 1).
{$PUBLIC_HOST} {
	encode gzip

	# API and operational endpoints go to Spring. Everything here is same-origin
	# with the SPA, which is why the frontend needs no CORS and no absolute API URL.
	@api path /api/* /actuator/* /v3/api-docs* /swagger-ui/* /swagger-ui.html
	handle @api {
		reverse_proxy backend:8080
	}

	# Everything else is the single-page app.
	handle {
		reverse_proxy frontend:80
	}

	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "strict-origin-when-cross-origin"
		-Server
	}

	log {
		output file /data/access.log {
			roll_size 10MB
			roll_keep 5
		}
	}
}
```

> **Swagger UI is public here.** It documents 62 endpoints. That is a deliberate choice for a
> student project — remove `/v3/api-docs*`, `/swagger-ui/*` and `/swagger-ui.html` from the `@api` matcher if you
> would rather it were not.

---

## Phase 4 — Secrets

On the host, in the repo root. **Never commit this file** — the root `.gitignore` already excludes
`.env`.

```bash
cd ~/career_compass
cat > .env <<EOF
PUBLIC_HOST=careercompass.duckdns.org
JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n')
AI_SERVICE_TOKEN=$(openssl rand -hex 32)
MYSQL_ROOT_PASSWORD=$(openssl rand -base64 24 | tr -d '\n/+=')
MYSQL_PASSWORD=$(openssl rand -base64 24 | tr -d '\n/+=')
POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '\n/+=')
OPENROUTER_API_KEY=PASTE_A_NEW_OPENROUTER_KEY_HERE
CC_MATCH_LLM=1
CC_MATCH_MODEL=openrouter/free
CC_INCLUDE_MOCK_COURSES=1
EOF
chmod 600 .env
```

Replace the OpenRouter placeholder before starting Compose (or leave it blank only when deliberately
setting `CC_MATCH_LLM=0`), then **write the secrets down somewhere you will not lose them.** There is
no password-reset flow in this build (see Section 11), and losing database passwords complicates
recovery. Never reuse a key from a chat or transcript.

`JWT_SECRET` must be at least 32 characters — `JwtProperties` validates it and the application
refuses to start otherwise. That refusal is intentional: the alternative is signing tokens with a
key published in this repository.

---

## Phase 5 — First deploy

```bash
cd ~
git clone https://github.com/YOUR_ORG/career_compass.git
cd career_compass
# create .env as in Phase 4

# The first build downloads Maven, npm and Python dependencies; allow time.
docker compose -f docker-compose.prod.yml build

# Databases first, so migrations have something to run against.
docker compose -f docker-compose.prod.yml up -d mysql postgres
docker compose -f docker-compose.prod.yml ps    # wait for both: healthy
```

### 5.1 AI service schema

The AI service does **not** migrate itself (`CC_DB_AUTO_MIGRATE=0`). Apply it explicitly:

```bash
docker compose -f docker-compose.prod.yml run --rm ai-service cc-db-migrate
```

It takes a PostgreSQL advisory lock, verifies immutable SHA-256 checksums against
`careercompass_ai_schema_history`, and applies pending `NNN_*.sql` files in one transaction. Safe
to repeat. **Never edit an applied migration** — add the next numbered file.

### 5.2 Backend schema

Flyway runs automatically at startup and migrates the empty database from the packaged `V1`
baseline through `V6`. Hibernate is in `validate` mode, so a mismatch fails fast rather than
silently drifting.

Nothing to do — but note `baseline-on-migrate` is deliberately `false`. If you ever point this at
a hand-created database, read `backend/db/README.md` first; do not switch that flag on to make an
error go away.

### 5.3 Validate the OpenRouter configuration

```bash
# This checks interpolation without printing the resolved secrets.
docker compose -f docker-compose.prod.yml config --quiet

# Start the AI service and inspect its own logs. The key is not sent until an
# LLM-backed action (such as quiz generation) is requested.
docker compose -f docker-compose.prod.yml up -d ai-service
docker compose -f docker-compose.prod.yml logs --tail=100 ai-service

# When CC_MATCH_LLM=1, make one small real request. It counts against the daily
# free quota and validates the key, outbound DNS/TLS and response parsing.
docker compose -f docker-compose.prod.yml exec ai-service python -c \
  'from careercompass.skills.llm import LLMDecider; d=LLMDecider(); assert d.available, d.reason_unavailable; assert d.complete("Reply with OK.", max_tokens=32); print("OpenRouter OK:", d.display_name)'
```

### 5.4 Everything else

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
```

The AI service takes up to five minutes on a cold start to assemble its matcher index; the backend
waits for it. That is what the generous `start_period` is for.

### 5.5 Create the first administrator

`DevDataSeeder` is `@Profile("dev & !test")` and **will not run** in production — deliberately, so
demo accounts with published passwords cannot reach a real deployment. There is also no
`/api/auth/admins/register` endpoint, because an open "create an admin" route is a privilege
escalation hole.

So the first administrator is inserted by hand:

```bash
# Load the generated database password, then read the admin password without
# echoing it or storing it in shell history.
set -a; . ./.env; set +a
read -rsp "Initial administrator password: " ADMIN_PASSWORD; echo
export ADMIN_PASSWORD

# Apache's htpasswd emits a Spring-compatible bcrypt hash. Passing the cleartext
# in an environment variable keeps it out of the process argument list.
ADMIN_HASH=$(docker run --rm -e ADMIN_PASSWORD httpd:alpine sh -c \
  'htpasswd -bnBC 12 "" "$ADMIN_PASSWORD" | tr -d ":\n"')

# Expansion is not recursive, so the dollar signs inside the bcrypt hash arrive
# unchanged. MYSQL_PWD also avoids an interactive prompt in this one-time command.
docker compose -f docker-compose.prod.yml exec -T \
  -e MYSQL_PWD="$MYSQL_PASSWORD" mysql \
  mysql -u careercompass careercompass -e \
  "INSERT INTO administrators (first_name, last_name, email, password_hash)
   VALUES ('Platform','Administrator','admin@yourdomain.com','${ADMIN_HASH}');"

unset ADMIN_PASSWORD ADMIN_HASH MYSQL_PWD
```

Then sign in as Administrator and use the UI to create universities, study fields, career paths,
content managers and mentors.

> Career path titles are **not** free text. They must match the nine names in
> `ai-service/data/extracted/jobs/career_path_skills.json` exactly, or Java accepts the row and
> Python then matches nothing, producing an empty skill gap that looks like a bug. The same
> applies to study field names against `data/mapping/study_field_career_paths.json`.

---

## Phase 6 — OpenRouter and the hard $0 boundary

The AI service now supports `ollama`, `anthropic`, `gemini` and `openrouter`. Production uses
`openrouter/free`, which dynamically chooses a zero-price model compatible with the request. The
LLM generates quizzes and optional gap narratives, and resolves ambiguous taxonomy terms; numeric
skill-gap calculations remain deterministic. The Java quiz deadline is 90 seconds.

The integration:

- sends the key only as an `Authorization: Bearer` header;
- requires strict JSON Schema support for quiz and matching responses;
- sets `provider.require_parameters=true` for those structured calls;
- defaults to `provider.data_collection=deny`, failing closed if no private compatible route exists;
- rejects truncated, blocked, empty, malformed or out-of-shortlist responses;
- uses only Python's standard library, so the existing AI image is sufficient.

### The quota is small

OpenRouter documents **50 free-model requests per day** for accounts that have not purchased at
least 10 credits. A quiz normally consumes one generation call plus one self-check, but validation
can retry generation up to three times; one quiz can therefore consume 2–4 requests. Ambiguous
taxonomy matching and optional narratives consume more. Treat this as a low-traffic demonstration,
not unlimited production capacity. At 429, the affected LLM operation fails safely; wait for quota
reset or use the no-LLM mode below. Do not purchase credits or enable auto top-up if $0 is absolute.

OpenRouter says prompt logging and using prompts to improve OpenRouter are opt-in and off by
default, but downstream providers have their own policies. This code additionally requests
`data_collection=deny`. Check the account Privacy page and keep prompt logging disabled. If any
transcript-derived text must never leave the host, use no-LLM mode.

### Privacy-first fallback — no LLM

```env
CC_MATCH_LLM=0
```

Quiz generation returns a clear "no language model available" error; ambiguous taxonomy terms stay
in manual review rather than being auto-resolved, and the optional narrative remains blank.
Transcript parsing, numeric skill gaps, course recommendations, mentor matching and the
content-manager workflow continue to work.

### Local Ollama alternative

The code still supports Ollama, but it is not part of this production Compose. Adding it means
building a separate, measured configuration: use a small model, add the service and model volume,
set `CC_MATCH_LLM_PROVIDER=ollama`, and measure a real four-question quiz against the 90-second
deadline. Do not assume an unmeasured local model is production-ready.

---

## Phase 7 — Verify

```bash
HOST=careercompass.duckdns.org

# TLS and reachability
curl -sI https://$HOST | head -1                       # HTTP/2 200

# Backend health through Caddy — a real check, not just "the servlet answered"
curl -s https://$HOST/actuator/health                  # {"status":"UP",...}

# The SPA is served and its routes fall back correctly
curl -s -o /dev/null -w '%{http_code}\n' https://$HOST/dashboard   # 200, not 404

# Auth boundary
curl -s -o /dev/null -w '%{http_code}\n' https://$HOST/api/job-seekers/me   # 401

# Nothing private is exposed
curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://$HOST:8000/  # connection refused
test "$(curl -s -o /dev/null -w '%{http_code}' https://$HOST/actuator/env)" != 200

# Admin login works
curl -s -X POST https://$HOST/api/auth/admins/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@yourdomain.com","password":"YOUR_ADMIN_PASSWORD"}' | head -c 120
```

Then in a browser: sign in, create reference data, register a student, upload a transcript PDF,
confirm it, and check that the skill dashboard renders. That exercises Java → Python → PostgreSQL
end to end.

---

## Phase 8 — Backups

Two databases and one upload volume. Losing any of them loses user data.

`~/backup.sh`:

```bash
#!/usr/bin/env bash
# Nightly local backup. Local-only is not a real backup strategy — see the note
# below — but it is enough to recover from a bad migration or a dropped table.
set -euo pipefail

cd "$HOME/career_compass"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$HOME/backups/$STAMP"
mkdir -p "$OUT"
set -a; . ./.env; set +a

docker compose -f docker-compose.prod.yml exec -T mysql \
  mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines \
  careercompass | gzip > "$OUT/mysql.sql.gz"

docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U careercompass -Fc careercompass_ai > "$OUT/postgres.dump"

docker run --rm \
  -v careercompass_learning_outcomes:/data:ro \
  -v "$OUT":/backup alpine \
  tar czf /backup/uploads.tar.gz -C /data .

# Keep 14 days.
find "$HOME/backups" -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
echo "backup complete: $OUT"
```

```bash
chmod +x ~/backup.sh
(crontab -l 2>/dev/null; echo '0 3 * * * $HOME/backup.sh >> $HOME/backup.log 2>&1') | crontab -
```

> **A backup on the same disk as the thing it backs up is not a backup.** It protects against
> operator error, not against losing the host. Copy `~/backups` off the host regularly — `rsync`
> to your laptop is free and takes one command. Whatever you choose, **rehearse a restore before
> you need one**; an untested backup is a guess.

**Restore:**

```bash
gunzip -c mysql.sql.gz | docker compose -f docker-compose.prod.yml exec -T mysql \
  mysql -u root -p"$MYSQL_ROOT_PASSWORD" careercompass

docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U careercompass -d careercompass_ai --clean --if-exists < postgres.dump

docker run --rm -v careercompass_learning_outcomes:/data \
  -v "$PWD":/backup alpine tar xzf /backup/uploads.tar.gz -C /data
```

---

## Phase 9 — Monitoring

What you get for free:

```bash
# Health, including database connectivity
curl -s https://$HOST/actuator/health

# Container state and restart counts
docker compose -f docker-compose.prod.yml ps

# Live resource use
docker stats --no-stream

# Application errors — unhandled exceptions are now logged with a stack trace
docker compose -f docker-compose.prod.yml logs backend | grep -A20 "Unhandled exception"
```

Cap log growth so a chatty week cannot fill the disk. Add to
`/etc/docker/daemon.json`, then `sudo systemctl restart docker`:

```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "5" }
}
```

Free uptime alerting: point **UptimeRobot** (50 monitors free) or **Better Stack** at
`https://$HOST/actuator/health` with a 5-minute interval and email alerts. That covers "is it
down", which is the question that matters most.

**Not included, and worth knowing you do not have it:** error tracking (no Sentry), metrics
history (no Prometheus), structured JSON logs, or request correlation IDs. You are reading
`docker logs` by hand.

---

## Phase 10 — Updating a running deployment

```bash
cd ~/career_compass
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f backend
```

There is **no zero-downtime path** on a single host — expect roughly 60–90 seconds of downtime
while the JVM restarts and Flyway runs.

**Before any update that includes a migration, take a backup.** Flyway has no `undo` on the free
edition, so the rollback story is restore-from-dump, and a dump you took *after* the bad migration
is no use.

### Rollback

```bash
cd ~/career_compass
git log --oneline -10
git checkout <last-known-good-commit>
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

If the bad release included a schema migration, restore the database from the pre-update backup
**first**, then redeploy the old image. Rolling code back under a newer schema will fail Hibernate
validation at startup — loudly, which is the intended behaviour.

### Optional: CD from GitHub Actions

The repo already has seven CI jobs. To deploy on green, add a workflow that SSHes in and runs the
update commands, with `SSH_HOST` / `SSH_USER` / `SSH_KEY` in repository secrets:

```yaml
  deploy:
    needs: [backend-test, ai-service, frontend, contract]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd ~/career_compass
            ./backup.sh
            git pull
            docker compose -f docker-compose.prod.yml build
            docker compose -f docker-compose.prod.yml up -d
```

Weigh this up: automatic deployment to a single box with no blue/green and no automated rollback
means a bad merge is live in minutes. Manual deploys are a reasonable choice at this scale.

---

## 11. Known limits of this $0 setup

Read this before showing the deployment to anyone who will rely on it.

**Single point of failure.** One home computer, no redundancy. Reboot, sleep, power loss, router
restart, ISP outage or disk failure takes the whole system down. Disable automatic sleep while
serving and configure Docker to start at boot.

**Residential hosting can stop working.** The public IPv4 can change, the ISP can introduce CGNAT
or block inbound ports, and some routers lose forwarding rules after a factory reset. DuckDNS fixes
only IP changes; it cannot fix CGNAT or blocked ports.

**OpenRouter is an external low-quota dependency.** Free-model availability, routing quality and
limits can change. Without purchased credits the documented allowance is only 50 requests/day.
`CC_MATCH_LLM=0` is the privacy- and quota-safe fallback.

**No password reset.** There is no forgotten-password flow and no email capability anywhere in the
codebase — no `JavaMailSender`, no SMTP config. Signed-in users can *change* their password; a user
who *forgets* one has no self-service recovery, and an administrator must reset it in the database.
Closing this needs an SMTP decision, which is why it is not in this plan.

**No email at all**, therefore no notifications. A student is not told when a mentor accepts or
declines a session; they have to come back and look.

**Rate limiting is in-process.** `LoginRateLimitFilter` counts in memory, so counters reset on
restart and would not coordinate across replicas. Correct for one instance; revisit before scaling.

**Uploads are on a local volume.** Durable here, and it survives `docker compose down`. It does
*not* survive `down --volumes`, and it is the thing that blocks running a second backend instance.

**AI job matching is descoped.** `/api/job-seekers/me/job-matches` and the employer candidate list
return 501 by design, with a clear message in the UI. Students can still browse all open postings.

**Synthetic course data is on by default.** `CC_INCLUDE_MOCK_COURSES=1` counts 96 synthetic course
maps alongside the 20 real extracted syllabi, because without them a student reaches at most ~40%
of any career path and the dashboard reads as "you are missing everything" when it means "we could
not read your courses". Every synthetic course is counted *and labelled on screen*. For a
deployment that must only ever reflect real documents, set it to `0` and accept the lower coverage.

**Spring Boot 3.3.4 (September 2024)** is past its OSS support window. No CVE scan has been run
against the Java dependency tree — `npm audit` and `pip-audit` are both clean, but there is no
equivalent result here. Plan the upgrade.

**Swagger UI is publicly reachable** with the routing above. Remove it from the `@api` matcher if
that is not what you want.

---

## 12. Scaling beyond one host — what breaks first

Not needed for $0, but this is the order things fail in, so you know what you are buying when you
outgrow this:

1. **File storage** — `FileStorageService` writes to local disk. A second backend instance cannot
   see the first one's uploads. This is the first hard blocker, and the fix is the S3/R2 refactor
   the earlier plan proposed. `application.yml:61-66` already flags it.
2. **Login rate limiting** — in-memory counters do not coordinate; move to Redis.
3. **Revoked-token table** — grows without bound and has no purge policy.
4. **AI service warm-up** — each instance builds its matcher index in memory at start, so every
   replica pays the same multi-minute cold start.

Everything else is already stateless: JWT sessions carry no server-side state.

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| DuckDNS resolves but site is unreachable | Missing router forwarding, host firewall, CGNAT, ISP filtering, or host asleep | Work through Phase 1 from WAN-IP comparison through mobile-data testing |
| Router WAN IP differs from `api.ipify.org` | CGNAT or double NAT | Forward through both routers or ask the ISP for a public IPv4; DuckDNS alone cannot solve it |
| Caddy cannot get a certificate | DNS stale, port 80 not forwarded, or ISP blocks it | `dig +short $HOST` must equal the public IP; test port 80 from mobile data |
| Backend exits immediately | `JWT_SECRET` missing or under 32 chars | Check `.env`; the refusal is intentional |
| Backend cannot reach the AI service | Copied `AI_SERVICE_BASE_URL` from the dev compose | Must be `http://ai-service:8000`, never `172.18.0.1` |
| AI service unhealthy for minutes at boot | Normal cold start building the matcher index | Wait out the 5-minute `start_period`; watch `logs -f ai-service` |
| Quiz says no LLM is available | Missing/revoked OpenRouter key or no compatible private free route | Create a fresh key, inspect `logs ai-service`, and verify Privacy settings |
| OpenRouter returns HTTP 429 | The shared 50-request daily free quota was reached | Wait for reset or set `CC_MATCH_LLM=0`; do not buy credits if the hard $0 ceiling matters |
| Locked out with HTTP 429 | The login rate limiter, working correctly | Wait 15 minutes, or `docker compose -f docker-compose.prod.yml restart backend` |
| Every skill shows "Missing" | Career path name does not match the AI ontology exactly | Compare against `career_path_skills.json` — Phase 5.5 |
| Build killed on the host | Maven/Node ran out of memory | Close heavy applications and add swap (Phase 1) |

---

## 14. Environment variable reference

### Backend

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SPRING_PROFILES_ACTIVE` | yes | `dev` | must be `prod` |
| `JWT_SECRET` | **yes** | none | ≥32 chars; startup fails without it |
| `DB_URL` | yes | localhost MySQL | |
| `DB_USERNAME` / `DB_PASSWORD` | yes | none | |
| `AI_SERVICE_BASE_URL` | **yes** | none in prod | `http://ai-service:8000` |
| `AI_SERVICE_TOKEN` | **yes** | none in prod | must match `CC_SERVICE_TOKEN` |
| `CORS_ALLOWED_ORIGINS` | no | localhost:3000,5173 | unused when same-origin |
| `LEARNING_OUTCOMES_DIR` | no | `./uploads/learning-outcomes` | |
| `JAVA_TOOL_OPTIONS` | no | — | production plan uses `-Xmx1536m -Xms256m` |

### AI service

| Variable | Required | Default | Notes |
|---|---|---|---|
| `CC_SERVICE_TOKEN` | **yes** | unset = **no auth** | blank leaves the API open; it warns at startup |
| `CC_DATA_DIR` | yes | — | `/app/data` in the image |
| `CC_DB_HOST` / `_PORT` / `_NAME` / `_USER` / `_PASSWORD` | yes | — | PostgreSQL, separate from the backend's MySQL |
| `CC_DB_AUTO_MIGRATE` | no | `0` | keep `0`; migrate as an explicit step |
| `CC_EMBEDDING_BACKEND` | no | `auto` | `lexical` — `bge` needs sentence-transformers |
| `CC_RERANKER` | no | `auto` | `lexical` |
| `CC_MATCH_LLM` | no | `1` | `0` disables quizzes and LLM disambiguation |
| `CC_MATCH_LLM_PROVIDER` | no | `ollama` | production sets `openrouter`; valid: `ollama`, `anthropic`, `gemini`, `openrouter` |
| `CC_MATCH_MODEL` | no | provider-specific | `openrouter/free` in this plan |
| `OPENROUTER_API_KEY` | **yes for OpenRouter** | none | create a replacement key; never commit or paste it |
| `CC_OPENROUTER_TIMEOUT` | no | `60` | outbound request timeout in seconds |
| `CC_OPENROUTER_SITE_URL` | no | blank | public site attribution sent as `HTTP-Referer` |
| `CC_OPENROUTER_DATA_COLLECTION` | no | `deny` | `deny` fails closed to providers marked as not collecting data |
| `GEMINI_API_KEY` / `CC_GEMINI_TIMEOUT` | only for Gemini | none / `60` | unused by this production plan |
| `CC_OLLAMA_URL` / `CC_OLLAMA_TIMEOUT` | only for Ollama | local URL / `300` | unused by this production plan |
| `CC_INCLUDE_MOCK_COURSES` | no | code default `0`; this Compose sets `1` | `0` = real extracted syllabi only |
| `CC_API_CORS_ORIGINS` | no | dev origins | leave unset — never browser-facing |
| `CC_API_MAX_UPLOAD_MB` | no | `20` | AI service request limit; Spring separately caps transcript uploads at 10 MB |

### Frontend (build-time only)

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | Inlined by Vite at build time. **Empty string** for same-origin. It is not read at runtime, so changing it means rebuilding the image. |

### Compose `.env`

`PUBLIC_HOST`, `JWT_SECRET`, `AI_SERVICE_TOKEN`, `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`,
`POSTGRES_PASSWORD`, `OPENROUTER_API_KEY`, `CC_MATCH_LLM`, `CC_MATCH_MODEL`,
`CC_INCLUDE_MOCK_COURSES`.

---

## 15. Deployment checklist

**Before**
- [ ] Home Linux host has adequate RAM/disk and automatic sleep is disabled
- [ ] Router WAN IPv4 equals the public IPv4 (no CGNAT)
- [ ] Host LAN address reserved; router forwards TCP 80/443 only
- [ ] Host firewall allows 80/443
- [ ] Docker + compose plugin installed, 4 GB swap added
- [ ] Rotated DuckDNS token stored outside the repo; updater cron installed
- [ ] `careercompass.duckdns.org` resolves to the current public IPv4
- [ ] `frontend/Dockerfile.prod`, `frontend/nginx.conf`, `docker-compose.prod.yml`, `Caddyfile` committed
- [ ] `.env` created with generated secrets, `chmod 600`, secrets recorded off-machine
- [ ] Pasted OpenRouter key revoked; fresh replacement added only to `.env`

**Deploy**
- [ ] `docker compose -f docker-compose.prod.yml build`
- [ ] Databases up and healthy
- [ ] `cc-db-migrate` run against PostgreSQL
- [ ] Compose validates and the one-request OpenRouter smoke test succeeds (or deliberate `CC_MATCH_LLM=0`)
- [ ] Full stack up, all containers healthy
- [ ] First administrator inserted

**Verify**
- [ ] `https://$HOST` serves the SPA over valid TLS
- [ ] `/actuator/health` → `UP`
- [ ] Deep link (`/dashboard`) returns 200, not 404
- [ ] Unauthenticated API call → 401
- [ ] `/actuator/env` is not 200 (normally 401/404); port 8000 refused from outside
- [ ] Admin sign-in works; reference data created
- [ ] Student registers → uploads transcript → confirms → dashboard renders
- [ ] Quiz generation completes inside the timeout, **or** `CC_MATCH_LLM=0` is set deliberately

**Operate**
- [ ] Nightly backup cron installed and a restore rehearsed
- [ ] Backups copied off the host
- [ ] Docker log rotation configured
- [ ] Uptime monitor pointed at `/actuator/health`
- [ ] Section 11 read and accepted
- [ ] Free-model usage kept within the documented 50-request daily allowance
