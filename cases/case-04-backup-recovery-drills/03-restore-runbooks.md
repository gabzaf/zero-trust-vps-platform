# Phase 3: Restore Runbooks

[← Phase 2: Restic Backups to B2](./02-restic-b2-backups.md) · **Phase 3 of 4** · [Next: Recovery Drills →](./04-recovery-drills.md)

---

### In this phase
- [7. Restoring from the Repository](#7-restoring-from-the-repository)
  - [7.1. Rules for Every Restore](#71-rules-for-every-restore)
  - [7.2. One File](#72-one-file)
  - [7.3. One Application's Data](#73-one-applications-data)
  - [7.4. Full Host Rebuild](#74-full-host-rebuild)
  - [7.5. Cutover](#75-cutover)
  - [7.6. Expected End State](#76-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 7. Restoring from the Repository
This section writes down every restore before it's needed, so the day it's needed is spent executing, not deciding.

#### 7.1. Rules for Every Restore
1. **Never restore over the only copy.** The current state is moved aside first, even when it's broken. It's evidence, and it's the way back if the restore is worse.
2. **Pick the snapshot deliberately.** `latest` is right for an accident. After a compromise, it's the last snapshot taken *before* it (Phase 1, 1.1).
3. **Validate before deleting anything.** The moved-aside copy is removed only after the restored service has been checked.
4. **Write down the timestamps.** Every restore is also a measurement of the RTO.

Finding the right snapshot and file:
```bash
sudo restic-srv01 snapshots --host srv01                     # every snapshot, newest last
sudo restic-srv01 ls latest /srv/apps/traefik                # what a snapshot contains under a path
sudo restic-srv01 find --host srv01 middlewares.yml          # which snapshots contain a file
sudo restic-srv01 diff <older-id> <newer-id>                 # what changed between two snapshots
```

#### 7.2. One File
Example: a Traefik dynamic file edited badly, with no clean copy at hand.

<details>
<summary><b>▶ View commands — restoring a single file</b></summary>

```bash
# Get the backed-up version without touching the live one
sudo restic-srv01 dump latest /srv/apps/traefik/dynamic/middlewares.yml > /tmp/middlewares.yml

# Compare, then replace
diff /srv/apps/traefik/dynamic/middlewares.yml /tmp/middlewares.yml
sudo cp /srv/apps/traefik/dynamic/middlewares.yml /srv/apps/traefik/dynamic/middlewares.yml.bad
sudo install -m 0644 /tmp/middlewares.yml /srv/apps/traefik/dynamic/middlewares.yml
```
</details>

Traefik watches the dynamic directory, so the restored file is live within seconds. No restart is needed.

#### 7.3. One Application's Data
Example: Uptime Kuma's data directory is lost or corrupted. This is drill [D2](./04-recovery-drills.md#92-d2-application-data-restore).

<details>
<summary><b>▶ View commands — restoring /srv/data/uptime-kuma</b></summary>

```bash
# 1. Stop the application
cd /srv/apps/uptime-kuma && docker compose stop

# 2. Move the damaged state aside (never delete it yet)
sudo mv /srv/data/uptime-kuma "/srv/data/uptime-kuma.broken-$(date +%F-%H%M)"

# 3. Restore that path, in place, from the chosen snapshot
sudo restic-srv01 restore latest --target / --include /srv/data/uptime-kuma

# 4. Ownership and modes come back as they were backed up
sudo ls -ln /srv/data/uptime-kuma | head

# 5. Start and validate
docker compose up -d
docker compose ps
```
</details>

Validation: over the VPN, Kuma shows every monitor **with its history up to the snapshot's time**. The gap between that time and the incident is the real RPO, and it's recorded. Only then is the `.broken-*` directory deleted.

> [!NOTE]
> `restore --target / --include <path>` writes the files back to their original location. Restic stores numeric owners, so the files return with the UIDs the container expects (Case 02's permission model) without a manual `chown`.

#### 7.4. Full Host Rebuild
The server is gone, or can't be trusted. A new VPS is rebuilt from the B2 repository and the password manager **only**: no snapshot, no access to the old host. This is drill [D3](./04-recovery-drills.md#93-d3-full-host-rebuild).

**What's needed before starting:**

| Item | Where it comes from |
| :--- | :--- |
| Restic password, B2 key ID and application key | Password manager |
| Provider and Cloudflare logins | Password manager (MFA) |
| The admin SSH key and the WireGuard client config | The admin device; the server side of both is in the backup |

**a. Create the VPS.** AlmaLinux 9, the admin's public SSH key added at creation, so it's key-only from the first boot. Note the new public IP.

> [!WARNING]
> Until step d, the new host is a default AlmaLinux install with SSH open on its public IP. Keys only, but exposed. The order below restores the perimeter first, to keep that window as short as possible.

**b. Install the platform's packages.**

<details>
<summary><b>▶ View commands — packages for the rebuild</b></summary>

```bash
sudo dnf install -y epel-release
sudo dnf install -y restic wireguard-tools iptables-services fail2ban cockpit cockpit-storaged rsync

# Docker Engine from Docker's repository (Case 02, 2.3)
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# One firewall only: iptables-services (Case 01). firewalld must not come back at boot.
sudo systemctl disable --now firewalld 2>/dev/null || true
sudo systemctl mask firewalld
```
</details>

**c. Reach the repository and restore into a staging directory.**

<details>
<summary><b>▶ View commands — Restic access and staging restore</b></summary>

```bash
# Recreate /etc/restic from the password manager (same files and modes as Phase 2, 5.3)
sudo install -d -m 0700 /etc/restic
sudo nano /etc/restic/env            # repository URL + B2 key
sudo nano /etc/restic/password       # repository password
sudo chmod 0600 /etc/restic/env; sudo chmod 0400 /etc/restic/password

sudo bash -c 'set -a; . /etc/restic/env; set +a; restic snapshots --host srv01'

# Restore the chosen snapshot into /restore, never straight onto /
sudo bash -c 'set -a; . /etc/restic/env; set +a; restic restore <snapshot-id> --target /restore'
```
</details>

**d. Put the host back together, perimeter first.** `/etc` is restored path by path, never as a whole: `/etc/fstab`, `/etc/machine-id` and the network configuration belong to the new host.

| Order | Restore from `/restore` | Then |
| :---: | :--- | :--- |
| 1 | Create `<username>` (`useradd -m -G wheel <username>`), then restore `/home/<username>/.ssh` and `/etc/sudoers.d/` | `visudo -c` |
| 2 | `/etc/ssh/sshd_config`, `/etc/ssh/sshd_config.d/`, `/etc/ssh/ssh_host_*` | Host private keys `root:ssh_keys 0640`; `sshd -t`, `systemctl restart sshd` |
| 3 | `/etc/wireguard/` | `systemctl enable --now wg-quick@wg0`; bring up the drill tunnel from the admin device and **continue over it** |
| 4 | `/etc/sysconfig/iptables`, `/usr/local/bin/cloudflare-firewall.sh`, `/etc/cloudflare-ips-v4.txt`, `/var/spool/cron/root` | `systemctl enable --now iptables`; WAN `:22` is now dropped |
| 5 | `/etc/fail2ban/jail.local` | `systemctl enable --now fail2ban` |
| 6 | `/etc/docker/daemon.json`, `/usr/local/bin/docker-user-firewall.sh`, `/etc/systemd/system/docker-user-firewall.service` | **Check the WAN interface name first** (below), then `systemctl daemon-reload`, `systemctl enable --now docker docker-user-firewall`, `usermod -aG docker <username>` |
| 7 | `/etc/ssl/cloudflare/` | Origin certificate and key in place for Traefik |
| 8 | `/etc/cockpit/`, `/etc/systemd/system/cockpit.socket.d/`, `/etc/logrotate.d/traefik` | `systemctl enable --now cockpit.socket` |
| 9 | `/etc/restic/`, `/usr/local/bin/restic-*`, `/etc/systemd/system/restic-*` | Backups resume on the new host (enabled after validation, step f) |
| 10 | `/srv/apps`, `/srv/data` | `rsync -aHAX --numeric-ids /restore/srv/ /srv/`, then `mkdir -p /srv/logs/traefik` |

> [!WARNING]
> **The interface name is a fail-open trap.** Case 02's `DOCKER-USER` filter names the public interface (`WAN_IF`). It only drops traffic arriving on that interface; everything else is handed back to Docker's `ACCEPT` rules. (A wrong name in Case 01's `INPUT` rules would fail closed instead, because that chain ends in `DROP`.) If the new VPS calls its public interface something else (`ens3` instead of `eth0`, for example), the rules restore without errors and **every published port is open to the internet**. Before order 4 and order 6:
> ```bash
> ip -br link                                                        # the new host's interface names
> sudo grep -nE '\b(eth[0-9]|ens[0-9]+|enp[0-9a-z]+)\b' /restore/etc/sysconfig/iptables \
>   /restore/usr/local/bin/docker-user-firewall.sh /restore/usr/local/bin/cloudflare-firewall.sh
> ```
> If the names differ, fix them in the restored files before enabling anything. Step f proves it from outside.

Restoring the **SSH host keys** (order 2) is deliberate: the admin device's `known_hosts` still matches, so the rebuild doesn't train me to accept a changed host key, which is exactly the warning that would matter during a real attack.

**e. Start the platform, in dependency order.**

<details>
<summary><b>▶ View commands — networks and stacks</b></summary>

```bash
docker network create proxy

cd /srv/apps/traefik       && docker compose up -d
cd /srv/apps/alves-jatoba  && docker compose up -d --build   # the site's image is rebuilt from its source
cd /srv/apps/portainer     && docker compose up -d
cd /srv/apps/netdata       && docker compose up -d
cd /srv/apps/loki          && docker compose up -d
cd /srv/apps/uptime-kuma   && docker compose up -d

docker ps --format '{{.Names}}\t{{.Status}}'
```
</details>

> [!NOTE]
> The client site's image isn't in any registry: it's built from source with `build: .`. Its source is in `/srv/apps/alves-jatoba`, so it's in the backup, and the build needs internet access for its dependencies. That build time is part of the measured RTO.

**f. Validate before any cutover.** Over the drill tunnel (VPN), ask Traefik for the public site directly:
```bash
curl -sS --resolve mysite.com:443:10.10.10.1 --cacert ~/origin_ca_rsa_root.pem \
  -o /dev/null -w '%{http_code}\n' https://mysite.com/
```
```text
200
```
And prove the perimeter from outside, with the VPN **down** on the admin device:
```bash
curl -sS -m 5 -o /dev/null -w '%{http_code}\n' -k https://<new-public-ip>/
```
```text
curl: (28) Connection timed out after 5001 milliseconds
000
```
A direct-to-origin request must time out, exactly as in Case 02. If it answers, the `DOCKER-USER` filter isn't matching the public interface: stop and fix it before going further.

Then run the [Case 03 access tests](../case-03-observability-metrics-logs-availability/01-observability-model-access.md#24-mandatory-tests) against the new host, and enable the backup timers: `systemctl enable --now restic-backup.timer restic-maintenance.timer`.

#### 7.5. Cutover
Only in a real incident (the drill stops before this): point the public names at the new host.

| Record | Change | Why |
| :--- | :--- | :--- |
| Site records (`@`, `www`) | Proxied A record → new public IP | Cloudflare switches its origin; visitors keep the same edge IP |
| `vpn` | DNS-only A record → new public IP | The admin tunnel's `Endpoint` is `vpn.mysite.com`, so the client config doesn't change |
| `srv01`, `traefik`, `cockpit`, `portainer`, `netdata`, `grafana`, `uptime` | **No change** | They point to `10.10.10.1`, which the restored WireGuard config provides again |

After the cutover, Uptime Kuma's *Public site* monitor turning green is the end of the incident. If the old host was compromised, it isn't destroyed: it's powered off and kept for analysis.

#### 7.6. Expected End State
- every restore follows the same rules: move aside, choose the snapshot, validate, then delete;
- a single file, one application's data and the whole host each have a written, ordered procedure;
- the full rebuild depends only on the B2 repository and the password manager;
- the host's perimeter (SSH, WireGuard, firewall) is restored before anything else;
- the cutover changes exactly three DNS records.

---

> Runbooks are a plan. The next phase executes all three and records how long each one actually took.

---

[← Phase 2: Restic Backups to B2](./02-restic-b2-backups.md) · **Phase 3 of 4** · [Next: Recovery Drills →](./04-recovery-drills.md)
