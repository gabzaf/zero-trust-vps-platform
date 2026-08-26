# Phase 1: Identity & DNS

[← Overview](./00-overview.md) · **Phase 1 of 4** · [Next: SSH & VPN Hardening →](./02-ssh-vpn-hardening.md)

---

### In this phase
- [1. Generate SSH Key Pair](#1-generate-ssh-key-pair)
- [2. System Base Configuration](#2-system-base-configuration)
  - [a. Create a user with sudo](#a-create-a-user-with-sudo)
  - [b. Copy SSH key to the new user](#b-copy-ssh-key-to-the-new-user)
- [3. Domain registration and DNS delegation in Cloudflare (DNS Only)](#3-domain-registration-and-dns-delegation-in-cloudflare-dns-only)
  - [Domain Delegation to Cloudflare](#domain-delegation-to-cloudflare)
  - [DNS Propagation Time](#dns-propagation-time)
  - [DNS Configuration in Cloudflare](#dns-configuration-in-cloudflare)

---

## Configuration Artifacts & Reference Code

### 1. Generate SSH Key Pair
To generate a modern, secure SSH key compatible with virtually any VPS provider, the recommended standard is **Ed25519**.

<details>
<summary><b>▶ View commands — SSH key generation</b></summary>

Open the terminal and type the following command:
```bash
ssh-keygen -t ed25519 -C "email@example.com" -f ~/.ssh/my_key
```
- `-t ed25519`: Defines the algorithm (faster and more secure than the old RSA).
- `-C`: Adds a comment (usually email) to identify the key on the server.
- `-f`: Defines a specific name and path for the key.

The terminal will ask two questions:
1.1. **Enter passphrase**: (Recommended) Enter a password to protect the private key file. Or press Enter twice to leave it without a password (passphrase empty).
1.2. **Enter same passphrase again**: Repeat the password.

The command will create two files in the `~/.ssh` folder:
- `my_key`: My Private Key. Never share this file.
- `my_key.pub`: My Public Key. This is the file I will send to the VPS provider.

I will need to copy the text inside the public key to paste into my provider's control panel. Use the command below to display the text:
```bash
cat ~/.ssh/my_key.pub
```
</details>

---

### 2. System Base Configuration
This section explains how to configure Linux OS base for secure and predictable administration before installing any stack.

<details>
<summary><b>▶ View commands — base packages and root user</b></summary>

**Initial update and base packages**

Install tools that assist in diagnosing and editing files on a daily basis:
```bash
sudo dnf check-update
sudo dnf -y update 
sudo dnf -y install ca-certificates curl wget gnupg2 vim nano jq unzip tar rsync bind-utils chrony
```
- `ca-certificates`, `curl`, `gnupg`: foundation for reliable repositories and downloads.
- `bind-utils`: necessary for debugging routes, domains and ports.
- `chrony`: correct timing avoids chaos with TLS, logs and validation.
- `vim`, `nano`: indispensable text editors for configuring system files.
- `jq`: JSON file processor via command line (essential for APIs and automations).
- `unzip`, `tar`: standard tools for unpacking packages and backups.
- `rsync`: efficient protocol for transferring and sync files between servers.
- `wget`: utility for downloading files via HTTP/HTTPS/FTP.

**Create an administrative user**

Before creating the administrative user, change the default root password and store it in a password manager.

Change `root` user password:
```bash
passwd root
```
This password will be used whenever I need to log in as `root`.
</details>

#### a. Create a user with sudo
The first step is to create a security layer by creating a regular user with administrative permissions.

<details>
<summary><b>▶ View commands — creating the admin user</b></summary>

Create a dedicated user (e.g., ops, admin, or any other name) and grant superuser privileges.

> [!NOTE]
> The commands below are executed as root.

Create `<username>` user:
```bash
useradd -m <username>
```
Set password for this user:
```bash
passwd <username>
```
Add to group 'wheel' (group that allows using sudo in this distro):
```bash
usermod -aG wheel <username>
```

> [!IMPORTANT]
> Never log out of the root terminal without first testing the new user.
</details>

#### b. Copy SSH key to the new user
From now on, I will use the `<username>` user for everything!

Therefore, I have to ensure I can access my server without root using an SSH public key.

> [!IMPORTANT]
> **Note on key reuse**: Using the same SSH key for `root` and the administrative user works, but reduces the security isolation between the two accounts, because if the key is leaked, both accesses are compromised together. To ensure complete security, consider generating a dedicated key per user.

<details>
<summary><b>▶ View commands — copying and testing the key</b></summary>

On my computer (or wherever my SSH public key was generated or is stored), run the command below to copy the public key to my VPS server and make it available to the newly created `<username>` user:

```bash
ssh-copy-id -i ~/.ssh/my_key.pub <username>@SERVER_IP
```
Test login as `<username>` user using SSH key:
```bash
ssh -i ~/.ssh/my_key <username>@SERVER_IP
```
</details>

---

### 3. Domain registration and DNS delegation in Cloudflare (DNS Only)
First I need to have a valid domain and I will delegate the DNS authority of this domain to Cloudflare, operating exclusively in DNS only.

&rarr; **Why is the domain mandatory?**
A correctly configured domain is a technical prerequisite for:
- **SSL/TLS Certificates**: The future issuance of SSL/TLS certificates requires that the domain is already assigned to the IP of the VPS to validate the ownership of the server.
- **Standard administrative access**: Using `ssh <username>@srv1.domain.com` is superior to using IP. If I need to change my server, just update the DNS and automation, monitoring and access scripts will continue working without alterations.
- **Reputation and security**: The domain allows me to implement layers of protection that direct IPs do not support, protecting my Web App against global attacks from bots.

#### Domain Delegation to Cloudflare
Cloudflare will act as my primary DNS zone, providing near-instant propagation and a foundation for future security. It will also serve as a central point for name management.

**a. DNS Operating Modes in Cloudflare**

In Cloudflare, each DNS record can operate in two modes:
- **DNS Only (gray cloud)**:
  - Cloudflare only responds to DNS queries.
  - Traffic goes directly to your VPS IP.
- **Proxied (orange cloud)**:
  - Cloudflare intercepts HTTP/HTTPS traffic.
  - Applies proxy, TLS, WAF, caching, etc.

**b. Adding the domain to Cloudflare**

<details>
<summary><b>▶ View steps — adding the domain and changing nameservers</b></summary>

With the domain registered, the next step is to use Cloudflare to manage the DNS. This involves adding the domain to a Cloudflare account and changing the nameservers at the registrar to point to Cloudflare.

After accessing Cloudflare dashboard, follow the steps below:
1. Click on **Add Domain** in the Cloudflare dashboard. When prompted, enter the domain (just the base name, for example, `mysite.com`, without `www`).
2. Select a Cloudflare plan. For my purpose, I choose the **Free** plan. It's sufficient for everything that I build.
3. Cloudflare will then scan the domain's current DNS records and list what it finds. **Review the detected DNS records** and adjust if necessary.
4. In the final step of adding the domain, Cloudflare will display two custom nameservers assigned to my domain (for example: `dana.ns.cloudflare.com` and `nick.ns.cloudflare.com`).
5. Copy the two displayed nameservers and proceed to change the domain's nameservers in my registrar's control panel (where I purchased the domain) to the values provided by Cloudflare:
   - Access the registrar's control panel,
   - Locate the domain's nameserver settings, and
   - Replace the existing values with the two provided by Cloudflare.
6. With the nameservers changed at the registrar, return to Cloudflare and click **Done, check nameservers** to start the verification.
</details>

#### DNS Propagation Time
After changing the nameservers at my registrar, I need to wait for DNS propagation:
```bash
dig NS mysite.com +short
```
The expected result is the two Cloudflare nameservers (e.g., `dana.ns.cloudflare.com`, `nick.ns.cloudflare.com`). As long as the old registrar nameservers are still shown, propagation is not yet complete.

#### DNS Configuration in Cloudflare
<details>
<summary><b>▶ View steps — creating the A records</b></summary>

With the domain active in Cloudflare (nameservers propagated), add the necessary DNS records in the **DNS > Records** tab:

1. **Create an A record** pointing the root domain (`@`) to the VPS IP address. Proxy status: **DNS Only** (Gray Cloud ☁️).
2. **Create an A record** pointing `srv01` to the VPS IP address. Proxy status: **DNS Only** (Gray Cloud ☁️).
3. **Create an A record** pointing `vpn` to the VPS IP address. Proxy status: **DNS Only** (Gray Cloud ☁️).
</details>

After adding the records, my DNS in Cloudflare will have:

| Type | Name  | Value        | Proxy     | Destination            | Purpose              |
|:----:|:------|:-------------|:----------|:-----------------------|:---------------------|
| **A** | `@`   | VPS IP       | DNS Only  | `mysite.com`           | Root domain          |
| **A** | `srv01` | VPS IP     | DNS Only  | `srv01.mysite.com`     | Administration       |
| **A** | `vpn` | VPS IP       | DNS Only  | `vpn.mysite.com`       | VPN connection       |

---

[← Overview](./00-overview.md) · **Phase 1 of 4** · [Next: Phase 2 — SSH & VPN Hardening →](./02-ssh-vpn-hardening.md)
