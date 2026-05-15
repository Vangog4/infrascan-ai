# Anti-Spam Middleware Specification
**Version:** 1.0  
**Date:** 2026-04-30  
**Status:** Implemented

---

## Problem Statement

Telegram bots face several categories of abuse:
- **Flood attacks** — rapid repeated messages from one user
- **Bot impersonation** — automated clients sending high-frequency requests
- **Content spam** — repeated identical messages or links
- **New-account abuse** — freshly created accounts used for bulk spam

---

## Best Practices (2024 research)

### 1. Rate Limiting (Token Bucket / Sliding Window)
- Allow burst of N messages, then throttle per-user
- Standard thresholds: **5 messages / 5 seconds** per user
- Cooldown period after violation: 30–60 seconds
- Per-chat limits for group bots: **20 messages / minute**

### 2. User Reputation Signals
- Account age < 7 days → higher suspicion weight
- No username + no profile photo → flag for extra scrutiny
- Premium users generally lower risk (paid verification)

### 3. Content Deduplication
- Hash of message text; reject if same hash seen within N seconds
- Applies to media captions too
- Window: 30 seconds, threshold: 3 identical messages

### 4. Command Abuse
- Rate-limit `/start` specifically (most abused): 3 per hour per user
- Ignore `/start` from forwarded messages (bot farm pattern)

### 5. Response Strategy
- **Silent drop** preferred over ban error (denies feedback to spammers)
- Log all drops for analysis
- Temporary cooldown (not permanent ban) for first offense
- Notify admins only on repeated/severe violations

### 6. External References
- [aiogram-throttling cookbook](https://docs.aiogram.dev/en/latest/dispatcher/middlewares.html)
- Telegram Bot API: `getChatMember` for join-date signals
- OWASP Bot Security Cheat Sheet (2024)

---

## Implementation Design

### Middleware: `RateLimitMiddleware`

```
User message → RateLimitMiddleware
                ├─ check user in cooldown? → DROP (silent)
                ├─ increment user counter
                ├─ counter > threshold? → set cooldown, DROP
                └─ pass to next handler
```

**Storage:** in-process `dict` (TTL-based); swap for Redis in production.

**Parameters (configurable via env):**

| Param | Default | Description |
|---|---|---|
| `RATELIMIT_MESSAGES` | 5 | max messages per window |
| `RATELIMIT_WINDOW` | 5 | window size in seconds |
| `RATELIMIT_COOLDOWN` | 30 | cooldown after violation (seconds) |

### Middleware: `ContentDedupeMiddleware`

Hash (SHA-256 truncated to 8 bytes) of `message.text`.  
Reject if same hash seen from same user within 30 seconds.

---

## Out of Scope (v1)

- ML-based content classification
- Cross-bot shared blocklist
- Captcha challenges
- Permanent bans (admin action only)
