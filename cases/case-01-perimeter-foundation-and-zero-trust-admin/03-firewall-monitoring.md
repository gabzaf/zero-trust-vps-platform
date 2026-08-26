# Phase 3: Firewall & Monitoring

[← Phase 2: SSH & VPN Hardening](./02-ssh-vpn-hardening.md) · **Phase 3 of 4** · [Next: Cloudflare & TLS →](./04-cloudflare-tls.md)

---

### In this phase
- [8. Perimeter Firewall and Network Isolation](#8-perimeter-firewall-and-network-isolation)
  - [Why a Firewall?](#why-a-firewall)
  - [Architectural Principle](#architectural-principle)
  - [Chosen Tool (iptables)](#chosen-tool)
  - [Secure Firewall Configuration](#secure-firewall-configuration-whitelist-before-drop)
  - [Persistence of Firewall Rules](#persistence-of-firewall-rules)
  - [Checking the iptables Rules](#checking-the-iptables-rules)
  - [Mandatory Tests](#mandatory-tests)
- [9. Active Monitoring and Incident Response](#9-active-monitoring-and-incident-response)
  - [Defense Architecture](#defense-architecture)
  - [1. Telemetry Preparation and Verification](#1-telemetry-preparation-and-verification)
  - [2. Configure Intrusion Detection](#2-configure-intrusion-detection)
  - [3. Automatic Response Validation](#3-automatic-response-validation)
  - [4. Controlled Tests (Mandatory)](#4-controlled-tests-mandatory)

---

## Configuration Artifacts & Reference Code

### 8. Perimeter Firewall and Network Isolation
Now I need to configure perimeter defense by blocking all traffic to the server and only allowing requests validated by my VPN tunnel.

After securing identity (SSH) and administrative channel (VPN), the next natural target for attacks is the network surface. Newly created servers are continuously scanned by bots attempting:
- Connections on standard ports (22, 80, 443);
- Service fingerprinting;
- Exploitation of services not yet installed.

At this point, no public services should exist. Here:
- I do not protect the application;
- I do not publish services;
- I do not integrate Cloudflare as a proxy.
- I protect raw network traffic, before any upper layer.

#### Why a Firewall?
Without a firewall:
- A VPN becomes just "another access point"
- Future services may leak
- Exposure returns due to carelessness

I implement a total isolation firewall whose objective is to make the server disappear from the public internet.

#### Architectural Principle
Blacklist is a reaction. Here, everything coming from the public internet will be blocked by default so that nothing is exposed. As of this moment:
- Cloudflare is DNS Only
- No HTTP/HTTPS services are published
- Reverse proxy does not yet exist
- Administration occurs exclusively through VPN

Deliberately, **EVERYTHING** will be blocked:
- ❌ Ports 22 (SSH) and 80/443 (HTTP/HTTPS) to the public internet
- ❌ Any public service
- ❌ Any direct external access to my VPS server's IP address

Maintaining only the bare minimum:
- 🟢 Loopback to ensure internal system communication
- 🟢 Connections established to maintain legitimate responses to traffic initiated by the server
- 🟢 Private administration of internal VPN traffic coming from the WireGuard interface (`wg0`)

Ports will not be opened "for later use". Open them when necessary!

#### Chosen Tool
I will use `iptables` for 3 reasons:
- **Predictability**: I see exactly the rule that the Kernel executes.
- **Performance**: Packet processing without the overhead of Python/Ruby services.
- **Portability**: The same script works on Ubuntu, AlmaLinux, Debian or Rocky Linux.

Therefore, I avoid abstraction layers. No UFW, firewalld or magic panels here.

<details>
<summary><b>▶ View commands — iptables rules (whitelist before drop)</b></summary>

Clears all existing rules to start from scratch:
```bash
sudo iptables -F
```

Loopback (mandatory):
```bash
sudo iptables -A INPUT -i lo -j ACCEPT
```
- `lo -j ACCEPT`: Allows traffic on the Loopback interface (localhost). Essential for internal services (such as the database communicating with the application) to function.

**Connections Established**
```bash
sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
```
- `m conntrack --ctstate ESTABLISHED,RELATED`: Ensures that if the server has initiated a conversation (e.g., `dnf update`), the response from the internet is allowed back.

**Administrative VPN**
```bash
# Allows WireGuard VPN access (UDP port 51820) via the public internet
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT

# Allows ALL traffic coming from within the VPN interface
sudo iptables -A INPUT -i wg0 -j ACCEPT
```
- `dport 51820`: Allows WireGuard VPN (UDP port 51820) to enter from the public internet. It is the only port that will remain "open" to the world, allowing me to connect the tunnel.
- `i wg0`: Allows ALL traffic coming from within the VPN interface. Since I am already protected by VPN encryption, I have fully opened the `wg0` interface. This allows SSH, Pings and future administrative services without new firewall rules.

**Default policy (deny all)**
```bash
# Define the DROP (total blocking) policy for inbound and outbound traffic:
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP

# Allows the server to send data to the internet (essential for updates):
sudo iptables -P OUTPUT ACCEPT
```
- `INPUT DROP`: Nothing enters without explicit permission.
- `FORWARD DROP`: No lateral routing.
- `OUTPUT ACCEPT`: The server can access the internet normally (updates, DNS, APIs).
</details>

#### Persistence of Firewall Rules

<details>
<summary><b>▶ View commands — persisting rules across reboot</b></summary>

`iptables` does not retain rules after a reboot. To ensure my settings are automatically applied when the system starts, install `iptables-services`:
```bash
sudo dnf install -y iptables-services
sudo systemctl enable iptables
```
Save the rules:
```bash
sudo service iptables save
```
Check current rules:
```bash
sudo iptables -L
```
</details>

#### Mandatory Tests

<details>
<summary><b>▶ View tests — perimeter validation</b></summary>

**5.1. Test via VPN** (expected success)
```bash
ssh -i ~/.ssh/my_key <username>@10.10.10.1
```
🟢 Must log in instantly.

**5.2. Test via Public IP** (Expected Blocking):
```bash
sudo wg-quick down vps-admin
ssh -i ~/.ssh/my_key <username>@srv01.mysite.com
```
🔴 It should remain "hanging" until it times out.

**5.3 Scan test via public access outside the VPN** (invisibility):
```bash
curl http://srv01.mysite.com
```
</details>

#### Expected End State
This is the correct baseline state before operating services:
- The server is an invisible target on the public network.
- The only port that responds externally is `51820/UDP` (WireGuard).
- All management is done via the secure `wg0` interface.

---

### 9. Active Monitoring and Incident Response
This section empowers me to identify intrusion patterns in real time, using log analysis and active defense tools to automatically detect and ban malicious actors.

Firewalls and VPNs reduce the attack surface, but do not eliminate attacks. Even with minimal open ports (e.g., `UDP 51820` from WireGuard), bots continue to attempt brute-force attacks via SSH, user enumeration, handshake floods, and exploitation attempts through noise.

I will create telemetry + reaction, ensuring that:
- I see what happens;
- The system responds automatically;
- Repeated attacks are stopped at the source;
- Processing power is not wasted on hostile connections;
- My logs remain clean, containing only relevant data.

#### Defense Architecture
The strategy is simple and verifiable layers:
1. Reliable logs (`systemd` + `sshd`)
2. Pattern detector (Fail2ban)
3. Automatic action (ban on the local firewall)
4. Correct scope (do not ban my own VPN)

No heavy SIEM, no external SaaS at this stage.

#### 1. Telemetry Preparation and Verification
<details>
<summary><b>▶ View commands — checking sshd LogLevel</b></summary>

Confirm that SSH is sending detailed data to the log system:
```bash
grep -i "^LogLevel" /etc/ssh/sshd_config
```
Expected result: `LogLevel VERBOSE`

This ensures a log of login attempts, rejected keys, non-existent users, source IPs.

If not configured in this mode, change and run:
```bash
sudo systemctl reload sshd
```
</details>

#### 2. Configure Intrusion Detection
Fail2ban is a tool that reads system logs and upon detecting an attack pattern, executes a blocking command in `iptables`.

<details>
<summary><b>▶ View commands — Fail2ban installation and configuration</b></summary>

**a. Fail2ban Installation**
```bash
sudo dnf install -y epel-release
sudo dnf install -y fail2ban
```
Enable and start the service:
```bash
sudo systemctl enable --now fail2ban
sudo systemctl status fail2ban
```

**b. Base Shielding (`jail.local`)**

Create an overlay file to customize the rules:

> [!WARNING]
> Never edit `jail.conf` directly.

```bash
sudo nano /etc/fail2ban/jail.local
```
Apply this configuration:
```text
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 3

backend = systemd
banaction = iptables-multiport

# EXCLUSION ZONE (CRITICAL): Never ban myself or the VPN
ignoreip = 127.0.0.1/8 ::1 10.10.10.0/24
```
- `bantime 1h`: Hostile IP is offline for 1 hour
- `findtime 10m`: Time window to count failures (10 minutes)
- `maxretry 3`: Number of failures allowed before ban (3 failures)
- `backend systemd`: Reads directly from the system journald (more reliable)
- `banaction`: Creates a specific chain in my Firewall for banned IPs.
- `ignoreip`: Never ban myself or the VPN.

> [!WARNING]
> Critical: If I forget to include the VPN network `10.10.10.0/24`, I may self-ban myself if I repeatedly enter the wrong SSH key, for example.

**c. SSH Jail**

Explicitly enable SSH jail:
```bash
sudo nano /etc/fail2ban/jail.local
```
```text
# AT THE END OF THE FILE, ADD THIS BLOCK [SSHD]
[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
```

Restart the service:
```bash
sudo systemctl restart fail2ban
```
</details>

#### 3. Automatic Response Validation
<details>
<summary><b>▶ View commands — general status and SSH jail</b></summary>

View general status:
```bash
sudo fail2ban-client status
```
Expected Result:
```text
Number of jails: 1
Jail list: sshd
```

View SSH jail status:
```bash
sudo fail2ban-client status sshd
```
I should see banned IPs (if any) and active counters.
</details>

#### 4. Controlled Tests (Mandatory)
<details>
<summary><b>▶ View tests — simulating an attack and validating the ban</b></summary>

**Test 1: Invalid Attempt (from outside the VPN)**

Since `iptables` DROPs any connection on port 22 coming from the public internet, `sshd` never gets to see the login attempt. To test Fail2ban, temporarily open the Firewall:

a. On the server, open port 22 on the public IP:
```bash
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
```

b. From an IP address outside the VPN (e.g., using 4G from a mobile phone), try logging in via SSH — repeat until exceeding 3 attempts (`maxretry`):

> [!IMPORTANT]
> **Split-Horizon DNS caveat**: `ssh fakeuser@srv01.mydomain.com` will NOT work because the domain resolves to the private VPN IP. Use the public IP of the VPS directly:

```bash
ssh fakeuser@<VPS_PUBLIC_IP>
```

c. On the server, check for the ban:
```bash
sudo fail2ban-client status sshd
```
🔴 Expected result: IP automatically banned; new attempts don't even reach SSH.

d. Check the Firewall:
```bash
sudo iptables -L -n
```
A new `f2b-sshd` rule blocking the attacking IP address will appear.

e. Finally, close port 22 again:
```bash
sudo iptables -D INPUT -p tcp --dport 22 -j ACCEPT
```

**Test 2: VPN Access Remains Functional**
```bash
ssh -i ~/.ssh/my_key ops@10.10.10.1
```
🟢 Expected result: normal access; no impact on VPN.
</details>

#### Expected final state
In the current configuration, Fail2ban will serve as a "second line of defense" if I need to open any public ports in the future or to protect the WireGuard port itself (`UDP 51820`) against packet flooding.

Therefore, at this point:
- Hostile attempts are detected;
- Malicious IPs are automatically banned;
- My VPN is never affected;
- The server responds automatically to external noise.

---

[← Phase 2: SSH & VPN Hardening](./02-ssh-vpn-hardening.md) · **Phase 3 of 4** · [Next: Phase 4 — Cloudflare Proxy & Full (Strict) SSL →](./04-cloudflare-tls.md)
