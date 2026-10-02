#!/usr/bin/env python3
"""Builds platform-dark.svg / platform-light.svg: the whole zero-trust-vps-platform
(Cases 01-04) in one data-flow diagram.

Layout: trust zones are columns, planes are rows (data plane, management plane),
plus an offsite strip for backups. Each component carries a tag with the case
that built it; Case 04 is drawn dashed because it is still in progress.
Claims stay at what the published repo and the running server both support.

Usage: python3 build_platform_diagram.py [dark|light]   (default: dark)"""
import sys
from pathlib import Path

THEME = sys.argv[1] if len(sys.argv) > 1 else "dark"
if THEME not in ("dark", "light"):
    sys.exit("usage: build_platform_diagram.py [dark|light]")

W, H = 1920, 1350
SANS = "'Liberation Sans', Arial, Helvetica, sans-serif"
MONO = "'DejaVu Sans Mono', 'Liberation Mono', monospace"

if THEME == "dark":
    INK, MUTED, PAPER = "#e6edf3", "#8d99a8", "#0b1016"
    RED, TEAL, DATA, VIOLET = "#ff6b5e", "#3fd18a", "#5cc8e0", "#b197fc"
    BOX_FILL, BODY, NOTE_FILL, NOTE_TEXT = "#111821", "#c9d3df", "#161b22", "#b9c2cd"
    BADGE_TEXT, RULE, DOTS = "#0b1016", "#3a4554", "#1c2633"
    ZONES = {  # band fill, border/label, box header
        "untrusted": ("#170f12", "#ff7a6b", "#3a1b1e"),
        "edge": ("#171309", "#f0a640", "#3a2a10"),
        "host": ("#0d1420", "#6ea8ff", "#15284a"),
        "origin": ("#0c1712", "#4fd18b", "#113322"),
        "admin": ("#0c1817", TEAL, "#103a2c"),
        "offsite": ("#130f1d", VIOLET, "#2a2142"),
    }
else:
    INK, MUTED, PAPER = "#1d2330", "#5a6272", "#fbfaf6"
    RED, TEAL, DATA, VIOLET = "#b3362c", "#1d7d7e", "#1f6f8b", "#6b4fc8"
    BOX_FILL, BODY, NOTE_FILL, NOTE_TEXT = "#ffffff", "#2a3140", "#fffdf1", "#3a404c"
    BADGE_TEXT, RULE, DOTS = "#ffffff", "#1d2330", None
    ZONES = {
        "untrusted": ("#fcefec", "#c0503f", "#f6d6cf"),
        "edge": ("#fff5e6", "#b86d12", "#fadfb8"),
        "host": ("#edf2fb", "#3f68ad", "#d0def4"),
        "origin": ("#ecf6ef", "#347f58", "#cbe6d5"),
        "admin": ("#e6f4f4", TEAL, "#c6e6e6"),
        "offsite": ("#f4f0fd", VIOLET, "#e3dafa"),
    }
COLORS = {"data": DATA, "admin": TEAL, "block": RED, "backup": VIOLET}

out = []
add = out.append


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=15, weight="normal", fill=INK, anchor="start",
         style="normal", family=SANS, halo=False, spacing=0, rotate=None):
    extra = (f' paint-order="stroke" stroke="{PAPER}" stroke-width="5" '
             f'stroke-linejoin="round"') if halo else ""
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    rot = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" font-style="{style}" fill="{fill}" '
        f'text-anchor="{anchor}"{sp}{extra}{rot}>{esc(s)}</text>')


HDR, LINE, PAD = 54, 22, 14


def box_height(sections):
    return HDR + sum(PAD + LINE * len(sec) for sec in sections) + 6


def case_tag(x, y, w, label, color):
    pw = 14 + 7.5 * len(label)
    px = x + w - 8 - pw
    add(f'<rect x="{px}" y="{y + 8}" width="{pw}" height="20" rx="10" fill="{PAPER}" '
        f'stroke="{color}" stroke-width="1.2"/>')
    text(px + pw / 2, y + 22.5, label, 11.5, "bold", color, "middle", family=MONO)


def box(x, y, w, stereo, title, sections, key, h=None, case=None, dashed=False):
    """UML-style box: «stereotype» + name, then compartments. A line that
    starts with '#' is a bold compartment heading."""
    total = h or box_height(sections)
    edge = ZONES[key][1]
    da = ' stroke-dasharray="7 5"' if dashed else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{total}" rx="7" fill="{BOX_FILL}" '
        f'stroke="{edge}" stroke-width="1.6"{da}/>')
    add(f'<path d="M{x},{y+HDR} L{x},{y+7} Q{x},{y} {x+7},{y} L{x+w-7},{y} '
        f'Q{x+w},{y} {x+w},{y+7} L{x+w},{y+HDR} Z" fill="{ZONES[key][2]}" '
        f'fill-opacity="{0.55 if dashed else 1}" stroke="{edge}" stroke-width="1.6"{da}/>')
    text(x + w / 2, y + 20, f"«{stereo}»", 13, "normal", MUTED, "middle", "italic")
    text(x + w / 2, y + 43, title, 18, "bold", edge, "middle")
    if case:
        case_tag(x, y, w, case, edge)
    cy = y + HDR
    for i, sec in enumerate(sections):
        if i:
            add(f'<line x1="{x}" y1="{cy}" x2="{x+w}" y2="{cy}" stroke="{edge}" stroke-width="1.2"{da}/>')
        ly = cy + PAD + 12
        for ln in sec:
            if ln.startswith("#"):
                text(x + 16, ly, ln[1:], 15, "bold", INK)
            else:
                text(x + 16, ly, ln, 15, "normal", BODY)
            ly += LINE
        cy += PAD + LINE * len(sec)
    return total


def arrow(pts, kind="data", dash=None, width=None):
    dasharray = dash or {"data": "", "admin": "9 6", "block": "8 6", "backup": "6 5"}[kind]
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    da = f' stroke-dasharray="{dasharray}"' if dasharray else ""
    sw = width or (2.8 if kind == "data" else 2.4)
    add(f'<path d="{d}" fill="none" stroke="{COLORS[kind]}" stroke-width="{sw}"{da} '
        f'marker-end="url(#ah-{kind})"/>')


def badge(x, y, n, kind="data"):
    r = 15 if len(str(n)) > 1 else 14
    add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{COLORS[kind]}" stroke="{PAPER}" stroke-width="2.5"/>')
    text(x, y + 5, str(n), 13, "bold", BADGE_TEXT, "middle")


def note(x, y, w, lines):
    fold, h = 16, 18 + 19 * len(lines)
    add(f'<path d="M{x},{y} L{x+w-fold},{y} L{x+w},{y+fold} L{x+w},{y+h} L{x},{y+h} Z" '
        f'fill="{NOTE_FILL}" stroke="{MUTED}" stroke-width="1.3"/>')
    add(f'<path d="M{x+w-fold},{y} L{x+w-fold},{y+fold} L{x+w},{y+fold}" fill="none" '
        f'stroke="{MUTED}" stroke-width="1.3"/>')
    ly = y + 23
    for ln in lines:
        text(x + 13, ly, ln, 14, "normal", NOTE_TEXT, style="italic")
        ly += 19


def flow_final(cx, cy, r=17):
    """UML activity flow-final node: the packet's path ends here."""
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{BOX_FILL}" stroke="{RED}" stroke-width="2.4"/>')
    k = r * 0.62
    add(f'<path d="M{cx-k},{cy-k} L{cx+k},{cy+k} M{cx+k},{cy-k} L{cx-k},{cy+k}" '
        f'stroke="{RED}" stroke-width="2.4" stroke-linecap="round"/>')


# ------------------------------------------------------------------ canvas
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add("<defs>")
for kind, color in COLORS.items():
    add(f'<marker id="ah-{kind}" viewBox="0 0 12 12" refX="10.5" refY="6" markerWidth="10" '
        f'markerHeight="10" orient="auto-start-reverse"><path d="M1,1 L11.5,6 L1,11 L4,6 Z" '
        f'fill="{color}"/></marker>')
if DOTS:
    add('<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
        f'<circle cx="2" cy="2" r="1.1" fill="{DOTS}"/></pattern>')
add("</defs>")
add(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
if DOTS:
    add(f'<rect width="{W}" height="{H}" fill="url(#dots)"/>')

# title block
text(40, 62, "Zero-Trust Linux VPS Platform", 38, "bold", DATA, family=MONO)
text(40, 94, "Case 01 · Perimeter & zero-trust admin   |   Case 02 · Container platform & ingress   |   "
     "Case 03 · VPN-only observability   |   Case 04 · Backups & recovery (in progress)",
     17, "normal", MUTED)
text(1880, 60, "Gabriel Affonso", 19, "bold", INK, "end")
text(1880, 86, "Linux System Administrator · Porto", 15, "normal", MUTED, "end")
add(f'<line x1="40" y1="112" x2="1880" y2="112" stroke="{RULE}" stroke-width="1.4"/>')

# ------------------------------------------------------------------ grid
BAND_TOP, BAND_BOT = 124, 1080
ROW_SPLIT = 620
COLS = {  # key: (x0, x1, label)
    "untrusted": (90, 390, "UNTRUSTED · INTERNET"),
    "edge": (405, 765, "EDGE · CLOUDFLARE"),
    "host": (780, 1200, "HOST · ALMALINUX VPS"),
    "origin": (1215, 1880, "ORIGIN · DOCKER PLATFORM"),
}
for key, (x0, x1, label) in COLS.items():
    fill, stroke, _ = ZONES[key]
    add(f'<rect x="{x0}" y="{BAND_TOP}" width="{x1-x0}" height="{BAND_BOT-BAND_TOP}" rx="18" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.8" stroke-dasharray="8 6"/>')
    text((x0 + x1) / 2, BAND_TOP + 32, label, 14, "bold", stroke, "middle", spacing=1.6)

add(f'<rect x="90" y="{ROW_SPLIT}" width="1790" height="{BAND_BOT-ROW_SPLIT}" fill="{TEAL}" '
    f'opacity="{0.045 if THEME == "dark" else 0.035}"/>')
add(f'<line x1="90" y1="{ROW_SPLIT}" x2="1880" y2="{ROW_SPLIT}" stroke="{TEAL}" '
    f'stroke-width="2" stroke-dasharray="10 6"/>')

for y0, y1, label, color in ((BAND_TOP, ROW_SPLIT, "DATA PLANE · PUBLIC", INK),
                             (ROW_SPLIT, BAND_BOT, "MANAGEMENT · VPN ONLY", TEAL)):
    add(f'<line x1="66" y1="{y0+12}" x2="66" y2="{y1-12}" stroke="{color}" stroke-width="2"/>')
    text(56, (y0 + y1) / 2, label, 13.5, "bold", color, "middle", spacing=1.6, rotate=-90)

FLOW_Y = 290

# ---------------------------------------------------------- data plane
box(115, 231, 250, "actor", "Web user", [["browser / client", "HTTPS only"]], "untrusted")
box(115, 488, 250, "actor", "Scanner / bot",
    [["direct hits on origin IP", "SSH brute force on :22"]], "untrusted")

cf_h = box(425, 190, 320, "edge", "Cloudflare",
           [["#WAF", "managed + custom rules", "rate limiting"],
            ["#Reverse proxy", "Full (Strict) TLS to origin"]], "edge", case="01")
note(425, 190 + cf_h + 16, 320, ["Origin IP hidden: direct hits are dropped.",
                                 "Cloudflare Tunnel planned (shared-IP gap)."])

ipt_h = box(800, 190, 380, "firewall", "iptables · default DROP",
            [["#DOCKER-USER (FORWARD) · to containers",
              "+ ACCEPT 80/443 ← Cloudflare CIDRs only",
              "+ fails closed · cached Cloudflare list"],
             ["#INPUT · to the host",
              "+ ACCEPT 51820/udp (WireGuard) · all on wg0",
              "+ policy DROP: all other WAN inbound"]], "host", case="01·02")
DROP_Y = 540
add(f'<line x1="840" y1="{190+ipt_h}" x2="840" y2="{DROP_Y-17}" stroke="{RED}" '
    f'stroke-width="1.8" stroke-dasharray="3 4"/>')
text(852, 190 + ipt_h + 40, "default policy", 13.5, "normal", MUTED, style="italic", halo=True)
flow_final(840, DROP_Y)
text(868, DROP_Y + 6, "DROP · no matching rule", 16, "bold", RED)

trf_h = box(1240, 190, 290, "ingress", "Traefik v3",
            [["+ Origin CA cert · TLS 1.2+", "+ HSTS & security headers",
              "+ per-client rate limiting", "+ VPN-only admin routers",
              "+ JSON access log (real client IP)"]], "origin", case="02")
apps_h = box(1570, 220, 290, "container", "Application containers",
             [["network: proxy", "icc off · no-new-privileges", "pinned official images"]],
             "origin", case="02")
db_h = box(1570, 430, 290, "container", "Databases & caches",
           [["per-stack internal network", "no egress · no published ports", "state: /srv/data bind mounts"]],
           "origin", case="02")

arrow([(365, FLOW_Y), (425, FLOW_Y)]); badge(395, FLOW_Y, 1)
arrow([(745, FLOW_Y), (800, FLOW_Y)]); badge(772, FLOW_Y, 2)
arrow([(1180, FLOW_Y), (1240, FLOW_Y)]); badge(1210, FLOW_Y, 3)
arrow([(1530, FLOW_Y), (1570, FLOW_Y)]); badge(1550, FLOW_Y, 4)
arrow([(1715, 220 + apps_h), (1715, 430)]); badge(1715, (220 + apps_h + 430) / 2, 5)
text(1738, (220 + apps_h + 430) / 2 + 5, "internal network", 14, "normal", MUTED, halo=True)

arrow([(365, DROP_Y), (820, DROP_Y)], "block")
text(582, DROP_Y - 12, "direct-to-origin scans · :22 brute force", 14.5, "bold", RED, "middle", halo=True)

# ---------------------------------------------------------- management plane
WG_Y = 640
wg_h = box(800, WG_Y, 380, "vpn", "WireGuard wg0",
           [["10.10.10.1 · UDP 51820 (only admin ingress)"]], "admin", case="01")
MG_Y = WG_Y + wg_h // 2
box(115, MG_Y - 59, 250, "actor", "SysAdmin", [["remote device", "Ed25519 key + VPN peer"]], "admin")
note(425, MG_Y + 34, 320, ["Not proxied by Cloudflare: admin", "traffic never uses the public path."])

ssh_y = WG_Y + wg_h + 22
ssh_h = box(800, ssh_y, 380, "service", "OpenSSH",
            [["Ed25519 keys only · no root · no passwords", "scoped sudo · reachable only via wg0"],
             ["#Fail2ban · second line of defense", "bans IPs if :22 is ever exposed"]], "admin", case="01")
low_y = ssh_y + ssh_h + 16
box(800, low_y, 185, "host view", "Cockpit", [["port 9090", "VPN only"]], "admin", case="03")
restic_h = box(995, low_y, 185, "planned", "Restic", [["nightly timer", "encrypted, to B2"]],
               "offsite", case="04", dashed=True)

ui_h = box(1240, WG_Y, 290, "routers", "VPN-only admin UIs",
           [["Traefik dashboard · Portainer", "Netdata · Grafana · Uptime Kuma",
             "ipAllowList · split-horizon DNS"]], "admin", case="02·03")
loki_h = box(1570, WG_Y, 290, "log pipeline", "Loki + Promtail",
             [["container and host logs", "7-day retention · not published"]], "admin", case="03")
chg_y = WG_Y + loki_h + 20
SSH_MID = chg_y + 59
chg_h = box(1570, chg_y, 290, "process", "Change cycle",
            [["pinned images · changelog-gated", "snapshot → change → rollback"]], "admin", case="02")

arrow([(365, MG_Y), (800, MG_Y)], "admin"); badge(582, MG_Y, "A1", "admin")
text(582, MG_Y - 24, "WireGuard tunnel · UDP 51820", 14, "bold", TEAL, "middle", halo=True)
arrow([(990, WG_Y + wg_h), (990, ssh_y)], "admin"); badge(1018, (WG_Y + wg_h + ssh_y) / 2, "A2", "admin")
arrow([(1180, MG_Y), (1240, MG_Y)], "admin"); badge(1210, MG_Y, "A3", "admin")
arrow([(1495, WG_Y), (1495, 190 + trf_h)], "admin"); badge(1495, 545, "A4", "admin")
text(1478, 537, "routed by", 13.5, "normal", TEAL, "end", style="italic", halo=True)
text(1478, 555, "Traefik", 13.5, "normal", TEAL, "end", style="italic", halo=True)
arrow([(1530, MG_Y + 10), (1570, MG_Y + 10)], "admin")
arrow([(1180, SSH_MID), (1570, SSH_MID)], "admin"); badge(1375, SSH_MID, "A5", "admin")
text(1375, SSH_MID - 24, "operate over SSH", 14, "bold", TEAL, "middle", halo=True)

# ---------------------------------------------------------- offsite strip (Case 04)
OFF_TOP, OFF_BOT = 1092, 1230
fill, stroke, _ = ZONES["offsite"]
add(f'<rect x="90" y="{OFF_TOP}" width="1790" height="{OFF_BOT-OFF_TOP}" rx="18" fill="{fill}" '
    f'stroke="{stroke}" stroke-width="1.8" stroke-dasharray="8 6"/>')
text(116, OFF_TOP + 34, "OFFSITE · BACKBLAZE B2", 14, "bold", stroke, spacing=1.6)
text(116, OFF_TOP + 58, "Case 04 · in progress", 14, "normal", MUTED, style="italic")
text(116, OFF_TOP + 82, "another provider, another account", 14, "normal", MUTED, style="italic")
b2_y = OFF_TOP + 10
box(800, b2_y, 380, "offsite", "Restic repository", [["encrypted client-side · Object Lock 30 days",
                                                      "the server's key can't delete locked versions"]],
    "offsite", case="04", dashed=True)
arrow([(1087, low_y + restic_h), (1087, b2_y)], "backup")
note(1240, OFF_TOP + 22, 620, ["Next: restore runbooks (one file · one app's data · a whole host)",
                               "and three timed recovery drills, published with Case 04."])

# ---------------------------------------------------------- footer
fy = 1246
add(f'<line x1="40" y1="{fy}" x2="1880" y2="{fy}" stroke="{RULE}" stroke-width="1.4"/>')
ly = fy + 30
arrow([(40, ly), (90, ly)]); text(102, ly + 5, "public data flow", 15, "normal", MUTED)
arrow([(262, ly), (312, ly)], "admin"); text(324, ly + 5, "management (VPN only)", 15, "normal", MUTED)
arrow([(530, ly), (580, ly)], "block"); text(592, ly + 5, "blocked / hostile", 15, "normal", MUTED)
arrow([(760, ly), (810, ly)], "backup"); text(822, ly + 5, "backup (planned)", 15, "normal", MUTED)
flow_final(1000, ly, 12); text(1021, ly + 5, "dropped", 15, "normal", MUTED)
badge(1125, ly, 1); text(1148, ly + 5, "sequence", 15, "normal", MUTED)
case_tag(1240, ly - 18, 46, "03", INK); text(1294, ly + 5, "built in Case 03", 15, "normal", MUTED)
add(f'<rect x="1460" y="{ly-10}" width="40" height="20" rx="4" fill="none" stroke="{VIOLET}" '
    f'stroke-width="1.6" stroke-dasharray="6 4"/>')
text(1510, ly + 5, "in progress", 15, "normal", MUTED)


def chip(x, y, label, w):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="30" rx="15" fill="{BOX_FILL}" stroke="{MUTED}" stroke-width="1.3"/>')
    text(x + w / 2, y + 20.5, label, 13.5, "bold", INK, "middle")


chip(40, fy + 56, "CIS Controls v8 · CSC 2–5, 7, 8, 11–13, 16", 360)
chip(414, fy + 56, "NIST CSF 2.0 · Identify · Protect · Detect · Recover", 430)
text(1880, fy + 77, "github.com/gabzaf/zero-trust-vps-platform", 17, "bold", INK, "end")

add("</svg>")

path = Path(__file__).with_name(f"platform-{THEME}.svg")
path.write_text("\n".join(out), encoding="utf-8")
print("wrote", path)
