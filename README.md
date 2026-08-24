# zero-trust-vps-platform
### *Zero-Trust Perimeter, Cloudflare Edge, Reverse Proxy, Container Isolation & Centralized Observability*

[![Linux](https://img.shields.io/badge/Linux-%20AlmaLinux-E95420?logo=linux&logoColor=white)](#)
[![Security](https://img.shields.io/badge/Security-Zero--Trust%20Perimeter-success?logo=shield&logoColor=white)](#)
[![Cloudflare](https://img.shields.io/badge/Edge-Cloudflare%20WAF%20%26%20Proxy-F38020?logo=cloudflare&logoColor=white)](#)
[![WireGuard](https://img.shields.io/badge/VPN-WireGuard%20S2C-88171A?logo=wireguard&logoColor=white)](#)
[![Traefik](https://img.shields.io/badge/Proxy-Traefik%20v3-24A1C1?logo=traefik&logoColor=white)](#)
[![Docker](https://img.shields.io/badge/Containers-Docker%20-2496ED?logo=docker&logoColor=white)](#)
[![Observability](https://img.shields.io/badge/Observability-Loki%20%2B%20Promtail%20%2B%20Grafana-F46800?logo=grafana&logoColor=white)](#)

---

## High-Level Architecture Diagram

```mermaid
graph TD
    User["Web User - Internet"]
    Attacker["Malicious Scanner or Bot"]
    Admin["SysAdmin Remote Device"]

    subgraph Cloudflare_Edge["Cloudflare Edge Layer"]
        CF_WAF["Cloudflare WAF, DDoS and Edge TLS"]
    end

    subgraph Host_Firewall["Host Firewall Perimeter - UFW iptables"]
        FW_CF["ALLOW: Cloudflare IPs Only - Ports 80 and 443"]
        FW_WG["ALLOW: WireGuard UDP - Port 51820"]
        FW_DROP["DEFAULT DROP: All Other WAN Inbound Traffic"]
    end

    subgraph Admin_Plane["Private Admin Plane - WireGuard 10.10.10.0/24"]
        SSH["Hardened OpenSSH - Ed25519, No Root"]
        Cockpit["Cockpit Web Admin and Telemetry"]
        Netdata["Netdata Real-Time Metrics"]
        Grafana["Grafana Dashboards"]
    end

    subgraph App_Platform["Docker Container Platform - /srv"]
        Traefik["Traefik v3 Reverse Proxy - Strict TLS"]
        WebApp["Web Applications and APIs"]
        DB["Persistent Database - PostgreSQL and Redis"]
        Promtail["Promtail Log Collector"]
        Loki["Grafana Loki Central Store"]
    end

    User -->|HTTPS 443| CF_WAF
    CF_WAF -->|Strict TLS Proxy| FW_CF
    FW_CF --> Traefik
    Traefik -->|proxy_net| WebApp
    WebApp -->|internal_db| DB

    Attacker -.->|Direct WAN Scan| FW_DROP

    Admin -->|WireGuard Tunnel| FW_WG
    FW_WG --> SSH
    FW_WG --> Cockpit
    FW_WG --> Netdata
    FW_WG --> Grafana

    Promtail -.->|Collect Logs| Loki
    Loki -->|VPN-Only Access| Grafana
```

---

## Engineering Case Studies (S.T.A.R. Format)

Each case below documents a real engineering decision behind this platform, following the **Situation, Task, Action, Result** format, the goal is to show *what* was deployed, *why* specific trade-offs were made and how they were validated.

| Case | Focus Area | Key Technologies | Status |
| :--- | :--- | :--- | :---: |
| **[Case 01](./cases/case-01-perimeter-and-edge-security.md)** | Perimeter Hardening, Edge Security & Zero-Trust Admin | Cloudflare WAF, WireGuard, UFW/iptables, SSH Hardening | 🟢 Published |
| *More cases coming soon* | — | — | 🟡 Planned |

---

## Security Posture & Defense-in-Depth Matrix

| Layer | Threat Vector | Implemented Defense & Controls | Validation Method |
| :--- | :--- | :--- | :--- |
| **Identity & Access** | SSH Password Brute-force & Credential Stuffing | Ed25519 asymmetric keys exclusively, PermitRootLogin no, PasswordAuthentication no, explicit AllowUsers whitelist. | `ssh -o PreferredAuthentications=password` fails instantly without password prompt. |
| **Network Perimeter** | Port Scanning & Direct Host Fingerprinting | Host firewall in **Default-DROP** mode. Port 22 blocked entirely from WAN; ports 80/443 restricted to Cloudflare CIDRs only. | Active nmap -sS -Pn -p- from non-Cloudflare IPs confirms no unintended TCP ports are open/responsive. |
| **Administrative Plane** | Unencrypted remote management & rogue admin probes | **WireGuard Site-to-Client VPN**. SSH & internal tools bind exclusively to the VPN interface (`10.10.10.x`). | Direct WAN connection to management ports times out; access succeeds exclusively when the WireGuard tunnel `wg0` is up. |
| **Edge / Web Ingress** | DDoS, Injections Attacks, Scrapers, Cloudflare Bypass | Cloudflare Proxy (Orange Cloud) + WAF rules + host firewall whitelist restricting 80/443 to Cloudflare CIDRs. | Direct `curl https://<VPS_IP>` times out/drops. Domain queries pass cleanly. |
| **Application Layer** | Container breakout & lateral network movement | Non-root containers, read-only root filesystem where applicable, segmented Docker bridge networks (`internal_db` isolated from gateway). | Compromised web container cannot reach other tenants or the DB network's gateway. |
| **Data & State** | Data loss & configuration drift | Atomic `/srv` directory mapping, named persistent volumes, snapshot baseline before changes. | Point-in-time rollback validated against snapshot baseline. |
