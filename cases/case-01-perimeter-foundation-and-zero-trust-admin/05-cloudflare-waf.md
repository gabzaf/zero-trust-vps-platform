# Phase 5: Cloudflare WAF & Edge Security

[← Phase 4: Cloudflare Proxy & TLS](./04-cloudflare-tls.md) · **Phase 5 of 5** · [Back to Overview →](./00-overview.md)

---

### In this phase
- [12. Cloudflare WAF & Edge Traffic Filtering](#12-cloudflare-waf--edge-traffic-filtering)
  - [12.1. End-to-End Traffic Filtering Architecture](#121-end-to-end-traffic-filtering-architecture)
  - [12.2. WAF Core Concepts & Execution Precedence](#122-waf-core-concepts--execution-precedence)
    - [WAF Custom Rules](#waf-custom-rules)
    - [WAF Managed Ruleset](#waf-managed-ruleset)
    - [Rate Limiting Rules](#rate-limiting-rules)
    - [Rules Precedence Order](#rules-precedence-order)
  - [12.3. Configure Security Level](#123-configure-security-level)
    - ["I'm Under Attack" (Emergency) Mode](#im-under-attack-emergency-mode)
  - [12.4. Creating Custom Rules](#124-creating-custom-rules)
    - [a. Enable geo-blocking](#a-enable-geo-blocking)
    - [b. Block malicious User-Agents](#b-block-malicious-user-agents)
    - [c. Brute-force protection on critical endpoints](#c-brute-force-protection-on-critical-endpoints)
  - [12.5. Create Rate Limiting Rules](#125-create-rate-limiting-rules)
  - [12.6. Monitoring](#126-monitoring)
    - [a. Monitoring events](#a-monitoring-events)
    - [b. Monitoring Traffic](#b-monitoring-traffic)
  - [12.7. Mandatory Tests](#127-mandatory-tests)

---

## Configuration Artifacts & Reference Code

### 12. Cloudflare WAF for Network Edge Blocking
I will implement Web Application Firewall (WAF) rules in Cloudflare to block malicious traffic at the edge before it reaches my VPS server.

Protecting my infrastructure is a multi-layered architecture:
- **Management layer**: Administrative isolation via S2C VPN (WireGuard), making the SSH port invisible to the public internet.
- **Network layer**: Infrastructure obfuscation via Cloudflare Proxy, masking the real IP of my VPS and absorbing volumetric DDoS attacks.
- **Data layer**: End-to-end encryption with Full (Strict) SSL, ensuring that traffic between the user, Cloudflare, and the server is always authenticated and encrypted.

Now, the Cloudflare WAF corresponds to the application layer. It operates at the network edge, filtering requests before forwarding them to the server.

#### 12.1. End-to-End Traffic Filtering Architecture

```text
==========================================================================================
                SECURITY FLOW AND TRAFFIC FILTERING (END-TO-END)
==========================================================================================

   [ INTERNET ]          
        |
        v
+-----------------------+
|  CLOUDFLARE EDGE      |
|                       |
|  1. FIREWALL RULES    |----[ BLOCK ]--> Banned Countries, Malicious IPs,
|     (L3/L4 & L7)      |                    Brute force attacks.
+-----------|-----------+
            |
            v
+-----------|-----------+
|  2. CLOUDFLARE WAF    |----[ FILTERING ]--> SQL Injection, XSS, RCE,
|     (Managed Rules)   |                     Known exploits (CVEs).
+-----------|-----------+
            |
            v
+-----------|-----------+
|  3. PROXY CLOUDFLARE  |----[ PERFORMANCE ]--> Real origin IP secrecy,
|     (CDN & Caching)   |                       Content acceleration.
+-----------|-----------+
            |
            | (SSL Full Strict Cryptography Tunnel)
            v
==========================================================================================
                            LOCAL INFRASTRUCTURE / VPS
==========================================================================================
            |
            v
+-----------|-----------+
|  4. LOCAL FIREWALL    |      [ ENTRANCE POLICY ]
|     (iptables)        |<---  DROP ALL (Standard full blocking)
|                       |<---  ALLOW Cloudflare IPs (Official list)
|                       |<---  ALLOW VPN Admin (Administrative access)
+-----------|-----------+
            |
            v   (Only clean and authenticated traffic)
            |
+-----------|-----------+
|  5. APPLICATION       |      [ FINAL DESTINATION ]
|     (Web Server)      |      Only legitimate requests processing.
+-----------------------+

==========================================================================================
Status: PROTECTED | Layers: 5 | Origin: HIDDEN IP
==========================================================================================
```

> [!WARNING]
> **Attention**: The goal of Cloudflare WAF is not to replace the security of the local firewall, but rather to discard abusive requests as early as possible, saving VPS resources and ensuring that only legitimate requests reach the origin infrastructure.

##### WAF Custom Rules

Edge WAF Custom Rules allows me to create access rules based on request properties such as source IP, country, HTTP headers or even the User Agent.

###### Available Actions

| Action              | Behavior                                                                 |
|---------------------|--------------------------------------------------------------------------|
| Block               | Request is immediately blocked. Client receives an error.                |
| Challenge (JS)      | Client must solve an invisible JavaScript challenge.                     |
| Challenge (Managed) | Cloudflare decides between a JS challenge or CAPTCHA.                    |
| Skip                | Skips subsequent rules (use with caution).                               |
| Log                 | Only logs the request, does not block. Useful for testing rules.         |

In the panel, select my account/domain and proceed to Security → Security rules → Create Custom Rules

Reference to official documentation: https://developers.cloudflare.com/waf/custom-rules/

##### WAF Managed Ruleset

In the panel, just make sure it is ACTIVE in Security → Settings → Cloudflare managed ruleset.

> [!IMPORTANT]
> The default configured rules are safe for deployment in most applications. If I wish to deploy a different set of rules, I will need to change my contracted plan.
>
> However, it is recommended that I do not attempt to micromanage these rules manually unless I have a confirmed false positive; Cloudflare's AI tunnels false positives better than a human in 2026.

- Official documentation reference: https://developers.cloudflare.com/waf/managed-rules/

##### Rate Limiting Rules

In addition to a WAF, Rate Limiting helps protect against brute-force and Layer 7 DDoS attacks.

The goal is to limit the number of requests a single IP can make to a specific endpoint in a given period of time.

In the panel, select my account/domain and proceed to Security → Security rules → Create Rate Limiting Rules.

- Official Documentation Reference: https://developers.cloudflare.com/waf/rate-limiting-rules/

##### Rules Precedence Order

For the resources presented, Cloudflare processes traffic in this order:
1. Firewall Rules (Custom Rules)
2. WAF Managed Rules
3. Rate Limiting Rules

The first matching rule is applied. I have to plan my rules considering this order.

I can simulate an HTTP request to understand the impact of the rules defined in Rules → Trace:

- Official Documentation Reference: https://developers.cloudflare.com/rules/trace-request/

#### 12.3. Configure Security Level

Security Level is Cloudflare's first line of automated defense. It is designed to protect customer websites against malicious activity.

##### "I'm Under Attack" (Emergency) Mode

> [!TIP]
> **Use only during an active attack**

Under Attack mode is my "panic button." It activates additional JavaScript checks to validate if the visitor is a human using a real browser.

It may temporarily pause legitimate access for a few seconds and affect analytics metrics (SEO), as indexing bots may also be challenged.

In the dashboard, select my account and domain and proceed to Security → Settings → Security level or quickly to Overview → Quick Actions (right sidebar menu).

- Official documentation reference: https://developers.cloudflare.com/fundamentals/reference/under-attack-mode/

#### 12.4. Creating Custom Rules

Cloudflare uses an expression language to define conditions.

The basic syntax is based on the filter model syntax of the network scanner called Wireshark:

`(field operator value)`

Common fields:
- `ip.src` — Source IP address
- `ip.geoip.country` — Country of origin
- `http.user_agent` — User-Agent of the request
- `http.request.uri.path` — URL path
- `http.request.method` — HTTP method (GET, POST, etc.)

Operators:
- `eq` — equal
- `ne` — not equal
- `contains` — contains
- `in` — is in the list

##### a. Enable geo-blocking

If my target audience is strictly local (e.g., Portugal), blocking traffic from countries known to be sources of automated attacks is a high-impact and low-cost security measure.

| Action                        | Expression                                      | Description                                                                                  |
|-------------------------------|--------------------------------------------------|----------------------------------------------------------------------------------------------|
| Block                         | `(ip.geoip.country in {"CN" "RU" "IR" "KP"})`      | Blocks traffic from countries with a high rate of attacks and botnet activity.         |
| Challenge / Managed Challenge | `(ip.geoip.country in {"UA" "VN" "TR"})`           | Presents a CAPTCHA or managed challenge for countries with suspicious but potentially legitimate traffic. |

> [!IMPORTANT]
> Important: Adjust the rule according to my actual audience. Do not block countries where I have users.

##### b. Block malicious User-Agents

Legitimate HTTP requests always include the User-Agent header. Its absence indicates a primitive bot or an attack tool. Furthermore, bots and scanners frequently use known user-agents:

| Action | Expression | Description |
| :--- | :--- | :--- |
| Block | `(http.user_agent eq "")` | Blocks requests with NO user-agent header |
| Block | `(http.user_agent contains "sqlmap") or`<br>`(http.user_agent contains "nikto") or`<br>`(http.user_agent contains "nmap") or`<br>`(http.user_agent contains "masscan") or`<br>`(http.user_agent contains "zgrab") or`<br>`(http.user_agent eq "BadBot/1.0.2 (+http://bad.bot)")` | Blocks known scanning tools and malicious bot user-agents |

##### c. Brute-force protection on critical endpoints

| Action | Expression | Description |
| :--- | :--- | :--- |
| Block | `(http.request.uri.path contains "/.env") or`<br>`(http.request.uri.path contains "/.git") or`<br>`(http.request.uri.path contains "/wp-login") or`<br>`(http.request.uri.path contains "/wp-admin") or`<br>`(http.request.uri.path contains "/xmlrpc.php") or`<br>`(http.request.uri.path contains "/phpinfo") or`<br>`(http.request.uri.path contains "/phpmyadmin") or`<br>`(http.request.uri.path contains "/adminer")` | Blocks access to files and directories that should never be publicly accessible. |
| Block | `(http.request.uri.path contains "/xmlrpc.php")` | It blocks access to legacy and frequently exploited endpoints, such as WordPress's `xmlrpc.php`, which is a common vector for distributed denial-of-service (DDoS) and brute-force attacks. |

> [!NOTE]
> If I use WordPress or need legitimate access to any of these paths, do not include them in the rule.

- `/.env` — environment variables file (contains secrets)
- `/.git` — exposed git repository (code leak)
- `/wp-login`, `/wp-admin`, `/xmlrpc.php` — WordPress (even if you don't use it, bots test it)
- `/phpinfo` — exposed PHP configuration
- `/phpmyadmin`, `/adminer` — database dashboards

#### 12.5. Create Rate Limiting Rules

For example, if I want to ensure that a legitimate user does not need more than 5 login attempts per minute, use this rule:

| Parameter | Suggested Value | Justification |
|-----------|-----------------|---------------|
| URL       | *mydomain.com/login* | Applies the rule to all variations of the login URL |
| Requests  | 5               | A legitimate user should not need more than 5 login attempts per minute |
| Period    | 60 seconds      | Enough time for a user to attempt login and correct typing errors |
| Action    | Block           | Blocks the IP for 1 hour after exceeding the limit |

Expression: `(http.host contains "mysite.com" and http.request.uri.path contains "/login")`

#### 12.6. Monitoring

The WAF is not a "set it and forget it" solution.

##### a. Monitoring events

In the new dashboard, select my account/domain and proceed to Security → Analytics → (Events tab), review periodically:

&rarr; Weekly: Check for false positives and adjust rules if necessary.<br>
&rarr; Monthly: Review if new managed rules have been added by Cloudflare and evaluate activating them.<br>
&rarr; After incidents: Create specific rules for identified attack patterns.<br>

- Official documentation reference: https://developers.cloudflare.com/security/analytics/

##### b. Monitoring Traffic

In the new dashboard, select my account/domain and proceed to Security → Analytics → (Traffic tab).

The Traffic tab displays information about all HTTP requests received for my domain, including requests not handled by Cloudflare security products.

I can perform several tasks:
&rarr; View the traffic distribution for my domain.<br>
&rarr; Understand which traffic is being mitigated by Cloudflare security products and where unmitigated traffic is being served from (Cloudflare global network or origin server).<br>
&rarr; Analyze suspicious traffic and create Custom Rules based on the applied filters.<br>
&rarr; Find an appropriate rate limit for incoming traffic.<br>

- Official Documentation Reference: https://developers.cloudflare.com/security/analytics/

#### 12.7. Mandatory Tests

From an external machine, test if the rules are working:

##### Test 1: Test blocking of malicious user-agent
```bash
curl -A "sqlmap/1.0" https://mydomain.com
```
🔴 Expected result: Cloudflare error page (403 or blocking page).

##### Test 2: Test blocking of sensitive path (Fetch the HTTP-header only!)
```bash
curl -I https://mydomain.com/.env
```
🔴 Expected result: Cloudflare error page (403 or blocking page).

##### Test 3: Verify if the Proxy is active
```bash
curl -I https://mydomain.com
```
🟢 Expected result: Should return 'Server: cloudflare'

---

[← Phase 4: Cloudflare Proxy & TLS](./04-cloudflare-tls.md) · **Phase 5 of 5** · [Back to Overview →](./00-overview.md)
