# Phase 4: Health, Restart & Change Cycle

[← Phase 3: Network Segmentation & State](./03-networks-state.md) · **Phase 4 of 5** · [Next: Traefik v3 Ingress →](./05-traefik-ingress.md)

---

### In this phase
- [6. Health, Restart Policies and Dependencies](#6-health-restart-policies-and-dependencies)
  - [6.1. The Problem: "Up" Isn't "Working"](#61-the-problem-up-isnt-working)
  - [6.2. Healthchecks](#62-healthchecks)
  - [6.3. Healthchecks by Service Type](#63-healthchecks-by-service-type)
  - [6.4. Restart Policies](#64-restart-policies)
  - [6.5. Health-Gated Dependencies](#65-health-gated-dependencies)
  - [6.6. Verification and Common Failures](#66-verification-and-common-failures)
  - [6.7. Expected End State](#67-expected-end-state)
- [7. Change Cycle: Updates and Rollback](#7-change-cycle-updates-and-rollback)
  - [7.1. Why a Defined Change Cycle?](#71-why-a-defined-change-cycle)
  - [7.2. Architectural Principle: Pinned Versions](#72-architectural-principle-pinned-versions)
  - [7.3. The Cycle](#73-the-cycle)
  - [7.4. Prepare → Execute → Validate → Confirm](#74-prepare--execute--validate--confirm)
  - [7.5. Rollback](#75-rollback)
  - [7.6. Updates with Dependencies](#76-updates-with-dependencies)
  - [7.7. Expected End State](#77-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 6. Health, Restart Policies and Dependencies
This section defines how containers prove they're healthy, what happens when they fail, and in what order they start. The goal: I shouldn't be woken up at 3 AM to restart something that could have recovered on its own.

#### 6.1. The Problem: "Up" Isn't "Working"
```bash
docker ps
```
```text
CONTAINER ID   IMAGE      STATUS        PORTS
abc123         my-app     Up 3 days     8080/tcp
```

That looks perfect, and it says nothing about whether:
- the application is deadlocked;
- the database filled its disk and stopped answering;
- the API returns `500` on every request;
- the process is alive but spinning at 100% CPU.

For Docker, `Up` only means the process exists. Without a health signal, a broken service keeps receiving traffic, and users see `502` errors while every dashboard shows green.

#### 6.2. Healthchecks
A healthcheck is a command Docker runs periodically **inside** the container to ask "are you actually working?".

- **Without a healthcheck**: the app hangs → Docker still shows `Up` → traffic keeps arriving → users get errors.
- **With a healthcheck**: the app hangs → the check fails `retries` times → the status becomes `unhealthy` → Traefik stops routing to it, and monitoring has a real signal to alert on.

<details>
<summary><b>▶ View config — healthcheck anatomy</b></summary>

```yaml
services:
  web:
    image: nginx:1.27-alpine
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://localhost/ || exit 1"]
      interval: 30s      # how often to check
      timeout: 10s       # how long one check may take
      retries: 3         # consecutive failures before "unhealthy"
      start_period: 30s  # boot grace period: failures don't count yet
```

| Field | What it does | Typical value |
| :--- | :--- | :--- |
| `test` | Command whose exit code is the verdict (0 = healthy) | `wget`, `curl`, `pg_isready` |
| `interval` | Time between checks | 30s |
| `timeout` | Maximum duration of one check | 10s |
| `retries` | Consecutive failures before `unhealthy` | 3 |
| `start_period` | Startup grace period | 30–60s |

| Format | Runs as | Use when |
| :--- | :--- | :--- |
| `["CMD", "bin", "arg"]` | Direct exec | A single binary, no shell needed |
| `["CMD-SHELL", "cmd \|\| exit 1"]` | `sh -c` | Pipes, redirects or `\|\|` logic |
| `["NONE"]` | — | Disable a healthcheck baked into the image |
</details>

> [!NOTE]
> The check runs inside the container, so it can only use tools the image ships. Alpine images often have `wget` but not `curl`. Check the image before choosing the command.

| State | Meaning |
| :--- | :--- |
| `health: starting` | Inside `start_period`; not judged yet |
| `healthy` | The last check passed |
| `unhealthy` | The last `retries` checks failed |

#### 6.3. Healthchecks by Service Type
<details>
<summary><b>▶ View config — healthchecks for common services</b></summary>

**PostgreSQL**: `pg_isready` checks whether the server accepts connections
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U app -d app"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s
```

**MariaDB**: the official image ships a `healthcheck.sh` helper
```yaml
healthcheck:
  test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s
```

**Redis**
```yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**Web application (HTTP)**
```yaml
healthcheck:
  test: ["CMD-SHELL", "wget -q --spider http://localhost:8080/health || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Worker without HTTP (process check)**
```yaml
healthcheck:
  test: ["CMD-SHELL", "pgrep -f worker-process || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 3
```
</details>

#### 6.4. Restart Policies
When a container dies, the restart policy decides what happens next.

| Policy | Behavior | Use |
| :--- | :--- | :--- |
| `no` | Never restarts | One-off jobs, tests |
| `on-failure` | Restarts only on a non-zero exit | Jobs that should stop when they succeed |
| `always` | Always restarts, even after I stopped it by hand (once the daemon restarts) | Avoid: it overrides my decisions |
| `unless-stopped` | Restarts on failure and on boot, but respects a manual `stop` | **Default for every long-running service** |

The difference matters during maintenance. With `always`, a service I stopped on purpose comes back after a reboot. With `unless-stopped`, it stays stopped until I decide otherwise.

> [!NOTE]
> Docker's restart policy reacts to the process *exiting*, not to `unhealthy`. An unhealthy container is taken out of Traefik's rotation and becomes an alert signal. Restarting it is a decision, made by me or by a tool I deliberately add, not something Docker does silently.

#### 6.5. Health-Gated Dependencies
The classic boot failure: the app starts before its database is ready, fails to connect and crash-loops. `depends_on` with `condition: service_healthy` keeps the app in `Created` until the database passes its healthcheck.

<details>
<summary><b>▶ View config — app waits for a healthy database</b></summary>

```yaml
services:
  db:
    image: postgres:16.4-alpine
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD: ${DB_PASS}         # from /srv/apps/example/.env (600), never written in Compose
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  app:
    image: example:1.0.0
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy          # starts only when the DB is healthy
```

| Condition | Waits until |
| :--- | :--- |
| `service_started` | The container has started (default; weak) |
| `service_healthy` | The container's healthcheck passes |
| `service_completed_successfully` | The container exited with code 0 (migrations, init jobs) |
</details>

#### 6.6. Verification and Common Failures
<details>
<summary><b>▶ View commands — inspecting health</b></summary>

Status at a glance:
```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'
```
```text
NAMES       STATUS
app         Up 2 hours (healthy)
app-db      Up 2 hours (healthy)
```

Full health history of one container:
```bash
docker inspect app --format '{{json .State.Health}}' | jq
```
```json
{
  "Status": "healthy",
  "FailingStreak": 0,
  "Log": [{ "ExitCode": 0, "Output": "..." }]
}
```
</details>

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Always `unhealthy` | The command or endpoint doesn't exist in the image | `docker exec -it app sh` and run the check by hand |
| App starts before the DB | `depends_on` without `condition` | Add `condition: service_healthy` |
| `unhealthy` but working | `start_period` too short for a slow boot | Raise `start_period` and/or `retries` |

#### 6.7. Expected End State
- Every long-running service declares a healthcheck that tests what users depend on, not just the process;
- every long-running service uses `restart: unless-stopped`;
- services with dependencies start in order, gated on health;
- `docker ps` shows `(healthy)`: `Up` alone is no longer accepted as "working".

---

### 7. Change Cycle: Updates and Rollback
This section turns updates from "run the command and hope" into a procedure with a known way back.

#### 7.1. Why a Defined Change Cycle?
Software keeps changing: new versions bring security fixes, and sometimes they also bring regressions. Two instincts pull in opposite directions: "if it works, don't touch it" and "keep everything updated". Both are risky without a procedure. Not updating means running known vulnerabilities. Updating blindly means finding out about a breaking change at 3 AM.

The answer is to update deliberately, with a checkpoint before and a decision after.

#### 7.2. Architectural Principle: Pinned Versions
Every image is pinned to an explicit version. Never `latest`.

```yaml
image: postgres:latest         # ❌ which version is this? How do I go back?
image: postgres:16.4-alpine    # ✅ I know what runs; changing it is a decision
```

`latest` changes underneath me without warning. With a pinned tag, an update is a visible, reviewable diff in `docker-compose.yml`, and a rollback is the same diff reversed.

| Change | Example | Risk | Cadence |
| :--- | :--- | :---: | :--- |
| Patch | 1.20.0 → 1.20.1 | Low | Weekly (security fixes) |
| Minor | 1.20.0 → 1.21.0 | Medium | Monthly, with testing |
| Major | 1.x → 2.x | High | Planned, changelog read in full |

> [!NOTE]
> A tag like `v3.7` still moves to every new `v3.7.x` patch. For strict reproducibility I pin the full patch tag, or the image digest (`image@sha256:...`), which can't change at all.

Image hygiene on this platform:
- **Official or verified publishers only**: an image from a random account is unaudited code running on my server.
- **Alpine variants when they fit**: fewer packages means a smaller attack surface and less to patch.
- **A non-root user when the image allows it** (`user:` in Compose).
- **Always a `container_name`**, so logs and commands target something predictable.

#### 7.3. The Cycle
```text
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ PREPARE  │ ─► │ EXECUTE  │ ─► │ VALIDATE │ ─► │ CONFIRM  │
└──────────┘    └──────────┘    └────┬─────┘    └──────────┘
     ▲                               │ failure
     │                          ┌────▼─────┐
     └──────────────────────────│ ROLLBACK │
                                └──────────┘
```

| Step | Action |
| :--- | :--- |
| **Prepare** | Snapshot, note the current version, read the changelog, edit the tag |
| **Execute** | Pull the new image, then recreate the container |
| **Validate** | Status, logs and a real request |
| **Confirm** | Keep the change, clean up old images |
| **Rollback** | Return to the previous stable state first, investigate later |

> [!NOTE]
> On a single VPS with Docker Compose, the update strategy is **Recreate**: a few seconds of downtime while the container is replaced. That's simple and robust. Zero-downtime strategies need replicas and an orchestrator, which this platform doesn't have.

#### 7.4. Prepare → Execute → Validate → Confirm
<details>
<summary><b>▶ View commands — a standard update</b></summary>

**1. Prepare**

Take a snapshot in the VPS panel (`pre-update-{app}-{version}`), then note the version currently running:
```bash
cd /srv/apps/myservice
docker compose images
```
```text
CONTAINER   REPOSITORY   TAG      IMAGE ID       SIZE
myservice   n8n          1.20.0   abc123def456   350MB
```
Write it down: `n8n:1.20.0` is the rollback target.

Read the release notes of the **new** version: breaking changes, data migrations, new dependencies. A "patch" release can still break things.

Edit the tag in `docker-compose.yml`:
```yaml
image: n8n:1.21.0   # was 1.20.0
```

**2. Execute**

Pull first, while the old version is still serving, to keep downtime to the recreate itself:
```bash
docker compose pull
docker compose up -d
```

**3. Validate**

The first 60 seconds are the most telling:
```bash
docker compose ps
docker compose logs -f --tail=100
curl -I https://myservice.mysite.com
```

Signs of failure:
- the container is in a `Restarting` loop;
- stack traces or `failed to connect` errors in the logs;
- an HTTP status other than the expected one;
- response times far above normal.

**4. Confirm**

Only when everything is validated, remove the previous version's image. Until this moment it was my instant rollback:
```bash
docker image rm n8n:1.20.0
```
</details>

#### 7.5. Rollback
> [!IMPORTANT]
> When an update fails, **don't debug in production**. Return to the stable state first, then investigate with the pressure off.

<details>
<summary><b>▶ View commands — the two rollback paths</b></summary>

**Method 1: Revert the tag** (seconds; for application-only failures)
```yaml
image: n8n:1.20.0   # back to the noted version
```
```bash
docker compose up -d
```
The previous image is usually still in the local cache, so this is almost instant. Then repeat the validation step.

**Method 2: Restore the snapshot** (minutes; when data or the host is affected)

If reverting the tag doesn't fix it (for example, the new version already migrated the database schema), restore the snapshot taken in *Prepare*. This returns the whole VPS to its pre-change state.
</details>

#### 7.6. Updates with Dependencies
When an application release requires a newer database, the two are updated together, in an order that protects the data.

<details>
<summary><b>▶ View commands — updating an application and its database</b></summary>

```bash
# 1. Logical backup of the database (mandatory before touching it)
docker exec app-db pg_dump -U postgres appdb | gzip > /srv/backups/appdb-$(date +%Y%m%d).sql.gz

# 2. Stop the application (the database keeps running)
docker compose stop app

# 3. Update the database first and confirm it's healthy
docker compose pull db
docker compose up -d db
docker compose ps db

# 4. Update the application
docker compose pull app
docker compose up -d app

# 5. Validate end to end
docker compose ps
curl -I https://myapp.mysite.com
```

> [!NOTE]
> `/srv/backups` is root-only (`700`), so step 1 runs from the root session. A major database version upgrade (for example PostgreSQL 15 → 16) also needs a dump and restore, or `pg_upgrade`. Changing the tag alone isn't enough.
</details>

#### 7.7. Expected End State
- No image on the platform uses `latest`; every version is an explicit, reviewable choice;
- every update follows prepare → execute → validate → confirm, with a snapshot taken first;
- a failed update has two documented ways back: revert the tag, or restore the snapshot;
- application and database updates follow an order that protects the data.

> [!IMPORTANT]
> Snapshot: create a snapshot named `case02-phase4-health-cycle-ok` and delete the previous one.

---

[← Phase 3: Network Segmentation & State](./03-networks-state.md) · **Phase 4 of 5** · [Next: Phase 5 — Traefik v3 Ingress & Origin TLS →](./05-traefik-ingress.md)
