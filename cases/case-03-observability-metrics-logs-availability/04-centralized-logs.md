# Phase 4: Centralized Logs (Loki, Promtail & Grafana)

[← Phase 3: Metrics with Netdata](./03-metrics-netdata.md) · **Phase 4 of 5** · [Next: Availability & Socket Review →](./05-availability-socket-review.md)

---

### In this phase
- [6. Log Pipeline Design](#6-log-pipeline-design)
  - [6.1. Why Centralize Logs?](#61-why-centralize-logs)
  - [6.2. Chosen Stack](#62-chosen-stack)
  - [6.3. Pipeline and Network Isolation](#63-pipeline-and-network-isolation)
  - [6.4. What Gets Collected](#64-what-gets-collected)
- [7. Deploying the Stack](#7-deploying-the-stack)
  - [7.1. Directories and Ownership](#71-directories-and-ownership)
  - [7.2. Persistent Journal](#72-persistent-journal)
  - [7.3. Promtail Configuration](#73-promtail-configuration)
  - [7.4. Loki Configuration and Retention](#74-loki-configuration-and-retention)
  - [7.5. Grafana Data Source and Admin Secret](#75-grafana-data-source-and-admin-secret)
  - [7.6. The Compose Stack](#76-the-compose-stack)
  - [7.7. Rotating Traefik's Log Files](#77-rotating-traefiks-log-files)
  - [7.8. Start and Verify](#78-start-and-verify)
- [8. Using the Logs](#8-using-the-logs)
  - [8.1. Security Queries](#81-security-queries)
  - [8.2. The Log Dashboard](#82-the-log-dashboard)
  - [8.3. Mandatory Tests](#83-mandatory-tests)
  - [8.4. Expected End State](#84-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 6. Log Pipeline Design
This section decides what is collected, where it's stored, who can reach it and how long it's kept, before writing any configuration.

#### 6.1. Why Centralize Logs?
Without a pipeline, the logs on this platform are:

- **ephemeral**: container output lives with the container. Recreating it, which the Case 02 change cycle does on every update, discards its history;
- **fragmented**: container output is in `docker logs`, SSH and `sudo` are in the journal, every HTTP request is in Traefik's `access.log` file. Correlating "what happened at 03:12" means three tools and an SSH session;
- **unbounded**: Traefik's log files have no rotation of their own and grow until the disk is full.

A central pipeline fixes all three: one place to search, history that survives container recreation, and retention that cleans up after itself.

#### 6.2. Chosen Stack

| Component | Role | Why it fits |
| :--- | :--- | :--- |
| **Promtail** | Collector: reads containers through the Docker API, the journal and Traefik's access log, and pushes to Loki | Built for Loki, discovers containers on its own, ~30 MB of RAM |
| **Loki** | Store: indexes labels, keeps compressed chunks, enforces retention | Indexes labels instead of full text, so it runs in a few hundred MB. ELK would need gigabytes. |
| **Grafana** | Lens: search, LogQL, a small dashboard | Loki has no UI of its own. Grafana is used for **logs only**; metrics stay in Netdata. |

> [!NOTE]
> Promtail is deprecated in favor of **Grafana Alloy**. It's still what this pipeline runs on, and it works, but it won't receive new features. Migrating to Alloy is tracked in [Phase 5, 10.3](./05-availability-socket-review.md#103-open-items).

#### 6.3. Pipeline and Network Isolation
Loki has no authentication of its own in single-tenant mode (`auth_enabled: false`). So its protection is the network: **nothing but Promtail and Grafana can reach it, and it can't reach anything.**

```text
 Host                                   Docker
 ─────────────────────────────          ─────────────────────────────────────────────────
 Docker API (socket) ──┐
 /var/log/journal ─────┼──► Promtail ──► loki-internal (internal: no route out) ──► Loki
 /srv/logs/traefik ────┘                                     ▲
                                                             │ query
                                         proxy ◄─── Grafana ─┘
                                           ▲
                         Traefik router + vpn-allowlist (Phase 1)
                                           ▲
                                    Admin device (VPN)
```

| Container | Networks | Reachable from | Can reach |
| :--- | :--- | :--- | :--- |
| **Loki** | `loki-internal` | Promtail, Grafana | Nothing outside `loki-internal` |
| **Promtail** | `loki-internal` | Nobody | Loki, plus the host sources it mounts |
| **Grafana** | `loki-internal` + `proxy` | Traefik (VPN-only router) | Loki; the internet through `proxy` |

`loki-internal` is declared `internal: true`: it has no gateway, so a compromised Loki or Promtail has no path to the internet and no path to any other stack. Only Grafana, the one component a human uses, joins `proxy`.

#### 6.4. What Gets Collected

| Job | Source | What it contains | Why it matters |
| :--- | :--- | :--- | :--- |
| `docker` | Docker API (every container, present and future) | stdout/stderr of each service | Application errors, crashes, restarts |
| `journal` | systemd journal | `sshd`, `sudo`, Fail2ban, the kernel, every systemd unit | Admin access, privilege use, bans, OOM kills |
| `traefik` | `/srv/logs/traefik/access.log` (JSON, Case 02) | One line per HTTP request: host, router, status, real client IP | Who asked for what, and what they got |

> [!IMPORTANT]
> **AlmaLinux keeps authentication logs in the journal, not in `/var/log/auth.log`.** That file is a Debian/Ubuntu convention; on the RHEL family the equivalent is `/var/log/secure`, and only when `rsyslog` is installed. Case 01's Fail2ban already reads the journal (`backend = systemd`) for the same reason, so the log pipeline reads the same source.

> [!NOTE]
> Because WAN `:22` is dropped before it reaches `sshd` (Case 01), the `sshd` lines in the journal aren't internet noise. They're the audit trail of legitimate admin access through the VPN. That makes them more useful, not less: every line is either me or something I need to explain.

---

### 7. Deploying the Stack
This section writes the three configurations and the Compose stack, with every component running as the user its image expects.

#### 7.1. Directories and Ownership
Loki and Grafana don't run as root. Their images run as fixed, unprivileged UIDs, so the data directories are owned by those UIDs, exactly like the permission model in Case 02.

<details>
<summary><b>▶ View commands — directories and ownership</b></summary>

```bash
# Configuration
sudo mkdir -p /srv/apps/loki/grafana/provisioning/datasources /srv/apps/loki/secrets

# Persistent state
sudo mkdir -p /srv/data/loki/data /srv/data/loki/promtail /srv/data/grafana

# Loki runs as UID 10001, Grafana as UID 472 (group 0)
sudo chown -R 10001:10001 /srv/data/loki/data
sudo chown -R 472:0 /srv/data/grafana
```
</details>

| Container | Runs as | Why |
| :--- | :--- | :--- |
| Loki | `10001` (image default) | Writes only its own chunks and index under `/srv/data/loki/data` |
| Grafana | `472` (image default) | Writes only its own database under `/srv/data/grafana` |
| Promtail | `root` | Reads the journal and the Docker socket, which are root-only on the host |

> [!WARNING]
> The common shortcut, `user: "0"` on Loki and Grafana, makes permission errors disappear by running the store and the UI as root. It's the same mistake Case 02 avoided for application containers: a bug in either one would get root's file access inside the container. Fixing ownership once is the right fix.

#### 7.2. Persistent Journal
Promtail reads the journal from `/var/log/journal`. On AlmaLinux journald stores logs there only if the directory exists; otherwise they live in `/run` and vanish on reboot.

```bash
ls -d /var/log/journal 2>/dev/null || {
  sudo mkdir -p /var/log/journal
  sudo systemd-tmpfiles --create --prefix /var/log/journal
  sudo systemctl restart systemd-journald
}
journalctl --disk-usage
```

#### 7.3. Promtail Configuration
<details>
<summary><b>▶ View config — /srv/apps/loki/promtail-config.yml</b></summary>

```bash
sudo nano /srv/apps/loki/promtail-config.yml
```
```yaml
# =============================================================================
# Promtail - containers, host journal and Traefik access log
# =============================================================================

server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /positions/positions.yaml   # persisted: a restart resumes, it doesn't re-send

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:

  # ---------------------------------------------------------------------------
  # Container stdout/stderr, discovered through the Docker API
  # ---------------------------------------------------------------------------
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.*)'
        target_label: 'container'
      - source_labels: ['__meta_docker_container_log_stream']
        target_label: 'stream'
      - source_labels: ['__meta_docker_container_label_com_docker_compose_project']
        target_label: 'compose_project'
      - target_label: 'job'
        replacement: 'docker'
      - target_label: 'host'
        replacement: 'srv01'

  # ---------------------------------------------------------------------------
  # Host journal: sshd, sudo, Fail2ban, kernel, every systemd unit
  # ---------------------------------------------------------------------------
  - job_name: journal
    journal:
      path: /var/log/journal
      max_age: 12h                       # on first start, read at most 12 h back
      labels:
        job: journal
        host: srv01
    relabel_configs:
      - source_labels: ['__journal__systemd_unit']
        target_label: 'unit'
      - source_labels: ['__journal_syslog_identifier']
        target_label: 'identifier'
      - source_labels: ['__journal_priority_keyword']
        target_label: 'level'

  # ---------------------------------------------------------------------------
  # Traefik access log: one JSON line per request (Case 02)
  # ---------------------------------------------------------------------------
  - job_name: traefik
    static_configs:
      - targets: [localhost]
        labels:
          job: traefik
          host: srv01
          __path__: /srv/logs/traefik/access.log
    pipeline_stages:
      - json:
          expressions:
            status: DownstreamStatus
            router: RouterName
            time: time
      - labels:
          status:
          router:
      - timestamp:
          source: time
          format: RFC3339
```
</details>

| Decision | Why |
| :--- | :--- |
| `docker_sd_configs` instead of reading `/var/lib/docker/containers` | Discovers new containers on its own and gets clean labels from their Compose metadata. |
| `journal` instead of log files | It's where AlmaLinux keeps `sshd`, `sudo` and the kernel. It's structured, so `unit` and `identifier` become labels. |
| `status` and `router` as labels | A handful of values each, so queries like "every `403` per router" are cheap. |
| The client IP is **not** a label | It's high-cardinality and it's personal data. It stays inside the log line and is parsed at query time (8.1). |
| Positions file on a volume | After a restart Promtail resumes where it stopped instead of re-sending or skipping lines. |

#### 7.4. Loki Configuration and Retention
<details>
<summary><b>▶ View config — /srv/apps/loki/loki-config.yml</b></summary>

```bash
sudo nano /srv/apps/loki/loki-config.yml
```
```yaml
# =============================================================================
# Loki - single node, filesystem storage, 7-day retention
# =============================================================================

auth_enabled: false            # single tenant; access is controlled by the network (6.3)

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  instance_addr: 127.0.0.1
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: 168h       # 7 days
  max_query_parallelism: 2     # keep queries from saturating a small VPS

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m
  retention_enabled: true      # without this, retention_period is never enforced
  retention_delete_delay: 2h
  delete_request_store: filesystem
```
</details>

| Setting | Why |
| :--- | :--- |
| `retention_period: 168h` | 7 days covers "what happened last week" and keeps disk use in the low gigabytes at this traffic level. |
| `retention_enabled: true` | Retention is enforced by the compactor. Setting the period without enabling it deletes nothing. |
| `max_query_parallelism: 2` | A broad query over 7 days can't starve the services the VPS exists for. |

#### 7.5. Grafana Data Source and Admin Secret
The Loki data source is provisioned from a file, so a rebuilt Grafana comes back connected without clicking through the UI:

<details>
<summary><b>▶ View config — /srv/apps/loki/grafana/provisioning/datasources/loki.yml</b></summary>

```bash
sudo nano /srv/apps/loki/grafana/provisioning/datasources/loki.yml
```
```yaml
apiVersion: 1
datasources:
  - name: Loki
    type: loki
    access: proxy             # Grafana's backend queries Loki; the browser never talks to it
    url: http://loki:3100
    isDefault: true
```
</details>

The admin password is a file, not an environment variable written in the Compose file:

<details>
<summary><b>▶ View commands — Grafana admin secret</b></summary>

```bash
openssl rand -base64 32 | sudo tee /srv/apps/loki/secrets/grafana_admin_password >/dev/null
sudo chown 472:0 /srv/apps/loki/secrets/grafana_admin_password
sudo chmod 0400 /srv/apps/loki/secrets/grafana_admin_password
```
</details>

> [!NOTE]
> Grafana reads the admin password only when it creates its database, on the first start. Changing the file later doesn't change the password; that's done with `docker compose exec grafana grafana cli admin reset-admin-password`.

#### 7.6. The Compose Stack
<details>
<summary><b>▶ View config — /srv/apps/loki/docker-compose.yml</b></summary>

```bash
sudo nano /srv/apps/loki/docker-compose.yml
```
```yaml
services:

  # ---------------------------------------------------------------------------
  # Loki - log store (no published port, no route to the internet)
  # ---------------------------------------------------------------------------
  loki:
    image: grafana/loki:3.0.0          # TODO(verify): exact tag from the server
    container_name: loki
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    command: -config.file=/etc/loki/local-config.yaml
    volumes:
      - /srv/apps/loki/loki-config.yml:/etc/loki/local-config.yaml:ro
      - /srv/data/loki/data:/loki
    networks:
      - loki-internal
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:3100/ready | grep -q ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  # ---------------------------------------------------------------------------
  # Promtail - collector (runs as root: journal + Docker socket)
  # ---------------------------------------------------------------------------
  promtail:
    image: grafana/promtail:3.0.0      # TODO(verify): exact tag from the server
    container_name: promtail
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    command: -config.file=/etc/promtail/config.yml
    volumes:
      - /srv/apps/loki/promtail-config.yml:/etc/promtail/config.yml:ro
      - /srv/data/loki/promtail:/positions
      - /var/run/docker.sock:/var/run/docker.sock:ro    # container discovery (root-equivalent)
      - /var/log/journal:/var/log/journal:ro            # persistent journal
      - /run/log/journal:/run/log/journal:ro            # volatile journal (early boot)
      - /etc/machine-id:/etc/machine-id:ro              # journal file lookup
      - /srv/logs/traefik:/srv/logs/traefik:ro          # Traefik access log
    networks:
      - loki-internal
    depends_on:
      loki:
        condition: service_healthy

  # ---------------------------------------------------------------------------
  # Grafana - log UI only, VPN-only router
  # ---------------------------------------------------------------------------
  grafana:
    image: grafana/grafana:11.0.0      # TODO(verify): exact tag from the server
    container_name: grafana
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    volumes:
      - /srv/data/grafana:/var/lib/grafana
      - /srv/apps/loki/grafana/provisioning:/etc/grafana/provisioning:ro
    environment:
      - GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_admin_password
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_ANALYTICS_REPORTING_ENABLED=false
      - GF_SERVER_ROOT_URL=https://grafana.mysite.com
    secrets:
      - grafana_admin_password
    networks:
      - loki-internal
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=proxy"   # two networks: tell Traefik which one to use
      - "traefik.http.routers.grafana.rule=Host(`grafana.mysite.com`)"
      - "traefik.http.routers.grafana.entrypoints=websecure"
      - "traefik.http.routers.grafana.tls=true"
      - "traefik.http.routers.grafana.middlewares=vpn-allowlist@file,security-headers@file"
      - "traefik.http.services.grafana.loadbalancer.server.port=3000"
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    depends_on:
      loki:
        condition: service_healthy

secrets:
  grafana_admin_password:
    file: /srv/apps/loki/secrets/grafana_admin_password

networks:
  loki-internal:
    name: loki-internal
    internal: true      # no gateway: Loki and Promtail can't reach the internet
  proxy:
    external: true
```
</details>

| Choice | Why |
| :--- | :--- |
| `internal: true` on `loki-internal` | The store and the collector need no internet. Without a gateway, a compromise of either one can't call out. |
| `name: loki-internal` | Fixes the network name so tests and inspection don't depend on the Compose project prefix. |
| `traefik.docker.network=proxy` | Grafana is on two networks; Traefik must reach it over `proxy`, never over `loki-internal`. |
| `GF_SECURITY_ADMIN_PASSWORD__FILE` | The password lives in a `0400` file read by UID 472, not in plain text in the Compose file or in `docker inspect`. |
| `GF_ANALYTICS_REPORTING_ENABLED=false` | No usage reporting from this server. |
| Pinned tags | Updated through the Case 02 change cycle, like every other image. |

#### 7.7. Rotating Traefik's Log Files
Traefik writes `access.log` and `traefik.log` under `/srv/logs/traefik` but never rotates them. Loki's retention cleans up Loki's copy, not the source files. Without rotation they grow until the disk is full.

<details>
<summary><b>▶ View config — /etc/logrotate.d/traefik</b></summary>

```bash
sudo nano /etc/logrotate.d/traefik
```
```text
/srv/logs/traefik/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        # USR1 makes Traefik close and reopen its log files
        docker kill --signal=USR1 traefik >/dev/null 2>&1 || true
    endscript
}
```

```bash
sudo logrotate --debug /etc/logrotate.d/traefik     # dry run: shows what would happen
```
</details>

Promtail follows the rename and keeps reading the new `access.log`; the positions file means no line is sent twice.

#### 7.8. Start and Verify
```bash
cd /srv/apps/loki && docker compose up -d
docker compose ps
```
```text
NAME       IMAGE                    STATUS
grafana    grafana/grafana:11.0.0   Up 1 minute (healthy)
loki       grafana/loki:3.0.0       Up 1 minute (healthy)
promtail   grafana/promtail:3.0.0   Up 1 minute
```

> [!NOTE]
> Wait about 30 seconds for Loki to report `ready`. Promtail and Grafana wait for it (`depends_on: service_healthy`).

---

### 8. Using the Logs
This section turns the stored logs into answers: the queries a security reviewer asks first, and a small dashboard that keeps them one click away.

#### 8.1. Security Queries
Run in Grafana → **Explore** → data source **Loki**.

| Question | LogQL |
| :--- | :--- |
| Who logged in over SSH? | `{job="journal", unit="sshd.service"} \|= "Accepted publickey"` |
| Which SSH attempts were rejected (inside the VPN)? | `{job="journal", unit="sshd.service"} \|~ "Invalid user\|authenticating user"` |
| Which commands ran with `sudo`? | `{job="journal", identifier="sudo"} \|= "COMMAND="` |
| What did Fail2ban ban? | `{job="journal", unit="fail2ban.service"} \|= "Ban "` |
| Did the kernel kill anything for memory? | `{job="journal", identifier="kernel"} \|= "Out of memory"` |
| Is anyone reaching admin routers from outside the VPN? | `sum by (router) (count_over_time({job="traefik", status="403"}[1h]))` |
| Is any service failing? | `sum by (router) (rate({job="traefik", status=~"5.."}[5m]))` |
| Which clients are behind a 4xx burst? | `topk(10, sum by (request_Cf_Connecting_Ip) (count_over_time({job="traefik", status=~"4.."} \| json [1h])))` |
| Which containers are logging errors? | `sum by (container) (count_over_time({job="docker"} \|~ "(?i)(error\|fatal\|panic)" [15m]))` |

> [!NOTE]
> The client IP comes from the `CF-Connecting-IP` header that Case 02 keeps in the access log. LogQL's `| json` turns the field `request_Cf-Connecting-Ip` into the label name `request_Cf_Connecting_Ip` at query time, so it never becomes an indexed label (7.3).

> [!IMPORTANT]
> A `403` from `vpn-allowlist` is the signal that matters most here. Admin routers are only resolvable to `10.10.10.1`, so a `403` on one of them means a request reached Traefik for an admin hostname from somewhere other than the VPN. On this platform that should be zero. A non-zero count is something to investigate, not noise.

#### 8.2. The Log Dashboard
Grafana here is for logs, not for metric dashboards (that's Netdata). One dashboard keeps the security queries one click away:

| Panel | Query | Visualization |
| :--- | :--- | :--- |
| Requests by status | `sum by (status) (rate({job="traefik"}[5m]))` | Time series |
| `403` on admin routers | `sum by (router) (count_over_time({job="traefik", status="403"}[$__range]))` | Table |
| Admin logins | `{job="journal", unit="sshd.service"} \|= "Accepted publickey"` | Logs |
| `sudo` commands | `{job="journal", identifier="sudo"} \|= "COMMAND="` | Logs |
| Container errors | `{job="docker"} \|~ "(?i)(error\|fatal\|panic)"` | Logs |
| Log volume by source | `sum by (job) (rate({host="srv01"}[5m]))` | Time series |

![Grafana Explore: Traefik requests by status and router](./images/grafana-explore-traefik.png)
<!-- TODO(screenshot): grafana-explore-traefik.png -->

> [!WARNING]
> Before taking or sharing a screenshot of this dashboard, blur client IP addresses and anything that identifies a visitor. Access logs contain personal data.

#### 8.3. Mandatory Tests
<details>
<summary><b>▶ View tests — collection, isolation, retention and access</b></summary>

**Test 1: every source is indexed**
```bash
cd /srv/apps/loki
docker compose exec grafana wget -qO- http://loki:3100/loki/api/v1/labels
```
```text
{"status":"success","data":["compose_project","container","host","identifier","job","level","router","status","stream","unit"]}
```

**Test 2: a journal line arrives within seconds**
```bash
logger -t case03-test "loki ingestion test"
```
In Grafana → Explore: `{job="journal", identifier="case03-test"}` returns the line.

**Test 3: Loki isn't reachable from the `proxy` network**
```bash
docker run --rm --network proxy curlimages/curl -s -m 5 http://loki:3100/ready; echo "exit=$?"
```
```text
exit=6
```
Exit code 6 means the name `loki` doesn't even resolve from `proxy`.

**Test 4: `loki-internal` has no route to the internet**
```bash
docker run --rm --network loki-internal curlimages/curl -s -m 5 https://example.com; echo "exit=$?"
```
```text
exit=6
```
<!-- TODO(verify): exit code on the server (6 = no DNS, 7 = no route); any non-zero code passes -->
Any non-zero exit code passes: there's no gateway, so the request can't leave.

**Test 5: retention is active**
```bash
docker compose exec grafana wget -qO- http://loki:3100/config | grep -E 'retention_period|retention_enabled'
```
```text
  retention_period: 1w
  retention_enabled: true
```
<!-- TODO(verify): exact output format from the server -->

**Test 6: Loki and Grafana don't run as root**
```bash
docker top loki -o uid,comm; docker top grafana -o uid,comm
```
```text
UID     COMMAND
10001   loki
UID     COMMAND
472     grafana
```
`docker top` reads the processes from the host, so it works even on images without a shell.

**Tests 7–9:** run the [Phase 1 access tests](./01-observability-model-access.md#24-mandatory-tests) with `grafana.mysite.com`.
</details>

#### 8.4. Expected End State
- container output, the host journal and the Traefik access log are all searchable in Grafana;
- Loki and Promtail are on an internal network with no route out; only Grafana joins `proxy`;
- Loki and Grafana run as their image UIDs, not as root; the Grafana admin password is a `0400` file;
- logs are kept 7 days and deleted automatically; Traefik's source files rotate daily;
- the security queries in 8.1 return results and the dashboard in 8.2 exists;
- Grafana is reachable only through the VPN.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case03-phase4-logs-ok` and delete the previous one.

---

> The platform now records what happened, and keeps it for a week. The last phase checks the one thing logs and metrics can't prove on their own: that each service actually answers.

---

[← Phase 3: Metrics with Netdata](./03-metrics-netdata.md) · **Phase 4 of 5** · [Next: Availability & Socket Review →](./05-availability-socket-review.md)
