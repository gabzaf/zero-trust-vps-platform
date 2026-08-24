# Case 01: Perimeter Hardening, Edge Security & Zero-Trust Administration

> **Domain**: Infrastructure Security, Linux Administration, Network Hardening
>
> **Technologies**: Linux, Cloudflare Edge & WAF, WireGuard VPN, OpenSSH, UFW / iptables, Origin TLS 
>
> **Methodology**: S.T.A.R. Framework (Situation, Task, Action, Result)

## Executive Summary (S.T.A.R. Breakdown)

```mermaid
flowchart LR
    S["<b>Situation</b><br/>• Raw VPS on Public WAN<br/>• Constant Port Scans & Brute-force<br/>• DDoS & Origin Exposure"]
    T["<b>Task</b><br/>• Eliminate Public Admin Ports<br/>• Hide Origin Server Real IP<br/>• Enforce End-to-End Encryption"]
    A["<b>Action</b><br/>• WireGuard Admin Tunnel (Client→Origin)<br/>• SSH Hardening (Ed25519, No Root)<br/>• Cloudflare-Aware Host Firewall<br/>• Origin Locked to Cloudflare IPs + Origin CA"]
    R["<b>Result</b><br/>• 0 Exposed Admin Ports<br/>• Zero SSH Brute-force Incursions<br/>• Origin Unreachable Outside Edge"]

    S --> T --> A --> R
```
