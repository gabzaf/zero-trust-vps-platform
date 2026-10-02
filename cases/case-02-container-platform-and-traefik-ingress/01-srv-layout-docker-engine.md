]# Phase 1: Production Layout & Docker Engine

[← Overview](./00-overview.md) · **Phase 1 of 5** · [Next: Docker & the Host Firewall →](./02-docker-firewall.md)

---

### In this phase
- [Before Starting](#before-starting)
- [1. Production Directory Structure (/srv)](#1-production-directory-structure-srv)
  - [1.1. Why Decide This First?](#11-why-decide-this-first)
  - [1.2. Why /srv?](#12-why-srv)
  - [1.3. Adopted Structure](#13-adopted-structure)
  - [1.4. Create the Base Structure](#14-create-the-base-structure)
  - [1.5. Application Directory Convention](#15-application-directory-convention)
  - [1.6. Expected End State](#16-expected-end-state)
- [2. Docker Engine](#2-docker-engine)
  - [2.1. Why Containers?](#21-why-containers)
  - [2.2. Privilege Model in This Case](#22-privilege-model-in-this-case)
  - [2.3. Install Docker from the Official Repository](#23-install-docker-from-the-official-repository)
  - [2.4. Harden the Docker Daemon](#24-harden-the-docker-daemon)
  - [2.5. Administrative User and the docker Group](#25-administrative-user-and-the-docker-group)
  - [2.6. Mandatory Tests](#26-mandatory-tests)
  - [2.7. Expected End State](#27-expected-end-state)

---

## Configuration Artifacts & Reference Code

### Before Starting
Everything in this case is done through the private admin tunnel built in Case 01: the WireGuard tunnel and the `srv01` split-horizon name.

```bash
sudo wg-quick up vps-admin
ssh -i ~/.ssh/my_key <username>@srv01.mysite.com
```

> [!WARNING]
> Take a snapshot before starting: in the VPS panel, create a manual snapshot named `pre-case02-platform`. If any step in this phase goes wrong, it's my "undo" button.

---

### 1. Production Directory Structure (`/srv`)
Before launching any container, I decide where things will live. That decision affects everything that comes after: backups, permissions, migrations and troubleshooting.

#### 1.1. Why Decide This First?
Most setups skip this step, and the result is predictable:
- volumes scattered across `/var/lib/docker/volumes/` with random names;
- configuration files mixed with data;
- Compose files dumped in a home directory next to old experiments;
- backups that can't be automated, because nobody knows what to back up.

A fixed layout makes recovery, audits and backups mechanical instead of improvised.

#### 1.2. Why `/srv`?
The Linux **Filesystem Hierarchy Standard (FHS)** defines `/srv` as the place for data served by the system, which is exactly what self-hosted services are.

| Directory | Purpose (according to FHS) |
| :--- | :--- |
| `/home` | Data of human users |
| `/var` | Variable system data (logs, spool, cache) |
| `/opt` | Third-party software installed manually |
| `/srv` | Data served by the host's services |

#### 1.3. Adopted Structure
```text
/srv/
├── apps/       # Compose files and app configuration   (<username>, 755)
│   └── {app}/
├── data/       # Persistent state, bind-mounted         (<username>, 755)
│   └── {app}/
├── logs/       # App logs kept outside Docker           (<username>, 755)
│   └── {app}/
└── backups/    # Local backup staging before offsite    (root, 700)
```

| Directory | Content | Example |
| :--- | :--- | :--- |
| `/srv/apps/{app}/` | `docker-compose.yml` and configuration | `/srv/apps/traefik/docker-compose.yml` |
| `/srv/data/{app}/` | Persistent state mounted into containers | `/srv/data/uptime-kuma/` |
| `/srv/logs/{app}/` | Logs written to files instead of stdout | `/srv/logs/traefik/access.log` |
| `/srv/backups/` | Local dumps before shipping offsite | `/srv/backups/app-db-20260101.sql.gz` |

Separating configuration from state also separates their permissions: Compose files can be world-readable (`644`), sensitive files such as a stack's `.env` can be closed (`600`) and backups are root-only.

#### 1.4. Create the Base Structure
<details>
<summary><b>▶ View commands — creating `/srv` and its permissions</b></summary>

Create the directories:
```bash
sudo mkdir -p /srv/{apps,data,logs,backups}
```

Day-to-day directories belong to the administrative user:
```bash
sudo chown -R <username>:<username> /srv/{apps,data,logs}
sudo chmod 755 /srv/apps /srv/data /srv/logs
```

Backups belong to root and are closed to everyone else:
```bash
sudo chown root:root /srv/backups
sudo chmod 700 /srv/backups
```

Verify:
```bash
ls -la /srv
```
```text
drwxr-xr-x.  6 root       root       4096 ... .
drwxr-xr-x.  2 <username> <username> 4096 ... apps
drwx------.  2 root       root       4096 ... backups
drwxr-xr-x.  2 <username> <username> 4096 ... data
drwxr-xr-x.  2 <username> <username> 4096 ... logs
```
</details>

| Directory | Permission | Reason |
| :--- | :---: | :--- |
| `/srv/apps/` | `755` | Compose files can be read |
| `/srv/data/` | `755` | Parent directory only; each `/srv/data/{app}/` follows its container's UID ([Phase 3](./03-networks-state.md)) |
| `/srv/logs/` | `755` | Logs can be read for debugging |
| `/srv/backups/` | `700` | Backups contain sensitive data |

#### 1.5. Application Directory Convention
Every new application follows the same pattern:
```bash
sudo mkdir -p /srv/apps/{app} /srv/data/{app}
```

| Rule | Example | Avoid |
| :--- | :--- | :--- |
| Lowercase | `uptime-kuma` | `Uptime_Kuma` |
| Hyphens as separators | `uptime-kuma` | `uptime_kuma` |
| Project name, not image name | `vaultwarden` | `vaultwarden-server-docker` |
| No version in the name | `traefik` | `traefik-v3` |

Compose files always reference state with absolute paths under `/srv/data/`:
```yaml
services:
  app:
    image: example:1.0.0
    volumes:
      - /srv/data/example:/data
```

#### 1.6. Expected End State
- `/srv/{apps,data,logs}` exist and belong to `<username>`;
- `/srv/backups` exists, belongs to root and is closed (`700`);
- every future service has an obvious home for its configuration and its state.

---

### 2. Docker Engine
This section installs Docker and establishes the container runtime that every service on this platform will use.

#### 2.1. Why Containers?
Installing software directly on the host works until it doesn't: one service needs a different library version, configuration spreads across `/etc`, `/var` and `/usr`, and an update to one service breaks another. Multiply that by ten services and the server becomes something nobody wants to touch.

A container is an isolated process that carries its own code, libraries and configuration. It doesn't see the rest of the system, doesn't conflict with other containers and leaves nothing behind when removed.

| Pillar | What it means | Why it matters |
| :--- | :--- | :--- |
| **Isolation** | A container sees only what it's given | Services don't interfere with each other |
| **Reproducibility** | Same image, same behavior | No "works on my machine" drift |
| **Portability** | Runs anywhere Docker runs | Migrating providers doesn't mean reconfiguring |

Containers aren't virtual machines: they share the host kernel. Isolation comes from Linux namespaces and cgroups, which is why the daemon hardening below matters.

#### 2.2. Privilege Model in This Case
Case 01 scoped `<username>`'s `sudo` to `systemctl`, `journalctl` and `dnf`. Most steps here (creating directories under `/srv`, writing `/etc/docker/daemon.json`, editing firewall rules) fall outside that list.

> [!NOTE]
> Commands shown with `sudo` that aren't in the scoped `sudoers` file are run from a root session (`su -`), as defined in Case 01, or after adding that specific binary to `/etc/sudoers.d/ops` with `visudo`. Day-to-day container operations (`docker compose ...`) run as `<username>` through the `docker` group, configured in [2.5](#25-administrative-user-and-the-docker-group).

#### 2.3. Install Docker from the Official Repository
The Docker packages in distribution repositories lag behind and sometimes conflict with Podman. I install Docker Engine from Docker's own repository, which is signed and current.

<details>
<summary><b>▶ View commands — Docker Engine installation (AlmaLinux)</b></summary>

Remove old or conflicting packages that may come with the image:
```bash
sudo dnf remove -y docker docker-client docker-client-latest docker-common \
  docker-latest docker-latest-logrotate docker-logrotate docker-engine podman runc
```

Add Docker's official repository:
```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
```

> [!NOTE]
> The `rhel` repository is the right one for AlmaLinux: both are built from the same upstream sources.

Install the engine and the Compose plugin:
```bash
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

When `dnf` asks to import Docker's GPG key, check that the fingerprint matches the one published in Docker's installation documentation before accepting. That's what makes the packages verifiable instead of just downloaded.
</details>

> [!IMPORTANT]
> Don't start the service yet. The daemon configuration below must be in place before Docker creates its first network.

#### 2.4. Harden the Docker Daemon
The daemon defaults are tuned for convenience on a laptop, not for a production host. Before the first start, I set the following options in `/etc/docker/daemon.json`:

- **`live-restore`**: containers keep running if the daemon restarts (for example during a Docker update), which reduces downtime.
- **`log-driver` + `log-opts`**: caps each container's logs at 3 files of 10 MB, so a noisy container can't silently fill the disk.
- **`icc: false`**: disables container-to-container traffic on the default `bridge` network. On this platform, containers only talk when I put them on the same custom network.
- **`no-new-privileges`**: processes inside containers can't gain privileges through `setuid`/`setgid` binaries.
- **`userland-proxy: false`**: removes the `docker-proxy` user-space process per published port. Forwarding is handled entirely by kernel NAT rules, which is lighter and keeps every published port visible in `iptables`. That visibility is exactly what [Phase 2](./02-docker-firewall.md) relies on.
- **`default-ulimits`**: caps open files per container at 64,000, so a leaking or compromised container can't exhaust the host's file descriptors.

<details>
<summary><b>▶ View config — /etc/docker/daemon.json</b></summary>

```bash
sudo mkdir -p /etc/docker
sudo nano /etc/docker/daemon.json
```
```json
{
  "live-restore": true,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "icc": false,
  "no-new-privileges": true,
  "userland-proxy": false,
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }
  }
}
```

Enable on boot and start in one step:
```bash
sudo systemctl enable --now docker
```

Confirm the service and the versions:
```bash
sudo systemctl status docker
docker --version
docker compose version
```
```text
Active: active (running)
Docker version 29.x.x, build xxxxxxx
Docker Compose version v5.x.x
```

> [!NOTE]
> It's `docker compose` (with a space), the Compose plugin. The old `docker-compose` binary with a hyphen is discontinued.
</details>

> [!WARNING]
> `icc: false` breaks communication between containers that rely on the default `bridge` network. Everything in this case uses custom networks ([Phase 3](./03-networks-state.md)), so nothing here is affected.

#### 2.5. Administrative User and the docker Group
By default, every `docker` command needs root. Adding `<username>` to the `docker` group lets me operate containers without `sudo`, and this is a deliberate trade-off, not a free convenience:

> [!WARNING]
> **The `docker` group is root-equivalent.** Anyone who can talk to the Docker socket can start a privileged container that mounts the host's filesystem. In practice, this gives `<username>` root without going through the scoped `sudoers` file from Case 01.
>
> I accept this because the account is only reachable through the VPN, with a key, and with no password login. The alternatives were weighed and rejected:
> - **`sudo docker` through `sudoers`**: just as root-equivalent, only with more friction.
> - **Rootless Docker**: binding ports 80/443 and the networking model both get significantly more complex for a stack like this one.
>
> The Docker API is never exposed over TCP: it only listens on the local Unix socket.

<details>
<summary><b>▶ View commands — docker group membership</b></summary>

```bash
sudo usermod -aG docker <username>
```

Group membership is only read at login. Close the SSH session and connect again through the VPN:
```bash
exit
ssh -i ~/.ssh/my_key <username>@srv01.mysite.com
```

Confirm:
```bash
id -nG
docker ps
```
🟢 Expected result: `docker` appears in the group list and `docker ps` prints an empty table without `sudo`.
</details>

#### 2.6. Mandatory Tests
<details>
<summary><b>▶ View tests — engine, daemon flags and a throwaway container</b></summary>

**Test 1: Daemon hardening is active**
```bash
docker info --format 'LiveRestore={{.LiveRestoreEnabled}} SecurityOptions={{.SecurityOptions}}'
```
🟢 Expected result: `LiveRestore=true`, with `no-new-privileges` listed in the security options.

**Test 2: Log rotation is the default**
```bash
docker info --format '{{.LoggingDriver}}'
```
🟢 Expected result: `json-file`.

**Test 3: A container runs and leaves nothing behind**
```bash
docker run --rm hello-world && docker rmi hello-world
```
🟢 Expected result: `Hello from Docker!`, then the image is untagged and deleted.

> [!NOTE]
> This test deliberately doesn't publish a port. What happens to published ports with respect to the Case 01 firewall is the subject of the next phase.
</details>

#### 2.7. Expected End State
- Docker Engine is installed from the official, signed repository and starts on boot;
- the daemon runs with log rotation, `live-restore`, `icc` off, `no-new-privileges` and file limits;
- `<username>` operates containers without `sudo`, with the root-equivalence of that choice documented;
- no containers or test images are left on the host.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case02-phase1-docker-ready` and delete `pre-case02-platform`.

---

[← Overview](./00-overview.md) · **Phase 1 of 5** · [Next: Phase 2 — Docker & the Host Firewall →](./02-docker-firewall.md)
