# Phase 3: Host & Container Metrics with Netdata

[← Phase 2: Host & Container Views](./02-host-and-container-views.md) · **Phase 3 of 5** · [Next: Centralized Logs →](./04-centralized-logs.md)

---

### In this phase
- [5. Netdata: Metrics for the Host and Every Container](#5-netdata-metrics-for-the-host-and-every-container)
  - [5.1. Why Netdata?](#51-why-netdata)
  - [5.2. The Privileges It Needs](#52-the-privileges-it-needs)
  - [5.3. The Netdata Container](#53-the-netdata-container)
  - [5.4. Start and Verify](#54-start-and-verify)
  - [5.5. Reading the Dashboard](#55-reading-the-dashboard)
  - [5.6. Mandatory Tests](#56-mandatory-tests)
  - [5.7. Expected End State](#57-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 5. Netdata: Metrics for the Host and Every Container
This section adds per-second metrics for the host and for each container, published through the Phase 1 access pattern.

#### 5.1. Why Netdata?
`top`, `free` and `docker stats` show the present moment, one SSH session at a time. They can't answer *what was the load at 03:12?* or *which container was using the memory when the OOM killer fired?*

Netdata collects host and container metrics every second, discovers containers on its own and ships ready-made dashboards, in one container. On a single host that replaces four components (Prometheus, Node Exporter, cAdvisor, Grafana dashboards) that would each need configuring, securing and updating.

#### 5.2. The Privileges It Needs
To measure the host from inside a container, Netdata needs to see the host. That makes it the most privileged container on this platform after Portainer, so every grant is listed and justified:

| Grant | Why Netdata needs it | What it means |
| :--- | :--- | :--- |
| `pid: host` | See every host process, not only its own | It can see (not control) all processes and their command lines |
| `SYS_PTRACE` | Per-process metrics (`apps.plugin`) | Can inspect other processes' memory maps and file descriptors |
| `SYS_ADMIN` | Some kernel and cgroup collectors, network namespace names | A broad capability; one of the reasons Netdata stays VPN-only |
| `/proc`, `/sys` (`:ro`) | CPU, memory, disk, network and kernel counters | Read-only views of the kernel's state |
| `/etc/passwd`, `/etc/group` (`:ro`) | Resolve UIDs to user names in per-user charts | Account names, no password hashes (those are in `/etc/shadow`, not mounted) |
| `/var/log` (`:ro`) | Log-based collectors | Read access to host logs |
| `docker.sock` (`:ro`) | Name containers in the charts | Full Docker API access: root-equivalent (see [Phase 5](./05-availability-socket-review.md#101-docker-socket-inventory)) |

> [!NOTE]
> Netdata's upstream Compose example also sets `security_opt: apparmor:unconfined`. AlmaLinux uses SELinux, not AppArmor, so that line has no effect here and is left out.

> [!WARNING]
> These grants are why Netdata is never published. A Netdata dashboard is a live inventory of the host: every process, every container, every mount. It sits behind the VPN, the allow-list and nothing else on the public side.

#### 5.3. The Netdata Container
<details>
<summary><b>▶ View config — /srv/apps/netdata/docker-compose.yml</b></summary>

```bash
sudo mkdir -p /srv/apps/netdata /srv/data/netdata/{config,lib,cache}
sudo nano /srv/apps/netdata/docker-compose.yml
```
```yaml
services:
  netdata:
    image: netdata/netdata:v2.x.y   # TODO(verify): exact pinned tag from the server
    container_name: netdata
    hostname: srv01                 # the name shown in the dashboard
    restart: unless-stopped
    pid: host
    cap_add:
      - SYS_PTRACE
      - SYS_ADMIN
    volumes:
      # Persistent configuration, database and cache
      - /srv/data/netdata/config:/etc/netdata
      - /srv/data/netdata/lib:/var/lib/netdata
      - /srv/data/netdata/cache:/var/cache/netdata
      # Host views (read-only)
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /etc/os-release:/host/etc/os-release:ro
      - /etc/passwd:/host/etc/passwd:ro
      - /etc/group:/host/etc/group:ro
      - /var/log:/host/var/log:ro
      # Container names for the charts (see 5.2)
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - DO_NOT_TRACK=1              # no anonymous usage statistics
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.netdata.rule=Host(`netdata.mysite.com`)"
      - "traefik.http.routers.netdata.entrypoints=websecure"
      - "traefik.http.routers.netdata.tls=true"
      - "traefik.http.routers.netdata.middlewares=vpn-allowlist@file,security-headers@file"
      - "traefik.http.services.netdata.loadbalancer.server.port=19999"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:19999/api/v1/info"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

networks:
  proxy:
    external: true
```
</details>

| Choice | Why |
| :--- | :--- |
| Pinned tag, not `stable` | `stable` moves on its own. Updates go through the Case 02 change cycle like everything else. |
| `DO_NOT_TRACK=1` | Netdata sends anonymous usage statistics by default; this server doesn't. |
| No Netdata Cloud claim token | The agent isn't connected to Netdata Cloud: metrics stay on the server and are read over the VPN. |
| `hostname: srv01` | Charts are labeled with the same name used everywhere else in the cases. |

#### 5.4. Start and Verify
```bash
cd /srv/apps/netdata && docker compose up -d
docker compose ps
```
```text
NAME      IMAGE                    STATUS
netdata   netdata/netdata:v2.x.y   Up About a minute (healthy)
```

> [!NOTE]
> Give Netdata about a minute after the first start: it discovers collectors and containers before the dashboard is complete.

#### 5.5. Reading the Dashboard
With the VPN up, open `https://netdata.mysite.com`. The signals from [Phase 1, 1.4](./01-observability-model-access.md#14-signals-to-read-first) are on the overview:

| Section | What I check first |
| :--- | :--- |
| **System Overview** | Load against the number of cores, CPU `iowait`, memory *available* |
| **Disks** | Free space on `/`, I/O utilization and latency |
| **Network** | Traffic on the public interface and on `wg0` |
| **Applications / cgroups** | CPU and memory per container: which one is behind a spike |

![Netdata overview: load, CPU iowait, available memory and disk on srv01](./images/netdata-overview.png)
<!-- TODO(screenshot): netdata-overview.png -->

![Netdata per-container CPU and memory](./images/netdata-containers.png)
<!-- TODO(screenshot): netdata-containers.png -->

#### 5.6. Mandatory Tests
<details>
<summary><b>▶ View tests — Netdata is healthy, local-only and VPN-only</b></summary>

**Test 1: healthy and publishing nothing**
```bash
docker ps --filter name=netdata --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
```
```text
netdata   Up 5 minutes (healthy)   19999/tcp
```

**Test 2: containers are discovered by name**
```bash
docker compose -f /srv/apps/netdata/docker-compose.yml exec netdata \
  curl -s http://localhost:19999/api/v1/charts | grep -o '"cgroup_traefik[^"]*"' | head -3
```
Chart names for the `traefik` container are expected. If they appear as `cgroup_<container-id>`, the socket mount isn't working.

**Test 3: anonymous statistics are off**
```bash
docker compose -f /srv/apps/netdata/docker-compose.yml exec netdata printenv DO_NOT_TRACK
```
```text
1
```

**Tests 4–6:** run the [Phase 1 access tests](./01-observability-model-access.md#24-mandatory-tests) with `netdata.mysite.com`.
</details>

#### 5.7. Expected End State
- Netdata runs `healthy` on a pinned tag, on `proxy` only, with no published port;
- host and per-container metrics are collected every second and charts use container names;
- anonymous statistics are disabled and the agent isn't connected to Netdata Cloud;
- every privilege it holds is listed in 5.2, and the socket mount is recorded for the Phase 5 review;
- the dashboard is reachable only through the VPN.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case03-phase3-netdata-ok` and delete the previous one.

---

> Metrics say *how much* and *when*. The next phase adds *what happened*: every container log, the host journal and every HTTP request, searchable in one place.

---

[← Phase 2: Host & Container Views](./02-host-and-container-views.md) · **Phase 3 of 5** · [Next: Centralized Logs →](./04-centralized-logs.md)
