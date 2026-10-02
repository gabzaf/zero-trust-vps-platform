# Phase 2: Encrypted, Immutable Backups with Restic & Backblaze B2

[← Phase 1: Recovery Model](./01-recovery-model.md) · **Phase 2 of 4** · [Next: Restore Runbooks →](./03-restore-runbooks.md)

---

### In this phase
- [4. The Offsite Repository on B2](#4-the-offsite-repository-on-b2)
  - [4.1. Create the Bucket](#41-create-the-bucket)
  - [4.2. Object Lock: Why and How](#42-object-lock-why-and-how)
  - [4.3. A Key Scoped to One Bucket](#43-a-key-scoped-to-one-bucket)
- [5. The Restic Repository](#5-the-restic-repository)
  - [5.1. Why Restic?](#51-why-restic)
  - [5.2. Install Restic](#52-install-restic)
  - [5.3. Secrets and the Wrapper](#53-secrets-and-the-wrapper)
  - [5.4. Initialize the Repository](#54-initialize-the-repository)
- [6. The Nightly Backup Job](#6-the-nightly-backup-job)
  - [6.1. What Goes In](#61-what-goes-in)
  - [6.2. Consistent Copies of Live Databases](#62-consistent-copies-of-live-databases)
  - [6.3. The Backup Script](#63-the-backup-script)
  - [6.4. Scheduling with systemd](#64-scheduling-with-systemd)
  - [6.5. Retention and Integrity Checks](#65-retention-and-integrity-checks)
  - [6.6. Making Backups Visible](#66-making-backups-visible)
  - [6.7. Mandatory Tests](#67-mandatory-tests)
  - [6.8. Expected End State](#68-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 4. The Offsite Repository on B2
This section creates the place backups go: a private bucket at a provider unrelated to the VPS, where data can't be deleted for 30 days.

#### 4.1. Create the Bucket
In the Backblaze web console (account protected with MFA), **Buckets → Create a Bucket**:

| Setting | Value | Why |
| :--- | :--- | :--- |
| Bucket name | `srv01-restic-<random-suffix>` | Bucket names are global; a suffix avoids guessable names |
| Files in bucket | **Private** | Nothing in it is ever public |
| Default encryption | **Enable** (SSE-B2) | A second layer at rest; Restic already encrypts before upload |
| Object Lock | **Enable** | See 4.2 |

Then, in the bucket settings:

| Setting | Value |
| :--- | :--- |
| Object Lock default retention | **Governance**, **30 days** |
| Lifecycle | Custom rule: never hide automatically, **delete hidden files 31 days after hiding** |

The lifecycle rule is what eventually frees space: Restic's deletions only *hide* files (4.2), and B2 removes them for good a day after their lock can no longer protect anything.

#### 4.2. Object Lock: Why and How
A backup that the server can delete isn't protection against whoever controls the server. If an attacker gets root, the B2 credentials in `/etc/restic/env` are theirs too, and the first thing ransomware does is delete the backups.

Object Lock changes what those credentials can do:

- every object Restic uploads gets a 30-day retention lock on its version;
- a delete request without a version ID doesn't remove anything: it adds a delete marker and the file becomes *hidden*. The locked version is still there and can be restored;
- deleting a locked version itself is refused until its retention ends, unless the key has the `bypassGovernance` capability, and the server's key doesn't (4.3).

So the worst the server's own key can do is *hide* data, and anything hidden within the last 30 days can be brought back.

| Mode | Who can shorten or remove a lock | Why I chose / didn't choose it |
| :--- | :--- | :--- |
| **Governance** ✅ | Only a key with `bypassGovernance`: the account owner, from the console, with MFA | Protects against the server; I can still clean up a mistake from my own account |
| Compliance | Nobody, not even the account owner | Strongest, but a misconfigured retention would be a cost I could never undo |

> [!NOTE]
> Restic talks to B2 through its **S3-compatible API**, which is the access method Restic's documentation recommends for B2. Object Lock behaves as above on that API. Whether it does in practice is proven by [test 6.7-T6](#67-mandatory-tests), not assumed.
> <!-- TODO(verify): T6 result on the real bucket; if uploads to the locked bucket fail over the S3 API, switch the repository URL to Restic's native b2: backend and repeat 6.7 -->

#### 4.3. A Key Scoped to One Bucket
**App Keys → Add a New Application Key**:

| Setting | Value |
| :--- | :--- |
| Name | `srv01-restic` |
| Allow access to bucket(s) | **Only** `srv01-restic-<suffix>` |
| Type of access | Read and Write |
| `bypassGovernance` | **Not granted** |

The key ID and application key are shown **once**. They go straight into the password manager, then into the server in 5.3. The account's master key never leaves the console.

| What this key can do | What it can't do |
| :--- | :--- |
| Upload, list, read and hide files in one bucket | See or touch any other bucket |
| Run Restic's backup, restore, forget, prune and check | Remove a version that's still under its 30-day lock |

---

### 5. The Restic Repository
This section sets up the tool that encrypts, deduplicates and uploads the backups.

#### 5.1. Why Restic?

| Need | How Restic covers it |
| :--- | :--- |
| Encryption I control | AES-256 client-side, before anything leaves the server; B2 only ever sees ciphertext |
| Small nightly uploads | Content-defined deduplication: after the first run, only changed chunks are sent |
| Granular restore | One file, one directory, or a whole snapshot, by path |
| Integrity | `restic check` verifies the repository structure and can re-read a sample of the actual data |
| Simple to operate | One static binary, packaged in EPEL for AlmaLinux |

#### 5.2. Install Restic
```bash
sudo dnf install -y epel-release
sudo dnf install -y restic
restic version
```
```text
restic 0.x.y compiled with go1.x on linux/amd64
```
<!-- TODO(verify): restic version on the server -->

Installing from EPEL means Restic updates with the rest of the system through `dnf`, signed by the EPEL key, instead of being a binary someone has to remember to replace.

#### 5.3. Secrets and the Wrapper
<details>
<summary><b>▶ View commands — /etc/restic, the password and the environment file</b></summary>

```bash
sudo install -d -m 0700 -o root -g root /etc/restic

# Repository password: generated on the server, copied to the password manager right away
sudo sh -c 'umask 077; openssl rand -base64 48 > /etc/restic/password'
sudo chmod 0400 /etc/restic/password
sudo cat /etc/restic/password      # copy into the password manager, then clear the terminal

sudo nano /etc/restic/env
```
```bash
RESTIC_REPOSITORY=s3:https://s3.<region>.backblazeb2.com/srv01-restic-<suffix>/srv01
RESTIC_PASSWORD_FILE=/etc/restic/password
AWS_ACCESS_KEY_ID=<B2 key ID>
AWS_SECRET_ACCESS_KEY=<B2 application key>
```
```bash
sudo chmod 0600 /etc/restic/env
```
</details>

A small wrapper loads that environment, so every manual command reads the same configuration instead of exporting secrets into my shell:

<details>
<summary><b>▶ View script — /usr/local/bin/restic-srv01</b></summary>

```bash
sudo nano /usr/local/bin/restic-srv01
```
```bash
#!/usr/bin/env bash
# Run restic against srv01's repository. Usage: sudo restic-srv01 <restic args>
set -a; . /etc/restic/env; set +a
exec restic "$@"
```
```bash
sudo chmod 0750 /usr/local/bin/restic-srv01
```
</details>

| File | Mode | Holds |
| :--- | :---: | :--- |
| `/etc/restic/password` | `0400` | The repository password |
| `/etc/restic/env` | `0600` | Repository URL and the B2 key |
| `/usr/local/bin/restic-srv01` | `0750` | No secrets; only loads the file above |

#### 5.4. Initialize the Repository
```bash
sudo restic-srv01 init
```
```text
created restic repository 1a2b3c4d5e at s3:https://s3.<region>.backblazeb2.com/srv01-restic-<suffix>/srv01

Please note that knowledge of your password is required to access
the repository. Losing your password means that your data is
irrecoverably lost.
```

That warning is the reason for [Phase 1, 2.3](./01-recovery-model.md#23-the-secrets-outside-the-backup): the password in the password manager is the backup of the backup.

---

### 6. The Nightly Backup Job
This section turns the repository into an automatic, consistent, self-checking backup that reports when it didn't happen.

#### 6.1. What Goes In
The scope from [Phase 1, 2.1](./01-recovery-model.md#21-state-inventory) becomes two files:

<details>
<summary><b>▶ View config — /etc/restic/includes.txt and /etc/restic/excludes.txt</b></summary>

```bash
sudo nano /etc/restic/includes.txt
```
```text
/srv/apps
/srv/data
/etc
/usr/local/bin
/var/spool/cron/root
/home/<username>/.ssh
```

```bash
sudo nano /etc/restic/excludes.txt
```
```text
# High-churn history that is rebuilt automatically (Phase 1, 2.2)
/srv/data/loki
/srv/data/netdata/lib
/srv/data/netdata/cache
```
</details>

#### 6.2. Consistent Copies of Live Databases
Uptime Kuma and Grafana keep their state in SQLite; Portainer uses BoltDB. Copying one of those files while it's being written can capture a half-written page, and the copy then fails to open on restore. The backup would look fine until the day it's needed.

The fix is simple at this scale: stop those three containers for the duration of the backup and start them again right after.

| Container | Stopped during backup | Impact |
| :--- | :---: | :--- |
| `uptime-kuma`, `grafana`, `portainer` | ✅ | Admin UIs unavailable for about a minute at night; no public impact |
| The client site, Traefik | ❌ | Stateless (or state only in files that don't change at night); never interrupted |
| Netdata, Loki, Promtail | ❌ | Their data is excluded (6.1) |

#### 6.3. The Backup Script
<details>
<summary><b>▶ View script — /usr/local/bin/restic-backup.sh</b></summary>

```bash
sudo nano /usr/local/bin/restic-backup.sh
```
```bash
#!/usr/bin/env bash
# =============================================================================
# Nightly backup of srv01 to Backblaze B2 (Restic).
# Stops the containers that keep on-disk databases, backs up, restarts them,
# then reports success to an Uptime Kuma push monitor.
# =============================================================================
set -euo pipefail

set -a; . /etc/restic/env; set +a
STATEFUL=(uptime-kuma grafana portainer)
PUSH_TOKEN_FILE=/etc/restic/kuma-push-token

restart_stateful() { docker start "${STATEFUL[@]}" >/dev/null 2>&1 || true; }
trap restart_stateful EXIT          # the containers come back even if the backup fails

# 1. Consistent copy: no writes to SQLite/BoltDB while they're being read
docker stop "${STATEFUL[@]}" >/dev/null

# 2. Back up the declared scope
restic backup \
  --files-from /etc/restic/includes.txt \
  --exclude-file /etc/restic/excludes.txt \
  --host srv01 --tag nightly

# 3. Restart now, not at exit, so the heartbeat can reach Uptime Kuma
restart_stateful
trap - EXIT

# 4. Heartbeat: only reached if the backup succeeded (set -e)
for _ in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' uptime-kuma 2>/dev/null)" = "healthy" ] && break
  sleep 5
done
KUMA_IP=$(docker inspect -f '{{(index .NetworkSettings.Networks "proxy").IPAddress}}' uptime-kuma)
curl -fsS -m 10 -o /dev/null \
  "http://${KUMA_IP}:3001/api/push/$(cat "$PUSH_TOKEN_FILE")?status=up&msg=backup-ok"
```
```bash
sudo chmod 0750 /usr/local/bin/restic-backup.sh
```
</details>

| Decision | Why |
| :--- | :--- |
| `set -euo pipefail` | Any failure stops the script before the heartbeat, so a failed backup is never reported as a success. |
| `trap ... EXIT` | Whatever happens, the admin UIs come back. A failed backup shouldn't also become an outage. |
| Restic exit code `3` counts as failure | Exit code 3 means some files couldn't be read: the snapshot is incomplete, and it's treated that way. |
| Heartbeat to the container's address | Kuma isn't published (Case 03). The host reaches it directly on the `proxy` bridge, without going through Traefik. |

#### 6.4. Scheduling with systemd
<details>
<summary><b>▶ View config — restic-backup.service and restic-backup.timer</b></summary>

```bash
sudo nano /etc/systemd/system/restic-backup.service
```
```ini
[Unit]
Description=Nightly Restic backup of srv01 to Backblaze B2
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/restic-backup.sh
Nice=10
IOSchedulingClass=idle
```

```bash
sudo nano /etc/systemd/system/restic-backup.timer
```
```ini
[Unit]
Description=Run the Restic backup every night

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now restic-backup.timer
```
</details>

| Setting | Why |
| :--- | :--- |
| `Persistent=true` | If the server was off at 03:30, the backup runs as soon as it's back, instead of skipping a day. |
| `Nice=10`, `IOSchedulingClass=idle` | The backup yields CPU and disk to the services. |
| systemd instead of cron | Every run is in the journal with its exit status, which Loki already collects (Case 03). |

#### 6.5. Retention and Integrity Checks
A second, weekly job applies retention and checks the repository:

<details>
<summary><b>▶ View config — restic-maintenance.service and restic-maintenance.timer</b></summary>

```bash
sudo nano /etc/systemd/system/restic-maintenance.service
```
```ini
[Unit]
Description=Weekly Restic retention and integrity check
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/restic-srv01 forget --host srv01 --tag nightly \
  --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
ExecStart=/usr/local/bin/restic-srv01 check --read-data-subset=10%
Nice=10
IOSchedulingClass=idle
```

```bash
sudo nano /etc/systemd/system/restic-maintenance.timer
```
```ini
[Unit]
Description=Run Restic maintenance weekly

[Timer]
OnCalendar=Sun *-*-* 05:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now restic-maintenance.timer
```
</details>

| Policy | Keeps |
| :--- | :--- |
| `--keep-daily 7` | One snapshot per day for the last week |
| `--keep-weekly 4` | One per week for the last month |
| `--keep-monthly 6` | One per month for the last six months |
| `check --read-data-subset=10%` | Verifies the repository structure, then re-downloads and verifies a random 10% of the data, so corruption is caught without downloading everything every week |

> [!NOTE]
> With Object Lock, `prune` doesn't free space immediately: it hides what it deletes, and B2's lifecycle removes it 31 days later (4.1). At this repository's size that's a few cents of extra storage, and it's the price of being able to undo a malicious prune.

#### 6.6. Making Backups Visible
A backup that silently stops running is discovered on the day it's needed. Two signals from Case 03 prevent that:

**1. Uptime Kuma push monitor**: in Kuma, **Add New Monitor → Push**, heartbeat interval **90000 s** (25 hours). Kuma shows a push URL ending in a token; that token goes into a root-only file:
```bash
sudo sh -c 'umask 077; echo "<push-token>" > /etc/restic/kuma-push-token'
```
If a night passes without a successful backup, the monitor turns red.

**2. Loki queries** (Grafana → Explore):

| Question | LogQL |
| :--- | :--- |
| Did last night's backup run, and what did it save? | `{job="journal", unit="restic-backup.service"} \|= "snapshot"` |
| Did any backup or maintenance run fail? | `{job="journal", unit=~"restic-(backup\|maintenance).service"} \|~ "(?i)(fatal\|error\|failed)"` |
| Did the weekly integrity check pass? | `{job="journal", unit="restic-maintenance.service"} \|= "no errors were found"` |

#### 6.7. Mandatory Tests
<details>
<summary><b>▶ View tests — the job runs, the data is there, the secrets are closed, the lock holds</b></summary>

**T1: a manual run succeeds end to end**
```bash
sudo systemctl start restic-backup.service
journalctl -u restic-backup.service -n 15 --no-pager
```
```text
... Files:  <n> new, <n> changed, <n> unmodified
... Added to the repository: <size>
... snapshot 9f8e7d6c saved
... restic-backup.service: Deactivated successfully.
```
<!-- TODO(verify): real output from the first run, with sizes and duration -->

**T2: the snapshot is in the repository**
```bash
sudo restic-srv01 snapshots
```
```text
ID        Time                 Host   Tags     Paths
9f8e7d6c  2026-xx-xx 03:4x:xx  srv01  nightly  /etc
                                               /home/<username>/.ssh
                                               /srv/apps
                                               /srv/data
                                               /usr/local/bin
                                               /var/spool/cron/root
```

**T3: the stateful containers came back**
```bash
docker ps --filter name=uptime-kuma --filter name=grafana --filter name=portainer \
  --format '{{.Names}}\t{{.Status}}'
```
All three `Up ... (healthy)`.

**T4: secrets are root-only**
```bash
sudo stat -c '%a %U %n' /etc/restic/password /etc/restic/env /etc/restic/kuma-push-token
```
```text
400 root /etc/restic/password
600 root /etc/restic/env
600 root /etc/restic/kuma-push-token
```

**T5: the heartbeat arrived**: the Kuma push monitor is green, with a beat at the time of T1.

**T6: the server's key can't delete a locked version**

List the versions of the repository's `config` object, then try to delete one with the server's own credentials:
```bash
sudo bash -c 'set -a; . /etc/restic/env; set +a
curl -sS --aws-sigv4 "aws:amz:<region>:s3" --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  "https://s3.<region>.backblazeb2.com/srv01-restic-<suffix>?versions&prefix=srv01/config"'
```
Copy the `<VersionId>` from the output, then:
```bash
sudo bash -c 'set -a; . /etc/restic/env; set +a
curl -sS -X DELETE --aws-sigv4 "aws:amz:<region>:s3" --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  "https://s3.<region>.backblazeb2.com/srv01-restic-<suffix>/srv01/config?versionId=<VersionId>"'
```
The request must be **refused** with an access or lock error, and `sudo restic-srv01 snapshots` must still work afterwards.
<!-- TODO(verify): exact error returned by B2 -->

**T7: a failure is visible**: temporarily break the repository URL in `/etc/restic/env`, run T1 again, and confirm that the service fails, the Loki failure query returns it, and no heartbeat is sent. Restore the URL.
</details>

#### 6.8. Expected End State
- a private B2 bucket with Object Lock (governance, 30 days) and a lifecycle that deletes hidden files after 31 days;
- an application key limited to that bucket, without `bypassGovernance`;
- an encrypted Restic repository, with its password and key in the password manager and in root-only files on the server;
- a nightly backup of the declared scope, with the database containers stopped during the copy and always restarted;
- weekly retention and a random 10% data check;
- an Uptime Kuma push monitor and Loki queries that make a missing or failed backup visible;
- proof that the server's own key can't delete a locked backup.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a provider snapshot named `case04-phase2-backups-ok`. From now on, the provider snapshot and the B2 repository are two independent copies.

---

> The platform now has backups that leave the provider, can't be read by the provider and can't be deleted by the server. None of that is proven until something is restored. That's the next phase.

---

[← Phase 1: Recovery Model](./01-recovery-model.md) · **Phase 2 of 4** · [Next: Restore Runbooks →](./03-restore-runbooks.md)
