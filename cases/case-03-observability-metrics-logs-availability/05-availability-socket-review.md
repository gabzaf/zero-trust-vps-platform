# Phase 5: Availability with Uptime Kuma & Docker-Socket Review

[← Phase 4: Centralized Logs](./04-centralized-logs.md) · **Phase 5 of 5** · [Back to Overview →](./00-overview.md)

---

### In this phase
- [9. Uptime Kuma: Is It Actually Answering?](#9-uptime-kuma-is-it-actually-answering)
  - [9.1. Why "Up" Isn't Enough](#91-why-up-isnt-enough)
  - [9.2. The Uptime Kuma Container](#92-the-uptime-kuma-container)
  - [9.3. Monitors](#93-monitors)
  - [9.4. Monitoring Without Flattening the Networks](#94-monitoring-without-flattening-the-networks)
  - [9.5. Alert Routing](#95-alert-routing)
  - [9.6. Mandatory Tests](#96-mandatory-tests)
- [10. Security Review of the Observe Layer](#10-security-review-of-the-observe-layer)
  - [10.1. Docker Socket Inventory](#101-docker-socket-inventory)
  - [10.2. What Limits the Risk Today](#102-what-limits-the-risk-today)
  - [10.3. Open Items](#103-open-items)
  - [10.4. Expected End State](#104-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 9. Uptime Kuma: Is It Actually Answering?
This section adds checks that test each service the way a user or a dependency would, and records when they fail.

#### 9.1. Why "Up" Isn't Enough
Case 02 already separated *running* from *working* with healthchecks. But a healthcheck runs inside the container. It can't see a broken Cloudflare setting, an expired edge certificate, a `DOCKER-USER` rule that drops legitimate traffic or a router with a typo in its host rule. The site can be down for users while every container reports `healthy`.

Uptime Kuma closes that gap from two sides:

- **from outside in**: it requests the public site through Cloudflare, exactly like a visitor, and checks that real content comes back;
- **from inside**: it reads each container's state and healthcheck result through the Docker API.

#### 9.2. The Uptime Kuma Container
<details>
<summary><b>▶ View config — /srv/apps/uptime-kuma/docker-compose.yml</b></summary>

```bash
sudo mkdir -p /srv/apps/uptime-kuma /srv/data/uptime-kuma
sudo nano /srv/apps/uptime-kuma/docker-compose.yml
```
```yaml
services:
  uptime-kuma:
    image: louislam/uptime-kuma:1.23.x   # TODO(verify): exact pinned tag from the server
    container_name: uptime-kuma
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    volumes:
      - /srv/data/uptime-kuma:/app/data                  # SQLite: monitors, history, settings
      - /var/run/docker.sock:/var/run/docker.sock:ro     # container monitors (root-equivalent)
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.uptime.rule=Host(`uptime.mysite.com`)"
      - "traefik.http.routers.uptime.entrypoints=websecure"
      - "traefik.http.routers.uptime.tls=true"
      - "traefik.http.routers.uptime.middlewares=vpn-allowlist@file,security-headers@file"
      - "traefik.http.services.uptime.loadbalancer.server.port=3001"

networks:
  proxy:
    external: true
```
</details>

| Choice | Why |
| :--- | :--- |
| Pinned tag | A major-version tag like `:1` moves on every release. Updates go through the Case 02 change cycle. |
| No healthcheck in Compose | The image ships its own `HEALTHCHECK`; `docker ps` shows its result. <!-- TODO(verify): (healthy) shown on the server --> |
| On `proxy` | Traefik reaches the UI, and Kuma can reach other UIs' internal health endpoints. |

```bash
cd /srv/apps/uptime-kuma && docker compose up -d
```
Then, over the VPN, open `https://uptime.mysite.com` and create the admin account. In **Settings → Docker Hosts**, add the local socket (`/var/run/docker.sock`) so container monitors can use it.

#### 9.3. Monitors

| Monitor | Type | Target | What it proves |
| :--- | :--- | :--- | :--- |
| **Public site** | HTTP(s) – Keyword | `https://mysite.com`, a word that always renders on the page | The whole public path works: Cloudflare → `DOCKER-USER` → Traefik → app, **and** the app renders real content, not an error page |
| **Edge certificate** | HTTP(s), *Certificate Expiry Notification* on | `https://mysite.com` | The certificate visitors see won't expire unnoticed |
| **Traefik** | Docker Container | `traefik` | The ingress is running and its healthcheck passes |
| **Client site** | Docker Container | the site's container | The site's own container is running |
| **Observe layer** | Docker Container | `loki`, `promtail`, `grafana`, `netdata`, `portainer` | The tools that watch the platform are themselves watched |
| **Grafana API** | HTTP(s) | `http://grafana:3000/api/health` (over `proxy`) | The log UI answers, not only its process |

Every monitor runs every 60 seconds and needs 3 consecutive failures before it's marked down, so a single slow response doesn't count as an outage.

> [!NOTE]
> The **Public site** check leaves the VPS, goes to Cloudflare and comes back in through Cloudflare's addresses. That's what makes it end to end: it would fail if the origin certificate, the WAF, the `DOCKER-USER` filter or the router were wrong, even if every container reported `healthy`.

![Uptime Kuma: public site, edge certificate and every container monitor up](./images/uptime-kuma-monitors.png)
<!-- TODO(screenshot): uptime-kuma-monitors.png -->

#### 9.4. Monitoring Without Flattening the Networks
The client's site is a single container today, but the platform is built for stacks with databases (Case 02), so the rule is set now. The obvious way to check a database is a TCP check on its port. But the database is on its stack's internal network, and Kuma isn't. Adding the database to `proxy`, or Kuma to the database's network, would undo exactly what Case 02 built: a database reachable only by its own application.

So the database is checked through the **Docker API** instead (*Docker Container* monitor): Kuma reads the container's state and healthcheck result, and the healthcheck itself (`pg_isready` or equivalent, Case 02) runs inside the database's own network. The network topology stays exactly as designed; the monitoring adapts to it, not the other way round.

#### 9.5. Alert Routing

> [!IMPORTANT]
> **Status: not configured yet.** Monitors run and keep history, but a failure is only seen when someone opens the dashboard. Monitoring that nobody is notified about only helps after the fact.
>
> Next step: one notification channel (Telegram or email) on every monitor, with a test notification recorded here. Until then, availability is visible but not alerted.

#### 9.6. Mandatory Tests
<details>
<summary><b>▶ View tests — Kuma detects a real failure</b></summary>

**Test 1: a stopped container is detected**
```bash
docker stop grafana
```
Within about 3 minutes (3 failed checks at 60 s), the *Grafana API* and *grafana* container monitors turn red.
```bash
docker start grafana
```
Both turn green again, and the incident appears in each monitor's history with its duration.

**Test 2: a broken page is detected, not just a dead server**

Temporarily change the *Public site* keyword to a word that doesn't appear on the page. The monitor must turn red even though the site returns `200`. Change it back.

**Tests 3–5:** run the [Phase 1 access tests](./01-observability-model-access.md#24-mandatory-tests) with `uptime.mysite.com`.
</details>

---

### 10. Security Review of the Observe Layer
This section applies the same scrutiny to the observe layer as to the platform it watches, starting with the most sensitive thing it touches.

#### 10.1. Docker Socket Inventory
Whoever can talk to the Docker socket can start a privileged container that mounts the host's filesystem: that's root. Mounting the socket `:ro` doesn't change that; it only stops the container from replacing the socket file. After this case, five containers hold it:

| Container | Why it needs the socket | Faces the internet | Reachable by | Network |
| :--- | :--- | :---: | :--- | :--- |
| **Traefik** (Case 02) | Discover containers and their labels | **Yes** | Cloudflare (public), VPN (dashboard) | `proxy` |
| **Promtail** | Discover containers and read their logs | No | Nobody | `loki-internal` (no route out) |
| **Netdata** | Name containers in the charts | No | VPN only | `proxy` |
| **Uptime Kuma** | Read container state for monitors | No | VPN only | `proxy` |
| **Portainer** | Manage containers (by design) | No | VPN only | `proxy` |

Each one is a path to root if it's compromised. Listing them is the point: a root-equivalent component that nobody wrote down is how a monitoring tool becomes the way in.

<details>
<summary><b>▶ View command — finding every socket mount on the host</b></summary>

```bash
docker ps -q | xargs docker inspect --format \
  '{{.Name}}{{range .Mounts}}{{if eq .Source "/var/run/docker.sock"}} -> docker.sock{{end}}{{end}}' \
  | grep docker.sock
```
```text
/traefik -> docker.sock
/promtail -> docker.sock
/netdata -> docker.sock
/uptime-kuma -> docker.sock
/portainer -> docker.sock
```
</details>

#### 10.2. What Limits the Risk Today
- **Only one of them faces the internet.** Traefik is the single public component, and it has been since Case 02. The other four are behind the VPN, `vpn-allowlist` and their own logins, or not reachable at all (Promtail).
- **`no-new-privileges`** on every one of them, so a process inside can't gain privileges through setuid binaries.
- **Pinned images and the Case 02 change cycle**, so security patches are applied deliberately and can be rolled back.
- **The audit trail from Phase 4**: SSH logins, `sudo` and container output are recorded, so unexpected activity can be reconstructed.

#### 10.3. Open Items
The review also names what isn't done yet. Each item has a concrete next step:

| # | Item | Why it matters | Next step |
| :---: | :--- | :--- | :--- |
| 1 | **Docker socket proxy** for Traefik, Promtail, Netdata and Kuma | They only need read-only API calls (list containers, read events and logs), but the raw socket gives them everything | Put a socket proxy in front of the API that allows only those `GET` endpoints; keep the full socket for Portainer only |
| 2 | **Alert routing** for Uptime Kuma | Failures are recorded but not notified ([9.5](#95-alert-routing)) | One channel (Telegram or email) on every monitor, plus a recorded test notification |
| 3 | **Promtail → Grafana Alloy** | Promtail is deprecated and won't receive new features | Migrate the three jobs in 7.3 to Alloy and repeat the Phase 4 tests |
| 4 | **Image updates and scanning** | Pinned tags stop surprise upgrades but can't reveal known CVEs inside the pinned version | Scan images (e.g. Trivy) as a step of the Case 02 change cycle, and update the observe stack's tags through it |

#### 10.4. Expected End State
- Uptime Kuma runs on a pinned tag and is reachable only through the VPN;
- the public site is checked end to end through Cloudflare, with a keyword and certificate expiry;
- the client's container and every container of the observe layer are checked through the Docker API, without changing any network;
- a stopped container and a broken page are both detected and recorded with their duration;
- every Docker-socket consumer is listed with its justification, and the open items above are tracked.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case03-phase5-observe-ok` and delete the previous one.

---

> This closes the observe layer. The platform is no longer a black box: metrics show how much, logs show what happened, availability checks show whether it answers, and none of it is reachable from the internet. The next step is resilience: proving the platform can be recovered when something is lost, in [Case 04](../case-04-backup-recovery-drills/00-overview.md).

---

[← Phase 4: Centralized Logs](./04-centralized-logs.md) · **Phase 5 of 5** · [Back to Overview →](./00-overview.md)
