# Cloudflare Setup Guide for TotalReclaw Server

## Overview

Cloudflare sits in front of the Caddy reverse proxy and provides:
- DDoS mitigation
- Bot detection and blocking
- WAF (Web Application Firewall) rules
- Edge rate limiting
- IP reputation filtering
- Origin IP hiding

Architecture: `Client -> Cloudflare -> Caddy (TLS) -> FastAPI`

---

## 1. DNS Setup

1. Add your domain to Cloudflare (e.g., `api.totalreclaw.dev`)
2. Set the A record to point to your server IP
3. **Enable Proxy mode** (orange cloud icon) -- this routes traffic through Cloudflare
4. Set TTL to "Auto"

```
Type: A
Name: api
Content: <your-server-ip>
Proxy: ON (orange cloud)
TTL: Auto
```

**CRITICAL:** With proxy mode enabled, Cloudflare hides your origin IP. Direct requests to the origin IP will be blocked by Caddy (wrong hostname).

---

## 2. SSL/TLS Configuration

1. Go to SSL/TLS > Overview
2. Set SSL mode to **Full (Strict)**
   - This means: Client -> Cloudflare (TLS) -> Caddy (TLS with valid cert)
   - Caddy auto-provisions a Let's Encrypt certificate
   - Full (Strict) validates the origin certificate
3. Enable **Always Use HTTPS** under SSL/TLS > Edge Certificates
4. Set Minimum TLS Version to **TLS 1.2**
5. Enable **TLS 1.3**

---

## 3. WAF Rules

### 3.1 Managed Rules (Free Tier)

1. Go to Security > WAF > Managed Rules
2. Enable **Cloudflare Managed Ruleset** (free tier includes basic rules)
3. Enable **OWASP Core Ruleset** if available on your plan

### 3.2 Custom WAF Rules

Create these custom rules under Security > WAF > Custom Rules:

**Rule 1: Block non-API paths**
```
Expression: not (
    http.request.uri.path eq "/" or
    http.request.uri.path eq "/health" or
    http.request.uri.path eq "/ready" or
    http.request.uri.path eq "/metrics" or
    http.request.uri.path eq "/v1/register" or
    http.request.uri.path eq "/v1/store" or
    http.request.uri.path eq "/v1/search" or
    http.request.uri.path eq "/v1/export" or
    http.request.uri.path eq "/v1/account" or
    http.request.uri.path eq "/v1/sync" or
    http.request.uri.path eq "/v1/relay/sponsor" or
    http.request.uri.path matches "^/v1/relay/status/.*$" or
    http.request.uri.path eq "/v1/relay/webhook/pimlico" or
    http.request.uri.path eq "/v1/billing/checkout" or
    http.request.uri.path eq "/v1/billing/checkout/crypto" or
    http.request.uri.path eq "/v1/billing/webhook/stripe" or
    http.request.uri.path eq "/v1/billing/webhook/coinbase" or
    http.request.uri.path eq "/v1/billing/status"
)
Action: Block
```

**Rule 2: Block non-JSON content types on POST**
```
Expression: (
    http.request.method eq "POST" and
    not http.request.headers["content-type"] contains "application/json"
)
Action: Block
```

**Rule 3: Require Authorization header on protected endpoints**
```
Expression: (
    http.request.uri.path in {"/v1/store" "/v1/search" "/v1/export" "/v1/account" "/v1/sync" "/v1/relay/sponsor" "/v1/billing/checkout" "/v1/billing/checkout/crypto" "/v1/billing/status"} and
    not any(http.request.headers["authorization"][*] contains "Bearer")
)
Action: Block
```

---

## 4. Rate Limiting

Create rate limiting rules under Security > WAF > Rate Limiting Rules:

**Rule 1: Registration abuse**
```
Expression: http.request.uri.path eq "/v1/register"
Rate: 5 requests per 1 minute
Per: IP
Action: Block for 10 minutes
```

**Rule 2: General API abuse**
```
Expression: http.request.uri.path in {"/v1/store" "/v1/search"}
Rate: 300 requests per 1 minute
Per: IP
Action: Block for 5 minutes
```

**Rule 3: Export abuse**
```
Expression: http.request.uri.path eq "/v1/export"
Rate: 10 requests per 1 minute
Per: IP
Action: Block for 10 minutes
```

---

## 5. Bot Protection

1. Go to Security > Bots
2. Enable **Bot Fight Mode** (free tier)
3. Set **Challenge Solve Rate** threshold (if available on your plan)
4. Under Firewall Rules, add:

**Block known bad bots:**
```
Expression: cf.bot_management.score lt 10
Action: Block
```

(Note: Bot Management requires a paid plan. Bot Fight Mode is free.)

---

## 6. DDoS Protection

1. Go to Security > DDoS
2. DDoS protection is **automatic** on all Cloudflare plans (including free)
3. Review and accept the default DDoS rules
4. Optionally customize sensitivity level:
   - HTTP DDoS: High sensitivity recommended for API servers
   - L3/L4 DDoS: Default settings are usually sufficient

---

## 7. Page Rules (Optional)

Create page rules under Rules > Page Rules:

**Cache bypass for API:**
```
URL: api.totalreclaw.dev/*
Setting: Cache Level = Bypass
```

(API responses should never be cached by Cloudflare since they contain user-specific encrypted data.)

---

## 8. Origin IP Hiding

1. **Never publish your origin IP** in DNS records, emails, or documentation
2. Use Cloudflare proxy on all DNS records (orange cloud)
3. Configure Caddy to only accept connections from Cloudflare IP ranges:
   - See: https://www.cloudflare.com/ips/

---

## 9. Secret Rotation Procedure

If origin IP is leaked:
1. Provision a new server with a new IP
2. Update Cloudflare DNS A record
3. Decommission old server
4. Rotate database credentials (see server/.env.example)

---

## 10. Verification Checklist

- [ ] DNS A record points to server IP with proxy ON
- [ ] SSL mode is Full (Strict)
- [ ] Always Use HTTPS is enabled
- [ ] WAF managed rules are enabled
- [ ] Custom WAF rules are active
- [ ] Rate limiting rules are active
- [ ] Bot Fight Mode is enabled
- [ ] DDoS protection is active (automatic)
- [ ] Cache is bypassed for API routes
- [ ] Origin IP is hidden (test with `dig` -- should show Cloudflare IPs)
