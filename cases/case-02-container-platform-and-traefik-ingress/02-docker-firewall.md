# Phase 2: Docker & the Host Firewall

[← Phase 1: Production Layout & Docker Engine](./01-srv-layout-docker-engine.md) · **Phase 2 of 5** · [Next: Network Segmentation & State →](./03-networks-state.md)

---

### In this phase
- [3. Docker and the Host Firewall](#3-docker-and-the-host-firewall)
  - [3.1. The Problem: Published Ports Skip INPUT](#31-the-problem-published-ports-skip-input)
  - [3.2. Proving the Bypass](#32-proving-the-bypass)
  - [3.3. Architectural Principle](#33-architectural-principle)
  - [3.4. Options Considered](#34-options-considered)
  - [3.5. Cloudflare-Aware DOCKER-USER Filter](#35-cloudflare-aware-docker-user-filter)
  - [3.6. Final DOCKER-USER Structure](#36-final-docker-user-structure)
  - [3.7. Persistence Across Boot and Docker Restarts](#37-persistence-across-boot-and-docker-restarts)
  - [3.8. Living with iptables-services](#38-living-with-iptables-services)
  - [3.9. Mandatory Tests](#39-mandatory-tests)
  - [3.10. Expected End State](#310-expected-end-state)

---

## Configuration Artifacts & Reference Code

### 3. Docker and the Host Firewall
Case 01 ended with a strong guarantee: the origin only accepts ports 80/443 from Cloudflare, and everything else is dropped. That guarantee lives in the `INPUT` chain. The moment Docker publishes a port, traffic to that port stops passing through `INPUT` at all.

This phase proves that, explains why, and puts the guarantee back where the packets actually flow.

#### 3.1. The Problem: Published Ports Skip INPUT
When a container publishes a port (`-p 443:443`), Docker writes a NAT rule that rewrites the packet's destination from the host to the container *before* the kernel decides where the packet goes. From that point on, the packet isn't addressed to the host anymore, so the kernel routes it through `FORWARD`, not `INPUT`.

```text
Packet from the Internet → eth0 → VPS_IP:443
   │
   ├─ PREROUTING (nat): Docker DNAT  VPS_IP:443 → 172.18.0.2:443
   │
   │   The destination is now a container, not the host:
   │   INPUT (and Case 01's CLOUDFLARE_V4 chain) is never consulted.
   │
   └─ FORWARD
        ├─ DOCKER-USER     ← reserved for my rules; Docker never writes here
        └─ DOCKER-FORWARD  ← Docker's own rules: ACCEPT to published ports
```

Case 01's `FORWARD DROP` policy doesn't help either: Docker inserts explicit `ACCEPT` rules for published ports, and those match before the policy is ever applied.

The consequence: any port published by any container is reachable from the whole internet, whatever `INPUT` says. Behind Cloudflare, that means anyone who learns the origin IP (from historical DNS, certificate logs or a scan) can talk to Traefik directly and skip the WAF, the rate limiting and the bot protection configured in Case 01.

#### 3.2. Proving the Bypass
Before fixing anything, I reproduce the problem with a throwaway container on a port that was never opened in the firewall.

<details>
<summary><b>▶ View test — reproducing the bypass</b></summary>

On the server, publish a test page on port `8081`:
```bash
docker run -d --name exposure-test -p 8081:80 nginx:1.27-alpine
```

Docker wrote a NAT rule for it:
```bash
sudo iptables -t nat -S DOCKER | grep 8081
```
```text
-A DOCKER ! -i docker0 -p tcp -m tcp --dport 8081 -j DNAT --to-destination 172.17.0.2:80
```

From a machine **outside the VPN** (for example, a phone on 4G), request the port on the public IP:
```bash
curl -s --connect-timeout 5 http://<VPS_PUBLIC_IP>:8081 | head -n 4
```
⚠️ Result before the fix: the nginx welcome page is returned. Port `8081` was never allowed in `INPUT`, the policy is `DROP`, and the page still answers.

Leave `exposure-test` running: the same request is repeated after the fix.
</details>

> [!WARNING]
> Keep this window short: the test page is public until [3.5](#35-cloudflare-aware-docker-user-filter) is applied.

#### 3.3. Architectural Principle
Two rules drive the fix:

1. **Filter where the packet actually goes.** Docker reserves the `DOCKER-USER` chain for operator rules and evaluates it before its own `ACCEPT` rules. A filter there covers every container, current and future, without touching Docker's own chains.
2. **Fail closed.** If the Cloudflare IP list can't be downloaded, the filter must keep the last known list or drop everything from the WAN. A firewall that opens up when a download fails isn't a firewall.

The policy itself mirrors Case 01, applied to containers:
- 🟢 new connections from the WAN are accepted only from Cloudflare ranges, and only to original ports 80 and 443;
- 🟢 replies to connections the containers started themselves (updates, API calls) are allowed back in;
- 🟢 traffic from the VPN (`wg0`) and between containers isn't affected, so admin tools still work through the tunnel;
- ❌ everything else arriving on the public interface for a container is dropped.

The filter matches the **original** destination port (`--ctorigdstport`), not the port after NAT. That way I filter what was actually requested on the host. It also means the alternative HTTP ports Cloudflare can proxy (such as 8080 or 8443) aren't accepted by accident.

> [!NOTE]
> Case 01's `CLOUDFLARE_V4` chain on `INPUT` stays in place. It still protects anything that listens on the host itself. The two chains together cover both paths a packet can take.

#### 3.4. Options Considered

| Option | Decision | Why |
| :--- | :---: | :--- |
| Disable Docker's firewall management (`"iptables": false`) | ❌ | Breaks NAT for published ports and outbound traffic from containers; I'd be rebuilding Docker's networking by hand. |
| Run Traefik with `network_mode: host` | ❌ | Traffic would pass `INPUT` again, but Traefik would leave the segmented networks and lose Docker DNS. It also only fixes Traefik, not the next container published by mistake. |
| Bind ports to an address (`127.0.0.1:8081:80`) | ❌ | Restricts the listening interface, not the source. Cloudflare still couldn't be allow-listed. |
| Filter in `DOCKER-USER` | ✅ | The chain Docker reserves for operator rules, evaluated before Docker's own. Covers every container, present and future. |

#### 3.5. Cloudflare-Aware DOCKER-USER Filter
<details>
<summary><b>▶ View script — Cloudflare-aware filter for Docker-published ports</b></summary>

**a. Create the script**
```bash
sudo nano /usr/local/bin/docker-user-firewall.sh
```
```bash
#!/bin/bash
set -euo pipefail

# =============================================================================
# Cloudflare-Aware Filter for Docker-Published Ports (IPv4 Only)
# Rebuilds DOCKER-USER atomically. Fails closed if no Cloudflare list exists.
# =============================================================================

# 1. Definitions
CLOUDFLARE_IPS_URL="${CLOUDFLARE_IPS_URL:-https://www.cloudflare.com/ips-v4}"
CACHE_FILE="/etc/cloudflare-ips-v4.txt"
CHAIN_NAME="CLOUDFLARE_DOCKER_V4"
WAN_IF="${WAN_IF:-$(ip -4 route show default | awk '{print $5; exit}')}"
CIDR_REGEX='^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$'

if [ -z "$WAN_IF" ]; then
    echo "ERROR: Could not detect the public interface. Set WAN_IF and retry."
    exit 1
fi

# 2. Refresh the Cloudflare list; keep the last good copy if the download fails
TMP_FILE=$(mktemp)
if curl -fsS --connect-timeout 10 --max-time 20 "$CLOUDFLARE_IPS_URL" -o "$TMP_FILE" \
   && grep -Eq "$CIDR_REGEX" "$TMP_FILE"; then
    grep -E "$CIDR_REGEX" "$TMP_FILE" > "$CACHE_FILE"
else
    echo "WARNING: Download failed or returned no valid ranges. Using the cached list."
fi
rm -f "$TMP_FILE"

IPS=""
if [ -s "$CACHE_FILE" ]; then
    IPS=$(cat "$CACHE_FILE")
else
    echo "WARNING: No Cloudflare list available. Failing closed: all WAN traffic to containers is dropped."
fi

# 3. Build the ruleset and apply it in a single atomic transaction
{
    echo "*filter"
    echo ":DOCKER-USER - [0:0]"
    echo ":$CHAIN_NAME - [0:0]"
    for ip in $IPS; do
        echo "-A $CHAIN_NAME -s $ip -p tcp -m conntrack --ctorigdstport 80 --ctdir ORIGINAL -j RETURN"
        echo "-A $CHAIN_NAME -s $ip -p tcp -m conntrack --ctorigdstport 443 --ctdir ORIGINAL -j RETURN"
    done
    echo "-A $CHAIN_NAME -j DROP"
    echo "-A DOCKER-USER -i $WAN_IF -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN"
    echo "-A DOCKER-USER -i $WAN_IF -j $CHAIN_NAME"
    echo "-A DOCKER-USER -j RETURN"
    echo "COMMIT"
} | iptables-restore --noflush

echo "[$(date)] DOCKER-USER rebuilt on $WAN_IF with $(echo "$IPS" | grep -c . || true) Cloudflare ranges."
```
```bash
sudo chmod 700 /usr/local/bin/docker-user-firewall.sh
```

Script design decisions:
- `iptables-restore --noflush` replaces only `DOCKER-USER` and `CLOUDFLARE_DOCKER_V4`, in one transaction. There's no moment where the chain is half-built, and Docker's own chains aren't touched.
- Downloaded content is only accepted if every kept line looks like a CIDR. An HTML error page or an empty response never reaches `iptables`.
- The last good list is cached in `/etc/cloudflare-ips-v4.txt`. With no list at all, the chain contains only `DROP`: the platform goes dark instead of open.
- The public interface is detected from the default route. If it's ever wrong, I set it explicitly: `WAN_IF=eth0`.

**b. Apply the filter**
```bash
sudo /usr/local/bin/docker-user-firewall.sh
```
```text
[...] DOCKER-USER rebuilt on eth0 with 15 Cloudflare ranges.
```

**c. Verify the applied rules**
```bash
sudo iptables -S DOCKER-USER
sudo iptables -L CLOUDFLARE_DOCKER_V4 -n -v
```

**d. Keep the list current**

Cloudflare's ranges change rarely, but they do change. Refresh weekly, five minutes after Case 01's `INPUT` refresh:
```bash
sudo crontab -e
```
Add the line:
`5 4 * * 0 /usr/local/bin/docker-user-firewall.sh >> /var/log/docker-user-firewall.log 2>&1`
</details>

#### 3.6. Final DOCKER-USER Structure
```text
Chain FORWARD (policy DROP)
│
├─ DOCKER-USER  (evaluated first — Docker never writes here)
│   ├─ RETURN: in eth0, established/related      (replies to container egress)
│   ├─ CLOUDFLARE_DOCKER_V4: in eth0              (every new WAN connection)
│   │   ├─ RETURN: 173.245.48.0/20 → original port 80
│   │   ├─ RETURN: 173.245.48.0/20 → original port 443
│   │   ├─ RETURN: ... (ranges)
│   │   └─ DROP: everything else from the WAN
│   └─ RETURN                                      (VPN, container-to-container)
│
└─ DOCKER-FORWARD / DOCKER  (Docker's own rules: ACCEPT to published ports)
```

`RETURN` hands the packet back to Docker's normal processing. `DROP` ends it. Only Cloudflare traffic to 80/443, replies, and non-WAN traffic ever reach Docker's `ACCEPT` rules.

#### 3.7. Persistence Across Boot and Docker Restarts
The filter must exist *before* Docker starts its containers. Otherwise there's a window at boot where Traefik is reachable from anywhere. A systemd unit ordered before `docker.service` closes that window: it creates `DOCKER-USER` itself, and Docker adopts the existing chain when it starts.

<details>
<summary><b>▶ View config — systemd unit for the filter</b></summary>

```bash
sudo nano /etc/systemd/system/docker-user-firewall.service
```
```ini
[Unit]
Description=Cloudflare-aware filter for Docker-published ports (DOCKER-USER)
Wants=network-online.target
After=network-online.target iptables.service
Before=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/docker-user-firewall.sh

[Install]
RequiredBy=docker.service
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable docker-user-firewall.service
```

- `Before=docker.service`: the chain is populated before any container starts.
- `RequiredBy=docker.service`: if the filter can't be applied, Docker doesn't start. I'd rather have the platform down than exposed.
- Docker never flushes `DOCKER-USER`, so restarting the Docker daemon alone keeps the rules. [Test 4](#39-mandatory-tests) proves it.
</details>

#### 3.8. Living with iptables-services
Case 01 persists `INPUT` with `iptables-services`. With Docker running, two habits from Case 01 change:

> [!IMPORTANT]
> **Don't run `service iptables save` while Docker is running.** It would freeze Docker's runtime rules (NAT entries pointing at container IPs that change on every recreate) into `/etc/sysconfig/iptables`. Docker and the systemd unit rebuild their own chains on every start, so the saved file should only contain my host rules. When an `INPUT` change has to be persisted, save without the runtime chains:
> ```bash
> sudo sh -c "iptables-save | grep -vE 'DOCKER|docker0|br-[0-9a-f]{12}|f2b-' > /etc/sysconfig/iptables"
> ```
> Fail2ban (`f2b-`) is excluded for the same reason: it recreates its own chains when it starts.

> [!WARNING]
> **Restarting `iptables.service` flushes everything**, including Docker's chains and this filter, and containers lose connectivity. Rebuild both in order:
> ```bash
> sudo systemctl restart docker-user-firewall.service docker.service
> ```

#### 3.9. Mandatory Tests
<details>
<summary><b>▶ View tests — validating the filter</b></summary>

**Test 1: The bypass is closed** (from outside the VPN)
```bash
curl -s --connect-timeout 5 http://<VPS_PUBLIC_IP>:8081 | head -n 4
```
🔴 Expected result: timeout. Same request as [3.2](#32-proving-the-bypass), now dropped.

**Test 2: The VPN path still works** (connected to the VPN)
```bash
curl -s --connect-timeout 5 http://10.10.10.1:8081 | head -n 4
```
🟢 Expected result: the nginx welcome page. The filter only applies to the public interface.

**Test 3: The drop is counted**
```bash
sudo iptables -L CLOUDFLARE_DOCKER_V4 -n -v | tail -n 1
```
🟢 Expected result: the final `DROP` rule shows a packet count above zero after Test 1.

**Test 4: The filter survives a Docker restart**
```bash
sudo systemctl restart docker
sudo iptables -S FORWARD | head -n 3
sudo iptables -S DOCKER-USER
```
🟢 Expected result: `-A FORWARD -j DOCKER-USER` is still the first `FORWARD` rule, and `DOCKER-USER` still holds the three rules from [3.6](#36-final-docker-user-structure).

**Test 5: The filter fails closed** (from the root session)
```bash
mv /etc/cloudflare-ips-v4.txt /etc/cloudflare-ips-v4.txt.bak
CLOUDFLARE_IPS_URL=https://invalid.invalid /usr/local/bin/docker-user-firewall.sh
iptables -S CLOUDFLARE_DOCKER_V4
```
🔴 Expected result: a warning, and the chain contains only `-A CLOUDFLARE_DOCKER_V4 -j DROP`.

Restore the real list:
```bash
mv /etc/cloudflare-ips-v4.txt.bak /etc/cloudflare-ips-v4.txt
/usr/local/bin/docker-user-firewall.sh
```

**Test 6: The filter is in place after a reboot**
```bash
sudo systemctl reboot
```
Reconnect through the VPN, then:
```bash
systemctl status docker-user-firewall.service --no-pager
```
🟢 Expected result: `active (exited)`. Repeat Test 1 from outside the VPN: 🔴 still a timeout.

**Cleanup**
```bash
docker rm -f exposure-test
docker rmi nginx:1.27-alpine
```
</details>

#### 3.10. Expected End State
- Docker-published ports accept new WAN connections only from Cloudflare, and only on original ports 80/443;
- a port published by mistake is unreachable from the internet;
- the VPN and container-to-container traffic are unaffected;
- the filter is in place before Docker starts on boot, survives Docker restarts, refreshes weekly and fails closed;
- Case 01's origin guarantee holds again, now for both paths a packet can take: `INPUT` for the host, `DOCKER-USER` for containers.

> [!IMPORTANT]
> Snapshot: once every test above passes, create a snapshot named `case02-phase2-docker-firewall-ok` and delete the previous one.

---

[← Phase 1: Production Layout & Docker Engine](./01-srv-layout-docker-engine.md) · **Phase 2 of 5** · [Next: Phase 3 — Network Segmentation & Persistent State →](./03-networks-state.md)
