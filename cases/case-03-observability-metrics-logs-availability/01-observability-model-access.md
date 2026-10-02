# Phase 1: Observability Model & the VPN-only Access Pattern

[← Overview](./00-overview.md) · **Phase 1 of 5** · [Next: Host & Container Views →](./02-host-and-container-views.md)

---

### In this phase
- [Before Starting](#before-starting)
- [1. What This Platform Must Show](#1-what-this-platform-must-show)
  - [1.1. Monitoring vs Observability](#11-monitoring-vs-observability)
  - [1.2. Three Signals, Three Questions](#12-three-signals-three-questions)
  - [1.3. Why These Tools (and Not Prometheus or ELK)](#13-why-these-tools-and-not-prometheus-or-elk)
  - [1.4. Signals to Read First](#14-signals-to-read-first)
- [2. The Access Pattern for Every Dashboard](#2-the-access-pattern-for-every-dashboard)
  - [2.1. Every Dashboard Is Part of the Admin Plane](#21-every-dashboard-is-part-of-the-admin-plane)
  - [2.2. Split-Horizon DNS Records](#22-split-horizon-dns-records)
  - [2.3. The Router Template](#23-the-router-template)
  - [2.4. Mandatory Tests](#24-mandatory-tests)
  - [2.5. Expected End State](#25-expected-end-state)

---

## Configuration Artifacts & Reference Code

### Before Starting
Everything in this case is done through the private admin tunnel from Case 01 and on the platform from Case 02: the `proxy` network, Traefik v3, the `vpn-allowlist` and `security-headers` middlewares, and the Origin CA trusted on the admin device ([Case 02, 9.2](../case-02-container-platform-and-traefik-ingress/05-traefik-ingress.md#92-vpn-only-dashboard-split-horizon-dns)).

> [!WARNING]
> Take a snapshot before starting: in the VPS panel, create a manual snapshot named `pre-case03-observe`. Every tool in this case adds containers and configuration; this is the way back to the Case 02 end state.

---

### 1. What This Platform Must Show
This section decides what "visible" means before installing anything, so every tool that follows has one clear job.

#### 1.1. Monitoring vs Observability
**Monitoring** answers a question I already know to ask: *is CPU above 90%?*, *is the site up?* It's reactive and works on known failure modes.

**Observability** lets me answer questions I didn't know I'd need: *why did the site slow down at 03:12, and what else happened at that moment?* It needs enough raw data, kept long enough and correlated in one place, to reconstruct what happened after the fact.

On a single VPS I need both, but at a scale that one person can operate. Distributed tracing is out of scope: there's one host and a handful of services, so request paths are short and logs plus metrics are enough to reconstruct them.

#### 1.2. Three Signals, Three Questions

| Signal | Question it answers | Tool | Granularity / retention |
| :--- | :--- | :--- | :--- |
| **Metrics** | *How much?* CPU, load, memory, disk, network, per container | Netdata | 1 second, local storage |
| **Logs** | *What happened?* Container output, journal, every HTTP request | Loki + Promtail, read in Grafana | Per event, 7 days |
| **Availability** | *Is it answering?* End to end, per service | Uptime Kuma | Every 60 seconds, with history |

Two views sit beside them for operating the host and the containers: **Cockpit** (systemd units, disks, journal, updates) and **Portainer** (containers, networks, volumes). They're for inspection; changes still go through the CLI and the Compose files under `/srv/apps`.

#### 1.3. Why These Tools (and Not Prometheus or ELK)

| Need | Chosen | Considered | Why the choice fits this platform |
| :--- | :--- | :--- | :--- |
| Metrics | Netdata | Prometheus + Node Exporter + cAdvisor + Grafana | One container, autodiscovery, 1-second resolution and built-in dashboards. Four components to run and update would be more surface than value on one host. |
| Logs | Loki + Promtail | ELK, Graylog, Dozzle | ELK and Graylog need gigabytes of RAM and extra databases. Dozzle keeps no history. Loki indexes labels instead of full text, so it runs in a few hundred MB. |
| Log UI | Grafana (logs only) | `curl` against the Loki API | Loki has no UI. Grafana is used **only** for logs: metrics stay in Netdata, so nothing is duplicated. |
| Availability | Uptime Kuma | External SaaS monitors | Self-hosted, checks both the public path and internal container health, keeps its history locally. |

> [!NOTE]
> Promtail is deprecated in favor of **Grafana Alloy**. It still runs here because it's what this pipeline was built and validated with; the migration is an open item in [Phase 5](./05-availability-socket-review.md#103-open-items).

#### 1.4. Signals to Read First
Most incidents on a small VPS show up first in a handful of numbers. These are the ones I read before anything else, and what "bad" looks like:

| Metric | Watch for | Why |
| :--- | :--- | :--- |
| **Load average** | Sustained values above the number of CPU cores (`nproc`) | Load counts processes running *or waiting*. On 2 cores, a load of 4 means half of the work is queuing. |
| **CPU iowait** | Sustained high values | The CPU is idle because it's waiting for the disk. Adding CPU won't help. |
| **Memory: available** | Low `MemAvailable`, not low `free` | Linux uses free RAM as disk cache and gives it back on demand. `free` near zero is normal; `available` near zero is pressure. |
| **Disk free space** | Under 10% free | Logs, images and database growth fill disks quietly. A full disk stops databases and Docker itself. |
| **Container restarts** | A non-zero, growing restart count | A crash loop can look healthy between restarts. |

```bash
nproc                                   # number of cores: the reference for load
uptime                                  # load average over 1, 5 and 15 minutes
free -h                                 # read the "available" column, not "free"
df -h /                                 # free space on the root filesystem
docker ps --format '{{.Names}}\t{{.Status}}'   # look for "Restarting" or recent restarts
```

---

### 2. The Access Pattern for Every Dashboard
This section defines, once, how every administrative UI in this case is reached. Each later phase reuses it instead of inventing its own exposure.

#### 2.1. Every Dashboard Is Part of the Admin Plane
A monitoring dashboard is a map of the server: process names, container names, log lines, internal hostnames, sometimes credentials that leak into logs. Publishing one is publishing reconnaissance. So every UI in this case gets the same three layers that protect the Traefik dashboard in Case 02:

```text
Admin device (VPN up)
   │  DNS: grafana.mysite.com → 10.10.10.1  (DNS only, grey cloud)
   ▼
WireGuard tunnel (UDP 51820) ──► wg0 10.10.10.1
   │
   ▼
Traefik :443 ── router: Host(grafana.mysite.com)
   │            middlewares: vpn-allowlist@file → security-headers@file
   ▼
Grafana container (proxy network)
```

| Layer | What it stops |
| :--- | :--- |
| **Split-horizon DNS** | Off the VPN, the name resolves to `10.10.10.1`, which isn't routable. There's nothing to connect to. |
| **`vpn-allowlist` on the router** | A request that reaches Traefik from anywhere else (a Cloudflare edge address, a container, the host) gets `403`. |
| **The tool's own login** | Every UI keeps its own authentication on top. The network layers decide *who can reach the login page*; the login decides *who gets in*. |

Cockpit is the one exception to the router: it's a host service, not a container. It gets the same DNS model and is bound to the WireGuard address instead ([Phase 2](./02-host-and-container-views.md#33-listen-only-on-the-vpn-address)).

#### 2.2. Split-Horizon DNS Records
In Cloudflare, one record per UI, all pointing to the WireGuard address and all **DNS only**:

<details>
<summary><b>▶ View records — Cloudflare DNS for the admin UIs</b></summary>

| Type | Name | Value | Proxy | Purpose |
| :---: | :--- | :--- | :--- | :--- |
| **A** | `cockpit` | `10.10.10.1` | DNS Only (Grey ☁️) | Host view, port 9090 (Phase 2) |
| **A** | `portainer` | `10.10.10.1` | DNS Only (Grey ☁️) | Container view (Phase 2) |
| **A** | `netdata` | `10.10.10.1` | DNS Only (Grey ☁️) | Metrics (Phase 3) |
| **A** | `grafana` | `10.10.10.1` | DNS Only (Grey ☁️) | Logs (Phase 4) |
| **A** | `uptime` | `10.10.10.1` | DNS Only (Grey ☁️) | Availability (Phase 5) |

</details>

> [!WARNING]
> **Never orange-cloud these records.** Cloudflare can't reach `10.10.10.1`, so a proxied record would just fail. Worse, it would be a step toward publishing an admin UI. Each specific record overrides the proxied wildcard, exactly like `traefik` in Case 02.

> [!NOTE]
> The private address is visible in public DNS. That reveals an internal IP and the names of the tools, nothing more: neither is reachable without the VPN. It's the same trade-off accepted for `srv01` and `traefik` in Cases 01–02.

#### 2.3. The Router Template
Every containerized UI in this case is published with the same block of labels. Only the name, host and internal port change:

<details>
<summary><b>▶ View config — Traefik labels for a VPN-only UI</b></summary>

```yaml
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.<name>.rule=Host(`<name>.mysite.com`)"
      - "traefik.http.routers.<name>.entrypoints=websecure"
      - "traefik.http.routers.<name>.tls=true"
      - "traefik.http.routers.<name>.middlewares=vpn-allowlist@file,security-headers@file"
      - "traefik.http.services.<name>.loadbalancer.server.port=<internal-port>"
```
</details>

| Label | Why |
| :--- | :--- |
| `traefik.enable=true` | Nothing is routed without it (`exposedByDefault: false` in Case 02). |
| `entrypoints=websecure` + `tls=true` | HTTPS only, with the Origin certificate. Port 80 already redirects globally. |
| `vpn-allowlist@file` first | The source check runs before anything else: a non-VPN request never reaches the tool. |
| `loadbalancer.server.port` | The container's internal port. Nothing is published on the host. |

> [!IMPORTANT]
> No UI in this case uses `ports:`. If one ever did by mistake, the `DOCKER-USER` filter from Case 02 would still drop it at the WAN, but it would become reachable from the VPN without the allow-list. The template is the only supported way to publish a dashboard.

#### 2.4. Mandatory Tests
These tests run once per UI, as each one is deployed in the following phases. Grafana is used as the example.

<details>
<summary><b>▶ View tests — proving a UI is VPN-only</b></summary>

**Test 1: the name resolves to the private address**
```bash
dig +short grafana.mysite.com
```
```text
10.10.10.1
```

**Test 2: off the VPN, nothing answers** (VPN down on the admin device)
```bash
curl -sS -m 5 -o /dev/null -w '%{http_code}\n' https://grafana.mysite.com/
```
```text
curl: (28) Connection timed out after 5001 milliseconds
000
```

**Test 3: on the VPN, the tool answers** (VPN up)
```bash
curl -sS --cacert ~/origin_ca_rsa_root.pem -o /dev/null -w '%{http_code}\n' https://grafana.mysite.com/login
```
```text
200
```

**Test 4: reaching Traefik from anywhere but the VPN gets `403`** (on the server, not through the tunnel)
```bash
curl -sk -o /dev/null -w '%{http_code}\n' --resolve grafana.mysite.com:443:127.0.0.1 https://grafana.mysite.com/
```
```text
403
```
The request reaches Traefik from the host itself, so its source isn't in `10.10.10.0/24` and the allow-list rejects it before Grafana ever sees it.
</details>

#### 2.5. Expected End State
- every admin UI has a DNS-only record pointing to `10.10.10.1`, and none of them is proxied by Cloudflare;
- every containerized UI is published only through a Traefik router with `vpn-allowlist@file` and `security-headers@file`;
- no UI publishes a host port;
- off the VPN, every UI times out; from anywhere but the VPN, every router returns `403`.

---

> The access pattern is the contract for the rest of this case: every tool that follows is reached the same way, or not at all.

---

[← Overview](./00-overview.md) · **Phase 1 of 5** · [Next: Host & Container Views →](./02-host-and-container-views.md)
