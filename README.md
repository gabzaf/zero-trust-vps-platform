# zero-trust-vps-platform
### *Cloudflare Edge, Zero-Trust Perimeter, WireGuard S2C, Host Firewall & Hardened Administration*

[![Linux](https://img.shields.io/badge/Linux-%20AlmaLinux-E95420?logo=linux&logoColor=white)](#)
[![Security](https://img.shields.io/badge/Security-Zero--Trust%20Perimeter-success?logo=shield&logoColor=white)](#)
[![Cloudflare](https://img.shields.io/badge/Edge-Cloudflare%20WAF%20%26%20Proxy-F38020?logo=cloudflare&logoColor=white)](#)
[![WireGuard](https://img.shields.io/badge/VPN-WireGuard%20S2C-88171A?logo=wireguard&logoColor=white)](#)

---

## High-Level Perimeter Architecture Diagram

```mermaid
graph TD
    User["Web User - Internet"]
    Attacker["Malicious Scanner or Bot"]
    Admin["SysAdmin Remote Device"]

    subgraph Cloudflare_Edge["Cloudflare Edge Layer"]
        CF_WAF["Cloudflare WAF (Custom Rules & Managed Rules)"]
        CF_PROXY["Cloudflare Reverse Proxy (Strict TLS)"]
        CF_WAF --> CF_PROXY
    end

    subgraph Host_Firewall["Host Firewall Perimeter - iptables & Fail2ban"]
        FW_CF["ALLOW: Cloudflare IPs Only (Ports 80/443 TCP)"]
        FW_WG["ALLOW: WireGuard (Port 51820 UDP)"]
        FW_DROP["DEFAULT DROP: All Other WAN Inbound Traffic"]
        F2B["Fail2ban: Automated Hostile IP Banning"]
    end

    subgraph Admin_Plane["Private Management Plane - WireGuard 10.10.10.0/24"]
        WG_IF["WireGuard Interface (wg0 - 10.10.10.1)"]
        SSH["Hardened OpenSSH (Ed25519 Keys Only, No Root, Scoped Sudo)"]
        WG_IF --> SSH
    end

    subgraph Origin_Layer["VPS Origin Platform"]
        ORIGIN_SSL["Origin CA Certificate (/etc/ssl/cloudflare)"]
    end

    User -->|HTTPS 443| CF_WAF
    CF_PROXY -->|Strict TLS Proxy| FW_CF
    FW_CF --> ORIGIN_SSL

    Attacker -.->|Direct WAN Scan| FW_DROP
    Attacker -.->|Brute Force Attempt| F2B

    Admin -->|Encrypted VPN Tunnel| FW_WG
    FW_WG --> WG_IF
```

---

## Engineering Case Studies (S.T.A.R. Format)

Each case documents engineering decisions and trade-offs behind this platform following the **Situation, Task, Action, Result** methodology.

| Case | Focus Area | Key Technologies | Status |
| :--- | :--- | :--- | :---: |
| **[Case 01](./cases/case-01-perimeter-foundation-and-zero-trust-admin/00-overview.md)** | VPS Perimeter Foundation & Zero-Trust Administration | Cloudflare Proxy & WAF, WireGuard, iptables, Fail2ban, SSH Hardening | 🟢 Published |

---

## Repository Structure

```text
.
├── README.md                          # High-level architecture & case index
└── cases/
    └── case-01-perimeter-foundation-and-zero-trust-admin/
        ├── 00-overview.md             # S.T.A.R. breakdown, architecture & phase index
        ├── 01-identity-dns.md         # Phase 1: Ed25519 identity, OS baseline & DNS delegation
        ├── 02-ssh-vpn-hardening.md    # Phase 2: OpenSSH hardening, sudo scoping & WireGuard S2C
        ├── 03-firewall-monitoring.md  # Phase 3: iptables Default-DROP firewall & Fail2ban
        ├── 04-cloudflare-tls.md       # Phase 4: Cloudflare Proxy, Origin CA & Full (Strict) SSL
        └── 05-cloudflare-waf.md       # Phase 5: Cloudflare WAF Custom Rules & Edge Security
```
