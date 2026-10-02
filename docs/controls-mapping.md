# Controls Mapping

[← Back to README](../README.md)

This document maps every control on the platform to **CIS Critical Security Controls v8** and **NIST Cybersecurity Framework 2.0**, links each one to the case section that implements it and to the test that proves it, and lists the gaps that are still open.

---

### In this document
- [1. How to Read This Mapping](#1-how-to-read-this-mapping)
- [2. Coverage at a Glance](#2-coverage-at-a-glance)
- [3. Mapping by Case](#3-mapping-by-case)
  - [3.1. Case 01: Perimeter and Zero-Trust Administration](#31-case-01-perimeter-and-zero-trust-administration)
  - [3.2. Case 02: Container Platform and Ingress](#32-case-02-container-platform-and-ingress)
  - [3.3. Case 03: VPN-only Observability](#33-case-03-vpn-only-observability)
  - [3.4. Case 04: Backups and Recovery (Planned)](#34-case-04-backups-and-recovery-planned)
- [4. Known Gaps](#4-known-gaps)
- [5. Outside This Repository](#5-outside-this-repository)
- [6. References](#6-references)

---

### 1. How to Read This Mapping

**Two frameworks, two questions.**

| Framework | What it answers | How it's cited here |
| :--- | :--- | :--- |
| **[CIS Controls v8](https://www.cisecurity.org/controls/v8)** | *What should be done?* 18 controls broken into concrete, testable **safeguards**, prioritized in Implementation Groups (IG1 is the baseline every organization should meet) | By safeguard: `4.4` = Control 4, Safeguard 4 |
| **[NIST CSF 2.0](https://www.nist.gov/cyberframework)** | *What outcome is achieved?* Six functions (Govern, Identify, Protect, Detect, Respond, Recover) broken into categories and subcategories | By subcategory: `PR.IR-01` = Protect → Technology Infrastructure Resilience, outcome 01 |

CIS says what to build; NIST says what that building achieves. Citing both lets a reviewer check the work against either one. CIS publishes its own [mapping of CIS Controls v8 to NIST CSF 2.0](https://www.cisecurity.org/insights/white-papers/cis-controls-v8-mapping-to-nist-csf-2-0), which is the crosswalk this document follows.

> [!NOTE]
> **Versions.** Safeguard numbers here are from CIS Controls v8. [CIS Controls v8.1](https://www.cisecurity.org/controls/v8-1) (2024) revised Safeguard descriptions and asset classes and added the *Govern* function to align with NIST CSF 2.0. Check its change log before citing a Safeguard by its v8.1 wording. Every official source is listed in [section 6](#6-references).

**Each row links two things.** *Implemented in* points to the case section where the control is built. *Verified by* points to the test that proves it works. A control without a test is a claim, not a control.

**Status**

| | Meaning |
| :---: | :--- |
| ✅ | Implemented and tested in a published case |
| 🟡 | Implemented, but doesn't meet the full safeguard (the gap is in [section 4](#4-known-gaps)) |
| 🔵 | Designed and documented; not running yet (Case 04) |
| ❌ | Not implemented (listed in [section 4](#4-known-gaps)) |

**Scope.** One VPS, one administrator, one client site. Safeguards that assume an organization (asset inventories of hundreds of devices, security awareness training, service-provider management) are out of scope. The NIST *Govern* function is covered elsewhere ([section 5](#5-outside-this-repository)).

---

### 2. Coverage at a Glance

| CIS Control | Safeguards on this platform | Status |
| :--- | :--- | :---: |
| **2** Inventory and Control of Software Assets | 2.1 · 2.2 | 🟡 |
| **3** Data Protection | 3.3 · 3.10 · 3.11 | 🟡 |
| **4** Secure Configuration of Enterprise Assets and Software | 4.1 · 4.4 · 4.6 · 4.7 | ✅ |
| **5** Account Management | 5.4 | ✅ |
| **6** Access Control Management | 6.4 · 6.5 | ❌ |
| **7** Continuous Vulnerability Management | 7.1 · 7.3 · 7.4 · 7.5 · 7.6 | 🟡 |
| **8** Audit Log Management | 8.1 · 8.2 · 8.3 · 8.5 · 8.9 · 8.10 · 8.11 | 🟡 |
| **10** Malware Defenses | 10.1 | ❌ |
| **11** Data Recovery | 11.1 · 11.2 · 11.3 · 11.4 · 11.5 | 🔵 |
| **12** Network Infrastructure Management | 12.2 · 12.7 | ✅ |
| **13** Network Monitoring and Defense | 13.1 · 13.4 · 13.10 | 🟡 |
| **16** Application Software Security | 16.7 | ✅ |

| NIST CSF 2.0 function | Subcategories on this platform |
| :--- | :--- |
| **Identify** | ID.AM-02 |
| **Protect** | PR.AA-03 · PR.AA-05 · PR.DS-02 · PR.DS-11 · PR.PS-01 · PR.PS-02 · PR.PS-04 · PR.IR-01 |
| **Detect** | DE.CM-01 · DE.CM-03 · DE.CM-09 · DE.AE-03 |
| **Recover** | RC.RP-01 · RC.RP-03 (Case 04, planned) |

---

### 3. Mapping by Case

#### 3.1. Case 01: Perimeter and Zero-Trust Administration

| Control on the platform | CIS v8 | NIST CSF 2.0 | Implemented in | Verified by | |
| :--- | :--- | :--- | :--- | :--- | :---: |
| SSH: Ed25519 keys only, no passwords, no `root` login, `AllowUsers`, scoped `sudo` | 4.7 · 5.4 | PR.AA-03 · PR.AA-05 | [C01 §4](../cases/case-01-perimeter-foundation-and-zero-trust-admin/02-ssh-vpn-hardening.md#4-admin-access-hardening-etcsshsshd_configd) | [C01 §7](../cases/case-01-perimeter-foundation-and-zero-trust-admin/02-ssh-vpn-hardening.md#7-exclusively-private-administration) | ✅ |
| WireGuard site-to-client tunnel; SSH reachable only via `wg0` | 4.6 · 12.7 | PR.AA-03 · PR.IR-01 | [C01 §5](../cases/case-01-perimeter-foundation-and-zero-trust-admin/02-ssh-vpn-hardening.md#5-vpn-site-to-client-s2c-and-private-administration) | [C01 §7](../cases/case-01-perimeter-foundation-and-zero-trust-admin/02-ssh-vpn-hardening.md#7-exclusively-private-administration) | ✅ |
| Host firewall: `INPUT` default DROP; only WireGuard and Cloudflare-sourced 80/443 accepted | 4.4 · 12.2 | PR.IR-01 | [C01 §8](../cases/case-01-perimeter-foundation-and-zero-trust-admin/03-firewall-monitoring.md#8-perimeter-firewall-and-network-isolation), [§10.2](../cases/case-01-perimeter-foundation-and-zero-trust-admin/04-cloudflare-tls.md#102-adjust-local-firewall-to-cloudflare-aware) | [C01 §8.6](../cases/case-01-perimeter-foundation-and-zero-trust-admin/03-firewall-monitoring.md#86-mandatory-tests), [§10.4](../cases/case-01-perimeter-foundation-and-zero-trust-admin/04-cloudflare-tls.md#104-mandatory-tests) | ✅ |
| `sshd` at `LogLevel VERBOSE`; Fail2ban as a second line behind `sshd` | 8.2 · 8.5 | PR.PS-04 · DE.CM-03 | [C01 §9](../cases/case-01-perimeter-foundation-and-zero-trust-admin/03-firewall-monitoring.md#9-active-monitoring-and-incident-response) | [C01 §9.5](../cases/case-01-perimeter-foundation-and-zero-trust-admin/03-firewall-monitoring.md#95-controlled-tests-mandatory) | ✅ |
| Cloudflare proxy hides the origin IP | 12.2 | PR.IR-01 | [C01 §10](../cases/case-01-perimeter-foundation-and-zero-trust-admin/04-cloudflare-tls.md#10-cloudflare-proxy-and-infrastructure-obfuscation) | [C01 §10.4](../cases/case-01-perimeter-foundation-and-zero-trust-admin/04-cloudflare-tls.md#104-mandatory-tests) | ✅ |
| Full (Strict) TLS between Cloudflare and the origin, with an Origin CA certificate | 3.10 | PR.DS-02 | [C01 §11](../cases/case-01-perimeter-foundation-and-zero-trust-admin/04-cloudflare-tls.md#11-end-to-end-encryption-with-full-strict-ssl) | [C01 §11.7](../cases/case-01-perimeter-foundation-and-zero-trust-admin/04-cloudflare-tls.md#117-verify-files-on-the-server) | ✅ |
| Cloudflare WAF: managed and custom rules, rate limiting | 13.10 | PR.IR-01 · DE.CM-01 | [C01 §12](../cases/case-01-perimeter-foundation-and-zero-trust-admin/05-cloudflare-waf.md#12-cloudflare-waf-for-network-edge-blocking) | [C01 §12.7](../cases/case-01-perimeter-foundation-and-zero-trust-admin/05-cloudflare-waf.md#127-mandatory-tests) | ✅ |

#### 3.2. Case 02: Container Platform and Ingress

| Control on the platform | CIS v8 | NIST CSF 2.0 | Implemented in | Verified by | |
| :--- | :--- | :--- | :--- | :--- | :---: |
| Fixed `/srv` layout; configuration as versioned files | 4.1 | PR.PS-01 | [C02 §1](../cases/case-02-container-platform-and-traefik-ingress/01-srv-layout-docker-engine.md#1-production-directory-structure-srv) | [C02 §1.6](../cases/case-02-container-platform-and-traefik-ingress/01-srv-layout-docker-engine.md#16-expected-end-state) | ✅ |
| Docker from the official repository; hardened daemon (`icc` off, `no-new-privileges`, log rotation, `live-restore`, ulimits) | 4.1 | PR.PS-01 | [C02 §2](../cases/case-02-container-platform-and-traefik-ingress/01-srv-layout-docker-engine.md#2-docker-engine) | [C02 §2.6](../cases/case-02-container-platform-and-traefik-ingress/01-srv-layout-docker-engine.md#26-mandatory-tests) | ✅ |
| `DOCKER-USER` filter: published ports accept only Cloudflare on 80/443, fails closed | 4.4 · 12.2 | PR.IR-01 | [C02 §3](../cases/case-02-container-platform-and-traefik-ingress/02-docker-firewall.md#3-docker-and-the-host-firewall) | [C02 §3.9](../cases/case-02-container-platform-and-traefik-ingress/02-docker-firewall.md#39-mandatory-tests) | ✅ |
| Segmented networks: shared `proxy`, per-stack internal networks without egress, no published database ports | 12.2 · 13.4 | PR.IR-01 | [C02 §4](../cases/case-02-container-platform-and-traefik-ingress/03-networks-state.md#4-network-segmentation) | [C02 §4.8](../cases/case-02-container-platform-and-traefik-ingress/03-networks-state.md#48-mandatory-tests) | ✅ |
| State in bind mounts under `/srv/data`, owned by each container's UID | 3.3 | PR.AA-05 | [C02 §5](../cases/case-02-container-platform-and-traefik-ingress/03-networks-state.md#5-persistent-state) | [C02 §5.5](../cases/case-02-container-platform-and-traefik-ingress/03-networks-state.md#55-mandatory-tests) | ✅ |
| Healthchecks, restart policies, health-gated dependencies | — | DE.CM-09 | [C02 §6](../cases/case-02-container-platform-and-traefik-ingress/04-health-change-cycle.md#6-health-restart-policies-and-dependencies) | [C02 §6.6](../cases/case-02-container-platform-and-traefik-ingress/04-health-change-cycle.md#66-verification-and-common-failures) | ✅ |
| Pinned images from official sources; changelog-gated change cycle with rollback | 2.1 · 7.1 · 7.4 | ID.AM-02 · PR.PS-02 | [C02 §7](../cases/case-02-container-platform-and-traefik-ingress/04-health-change-cycle.md#7-change-cycle-updates-and-rollback) | [C02 §7.5](../cases/case-02-container-platform-and-traefik-ingress/04-health-change-cycle.md#75-rollback) | 🟡 |
| Traefik as the single ingress: Origin certificate with TLS 1.2+, HSTS and security headers, per-client rate limiting | 3.10 · 16.7 | PR.DS-02 · PR.PS-01 | [C02 §8](../cases/case-02-container-platform-and-traefik-ingress/05-traefik-ingress.md#8-traefik-v3-as-the-single-ingress) | [C02 §9.3](../cases/case-02-container-platform-and-traefik-ingress/05-traefik-ingress.md#93-mandatory-tests) | ✅ |
| VPN-only admin routers (`ipAllowList`) and split-horizon DNS | 4.6 · 12.7 | PR.AA-05 · PR.IR-01 | [C02 §9.2](../cases/case-02-container-platform-and-traefik-ingress/05-traefik-ingress.md#92-vpn-only-dashboard-split-horizon-dns) | [C02 §9.3](../cases/case-02-container-platform-and-traefik-ingress/05-traefik-ingress.md#93-mandatory-tests) | ✅ |
| JSON access log with the real client IP | 8.2 · 8.5 | PR.PS-04 | [C02 §8.5](../cases/case-02-container-platform-and-traefik-ingress/05-traefik-ingress.md#85-static-configuration) | [C02 §9.3](../cases/case-02-container-platform-and-traefik-ingress/05-traefik-ingress.md#93-mandatory-tests) | ✅ |

The change cycle is 🟡 because application updates are deliberate and manual (7.4 asks for automated patch management) and nothing scans the pinned images for known vulnerabilities yet ([gaps 5–6](#4-known-gaps)).

#### 3.3. Case 03: VPN-only Observability

| Control on the platform | CIS v8 | NIST CSF 2.0 | Implemented in | Verified by | |
| :--- | :--- | :--- | :--- | :--- | :---: |
| One access pattern for every admin UI: split-horizon DNS, `vpn-allowlist`, no published ports | 4.6 · 12.7 | PR.AA-05 · PR.IR-01 | [C03 §2](../cases/case-03-observability-metrics-logs-availability/01-observability-model-access.md#2-the-access-pattern-for-every-dashboard) | [C03 §2.4](../cases/case-03-observability-metrics-logs-availability/01-observability-model-access.md#24-mandatory-tests) | ✅ |
| Cockpit bound to the WireGuard address only (no public or IPv6 listener) | 4.1 · 12.2 | PR.IR-01 | [C03 §3.3](../cases/case-03-observability-metrics-logs-availability/02-host-and-container-views.md#33-listen-only-on-the-vpn-address) | [C03 §3.6](../cases/case-03-observability-metrics-logs-availability/02-host-and-container-views.md#36-mandatory-tests) | ✅ |
| Portainer for inspection only; the Compose files stay the source of truth | 4.1 | PR.PS-01 | [C03 §4](../cases/case-03-observability-metrics-logs-availability/02-host-and-container-views.md#4-portainer-the-container-view) | [C03 §4.5](../cases/case-03-observability-metrics-logs-availability/02-host-and-container-views.md#45-mandatory-tests) | ✅ |
| Per-second host and container metrics (Netdata) | — | DE.CM-09 | [C03 §5](../cases/case-03-observability-metrics-logs-availability/03-metrics-netdata.md#5-netdata-metrics-for-the-host-and-every-container) | [C03 §5.6](../cases/case-03-observability-metrics-logs-availability/03-metrics-netdata.md#56-mandatory-tests) | ✅ |
| Centralized logs: container output, the journal (`sshd`, `sudo`, Fail2ban, kernel) and the Traefik access log | 8.1 · 8.2 · 8.9 | PR.PS-04 · DE.AE-03 | [C03 §6](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#6-log-pipeline-design), [§7](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#7-deploying-the-stack) | [C03 §8.3](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#83-mandatory-tests) | ✅ |
| 7-day retention enforced by the compactor; Traefik's files rotated daily | 8.3 · 8.10 | PR.PS-04 | [C03 §7.4](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#74-loki-configuration-and-retention), [§7.7](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#77-rotating-traefiks-log-files) | [C03 §8.3](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#83-mandatory-tests) | 🟡 |
| Log store isolated (internal network, no egress); Loki and Grafana not running as root; file-based admin secret | 4.1 · 12.2 | PR.PS-01 · PR.IR-01 | [C03 §6.3](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#63-pipeline-and-network-isolation), [§7.1](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#71-directories-and-ownership), [§7.5](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#75-grafana-data-source-and-admin-secret) | [C03 §8.3](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#83-mandatory-tests) | ✅ |
| Security queries: admin logins, `sudo`, bans, VPN-allow-list `403`s, 5xx spikes, 4xx sources | 8.11 | DE.CM-03 · DE.AE-03 | [C03 §8.1](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#81-security-queries) | [C03 §8.2](../cases/case-03-observability-metrics-logs-availability/04-centralized-logs.md#82-the-log-dashboard) | 🟡 |
| End-to-end availability through Cloudflare; container health through the Docker API | — | DE.CM-09 | [C03 §9](../cases/case-03-observability-metrics-logs-availability/05-availability-socket-review.md#9-uptime-kuma-is-it-actually-answering) | [C03 §9.6](../cases/case-03-observability-metrics-logs-availability/05-availability-socket-review.md#96-mandatory-tests) | ✅ |
| Alert routing for monitors | 13.1 | DE.CM-09 | [C03 §9.5](../cases/case-03-observability-metrics-logs-availability/05-availability-socket-review.md#95-alert-routing) | — | ❌ |
| Inventory of every Docker-socket consumer, with justification | 2.1 · 5.4 | ID.AM-02 · PR.AA-05 | [C03 §10.1](../cases/case-03-observability-metrics-logs-availability/05-availability-socket-review.md#101-docker-socket-inventory) | [C03 §10.1](../cases/case-03-observability-metrics-logs-availability/05-availability-socket-review.md#101-docker-socket-inventory) | ✅ |

`—` in the CIS column means no CIS safeguard asks for it: performance metrics and availability checks are operational monitoring. They're mapped to NIST, which covers monitoring of runtime environments (DE.CM-09).

#### 3.4. Case 04: Backups and Recovery (Planned)

| Control on the platform | CIS v8 | NIST CSF 2.0 | Implemented in | Verified by | |
| :--- | :--- | :--- | :--- | :--- | :---: |
| Recovery model: failure modes, state inventory, RTO/RPO per scenario, secrets held off-server | 11.1 | PR.DS-11 | [C04 §1–2](../cases/case-04-backup-recovery-drills/01-recovery-model.md#1-what-can-go-wrong) | — | 🔵 |
| Nightly Restic backups, encrypted client-side, to another provider; consistent copies of live databases | 11.2 · 3.11 | PR.DS-11 | [C04 §6](../cases/case-04-backup-recovery-drills/02-restic-b2-backups.md#6-the-nightly-backup-job) | [C04 §6.7](../cases/case-04-backup-recovery-drills/02-restic-b2-backups.md#67-mandatory-tests) | 🔵 |
| B2 Object Lock (governance, 30 days); a bucket-scoped key without `bypassGovernance` | 11.3 · 11.4 | PR.DS-11 | [C04 §4](../cases/case-04-backup-recovery-drills/02-restic-b2-backups.md#4-the-offsite-repository-on-b2) | [C04 §6.7 (T6)](../cases/case-04-backup-recovery-drills/02-restic-b2-backups.md#67-mandatory-tests) | 🔵 |
| Retention policy and weekly integrity check (`restic check`) | 11.3 | PR.DS-11 · RC.RP-03 | [C04 §6.5](../cases/case-04-backup-recovery-drills/02-restic-b2-backups.md#65-retention-and-integrity-checks) | [C04 §6.7](../cases/case-04-backup-recovery-drills/02-restic-b2-backups.md#67-mandatory-tests) | 🔵 |
| Backup heartbeat (Uptime Kuma push) and failure queries in Loki | 8.2 | DE.CM-09 | [C04 §6.6](../cases/case-04-backup-recovery-drills/02-restic-b2-backups.md#66-making-backups-visible) | [C04 §6.7](../cases/case-04-backup-recovery-drills/02-restic-b2-backups.md#67-mandatory-tests) | 🔵 |
| Written restore runbooks and timed drills: rollback, app data restore, full host rebuild | 11.5 | RC.RP-01 · RC.RP-03 | [C04 §7](../cases/case-04-backup-recovery-drills/03-restore-runbooks.md#7-restoring-from-the-repository) | [C04 §9](../cases/case-04-backup-recovery-drills/04-recovery-drills.md#9-the-drills) | 🔵 |

These rows turn ✅ only when the drills in Case 04 have been run and their results recorded.

---

### 4. Known Gaps
A mapping that only lists what's covered is marketing. These are the safeguards the platform doesn't fully meet, why that's accepted today, and what closes each one.

| # | Safeguard | What it asks | Current state | Why it's accepted for now | Next step |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 1 | **6.4** Require MFA for Remote Network Access · **6.5** Require MFA for Administrative Access | Two different factor types for remote and admin access | WireGuard and SSH both use private keys on the admin device: two keys, but one factor type (*something you have*) | Neither is reachable without the other, and neither accepts passwords; the remaining risk is a compromised admin device | Hardware-backed SSH key (`ed25519-sk` on a FIDO2 token, with PIN), so SSH needs the token and its PIN |
| 2 | **8.10** Retain Audit Logs | At least 90 days | 7 days in Loki | Sized for a small disk; enough for operational troubleshooting | Archive logs older than 7 days off the host (also closes Case 04's "logs off the host" item), then raise retention |
| 3 | **8.11** Conduct Audit Log Reviews | Weekly reviews | The queries and the dashboard exist; no review schedule | A one-person platform; reviews happen during changes | A weekly review of the Case 03 dashboard, with what was checked recorded |
| 4 | **13.1** Centralize Security Event Alerting | Alerts sent to a central place | Monitors and logs record failures; nobody is notified | Found during routine checks today | One notification channel on every monitor and on critical log queries |
| 5 | **7.3 / 7.4** Perform Automated Operating System / Application Patch Management | Automatic OS and application updates | Both are applied manually, through the change cycle | Each update goes through a snapshot and a check, which automation would skip | `dnf-automatic` limited to OS security updates; image updates stay deliberate but get scanned (gap 6) |
| 6 | **7.5 / 7.6** Automated Vulnerability Scans | Scan internal and external assets | No scanner runs | Pinned, official images reduce but don't remove the risk | Image scanning (e.g. Trivy) as a step of the change cycle; a scheduled external scan of the public surface |
| 7 | **2.2** Ensure Authorized Software is Currently Supported | Only supported software | Promtail is deprecated; the observe stack still runs its initial pinned tags | It still works and gets no new features; nothing it does is internet-facing | Migrate Promtail to Grafana Alloy; update the observe stack through the change cycle |
| 8 | **10.1** Deploy and Maintain Anti-Malware Software | Anti-malware on every asset | None on the host | Single-purpose server, no user uploads, containers from pinned official images | Evaluate a host-based detection agent that reports into the existing log pipeline |
| 9 | **3.11** Encrypt Sensitive Data at Rest | Encryption of stored sensitive data | The VPS disk isn't encrypted by me; secrets are root-only files; backups will be encrypted (Case 04) | The provider controls the hypervisor either way; the backups are the copy that leaves the server | Encrypted backups first (Case 04), then assess disk encryption for the secrets on the host |
| 10 | **11.1–11.5** Data Recovery | A tested recovery process | Designed and documented in Case 04; not running yet | — | Build Case 04 and run its three drills; 11.5 asks for quarterly tests, matching the D2 schedule |

---

### 5. Outside This Repository
- **NIST CSF 2.0 *Govern*** (policy, risk strategy, roles, supply chain) is an organizational function, not a property of one server. The governance side of my work, including NIS2 and the Portuguese RJC/QNRCS, is in [cybersecurity-officer](https://github.com/gabzaf/cybersecurity-officer).
- **CIS safeguards for organizations** (enterprise asset inventories, awareness training, service-provider management, penetration testing programs) don't apply to a single-administrator platform and aren't mapped.

---

### 6. References
Official sources only. Every safeguard ID and subcategory in this document was checked against them.

**CIS Critical Security Controls** (Center for Internet Security)

| Resource | What it is | Access |
| :--- | :--- | :--- |
| [CIS Critical Security Controls](https://www.cisecurity.org/controls) | Overview of the 18 Controls and the Implementation Groups | Free |
| [CIS Controls v8](https://www.cisecurity.org/controls/v8) | The version mapped in this document | Free |
| [CIS Controls v8.1](https://www.cisecurity.org/controls/v8-1) | The 2024 update: revised descriptions and asset classes, adds *Govern* | Free |
| [CIS Controls download (PDF, spreadsheet, change log)](https://learn.cisecurity.org/cis-controls-download) | The full documents: every Control and Safeguard | Free, registration form required |
| [CIS Controls Assessment Specification v8](https://cas8.docs.cisecurity.org/en/latest/) | How each Safeguard is measured | Free |
| [CIS Controls v8 mapping to NIST CSF 2.0](https://www.cisecurity.org/insights/white-papers/cis-controls-v8-mapping-to-nist-csf-2-0) | CIS's official crosswalk between the two frameworks | Free, registration form may be required |
| [CIS Controls Navigator (v8)](https://www.cisecurity.org/controls/cis-controls-navigator/v8) | Interactive view of every Safeguard and its mappings to other frameworks | Free |

**NIST Cybersecurity Framework** (National Institute of Standards and Technology)

| Resource | What it is | Access |
| :--- | :--- | :--- |
| [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework) | Framework homepage | Free |
| [The NIST Cybersecurity Framework (CSF) 2.0, NIST CSWP 29 (PDF)](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf) | The framework itself, published 26 February 2024 ([DOI 10.6028/NIST.CSWP.29](https://doi.org/10.6028/NIST.CSWP.29)) | Free |
| [CSF 2.0 Reference Tool](https://csrc.nist.gov/Projects/cybersecurity-framework/Filters#/csf/filters) | Searchable list of every function, category and subcategory | Free |
| [CSF 2.0 Quick-Start Guides](https://www.nist.gov/cyberframework/quick-start-guides) | Short guides for applying the framework | Free |
| [CSF Informative References](https://www.nist.gov/cyberframework/informative-references) | NIST's index of mappings between CSF and other standards | Free |

---

*Mapping against CIS Controls v8 and NIST CSF 2.0. Last reviewed: 2026-10-02.*

[← Back to README](../README.md)
