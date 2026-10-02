# Phase 5: Traefik v3 Ingress & Origin TLS

[← Phase 4: Health, Restart & Change Cycle](./04-health-change-cycle.md) · **Phase 5 of 5** · [Back to Overview →](./00-overview.md)

---

### In this phase
- [8. Traefik v3 as the Single Ingress](#8-traefik-v3-as-the-single-ingress)
  - [8.1. Why a Reverse Proxy?](#81-why-a-reverse-proxy)
  - [8.2. Chosen Tool (Traefik v3)](#82-chosen-tool-traefik-v3)
  - [8.3. How Traefik Works](#83-how-traefik-works)
  - [8.4. Request Path and Adopted Layout](#84-request-path-and-adopted-layout)
  - [8.5. Static Configuration](#85-static-configuration)
  - [8.6. TLS with the Cloudflare Origin Certificate](#86-tls-with-the-cloudflare-origin-certificate)
  - [8.7. Reusable Middlewares](#87-reusable-middlewares)
  - [8.8. The Traefik Container](#88-the-traefik-container)
  - [8.9. Start and Verify](#89-start-and-verify)
- [9. Exposing Services & the Private Dashboard](#9-exposing-services--the-private-dashboard)
  - [9.1. Publishing a Service with Labels](#91-publishing-a-service-with-labels)
  - [9.2. VPN-only Dashboard (Split-Horizon DNS)](#92-vpn-only-dashboard-split-horizon-dns)
  - [9.3. Mandatory Tests](#93-mandatory-tests)
  - [9.4. Cleanup and Useful Commands](#94-cleanup-and-useful-commands)
  - [9.5. Expected End State](#95-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 8. Traefik v3 as the Single Ingress
This section puts a reverse proxy in front of every service: one entry point that terminates TLS, applies security policy and routes each request to the right container.

#### 8.1. Why a Reverse Proxy?
The naive way to expose services is one published port per service:

```yaml
# ❌ every service on its own port
services:
  app1:
    ports: ["8080:80"]
  app2:
    ports: ["8081:80"]
  app3:
    ports: ["8082:80"]
```

That means ugly URLs (`mysite.com:8081`), one firewall decision per service, TLS configured separately in every application, and no single place to apply security policy.

A reverse proxy receives all traffic on 443 and forwards each request to the right container based on its hostname. Containers don't publish anything; they're only reachable through the proxy, over the `proxy` network.

```text
❌ Without a reverse proxy          ✅ With a reverse proxy

Internet → :8080 → App1            Internet → :443 → Traefik → App1 (app1.mysite.com)
Internet → :8081 → App2                                     → App2 (app2.mysite.com)
Internet → :8082 → App3                                     → App3 (app3.mysite.com)
                                                            → 404  (unknown host)
```

#### 8.2. Chosen Tool (Traefik v3)
Nginx, Caddy and HAProxy are all solid reverse proxies. I chose **Traefik** because it's built for Docker: it discovers containers through labels in their own `docker-compose.yml` and reconfigures routing instantly, with no reload and no central file to edit.

| Feature | Nginx | Traefik |
| :--- | :--- | :--- |
| Container discovery | ❌ Manual configuration | ✅ Automatic, via labels |
| Change in containers | ❌ Requires a reload | ✅ Applied live |
| Where a service's routing lives | Central configuration file | Next to the service, in its Compose file |
| Learning curve | Lower | Higher at first |

#### 8.3. How Traefik Works
Traefik is built from five concepts that chain together:

| Concept | Role | On this platform |
| :--- | :--- | :--- |
| **Entrypoint** | Where Traefik listens | `web` (:80, redirects only) and `websecure` (:443) |
| **Provider** | Where routing configuration comes from | `docker` (container labels) + `file` (shared TLS and middlewares) |
| **Router** | Which request goes where | `Host(\`app.mysite.com\`)`, optionally with `PathPrefix` |
| **Middleware** | Processing between the router and the service | Allow-list → headers → rate limit, chained per router |
| **Service** | The final destination | The container's internal port, discovered automatically |

Configuration comes in two types:

| Type | Defines | Lives in | Changes |
| :--- | :--- | :--- | :--- |
| **Static** | Entrypoints, providers, logs | `traefik.yml` | Rarely; requires a restart |
| **Dynamic** | Routers, middlewares, services, TLS | Labels and `dynamic/*.yml` | Often; hot-reloaded |

#### 8.4. Request Path and Adopted Layout
A public request crosses every layer built so far:

```text
User ──HTTPS──► Cloudflare (edge TLS, WAF, rate limiting — Case 01)
                   │
                   │ HTTPS, validated against the Origin certificate (Full Strict)
                   ▼
            VPS eth0 :443
                   │  DNAT to the Traefik container
                   ▼
            DOCKER-USER: Cloudflare source + original port 443? (Phase 2)
                   │  yes
                   ▼
            Traefik :443 ── terminates TLS with the Origin certificate
                   │       ── matches Host → router → middlewares
                   ▼
            proxy network ──► application container
                                   │
                                   └─► app-internal network ──► database (Phase 3)
```

The configuration follows the `/srv` convention from Phase 1:
```text
/srv/apps/traefik/
├── docker-compose.yml   # the Traefik container
├── traefik.yml          # static: entrypoints, providers, logs
└── dynamic/
    ├── tls.yml          # dynamic: Origin certificate and TLS policy
    └── middlewares.yml  # dynamic: reusable middlewares

/srv/data/traefik/       # per-app convention from Phase 1; empty for now

/srv/logs/traefik/
├── traefik.log          # Traefik's own log
└── access.log           # one JSON line per request
```

`/srv/data/traefik` follows the per-app convention from Phase 1. It stays empty for now: the certificate lives in `/etc/ssl/cloudflare` (Case 01), not in a file Traefik manages.

**Prerequisites** (don't continue unless all are true):
- [x] Wildcard `*` record proxied (orange cloud), Origin certificate in `/etc/ssl/cloudflare/`, Full (Strict) active (Case 01, Phase 4)
- [x] `DOCKER-USER` filter active and enabled on boot ([Phase 2](./02-docker-firewall.md))
- [x] `proxy` network created ([Phase 3](./03-networks-state.md))

<details>
<summary><b>▶ View commands — Traefik directories</b></summary>

```bash
sudo mkdir -p /srv/apps/traefik/dynamic /srv/data/traefik /srv/logs/traefik
sudo chown -R root:root /srv/apps/traefik /srv/data/traefik /srv/logs/traefik
```
Traefik's configuration is root-owned: changing how the internet reaches the platform is an administrative act, not a day-to-day one.
</details>

> [!WARNING]
> Take a snapshot named `pre-case02-traefik` before continuing.

#### 8.5. Static Configuration
<details>
<summary><b>▶ View config — /srv/apps/traefik/traefik.yml</b></summary>

```bash
sudo nano /srv/apps/traefik/traefik.yml
```
```yaml
# =============================================================================
# Traefik v3 - Static Configuration
# =============================================================================

api:
  dashboard: true
  insecure: false          # no unauthenticated :8080 dashboard; it's served by a router (9.2)

ping:
  entryPoint: traefik      # internal :8080 endpoint for the healthcheck; never published

log:
  level: INFO
  filePath: /var/log/traefik/traefik.log

accessLog:
  filePath: /var/log/traefik/access.log
  format: json
  bufferingSize: 100
  fields:
    headers:
      defaultMode: drop
      names:
        CF-Connecting-IP: keep   # the real client IP, set by Cloudflare
        User-Agent: keep

entryPoints:
  web:
    address: ":80"
    http:
      redirections:              # global HTTP -> HTTPS for every current and future service
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: ":443"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false      # nothing is routed without traefik.enable=true
    network: proxy               # always reach containers over the proxy network
    watch: true
  file:
    directory: /etc/traefik/dynamic
    watch: true
```
</details>

Key decisions:

| Setting | Why |
| :--- | :--- |
| `exposedByDefault: false` | A new container is invisible until it's explicitly labeled. Exposure is a decision, never a default. |
| Global redirect on `web` | Port 80 does nothing but redirect, so no service can accidentally answer in plain HTTP. |
| `network: proxy` | Traefik never tries to reach a container over one of its internal networks. |
| JSON access log + `CF-Connecting-IP` | Behind Cloudflare, every request comes from a Cloudflare IP. Without the header, the access log can't say who actually made a request, which makes incident response guesswork. |
| `api.insecure: false` | The dashboard is never served on a raw port. It goes through a router with the VPN allow-list. |

#### 8.6. TLS with the Cloudflare Origin Certificate
The Origin certificate generated in Case 01 becomes Traefik's default certificate for every HTTPS connection, and TLS below 1.2 is refused.

<details>
<summary><b>▶ View config — /srv/apps/traefik/dynamic/tls.yml</b></summary>

Confirm the files from Case 01 exist:
```bash
sudo ls -la /etc/ssl/cloudflare/
```
`origin.crt` and `origin.key` must both be there.

```bash
sudo nano /srv/apps/traefik/dynamic/tls.yml
```
```yaml
# =============================================================================
# TLS - Cloudflare Origin Certificate
# =============================================================================

tls:
  options:
    default:
      minVersion: VersionTLS12   # Cloudflare connects with TLS 1.2/1.3; nothing older is needed

  stores:
    default:
      defaultCertificate:
        certFile: /etc/ssl/cloudflare/origin.crt
        keyFile: /etc/ssl/cloudflare/origin.key
```
</details>

> [!NOTE]
> An Origin certificate is trusted by Cloudflare, not by browsers. That's exactly right for public traffic, which always arrives through Cloudflare. It matters for admin access over the VPN, which reaches Traefik directly. [9.2](#92-vpn-only-dashboard-split-horizon-dns) deals with that.

#### 8.7. Reusable Middlewares
Middlewares are defined once and referenced by any router with the `@file` suffix.

<details>
<summary><b>▶ View config — /srv/apps/traefik/dynamic/middlewares.yml</b></summary>

```bash
sudo nano /srv/apps/traefik/dynamic/middlewares.yml
```
```yaml
# =============================================================================
# Reusable Middlewares
# =============================================================================

http:
  middlewares:

    # -------------------------------------------------------------------------
    # VPN-only access for administrative routers
    # -------------------------------------------------------------------------
    vpn-allowlist:
      ipAllowList:
        sourceRange:
          - "10.10.10.0/24"

    # -------------------------------------------------------------------------
    # Security headers for every public router
    # -------------------------------------------------------------------------
    security-headers:
      headers:
        stsSeconds: 31536000             # HSTS: browsers remember HTTPS-only for 1 year
        stsIncludeSubdomains: true
        stsPreload: true
        forceSTSHeader: true
        contentTypeNosniff: true         # no MIME-type guessing
        frameDeny: true                  # no framing: blocks clickjacking
        referrerPolicy: "strict-origin-when-cross-origin"

    # -------------------------------------------------------------------------
    # Rate limiting per real client (not per Cloudflare edge IP)
    # -------------------------------------------------------------------------
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
        sourceCriterion:
          requestHeaderName: CF-Connecting-IP

    # -------------------------------------------------------------------------
    # Response compression
    # -------------------------------------------------------------------------
    compress:
      compress: {}
```
</details>

| Middleware | What it does | Applied to |
| :--- | :--- | :--- |
| `vpn-allowlist` | Accepts only sources in `10.10.10.0/24` | Administrative routers |
| `security-headers` | HSTS, `nosniff`, framing denied, referrer policy | Every public router |
| `rate-limit` | 100 req/s on average, bursts of 50, per real client | Public routers, APIs, forms |
| `compress` | Compresses responses | Optional, bandwidth |

Two design decisions are worth spelling out:

- **The allow-list trusts the TCP source address, never a header.** `ipAllowList` uses the connection's real source by default. I deliberately don't configure it to read `X-Forwarded-For`, which any client can forge. A request that comes through Cloudflare has a Cloudflare source address, so it can never pass the VPN allow-list.
- **Rate limiting trusts `CF-Connecting-IP` only because of Phase 2.** Behind Cloudflare, all visitors share a handful of Cloudflare source IPs. Limiting by source address would throttle everyone together. `CF-Connecting-IP` holds the real client and is overwritten by Cloudflare on every request. That header is only trustworthy because nothing except Cloudflare can reach Traefik from the internet: the `INPUT` allow-list (Case 01) plus `DOCKER-USER` (Phase 2) make it so.

> [!NOTE]
> The legacy `X-XSS-Protection` header (`browserXssFilter`) is deliberately left out: modern browsers have removed that filter, and current guidance is not to send it. `stsPreload` only signals consent: actually submitting the domain to browser preload lists is a separate, hard-to-reverse decision.

#### 8.8. The Traefik Container
<details>
<summary><b>▶ View config — /srv/apps/traefik/docker-compose.yml</b></summary>

```bash
sudo nano /srv/apps/traefik/docker-compose.yml
```
```yaml
services:
  traefik:
    image: traefik:v3.7
    container_name: traefik
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    ports:
      - "80:80"      # filtered by DOCKER-USER: Cloudflare only
      - "443:443"    # filtered by DOCKER-USER: Cloudflare only
    volumes:
      - /srv/apps/traefik/traefik.yml:/traefik.yml:ro        # static configuration
      - /srv/apps/traefik/dynamic:/etc/traefik/dynamic:ro    # TLS + middlewares
      - /var/run/docker.sock:/var/run/docker.sock:ro         # service discovery (see warning)
      - /etc/ssl/cloudflare:/etc/ssl/cloudflare:ro           # Origin certificate (Case 01)
      - /srv/logs/traefik:/var/log/traefik                   # logs
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      # Dashboard: Split-Horizon DNS name, VPN-only (9.2)
      - "traefik.http.routers.dashboard.rule=Host(`traefik.mysite.com`) && (PathPrefix(`/api`) || PathPrefix(`/dashboard`))"
      - "traefik.http.routers.dashboard.entrypoints=websecure"
      - "traefik.http.routers.dashboard.tls=true"
      - "traefik.http.routers.dashboard.service=api@internal"
      - "traefik.http.routers.dashboard.middlewares=vpn-allowlist@file,security-headers@file"
    healthcheck:
      test: ["CMD", "traefik", "healthcheck"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

networks:
  proxy:
    external: true
```
</details>

| Volume | Purpose |
| :--- | :--- |
| `traefik.yml` (ro) | Static configuration |
| `dynamic/` (ro) | TLS policy and middlewares, hot-reloaded |
| `docker.sock` (ro) | Discovering containers and their labels |
| `/etc/ssl/cloudflare` (ro) | The Origin certificate and key |
| `/srv/logs/traefik` | Persistent logs |

The healthcheck uses Traefik's built-in `traefik healthcheck`, which queries the internal `ping` endpoint. It tells whether Traefik is actually serving, not just whether the process exists.

> [!WARNING]
> **The Docker socket is the most sensitive mount on this platform.** `:ro` only stops the container from replacing the socket file. It doesn't make the Docker API read-only. Whoever controls Traefik can drive Docker, and that's root on the host. Traefik is also the one container that faces the internet.
>
> What limits that risk today: `no-new-privileges`, `exposedByDefault: false`, a VPN-only dashboard, and the Phase 4 change cycle, so Traefik patches are applied promptly. The planned next step is a **socket proxy** between Traefik and Docker that only allows the read-only API calls discovery needs (listing containers, networks and events).

#### 8.9. Start and Verify
<details>
<summary><b>▶ View commands — starting Traefik</b></summary>

```bash
cd /srv/apps/traefik && docker compose up -d
docker compose ps
```
```text
NAME      IMAGE          STATUS                   PORTS
traefik   traefik:v3.7   Up 1 minute (healthy)    0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```
`(healthy)` confirms the healthcheck passed. If it shows `(health: starting)`, wait 30 seconds and check again.

Confirm that Traefik loaded both providers without errors:
```bash
sudo grep -iE "error|warn" /srv/logs/traefik/traefik.log | tail -n 20
```
🟢 Expected result: no errors about `middlewares.yml`, `tls.yml` or the Docker provider.
</details>

---

### 9. Exposing Services & the Private Dashboard

#### 9.1. Publishing a Service with Labels
A service never publishes a port. It joins `proxy` and declares, in its own Compose file, how Traefik should route it. I validate the whole path with a throwaway `whoami` container, which echoes back the request it receives, headers included.

<details>
<summary><b>▶ View config — /srv/apps/whoami/docker-compose.yml</b></summary>

```bash
sudo mkdir -p /srv/apps/whoami
sudo chown <username>:<username> /srv/apps/whoami
nano /srv/apps/whoami/docker-compose.yml
```
```yaml
services:
  whoami:
    image: traefik/whoami     # throwaway test image, removed in 9.4
    container_name: whoami
    restart: unless-stopped
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.whoami.rule=Host(`whoami.mysite.com`)"
      - "traefik.http.routers.whoami.entrypoints=websecure"
      - "traefik.http.routers.whoami.tls=true"
      - "traefik.http.routers.whoami.middlewares=security-headers@file,rate-limit@file"
      - "traefik.http.services.whoami.loadbalancer.server.port=80"

networks:
  proxy:
    external: true
```
```bash
cd /srv/apps/whoami && docker compose up -d
```
</details>

| Label | What it does |
| :--- | :--- |
| `traefik.enable=true` | Opts the container in (required by `exposedByDefault: false`) |
| `routers.whoami.rule` | The routing condition: the hostname |
| `routers.whoami.entrypoints` | HTTPS only |
| `routers.whoami.tls` | TLS with the default (Origin) certificate |
| `routers.whoami.middlewares` | The middleware chain, in order |
| `services.whoami.loadbalancer.server.port` | The container's internal port |

To make any service VPN-only, the router adds `vpn-allowlist@file` to its middleware chain. That's all it takes.

#### 9.2. VPN-only Dashboard (Split-Horizon DNS)
The dashboard shows every router, service and middleware live. It's an administrative interface, so it follows the same model as `srv01` in Case 01: a DNS name that only resolves to something reachable from inside the VPN.

<details>
<summary><b>▶ View steps — DNS record, trust and access</b></summary>

**a. DNS record in Cloudflare**

| Type | Name | Value | Proxy | Purpose |
| :---: | :--- | :--- | :--- | :--- |
| **A** | `traefik` | `10.10.10.1` | DNS Only (Grey ☁️) | Traefik dashboard (VPN only) |

The specific `traefik` record overrides the proxied wildcard. Off the VPN, `10.10.10.1` simply isn't routable.

**b. Trust the Origin CA on the admin device only**

Over the VPN, my browser talks to Traefik directly and sees the Origin certificate, which public trust stores don't include. Instead of training myself to click through certificate warnings, I trust Cloudflare's Origin CA root on my admin device only:
```bash
curl -fsS -o ~/origin_ca_rsa_root.pem https://developers.cloudflare.com/ssl/static/origin_ca_rsa_root.pem
```
Then import it into the admin device's trust store (or the browser's certificate manager). Command-line tests use it explicitly with `--cacert`.

**c. Access**

With the VPN up, open `https://traefik.mysite.com/dashboard/`. It shows the entrypoints (80, 443), the routers and their status, the services and the active middlewares.
</details>

> [!NOTE]
> The private IP `10.10.10.1` is visible in public DNS. That reveals an internal address, nothing more: it isn't reachable without the VPN, and the router also enforces `vpn-allowlist`. It's the same trade-off accepted for `srv01` in Case 01.

#### 9.3. Mandatory Tests
<details>
<summary><b>▶ View tests — the whole ingress path, end to end</b></summary>

**Test 1: Traefik is healthy**
```bash
cd /srv/apps/traefik && docker compose ps
```
🟢 Expected result: `Up ... (healthy)`.

**Test 2: HTTP is redirected to HTTPS**
```bash
curl -sI http://whoami.mysite.com | head -n 3
```
🟢 Expected result: `301` or `308` with `Location: https://whoami.mysite.com/`. A `301` from Cloudflare (when "Always Use HTTPS" is on) or a `308` from Traefik both prove plain HTTP never reaches a service.

**Test 3: The request really traveled through Cloudflare**
```bash
curl -s https://whoami.mysite.com | grep -iE "^(X-Real-Ip|Cf-Connecting-Ip):"
```
🟢 Expected result: `X-Real-Ip` is a Cloudflare address, and `Cf-Connecting-Ip` is my own public IP.

```bash
curl -sI https://whoami.mysite.com | grep -iE "^(server|strict-transport-security|x-content-type-options|x-frame-options):"
```
🟢 Expected result: `server: cloudflare`, plus the three security headers from `security-headers`.

**Test 4: Bypassing Cloudflare with the right hostname fails** (from outside the VPN)

This is the realistic bypass attempt: correct hostname and SNI, sent straight to the origin IP.
```bash
curl -sk --connect-timeout 5 --resolve whoami.mysite.com:443:<VPS_PUBLIC_IP> https://whoami.mysite.com
```
🔴 Expected result: timeout. On the server, the counters prove which rule decided:
```bash
sudo iptables -L CLOUDFLARE_DOCKER_V4 -n -v
```
🟢 Expected result: the final `DROP` counter increased with Test 4, while packets from Tests 2–3 are counted on the Cloudflare `RETURN` rules for port 443.

**Test 5: The VPN allow-list rejects traffic that comes through Cloudflare**

Temporarily put `whoami` behind `vpn-allowlist`:
```bash
cd /srv/apps/whoami
sed -i 's/middlewares=security-headers@file,rate-limit@file/middlewares=vpn-allowlist@file,security-headers@file/' docker-compose.yml
docker compose up -d
```
Through Cloudflare (VPN up or down, it doesn't matter):
```bash
curl -s -o /dev/null -w '%{http_code}\n' https://whoami.mysite.com
```
🔴 Expected result: `403`. The source is a Cloudflare IP, outside `10.10.10.0/24`.

Through the VPN, straight to Traefik:
```bash
curl -s -o /dev/null -w '%{http_code}\n' --cacert ~/origin_ca_rsa_root.pem \
  --resolve whoami.mysite.com:443:10.10.10.1 https://whoami.mysite.com
```
🟢 Expected result: `200`. The same router, a VPN source and a certificate verified against the Origin CA.

**Test 6: The dashboard exists only inside the VPN**

With the VPN up:
```bash
curl -s -o /dev/null -w '%{http_code}\n' --cacert ~/origin_ca_rsa_root.pem https://traefik.mysite.com/dashboard/
```
🟢 Expected result: `200`.

With the VPN down (`sudo wg-quick down vps-admin`), the same command:
🔴 Expected result: timeout. `10.10.10.1` isn't routable from the internet.

**Test 7: The access log records the real client**
```bash
sudo tail -n 1 /srv/logs/traefik/access.log | jq '{ClientHost, RequestHost, DownstreamStatus, real_client: ([to_entries[] | select(.key | test("connecting-ip"; "i")) | .value][0])}'
```
🟢 Expected result: `ClientHost` is a Cloudflare address, and `real_client` is my own public IP.
</details>

#### 9.4. Cleanup and Useful Commands
<details>
<summary><b>▶ View commands — removing the test service</b></summary>

```bash
cd /srv/apps/whoami && docker compose down --rmi all
sudo rm -rf /srv/apps/whoami
```
</details>

<details>
<summary><b>▶ View commands — day-to-day Traefik operations</b></summary>

```bash
# Status and health
cd /srv/apps/traefik && docker compose ps

# Traefik's own log
sudo tail -f /srv/logs/traefik/traefik.log

# Live access log, one compact line per request
sudo tail -f /srv/logs/traefik/access.log | jq -c '{time: .time, host: .RequestHost, path: .RequestPath, status: .DownstreamStatus}'

# Dynamic files (dynamic/*.yml) reload automatically; static changes need a restart
docker compose restart traefik
```
</details>

#### 9.5. Expected End State
- Traefik is the platform's only published service: `healthy`, ports 80/443, reachable from the internet only through Cloudflare;
- every HTTP request is redirected to HTTPS; TLS terminates with the Origin certificate, and nothing older than TLS 1.2 is accepted;
- a new service is published with labels alone, and nothing is routed without `traefik.enable=true`;
- public routers send security headers and rate-limit per real client;
- administrative routers accept only VPN sources, and the dashboard is only resolvable to a VPN address;
- the access log records the real client IP for every request;
- the test service is removed.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case02-phase5-traefik-ok` and delete the previous one.

---

> This closes the platform layer. The perimeter from Case 01 now has a single, filtered entry point. Behind it, services are segmented, their state is persistent, their health is measured and their updates are reversible. The next step is observability: making this platform's behavior visible in real time, in [Case 03](../case-03-observability-metrics-logs-availability/00-overview.md).

---

[← Phase 4: Health, Restart & Change Cycle](./04-health-change-cycle.md) · **Phase 5 of 5** · [Back to Overview →](./00-overview.md)
