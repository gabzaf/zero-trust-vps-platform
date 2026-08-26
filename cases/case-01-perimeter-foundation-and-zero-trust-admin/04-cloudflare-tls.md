# Phase 4: Cloudflare Proxy & Full (Strict) SSL

[← Phase 3: Firewall & Monitoring](./03-firewall-monitoring.md) · **Phase 4 of 4** · [Back to Overview →](./00-overview.md)

---

### In this phase
- [10. Cloudflare Proxy and Infrastructure Obfuscation](#10-cloudflare-proxy-and-infrastructure-obfuscation)
  - [1. Cloudflare Proxy Activation](#1-cloudflare-proxy-activation)
  - [2. Adjust Local Firewall to Cloudflare-Aware](#2-adjust-local-firewall-to-cloudflare-aware)
  - [3. Final Cloudflare-aware Firewall Structure](#3-final-cloudflare-aware-firewall-structure)
  - [4. Mandatory Tests](#4-mandatory-tests)
- [11. End-to-end Encryption with Full (Strict) SSL](#11-end-to-end-encryption-with-full-strict-ssl)
  - [The two layers of encryption](#the-two-layers-of-encryption)
  - [The strategy adopted: Cloudflare Origin Certificate](#the-strategy-adopted-cloudflare-origin-certificate)
  - [End-to-End Encryption Structure](#end-to-end-encryption-structure)
  - [1. Generate the Cloudflare Origin Certificate](#1-generate-the-cloudflare-origin-certificate)
  - [2. Installing the certificate on the origin (VPS)](#2-installing-the-certificate-on-the-origin-vps)
  - [3. Enabling Full (Strict) in Cloudflare](#3-enabling-full-strict-in-cloudflare)
  - [4. Verify files on the server](#4-verify-files-on-the-server)

---

## Configuration Artifacts & Reference Code

### 10. Cloudflare Proxy and Infrastructure Obfuscation
This section activates Cloudflare Proxy as a layer of protection, ensuring that my VPS's real address is never exposed to the public network.

Up to this point, my VPS is not visible on the internet because no public ports are open, all administration occurs via VPN and the local firewall operates in `deny all` mode.

This state is intentional, but impractical for serving applications and receiving end-user traffic. The solution is not to open ports to the global internet, but to create a single trusted edge.

From now on, Cloudflare ceases to be just a DNS server and begins to act as a reverse proxy, an attack absorption layer and a single point of entry, ensuring that my VPS's real address is never exposed to the public network.

Users will never communicate with my VPS; they will communicate with Cloudflare!

At the end:
- The Cloudflare proxy will be activated (orange cloud);
- Ports 80/443 remain closed to the world;
- Only Cloudflare IPs will be allowed on the local firewall;
- Any attempt to directly access the real IP address will continue to be blocked.

#### 1. Cloudflare Proxy Activation

<details open>
<summary><b>▶ View steps — enabling proxy and configuring records</b></summary>

In the Cloudflare panel, access **DNS → Records** and configure the records as follows:

**a. Activate Proxy on the root record**
Locate the `@` record and change it from DNS Only (gray) to **Proxied** (**orange cloud**).

| Type | Name | Value | Proxy | Destination | Purpose |
|:---:|:---|:---|:---|:---|:---|
| **A** | `@` | VPS IP | Proxied (Orange) | `mysite.com` | Root domain |

**b. Add Wildcard record for public domains**
Add a new record:

| Type | Name | Value | Proxy | Destination | Purpose |
|:---:|:---|:---|:---|:---|:---|
| **A** | `*` | VPS IP | Proxied (Orange) | `mysite.com` | Wildcard: allows any PUBLIC subdomain to work automatically. |

> The wildcard (*) allows any subdomain to work automatically. When I need to create `app.mysite.com` or `admin.mysite.com`, the DNS already responds without needing to create an individual record.

**c. Keep `srv01` in DNS Only**
The `srv01` record should remain **DNS Only (grayed out)**. It is used for direct SSH access, which does not work through the Cloudflare proxy.

**d. Final state of the records**:

| Type | Name  | Value       | Proxy              | Usage                                      |
|:----:|:------|:------------|:-------------------|:-------------------------------------------|
| **A** | `@`     | VPS IP      | Proxied (Orange)   | Root domain                                |
| **A** | `*`     | VPS IP      | Proxied (Orange)   | Current and future public subdomains        |
| **A** | `srv01` | `10.10.10.1` | DNS Only (Grey ☁️)  | SSH / Administration (VPN only)             |

> Immediate result: From this point on, HTTP/HTTPS requests pass through Cloudflare's servers, and the VPS's real IP address no longer appears in any public response.
</details>

#### 2. Adjust Local Firewall to Cloudflare-Aware
Do not open ports 80/443 to the world. I will only authorize official Cloudflare IPs and make the local firewall on my VPS server a Cloudflare-aware firewall.

<details open>
<summary><b>▶ View script — Cloudflare-aware firewall (iptables)</b></summary>

**a. Consult the official Cloudflare IPs**
```bash
# Download updated list of IPv4 IPs
curl -s https://www.cloudflare.com/ips-v4 -o /tmp/cloudflare-ips-v4.txt

# Verify contents
cat /tmp/cloudflare-ips-v4.txt
```

> [!WARNING]
> Never copy static lists of tutorials from the internet; they may be outdated.

**b. Create a Cloudflare rules script**
```bash
sudo nano /usr/local/bin/cloudflare-firewall.sh
```
```bash
#!/bin/bash
set -euo pipefail

# =============================================================================
# Cloudflare-Aware Firewall (IPv4 Only) - v2026
# =============================================================================

# 1. Definitions
CLOUDFLARE_IPS_URL="https://www.cloudflare.com/ips-v4"
CHAIN_NAME="CLOUDFLARE_V4"

echo "Cloudflare-aware Firewall update initialized..."

# 2. Create or Cleaning the Dedicated Chain
if ! iptables -L "$CHAIN_NAME" >/dev/null 2>&1; then
    iptables -N "$CHAIN_NAME"
fi
iptables -F "$CHAIN_NAME"

# 3. Download IPs and populate Chain
IPS=$(curl -s --connect-timeout 10 "$CLOUDFLARE_IPS_URL")

if [ -z "$IPS" ]; then
    echo "ERROR: Could not get Cloudflare IPs. Aborting to prevent lockout."
    exit 1
fi

for ip in $IPS; do
    iptables -A "$CHAIN_NAME" -s "$ip" -p tcp -m multiport --dports 80,443 -j ACCEPT
done

# 4. Configure the jump in the INPUT (Ensuring it is unique)
iptables -D INPUT -p tcp -m multiport --dports 80,443 -j "$CHAIN_NAME" 2>/dev/null || true
iptables -I INPUT 1 -p tcp -m multiport --dports 80,443 -j "$CHAIN_NAME"

# 5. Apply DROP right after the Cloudflare rule
iptables -D INPUT -p tcp -m multiport --dports 80,443 -j DROP 2>/dev/null || true
iptables -I INPUT 2 -p tcp -m multiport --dports 80,443 -j DROP

echo "[$(date)] IPv4 rules applied successfully."
echo "Free total IPv4 ranges: $(echo "$IPS" | wc -l)"
```
```bash
# Make it executable
sudo chmod +x /usr/local/bin/cloudflare-firewall.sh
```

**c. Apply the rules**
```bash
sudo /usr/local/bin/cloudflare-firewall.sh
```

**d. Verify applied rules**
```bash
sudo iptables -L CLOUDFLARE_V4 -n -v
```

**e. Persist the rules**
```bash
sudo service iptables save
```

**f. Configure periodic updates (optional)**
```bash
# Add to crontab (runs every Sunday at 4 AM)
sudo crontab -e
```
Add the line:
`0 4 * * 0 /usr/local/bin/cloudflare-firewall.sh >> /var/log/cloudflare-firewall.log 2>&1`
</details>

#### 3. Final Cloudflare-aware Firewall Structure
```text
Chain INPUT (policy DROP)
│
├─ ACCEPT: loopback (lo)
├─ ACCEPT: established, related
├─ ACCEPT: interface wg0 (VPN)
├─ CLOUDFLARE: tcp dports 80,443 → dedicated chain
│   ├─ ACCEPT: 173.245.48.0/20
│   ├─ ACCEPT: 103.21.244.0/22
│   ├─ ACCEPT: ... (ranges)
│   └─ (return for INPUT)
├─ DROP: tcp dports 80,443 (non-Cloudflare)
└─ DROP: all the rest (policy)
```

#### 4. Mandatory Tests
<details open>
<summary><b>▶ View tests — validating origin invisibility</b></summary>

**Test 1: Access via browser**
```text
http://mysite.com
```
🔴 Expected result: Cloudflare error 521 or 522. Proves the proxy is active, the real IP is hidden and the origin is not yet responding (Traefik is not yet configured).

**Test 2: Direct access to the real IP**
```bash
curl --connect-timeout 5 http://VPS_IP
```
🔴 Expected result: Timeout. Invisible server.

**Test 3: Check counters**
```bash
sudo iptables -L CLOUDFLARE_V4 -n -v
```
🟢 Expected result: After accessing via Cloudflare, the packet and byte counters should increase.

**Test 4: VPN Access**
```bash
curl http://10.10.10.1
```
🟢 Expected result: Connection works if a server is set. Proves that the block is perimeter-based.
</details>

---

### 11. End-to-end Encryption with Full (Strict) SSL

I will prepare the cryptographic foundation for secure traffic between Cloudflare and my VPS by installing the origin certificate that will be used by the reverse proxy I will install later.

> [!IMPORTANT]
> The HTTPS tunnel between Cloudflare and my VPS will only be complete after configuring Traefik. Now, I prepare the certificate.

When a user accesses `https://mysite.com`, traffic doesn't go directly to my VPS — it passes through Cloudflare first:
```text
\o/ User ←──HTTPS──→ Cloudflare ←──HTTPS──→ VPS Server | - |
 |         (Edge)                 (Origin)             | - |
/ \                                                    | - |
```

#### The two layers of encryption

##### Edge Layer (User ↔ Cloudflare)
This layer is already in place. As soon as I add a domain to Cloudflare, it automatically issues a universal SSL certificate that covers my domain and the www subdomain.

##### Origin Layer (Cloudflare ↔ VPS Server)
This layer is my responsibility. Cloudflare needs a valid certificate on my VPS to close the encrypted tunnel. Without it, traffic between Cloudflare and my server can be intercepted.

##### Why does this matter?
| Mode | What Happens | Verdict |
|:---|:---|:---:|
| **Off** | No encryption at any point | ❌ Never use |
| **Flexible** | HTTPS only between user and Cloudflare. Traffic to my VPS is plaintext | ❌ Avoid as much as possible |
| **Full** | HTTPS on both ends, but accepts any certificate (even expired or invalid) | ⚠️ Vulnerable to MITM attacks |
| **Full (Strict)** | HTTPS on both ends with strict origin certificate validation | ✅ The only acceptable option |

There is **only one valid choice for production**: **Full (Strict)**.

#### The strategy adopted: Cloudflare Origin Certificate
- **Let's Encrypt** — Standard public certificate, accepted by any client. Requires renewal every 90 days.
- **Cloudflare Origin Certificate** — Certificate issued free of charge by the Cloudflare CA, valid for up to 15 years. Zero renewal maintenance. Ideal for servers behind Cloudflare.

#### End-to-End Encryption Structure

```text
   CLIENT  (Browser)          CLOUDFLARE (Proxy)            VPS (Origin)
  +-----------------+        +------------------+        +------------------+
  |                 |        |                  |        |                  |
  |    O            |        |    Orange        |        |    Private       |
  |   /|\  USER     |        |    Cloud         |        |    Vault         |
  |   / \           |        |                  |        |                  |
  +--------+--------+        +---------+--------+        +---------+--------+
           |                           |                           |
           |       EDGE TUNNEL         |       ORIGIN TUNNEL       |
           |    (Public HTTPS)         |    (Private HTTPS)        |
           +-------------------------->+-------------------------->+
           |                           |                           |
    CERTIFICATE:                CERTIFICATE:                CERTIFICATE:
    Universal SSL               Cloudflare CA               Origin Cert
    (Emitted by CF)           (Validated by CF)          (Installed in /etc/ssl)
           |                           |                           |
           |                           |                           |
    MODE: SSL FULL (STRICT) <--------------------------------------+
```

#### 1. Generate the Cloudflare Origin Certificate
<details open>
<summary><b>▶ View steps — issuing the certificate in the dashboard</b></summary>

1. Go to **SSL/TLS → Origin Server**.
2. Click on **Create Certificate**.
3. Keep default settings (RSA 2048 or ECDSA).
4. Make sure hostnames cover: `mysite.com` and `*.mysite.com`.
5. Select a validity of 15 years.

> [!IMPORTANT]
> Cloudflare will display the **Origin Certificate** (CRT) and the **Private Key** (KEY) only once.
</details>

#### 2. Installing the certificate on the origin (VPS)
<details open>
<summary><b>▶ View commands — certificate installation and validation</b></summary>

On the server (via VPN):

**a. Create an isolated and protected directory**
```bash
sudo mkdir -p /etc/ssl/cloudflare
sudo chmod 700 /etc/ssl/cloudflare
```

**b. Create the files**
```bash
# Paste Origin Certificate content
sudo nano /etc/ssl/cloudflare/origin.crt

# Paste Private Key content
sudo nano /etc/ssl/cloudflare/origin.key

# Restrict permissions
sudo chown root:root /etc/ssl/cloudflare/*
sudo chmod 600 /etc/ssl/cloudflare/*
```

**c. Validate the installation**
```bash
sudo openssl x509 -in /etc/ssl/cloudflare/origin.crt -text -noout | head -20
```

Verify that the private key matches the certificate:
```bash
# Certificate hash
sudo openssl x509 -noout -modulus -in /etc/ssl/cloudflare/origin.crt | openssl md5

# Key hash
sudo openssl rsa -noout -modulus -in /etc/ssl/cloudflare/origin.key | openssl md5
```
🟢 Expected result: The MD5 hashes should be identical.
</details>

#### 3. Enabling Full (Strict) in Cloudflare
<details open>
<summary><b>▶ View steps — enabling Full (Strict) and checking files</b></summary>

In the panel:
- **SSL/TLS → Overview**
- Select **Full (Strict)**
</details>

#### 4. Verify files on the server
```bash
ls -la /etc/ssl/cloudflare/
```
```text
drwx------ 2 root root 4096 ... .
-rw------- 1 root root ... origin.crt
-rw------- 1 root root ... origin.key
```

---

> This closes the perimeter foundation: identity, private administration, network isolation, monitoring and edge encryption are all in place.

---

[← Phase 3: Firewall & Monitoring](./03-firewall-monitoring.md) · **Phase 4 of 4** · [Back to Overview →](./00-overview.md)
