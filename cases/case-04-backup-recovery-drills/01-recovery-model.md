# Phase 1: Recovery Model

[← Overview](./00-overview.md) · **Phase 1 of 4** · [Next: Restic Backups to B2 →](./02-restic-b2-backups.md)

---

### In this phase
- [1. What Can Go Wrong](#1-what-can-go-wrong)
  - [1.1. Failure Modes](#11-failure-modes)
  - [1.2. Recovery Objectives per Scenario](#12-recovery-objectives-per-scenario)
- [2. What Is State](#2-what-is-state)
  - [2.1. State Inventory](#21-state-inventory)
  - [2.2. What Isn't Backed Up, and Why](#22-what-isnt-backed-up-and-why)
  - [2.3. The Secrets Outside the Backup](#23-the-secrets-outside-the-backup)
- [3. Snapshots vs Backups](#3-snapshots-vs-backups)
  - [3.1. Two Tools, Two Jobs](#31-two-tools-two-jobs)
  - [3.2. The 3-2-1-1-0 Rule on This Platform](#32-the-3-2-1-1-0-rule-on-this-platform)
  - [3.3. Expected End State](#33-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 1. What Can Go Wrong
This section names the failures the platform has to survive, because each one needs a different recovery path.

#### 1.1. Failure Modes

| Scenario | Examples | Recovery path | Tool |
| :--- | :--- | :--- | :--- |
| **Bad change** | An update breaks the site; a config edit takes a service down | Roll back the tag, or restore the pre-change snapshot ([Case 02, 7.5](../case-02-container-platform-and-traefik-ingress/04-health-change-cycle.md#75-rollback)) | Compose, provider snapshot |
| **Lost data, host fine** | A directory deleted by mistake; a corrupted SQLite file | Restore that path from the offsite repository | Restic |
| **Host lost** | Disk or provider failure, a locked account, a host that can't be trusted any more | Rebuild a new VPS from the offsite repository only | Restic + rebuild runbook |
| **Compromise** | An attacker with root deletes data and then tries to delete the backups | Rebuild clean, from a snapshot taken *before* the compromise | Object Lock + rebuild runbook |

> [!IMPORTANT]
> A compromised host is never restored in place. It's rebuilt on a new VPS, from a backup older than the compromise. A backup taken after it may contain whatever the attacker left behind. That's why retention keeps weeks, not days, and why the backups are immutable for 30 days ([Phase 2](./02-restic-b2-backups.md#42-object-lock-why-and-how)).

#### 1.2. Recovery Objectives per Scenario
One RTO for everything would either be unrealistic for a lost host or meaningless for a rollback. Each scenario gets its own target:

| Scenario | RTO target (time to working service) | RPO target (data that may be lost) | Drill |
| :--- | :--- | :--- | :---: |
| Bad change | < 60 s | None: nothing is lost, the previous version returns | [D1](./04-recovery-drills.md#91-d1-failed-release-rollback) |
| Lost data, host fine | < 10 min | ≤ 24 h (nightly backup) | [D2](./04-recovery-drills.md#92-d2-application-data-restore) |
| Host lost | < 2 h | ≤ 24 h (nightly backup) | [D3](./04-recovery-drills.md#93-d3-full-host-rebuild) |

Why 24 hours of RPO is acceptable here: the client's site holds no data of its own (its content lives in its Git repository), platform changes are infrequent and made by me, and losing up to a day of monitoring history doesn't hurt anyone. If a stack with a real database is ever added, its RPO has to be decided on its own, and probably needs more frequent database dumps.

> [!NOTE]
> These are **targets**. The numbers this case claims are the ones measured in the drills, in [Phase 4](./04-recovery-drills.md).

---

### 2. What Is State
This section decides exactly what is backed up, by sorting everything on the server into state, configuration and things that can be rebuilt.

#### 2.1. State Inventory

| Path | What it holds | Kind | Backed up |
| :--- | :--- | :--- | :---: |
| `/srv/apps` | Every Compose file and its configuration, Grafana's secret, the client site's source | Configuration | ✅ |
| `/srv/data/uptime-kuma` | Monitors and their history (SQLite) | State | ✅ container stopped during copy |
| `/srv/data/grafana` | Users, dashboards, preferences (SQLite) | State | ✅ container stopped during copy |
| `/srv/data/portainer` | Users and settings (BoltDB) | State | ✅ container stopped during copy |
| `/srv/data/netdata/config` | Netdata configuration | Configuration | ✅ |
| `/etc` | WireGuard keys, `sshd` config and host keys, iptables rules, Fail2ban, `sudoers.d`, Docker daemon, systemd units, Cockpit, logrotate, the Origin certificate and key, Restic's own config | Configuration and secrets | ✅ restored selectively |
| `/usr/local/bin` | The firewall scripts (`cloudflare-firewall.sh`, `docker-user-firewall.sh`) and the backup script | Configuration | ✅ |
| `/var/spool/cron/root` | Root's crontab: the scheduled Cloudflare IP syncs | Configuration | ✅ |
| `/home/<username>/.ssh` | The admin's `authorized_keys` | Configuration | ✅ |

> [!NOTE]
> All of `/etc` is a few megabytes, so it's backed up whole. It's **never restored whole**, though: on a new host, files like `/etc/fstab`, `/etc/machine-id` and the network configuration belong to that host. The rebuild runbook restores a named list of paths ([Phase 3, 7.4](./03-restore-runbooks.md#74-full-host-rebuild)).

#### 2.2. What Isn't Backed Up, and Why

| Path | Why it's left out |
| :--- | :--- |
| `/srv/data/loki` | Seven days of logs that change every second. Copying a live TSDB index nightly gives an inconsistent snapshot of data that expires within a week anyway. |
| `/srv/data/netdata/lib`, `/srv/data/netdata/cache` | Metrics history: high churn, rebuilt automatically, low recovery value. |
| `/srv/data/loki/promtail` | Promtail's read positions; a new host starts its own. |
| `/srv/logs` | Rotating log files; their content is already in Loki while it's useful. |
| Docker images | Public images are pulled again by their pinned tags. The client site's image is rebuilt from its source in `/srv/apps`. |

> [!WARNING]
> Leaving the logs out has a consequence worth stating: if the host is compromised and wiped, the last seven days of logs go with it, which is exactly when they'd matter most. A nightly copy wouldn't fix that, because an attacker acts between copies. Shipping logs off the host as they're written is the real fix, and it's an [open item](./04-recovery-drills.md#103-open-items).

#### 2.3. The Secrets Outside the Backup
Two secrets can't live only in the backup, because they're needed to *read* it:

| Secret | Where it lives on the server | Where the copy lives |
| :--- | :--- | :--- |
| Restic repository password | `/etc/restic/password` (`0400`, root) | My password manager, on the admin device |
| B2 application key (ID + key) | `/etc/restic/env` (`0600`, root) | My password manager, on the admin device |

> [!IMPORTANT]
> Restic encrypts everything with the repository password. **If that password exists only on the server, losing the server loses the backups too.** The drill in D3 starts from an empty VPS and the password manager, never from the old host, precisely to prove this copy is enough.

---

### 3. Snapshots vs Backups
This section separates the two safety nets, because they protect against different things and are easy to confuse.

#### 3.1. Two Tools, Two Jobs

| | Provider snapshot | Restic backup to B2 |
| :--- | :--- | :--- |
| **What it copies** | The whole disk, at the hypervisor | Chosen paths, file by file, deduplicated |
| **Where it lives** | The same provider, the same account | Another provider (Backblaze), another account |
| **Encrypted by me** | No | Yes, before it leaves the server |
| **Survives the provider account** | No | Yes |
| **Restore granularity** | Whole server only | One file, one directory, or everything |
| **Best for** | Undoing a change in minutes | Lost data, a lost host, a compromise |
| **Cost** | Per snapshot, per GB | Per GB stored |

A snapshot is a checkpoint, used before a risky change and deleted after it's confirmed (Case 02's change cycle). It isn't a backup, because it shares the fate of the thing it protects.

#### 3.2. The 3-2-1-1-0 Rule on This Platform

| Rule | Meaning | Here |
| :---: | :--- | :--- |
| **3** | Three copies of the data | The live server, the latest provider snapshot, the B2 repository |
| **2** | On two different storage systems | The provider's block storage and Backblaze's object storage |
| **1** | One copy offsite | B2: another provider, another region |
| **1** | One copy immutable | B2 Object Lock: 30 days during which nothing can be deleted |
| **0** | Zero errors, verified | `restic check` on a schedule, and restores proven by the drills |

#### 3.3. Expected End State
- every failure mode has a named recovery path and a drill;
- each scenario has its own RTO and RPO target;
- every path on the server is classified as backed up or deliberately excluded, with a reason;
- the repository password and the B2 key exist in the password manager, off the server;
- snapshots are used as change checkpoints; Restic to B2 is the backup.

---

> The model decides *what* to protect and *how fast* it has to come back. The next phase builds the backups themselves.

---

[← Overview](./00-overview.md) · **Phase 1 of 4** · [Next: Restic Backups to B2 →](./02-restic-b2-backups.md)
