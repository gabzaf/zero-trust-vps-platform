# Phase 4: Recovery Drills

[← Phase 3: Restore Runbooks](./03-restore-runbooks.md) · **Phase 4 of 4** · [Back to Overview →](./00-overview.md)

---

### In this phase
- [8. How the Drills Are Run](#8-how-the-drills-are-run)
  - [8.1. Rules](#81-rules)
  - [8.2. Measuring](#82-measuring)
- [9. The Drills](#9-the-drills)
  - [9.1. D1: Failed Release Rollback](#91-d1-failed-release-rollback)
  - [9.2. D2: Application Data Restore](#92-d2-application-data-restore)
  - [9.3. D3: Full Host Rebuild](#93-d3-full-host-rebuild)
- [10. Results and Follow-up](#10-results-and-follow-up)
  - [10.1. Results](#101-results)
  - [10.2. What the Drills Exposed](#102-what-the-drills-exposed)
  - [10.3. Open Items](#103-open-items)
  - [10.4. Expected End State](#104-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 8. How the Drills Are Run
This section fixes the rules and the stopwatch, so the three drills produce numbers that mean something.

#### 8.1. Rules
- **Follow the runbook as written.** If a step is wrong or missing, the drill records it and the runbook is fixed afterwards. Improvising during the drill would hide the gap.
- **Production impact is declared upfront.** D1 takes the client's site down for real, so it runs at a low-traffic hour and the client knows about it. D2 only affects an admin tool. D3 runs on a separate, temporary VPS and never touches production DNS.
- **Start from what a real incident would have.** D3 uses only the B2 repository and the password manager: no snapshot, no SSH access to the production host.
- **Everything is written down**, including what went wrong.

#### 8.2. Measuring
Two clocks, so no number depends on one source:

1. **Timestamps I take**: `date -Is` at the start of each step, written into the drill log.
2. **Uptime Kuma's incident history** (Case 03): an independent record of when a monitor went red and when it came back.

A small loop on the admin device gives the exact moment a service answers again:
```bash
start=$(date +%s)
until curl -fsS -m 3 -o /dev/null https://mysite.com/; do sleep 1; done
echo "answered after $(( $(date +%s) - start )) s"
```

| Measured | Meaning |
| :--- | :--- |
| **Time to detect** | From the failure to Kuma marking the monitor down |
| **Time to recover** (RTO) | From starting the recovery to the service answering correctly |
| **Data lost** (RPO) | From the snapshot used to the moment of the failure |

---

### 9. The Drills
This section runs each recovery path for real and records the result.

#### 9.1. D1: Failed Release Rollback
**Scenario**: a new release of the client's site doesn't start. **Target**: recover in under 60 seconds.

<details>
<summary><b>▶ View steps — D1</b></summary>

**Prepare** (the Case 02 change cycle)
```bash
cd /srv/apps/alves-jatoba
grep 'image:' docker-compose.yml                  # note the stable tag, e.g. alves-jatoba:1.0.0
docker pull busybox:1.36
docker tag busybox:1.36 alves-jatoba:drill-broken # a "release" that can't serve the site
```

**Execute the bad release**
```bash
date -Is                                           # T_fail
sed -i 's/alves-jatoba:1.0.0/alves-jatoba:drill-broken/' docker-compose.yml
docker compose up -d
```
The container starts BusyBox instead of the site and exits. Traefik has nothing to route to.

**Detect**: wait for Kuma's *Public site* monitor to turn red, then note the time (`T_detect`).

**Roll back** (Case 02, 7.5, method 1)
```bash
date -Is                                           # T_rollback
sed -i 's/alves-jatoba:drill-broken/alves-jatoba:1.0.0/' docker-compose.yml
docker compose up -d
```
Run the measuring loop from 8.2 at the same moment.

**Clean up**
```bash
docker image rm alves-jatoba:drill-broken
```
</details>

**Success criteria**: the site answers with its real content; Kuma records the incident; the stable tag is the one running.

| Date | Time to detect | Time to recover | Total outage (Kuma) | Data lost |
| :--- | :--- | :--- | :--- | :--- |
| <!-- TODO(drill): D1 date --> | <!-- TODO(drill) --> | <!-- TODO(drill) --> | <!-- TODO(drill) --> | None |

#### 9.2. D2: Application Data Restore
**Scenario**: Uptime Kuma's data is lost while the host is fine. **Target**: recover in under 10 minutes, losing at most 24 hours.

<details>
<summary><b>▶ View steps — D2</b></summary>

**Simulate the loss**
```bash
sudo restic-srv01 snapshots --host srv01 | tail -3  # note the latest snapshot's time
date -Is                                            # T_fail
cd /srv/apps/uptime-kuma && docker compose stop
sudo mv /srv/data/uptime-kuma /srv/data/uptime-kuma.drill-lost
docker compose up -d
```
Kuma starts empty and asks for a new admin account: monitors and history are gone.

**Restore** ([Phase 3, 7.3](./03-restore-runbooks.md#73-one-applications-data))
```bash
date -Is                                            # T_restore_start
docker compose stop
sudo mv /srv/data/uptime-kuma /srv/data/uptime-kuma.drill-empty
sudo restic-srv01 restore latest --target / --include /srv/data/uptime-kuma
docker compose up -d
date -Is                                            # T_restored (when the UI shows every monitor)
```

**Clean up**, after validating:
```bash
sudo rm -rf /srv/data/uptime-kuma.drill-lost /srv/data/uptime-kuma.drill-empty
```
</details>

**Success criteria**: every monitor is back with its history up to the snapshot's time; the backup push monitor still exists; no permission errors in `docker compose logs uptime-kuma`.

| Date | Snapshot used (time) | Time to recover | Data lost | Restored size |
| :--- | :--- | :--- | :--- | :--- |
| <!-- TODO(drill): D2 date --> | <!-- TODO(drill) --> | <!-- TODO(drill) --> | <!-- TODO(drill) --> | <!-- TODO(drill) --> |

#### 9.3. D3: Full Host Rebuild
**Scenario**: the production host is gone. A new one is built from the B2 repository and the password manager only. **Target**: the site served by the new host in under 2 hours, losing at most 24 hours.

<details>
<summary><b>▶ View steps — D3</b></summary>

**Before starting**
- Create a **temporary** VPS (hourly billing): AlmaLinux 9, admin SSH key added at creation.
- On the admin device, copy the WireGuard client config to a drill profile and change only its `Endpoint` to the temporary VPS's public IP. Bring the production tunnel **down** first: both hosts use the same keys and the same `10.10.10.1`.
- Don't enable the Restic timers on the drill host: it must not write snapshots into production's repository.

**Run [Phase 3, 7.4](./03-restore-runbooks.md#74-full-host-rebuild) steps a → f**, writing a timestamp at the start of each step:

| Step | Started | Notes |
| :--- | :--- | :--- |
| a. VPS created | <!-- TODO(drill) --> | |
| b. Packages installed | <!-- TODO(drill) --> | |
| c. Repository reached, staging restore done | <!-- TODO(drill) --> | |
| d. Perimeter restored (orders 1–5), drill tunnel up | <!-- TODO(drill) --> | |
| d. Platform restored (orders 6–10) | <!-- TODO(drill) --> | |
| e. Stacks up (including the site's build) | <!-- TODO(drill) --> | |
| f. Site answers over the tunnel; direct-to-origin times out | <!-- TODO(drill) --> | |

**After the drill**
```bash
# on the admin device
sudo wg-quick down vps-drill
sudo wg-quick up vps-admin
```
Then **destroy the temporary VPS** in the provider console and confirm it's gone: for the duration of the drill it held production's WireGuard, SSH host and Origin certificate keys.
</details>

**Success criteria**: the client site answers over the drill tunnel with its real content; a direct-to-origin request from outside times out; every Case 03 UI answers through the VPN; Kuma's history and Grafana's users are the restored ones.

| Date | Snapshot used (time) | Time to recover (a → f) | Data lost | Cutover |
| :--- | :--- | :--- | :--- | :--- |
| <!-- TODO(drill): D3 date --> | <!-- TODO(drill) --> | <!-- TODO(drill) --> | <!-- TODO(drill) --> | Not exercised: 3 DNS records ([7.5](./03-restore-runbooks.md#75-cutover)) |

> [!NOTE]
> The cutover is left out of the drill on purpose: changing production DNS would move the client's real traffic onto a temporary host. It's three record edits in Cloudflare; in a real incident they're the last step after f.

---

### 10. Results and Follow-up
This section is the honest summary: what was measured, and what the drills found that the runbooks didn't know.

#### 10.1. Results

| Drill | Target | Measured | Met |
| :---: | :--- | :--- | :---: |
| **D1** Rollback | < 60 s | <!-- TODO(drill) --> | <!-- TODO(drill) --> |
| **D2** App data restore | < 10 min, RPO ≤ 24 h | <!-- TODO(drill) --> | <!-- TODO(drill) --> |
| **D3** Full host rebuild | < 2 h, RPO ≤ 24 h | <!-- TODO(drill) --> | <!-- TODO(drill) --> |

#### 10.2. What the Drills Exposed
Every gap found during a drill is listed here with the fix applied to the runbook.

| Drill | What broke or was missing | Fix |
| :---: | :--- | :--- |
| <!-- TODO(drill): fill from the drill logs --> | | |

#### 10.3. Open Items

| # | Item | Why it matters | Next step |
| :---: | :--- | :--- | :--- |
| 1 | **Logs off the host** | A wiped host takes its last 7 days of logs with it (Phase 1, 2.2) | Ship logs to a second destination as they're written |
| 2 | **Alert routing** | Kuma would show a failed backup or a down site, but notifies nobody yet (Case 03) | One notification channel on every monitor, including the backup push monitor |
| 3 | **Drill schedule** | A runbook nobody has run for a year is a hypothesis again | D2 every quarter, D3 once a year, after any major platform change |
| 4 | **Database dumps** | If a stack with a real database is added, a nightly file copy and a 24 h RPO won't be enough | Logical dumps to `/srv/backups` before each backup, and an RPO decided per stack |
| 5 | **Automated rebuild** | Most of D3's time is manual, ordered steps | Turn 7.4 into an Ansible playbook and re-measure D3 |

#### 10.4. Expected End State
- all three drills were run, with timestamps, and their numbers are the RTO and RPO this case claims;
- every gap found during a drill is fixed in the runbook it came from;
- the temporary VPS from D3 is destroyed;
- the open items above are tracked;
- the provider snapshot from Phase 2 is replaced by `case04-drills-ok`.

---

> This closes the platform's lifecycle: provisioned and protected (Case 01), operated (Case 02), observed (Case 03), and now recoverable, with the numbers to prove it.

---

[← Phase 3: Restore Runbooks](./03-restore-runbooks.md) · **Phase 4 of 4** · [Back to Overview →](./00-overview.md)
