# Phase 3: Network Segmentation & Persistent State

[← Phase 2: Docker & the Host Firewall](./02-docker-firewall.md) · **Phase 3 of 5** · [Next: Health, Restart & Change Cycle →](./04-health-change-cycle.md)

---

### In this phase
- [4. Network Segmentation](#4-network-segmentation)
  - [4.1. Why Segment Container Networks?](#41-why-segment-container-networks)
  - [4.2. Architectural Principle](#42-architectural-principle)
  - [4.3. Default Bridge vs Custom Bridge](#43-default-bridge-vs-custom-bridge)
  - [4.4. Adopted Network Architecture](#44-adopted-network-architecture)
  - [4.5. Create the Shared proxy Network](#45-create-the-shared-proxy-network)
  - [4.6. Per-Stack Internal Networks](#46-per-stack-internal-networks)
  - [4.7. Isolation Patterns](#47-isolation-patterns)
  - [4.8. Mandatory Tests](#48-mandatory-tests)
  - [4.9. Expected End State](#49-expected-end-state)
- [5. Persistent State](#5-persistent-state)
  - [5.1. Why Containers Lose Data](#51-why-containers-lose-data)
  - [5.2. Decision: Bind Mounts Under /srv/data](#52-decision-bind-mounts-under-srvdata)
  - [5.3. Mount Modes](#53-mount-modes)
  - [5.4. The Permission Model (UIDs)](#54-the-permission-model-uids)
  - [5.5. Mandatory Tests](#55-mandatory-tests)
  - [5.6. Expected End State](#56-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 4. Network Segmentation
This section isolates containers from each other, so that a compromised or misbehaving service can only reach what it strictly needs.

#### 4.1. Why Segment Container Networks?
By default, Docker puts every container on the same network, where they can all reach each other. That's convenient for testing and a liability in production: if one container is compromised, the attacker gets network access to every other one: the database, the cache, the internal tools. Everything is laterally exposed.

Phase 2 protected the platform from the internet. This phase protects services from each other. It's the east–west counterpart of the north–south filter.

#### 4.2. Architectural Principle
> **Zero trust between containers**: services that don't need to communicate must not be able to communicate.

- ❌ No service runs on Docker's default `bridge` network.
- ❌ No database or cache joins the network Traefik uses.
- ❌ No database publishes a port on the host.
- 🟢 One shared network, `proxy`, exists only for what Traefik must reach.
- 🟢 Each stack gets its own internal network, with no route to the internet, for its private dependencies.
- 🟢 The application container is the only bridge between the two.

#### 4.3. Default Bridge vs Custom Bridge

| Aspect | `bridge` (default) | Custom bridge |
| :--- | :--- | :--- |
| Internal DNS | ❌ Not available | ✅ Containers resolve each other by name |
| Isolation | ❌ All containers share it | ✅ Only the containers I attach |
| Control | ❌ Implicit | ✅ Declared in Compose, reviewable |

With `icc: false` from Phase 1, the default bridge doesn't even allow container-to-container traffic. Custom networks are the only way services talk on this platform.

#### 4.4. Adopted Network Architecture

| Network | Scope | Created by | Internet access |
| :--- | :--- | :--- | :---: |
| `proxy` | Global, shared between stacks | `docker network create proxy` (once, by hand) | ✅ |
| `{app}-internal` | One per stack | The stack's own `docker-compose.yml` (`internal: true`) | ❌ |

```text
                     Traefik (published 80/443, filtered by DOCKER-USER)
                         │
┌────────────────────────┼─────────────────────────────┐
│                  NETWORK: proxy                      │
│   ┌─────────┐     ┌────┴────┐     ┌─────────────┐    │
│   │ Traefik │     │   App   │     │ Uptime Kuma │    │
│   └─────────┘     └────┬────┘     └─────────────┘    │
└────────────────────────┼─────────────────────────────┘
                         │  (the app joins both networks)
┌────────────────────────┼─────────────────────────────┐
│   ┌──────────┐    ┌────┴────┐     ┌─────────┐        │
│   │ Postgres │◄───│   App   │────►│  Redis  │        │
│   └──────────┘    └─────────┘     └─────────┘        │
│             NETWORK: app-internal (internal: true)   │
│             no internet, invisible to other stacks   │
└──────────────────────────────────────────────────────┘
```

#### 4.5. Create the Shared proxy Network
<details>
<summary><b>▶ View commands — creating the proxy network</b></summary>

Check the current networks on a clean installation:
```bash
docker network ls
```
```text
NETWORK ID     NAME      DRIVER    SCOPE
xxxxxxxxxxxx   bridge    bridge    local
xxxxxxxxxxxx   host      host      local
xxxxxxxxxxxx   none      null      local
```
These are Docker's built-in networks. None of my services use them.

Create the single shared network:
```bash
docker network create proxy
```
Verify:
```bash
docker network inspect proxy --format '{{.Name}}: driver={{.Driver}} internal={{.Internal}}'
```
```text
proxy: driver=bridge internal=false
```

> [!NOTE]
> `proxy` can't be `internal`: Traefik publishes ports on it, and internal networks have no path to or from the host's interfaces.
</details>

#### 4.6. Per-Stack Internal Networks
Internal networks aren't created by hand. Each stack declares its own in its `docker-compose.yml`. Compose creates the network on `up` and removes it on `down`, so it lives and dies with the stack.

<details>
<summary><b>▶ View config — stack with a shared and an internal network</b></summary>

```yaml
# /srv/apps/example/docker-compose.yml
services:
  app:
    image: example:1.0.0
    networks:
      - proxy             # shared: Traefik can reach it
      - example-internal  # private: only this stack

  db:
    image: postgres:16.4-alpine
    networks:
      - example-internal  # private only: no Traefik, no internet
    # no "ports:" — a database is never published on the host

networks:
  proxy:
    external: true        # created once by hand in 4.5
  example-internal:
    driver: bridge
    internal: true        # no route to the internet, not reachable from outside
```

Inside a network, containers resolve each other by service name. The app reaches the database at `db:5432`, never at a fixed IP.
</details>

> [!WARNING]
> The most common mistake is a database exposed "temporarily":
> ```yaml
> db:
>   ports:
>     - "5432:5432"   # ❌ published on the host
>   networks:
>     - proxy         # ❌ reachable by Traefik and every other proxy member
> ```
> Phase 2's filter would still drop it at the WAN, but it would be reachable from the VPN and from every container on `proxy`. Defense in depth is a safety net, not a reason to stop configuring things correctly.

#### 4.7. Isolation Patterns

| Pattern | Topology | Networks | Examples |
| :--- | :--- | :--- | :--- |
| **Simple service** | `proxy → app` | app: `proxy` | Uptime Kuma, static pages |
| **App + database** | `proxy → app → db` | app: `proxy` + `internal`; db: `internal` | Gitea, Vaultwarden |
| **App + database + cache** | `proxy → app → db, redis` | app: `proxy` + `internal`; db, redis: `internal` | Nextcloud with Redis |

#### 4.8. Mandatory Tests
<details>
<summary><b>▶ View tests — proving isolation (names, addresses and egress)</b></summary>

Set up a shielded "database" on an internal network:
```bash
docker network create --internal example_internal
docker run -d --name db_secret --network example_internal alpine:3.20 sleep infinity
```

**Test 1: Invisible by name from the proxy network**
```bash
docker run --rm --network proxy alpine:3.20 ping -c 2 -W 2 db_secret
```
🔴 Expected result: `ping: bad address 'db_secret'`. The name doesn't exist outside its network.

**Test 2: Unreachable by address from the proxy network**

A missing DNS name isn't isolation on its own, so I also try the container's IP directly:
```bash
DB_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' db_secret)
docker run --rm --network proxy alpine:3.20 ping -c 2 -W 2 "$DB_IP"
```
🔴 Expected result: `100% packet loss`.

**Test 3: No internet from the internal network**
```bash
docker run --rm --network example_internal alpine:3.20 wget -T 5 -q -O- http://example.com
```
🔴 Expected result: a timeout or `bad address`. A service on an internal network can't download tooling or send data out.

**Test 4: Containers on the same network do see each other**
```bash
docker run --rm --network example_internal alpine:3.20 ping -c 2 -W 2 db_secret
```
🟢 Expected result: replies from `db_secret`. Isolation is between networks, not inside them.

**Cleanup**
```bash
docker rm -f db_secret
docker network rm example_internal
```
</details>

#### 4.9. Expected End State
- The `proxy` network exists and is the only network shared between stacks;
- every private dependency (database, cache) lives on its stack's internal network, without internet access;
- isolation is proven by name, by address and for outbound traffic;
- no test containers or test networks remain.

---

### 5. Persistent State
This section makes sure data survives restarts, recreations and updates by keeping it outside the container.

#### 5.1. Why Containers Lose Data
Containers are ephemeral by design. An update recreates the container from a new image. If the data lived inside the old container, it's gone with it.

| What | Where it lives | On recreate |
| :--- | :--- | :--- |
| Application code | Image | Replaced (expected) |
| Configuration | `/srv/apps/{app}` (read-only mount) | Kept |
| User data, databases | `/srv/data/{app}` (read-write mount) | Kept |
| Logs | stdout (rotated by the daemon) or `/srv/logs/{app}` | Kept per strategy |

If data has to outlive the container, it goes in a mount. No exceptions.

#### 5.2. Decision: Bind Mounts Under /srv/data
Docker offers two kinds of persistence:

| | Named volumes | Bind mounts (adopted) |
| :--- | :--- | :--- |
| Location | `/var/lib/docker/volumes/<name>/_data` | A directory I choose under `/srv/data/` |
| Inspection | Through Docker | Plain `ls` |
| Backup | Indirect | `tar` of a known path |
| Migration | Needs Docker tooling | Copy the directory |
| Permissions | Managed by Docker | Managed by me (see 5.4) |

For Docker Compose on a single VPS, I choose **bind mounts under `/srv/data/{app}`**. The location is predictable, backups are a plain directory copy, and migration is a copy plus `docker compose up -d`. Named volumes make more sense under orchestrators (Swarm, Kubernetes), where the storage driver matters more than the path.

#### 5.3. Mount Modes
```yaml
volumes:
  - /srv/data/app:/data                            # read-write: state the app changes
  - /srv/apps/app/config.yml:/etc/app/config.yml:ro # read-only: config the app must not change
```

Configuration is always mounted read-only. If an application is compromised, it can't rewrite its own configuration.

#### 5.4. The Permission Model (UIDs)
The most common failure with bind mounts: the container runs as a non-root UID (good practice), but the host directory belongs to another owner. The result is `Permission denied`.

<details>
<summary><b>▶ View commands — matching host ownership to the container's UID</b></summary>

Find the UID the container runs as:
```bash
# From the image metadata
docker inspect <image> --format '{{.Config.User}}'

# Or from a running container
docker exec <container> id
```

Then pick one of three approaches:

**Option 1: Give the directory to the container's UID**
```bash
sudo chown -R 1000:1000 /srv/data/app
```

**Option 2: Set the user in Compose** (the image must support it)
```yaml
services:
  app:
    image: example:1.0.0
    user: "1000:1000"
    volumes:
      - /srv/data/app:/data
```

**Option 3: Images that take PUID/PGID** (LinuxServer.io style)
```yaml
environment:
  - PUID=1000
  - PGID=1000
```
</details>

| Image | Typical UID | Note |
| :--- | :---: | :--- |
| PostgreSQL (Alpine) | 70 | 999 on Debian-based tags |
| MySQL / MariaDB | 999 | `mysql` user |
| Nginx | 101 | Or root, depending on the image |
| Node.js apps | 1000 | Varies |
| LinuxServer.io | Configurable | Uses PUID/PGID |

> [!WARNING]
> Never mix data from different applications in the same directory. One app, one `/srv/data/{app}`. That keeps permissions, backups and restores independent.

#### 5.5. Mandatory Tests
<details>
<summary><b>▶ View tests — data survives container destruction</b></summary>

Prepare a test stack:
```bash
sudo mkdir -p /srv/apps/test-volume /srv/data/test-volume
sudo chown <username>:<username> /srv/apps/test-volume /srv/data/test-volume
```
```bash
cat << 'EOF' > /srv/apps/test-volume/docker-compose.yml
services:
  app:
    image: alpine:3.20
    container_name: test-volume
    command: ["sh", "-c", "echo \"Persistent data: $$(date)\" >> /data/test.txt && sleep infinity"]
    volumes:
      - /srv/data/test-volume:/data
EOF
```

**Test 1: First run writes to the host**
```bash
cd /srv/apps/test-volume && docker compose up -d
sleep 2 && cat /srv/data/test-volume/test.txt
```
🟢 Expected result: one line, `Persistent data: <date>`.

**Test 2: The data outlives the container**
```bash
docker compose down
cat /srv/data/test-volume/test.txt
```
🟢 Expected result: the line is still there, with no container running.

**Test 3: A new container appends to the same state**
```bash
docker compose up -d
sleep 2 && cat /srv/data/test-volume/test.txt
```
🟢 Expected result: two lines, one per container lifetime.

**Cleanup**
```bash
docker compose down --rmi all
sudo rm -rf /srv/apps/test-volume /srv/data/test-volume
```
</details>

#### 5.6. Expected End State
- Every stateful service keeps its data in `/srv/data/{app}`, mounted read-write;
- configuration is mounted read-only from `/srv/apps/{app}`;
- ownership of each data directory matches its container's UID;
- data persistence across container destruction is proven, and the test stack is removed.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case02-phase3-networks-state-ok` and delete the previous one.

---

[← Phase 2: Docker & the Host Firewall](./02-docker-firewall.md) · **Phase 3 of 5** · [Next: Phase 4 — Health, Restart & Change Cycle →](./04-health-change-cycle.md)
