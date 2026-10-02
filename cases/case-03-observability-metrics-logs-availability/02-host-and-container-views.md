# Phase 2: Host & Container Views (Cockpit and Portainer)

[← Phase 1: Observability Model & Access Pattern](./01-observability-model-access.md) · **Phase 2 of 5** · [Next: Metrics with Netdata →](./03-metrics-netdata.md)

---

### In this phase
- [3. Cockpit: The Host View](#3-cockpit-the-host-view)
  - [3.1. Why a Host View?](#31-why-a-host-view)
  - [3.2. Install Cockpit](#32-install-cockpit)
  - [3.3. Listen Only on the VPN Address](#33-listen-only-on-the-vpn-address)
  - [3.4. Session and Origin Settings](#34-session-and-origin-settings)
  - [3.5. Certificate and Login](#35-certificate-and-login)
  - [3.6. Mandatory Tests](#36-mandatory-tests)
  - [3.7. Expected End State](#37-expected-end-state)
- [4. Portainer: The Container View](#4-portainer-the-container-view)
  - [4.1. Why Portainer, and Its Limits](#41-why-portainer-and-its-limits)
  - [4.2. The Docker Socket Trade-off](#42-the-docker-socket-trade-off)
  - [4.3. The Portainer Container](#43-the-portainer-container)
  - [4.4. First Start](#44-first-start)
  - [4.5. Mandatory Tests](#45-mandatory-tests)
  - [4.6. Expected End State](#46-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 3. Cockpit: The Host View
This section adds a web view of the host itself: systemd units, disks, the journal and pending updates, reachable only through the tunnel.

#### 3.1. Why a Host View?
Netdata and Grafana show what the host *does*. Cockpit shows what the host *is*: which units are running or failed, how the disks are laid out, what the journal says, which updates are pending. Those are things I'd otherwise check over SSH one command at a time. Cockpit is native to the RHEL family, so on AlmaLinux it's a supported package, not a third-party add-on.

It's a view, not a second way to administer the server. Configuration changes still go through SSH and versioned files, so there's one place where the server's state is defined.

#### 3.2. Install Cockpit
<details>
<summary><b>▶ View commands — Cockpit installation (AlmaLinux)</b></summary>

```bash
sudo dnf install -y cockpit cockpit-storaged
```

Don't enable the socket yet: by default it listens on every interface. The next step restricts it first.
</details>

> [!NOTE]
> Cockpit has no official Docker module. Containers are inspected in Portainer ([section 4](#4-portainer-the-container-view)).

#### 3.3. Listen Only on the VPN Address
Out of the box, `cockpit.socket` listens on `[::]:9090`: every interface, IPv4 and IPv6. Case 01's firewall already drops `9090` on the WAN, so it isn't reachable today. But that makes Cockpit's exposure depend on a single control. Case 02 documents a real window where that control disappears: restarting `iptables.service` flushes the rules until they're rebuilt.

So Cockpit doesn't listen on the public interface at all. It binds to the WireGuard address only:

<details>
<summary><b>▶ View config — systemd drop-in for cockpit.socket</b></summary>

```bash
sudo systemctl edit cockpit.socket
```
```ini
[Socket]
# Drop the default [::]:9090 listener, then bind to the WireGuard address only
ListenStream=
ListenStream=10.10.10.1:9090
# wg0 may come up after the socket unit at boot: allow binding before the address exists
FreeBind=yes
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cockpit.socket
```
</details>

| Setting | Why |
| :--- | :--- |
| `ListenStream=` (empty) | Clears the default listener; without it, the new address would be *added* to `[::]:9090`. |
| `ListenStream=10.10.10.1:9090` | Cockpit only exists on the tunnel. There's no public socket to protect. |
| `FreeBind=yes` | At boot, `wg0` may not have its address yet. Without this, the socket would fail to bind and Cockpit would be unavailable until restarted. |

With both layers, a flushed or broken firewall no longer exposes Cockpit, and it doesn't listen on IPv6, which an IPv4 ruleset wouldn't cover.

#### 3.4. Session and Origin Settings
<details>
<summary><b>▶ View config — /etc/cockpit/cockpit.conf</b></summary>

```bash
sudo nano /etc/cockpit/cockpit.conf
```
```ini
[WebService]
Origins = https://cockpit.mysite.com:9090 https://10.10.10.1:9090
AllowUnencrypted = false

[Session]
IdleTimeout = 15
```

```bash
sudo systemctl restart cockpit.socket
```
</details>

| Setting | What it actually does |
| :--- | :--- |
| `Origins` | Lists the web origins allowed to open Cockpit's WebSocket. It's a cross-site request check for the browser, **not** a source-IP filter. Access control is the bind address from 3.3. |
| `AllowUnencrypted = false` | HTTPS only. |
| `IdleTimeout = 15` | An idle session is logged out after 15 minutes. |

> [!NOTE]
> It's easy to read `Origins` as "only accept connections from these addresses". It isn't. If the bind address in 3.3 were missing, `Origins` wouldn't stop anyone from reaching the login page.

#### 3.5. Certificate and Login
Cockpit serves its own self-signed certificate. Instead of clicking through the warning blindly, I compare the fingerprint the browser shows with the one on the server, once, before trusting it:

```bash
sudo openssl x509 -in /etc/cockpit/ws-certs.d/0-self-signed.cert -noout -fingerprint -sha256
```

Login is with `<username>` and its local password. That account is only reachable through the VPN, and `root` can't log in to Cockpit at all:

<!-- TODO(verify): run on the server and confirm the file lists root -->
```bash
cat /etc/cockpit/disallowed-users
```
```text
root
```

#### 3.6. Mandatory Tests
<details>
<summary><b>▶ View tests — Cockpit exists only on the tunnel</b></summary>

**Test 1: the socket is bound to the WireGuard address only**
```bash
sudo ss -tlnp | grep 9090
```
```text
LISTEN 0  4096  10.10.10.1:9090  0.0.0.0:*  users:(("systemd",pid=1,fd=...))
```
There must be no `0.0.0.0:9090`, `*:9090` or `[::]:9090` line.

**Test 2: the listener survives a reboot** (`FreeBind`)
```bash
sudo reboot
# after reconnecting through the VPN
sudo ss -tlnp | grep 9090
```
The same single `10.10.10.1:9090` line is expected.

**Test 3: off the VPN, nothing answers** (VPN down)
```bash
curl -sS -m 5 -o /dev/null -w '%{http_code}\n' https://cockpit.mysite.com:9090/
```
```text
curl: (28) Connection timed out after 5001 milliseconds
000
```

**Test 4: on the VPN, the login page answers** (VPN up)
```bash
curl -sSk -o /dev/null -w '%{http_code}\n' https://cockpit.mysite.com:9090/
```
```text
200
```
</details>

![Cockpit overview: host health, systemd units and pending updates](./images/cockpit-overview.png)
<!-- TODO(screenshot): cockpit-overview.png -->

#### 3.7. Expected End State
- Cockpit is installed from the AlmaLinux repositories;
- `cockpit.socket` listens on `10.10.10.1:9090` only, including after a reboot;
- it doesn't listen on any public address or on IPv6;
- `root` can't log in; idle sessions end after 15 minutes;
- off the VPN, the port doesn't answer.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case03-phase2-cockpit-ok` and delete `pre-case03-observe`.

---

### 4. Portainer: The Container View
This section adds a visual view of containers, networks, volumes and logs, published through the access pattern from Phase 1.

#### 4.1. Why Portainer, and Its Limits
The CLI answers one question per command: `docker ps`, `docker logs`, `docker inspect`, `docker network inspect`. Portainer shows the same information on one screen, which is faster when I'm looking for something and don't know where it is yet.

What Portainer is **not**: the place where containers are defined. Every service on this platform is a Compose file under `/srv/apps/{app}`, versioned and changed through the Case 02 change cycle. A container created or edited in Portainer would be invisible to that process and lost on the next `docker compose up`. So Portainer is used for inspection only. Its Stacks feature isn't used.

#### 4.2. The Docker Socket Trade-off

> [!WARNING]
> **Portainer is root on this host.** It manages Docker through the socket, and whoever controls Docker can start a privileged container that mounts the host's filesystem. Mounting the socket `:ro` doesn't change that: it only stops the container from replacing the socket file, not from calling the API.
>
> What I accept, and why: Portainer is reachable only through the VPN, behind `vpn-allowlist`, behind its own admin login, and it has no reason to talk to the internet. It's listed with the other socket consumers in the [Phase 5 review](./05-availability-socket-review.md#101-docker-socket-inventory).

#### 4.3. The Portainer Container
<details>
<summary><b>▶ View config — /srv/apps/portainer/docker-compose.yml</b></summary>

```bash
sudo mkdir -p /srv/apps/portainer /srv/data/portainer
sudo nano /srv/apps/portainer/docker-compose.yml
```
```yaml
services:
  portainer:
    image: portainer/portainer-ce:2.21-alpine   # TODO(verify): exact tag from the server
    container_name: portainer
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro   # full Docker API access (see 4.2)
      - /srv/data/portainer:/data                       # users, settings
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.portainer.rule=Host(`portainer.mysite.com`)"
      - "traefik.http.routers.portainer.entrypoints=websecure"
      - "traefik.http.routers.portainer.tls=true"
      - "traefik.http.routers.portainer.middlewares=vpn-allowlist@file,security-headers@file"
      - "traefik.http.services.portainer.loadbalancer.server.port=9000"
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--spider", "http://localhost:9000/api/status"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

networks:
  proxy:
    external: true
```
</details>

| Choice | Why |
| :--- | :--- |
| No `ports:` | Portainer's own `9000`, `9443` and `8000` listeners stay inside the container. Traefik reaches `9000` over `proxy`. |
| No Edge agent | The `8000` tunnel port is for managing remote environments. There's only one environment here: the local socket. |
| `-alpine` image | Smaller, and it ships `wget` for the healthcheck. |

#### 4.4. First Start
```bash
cd /srv/apps/portainer && docker compose up -d
```

> [!IMPORTANT]
> Portainer requires the admin account to be created **within 5 minutes** of the first start. After that it locks itself and has to be restarted. Open `https://portainer.mysite.com` over the VPN right after starting it.

On the first screen:
1. create the admin user with a strong, unique password;
2. **uncheck** *Allow collection of anonymous statistics*: nothing about this server leaves it;
3. choose **Get Started**: the `local` environment (the mounted socket) is already connected.

#### 4.5. Mandatory Tests
<details>
<summary><b>▶ View tests — Portainer is healthy and VPN-only</b></summary>

**Test 1: the container is healthy and publishes nothing**
```bash
docker ps --filter name=portainer --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
```
```text
portainer   Up 2 minutes (healthy)   8000/tcp, 9000/tcp, 9443/tcp
```
The ports are listed without a host address (`0.0.0.0:...->`), which means they're exposed inside the container only.

**Tests 2–4:** run the [Phase 1 access tests](./01-observability-model-access.md#24-mandatory-tests) with `portainer.mysite.com`. Expected: `10.10.10.1`, a timeout off the VPN, `200` on the VPN, `403` from the host.
</details>

![Portainer container list: every service running, nothing published except Traefik](./images/portainer-containers.png)
<!-- TODO(screenshot): portainer-containers.png -->

#### 4.6. Expected End State
- Portainer runs `healthy` on `proxy`, publishes no host port and is reachable only through the VPN;
- the admin account exists, sign-up isn't possible and anonymous statistics are off;
- Compose files under `/srv/apps` remain the only definition of every service;
- Portainer is recorded as a Docker-socket consumer for the Phase 5 review.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case03-phase2-views-ok` and delete the previous one.

---

> The host and its containers can now be inspected without SSH. Next, the numbers behind them: per-second metrics for the host and every container.

---

[← Phase 1: Observability Model & Access Pattern](./01-observability-model-access.md) · **Phase 2 of 5** · [Next: Metrics with Netdata →](./03-metrics-netdata.md)
