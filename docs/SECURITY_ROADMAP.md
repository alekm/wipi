# WiPi Security Hardening Roadmap

This document outlines a phased approach to hardening WiPi security beyond the current frontend-only authentication.

## Current Security Posture (v1.0 - Implemented)

**Authentication:**
- ✅ Frontend password protection (SHA-256 hash)
- ✅ Demo mode (default, read-only)
- ✅ Admin mode (requires password: `Ruckus123!`)

**Access Control:**
- ✅ Conditional UI rendering (hide admin features in demo mode)
- ✅ Route protection (redirect /simulation in demo mode)

**Infrastructure:**
- ✅ Firewall/VPN assumed for network-level security
- ✅ Docker isolation

**Known Limitations:**
- ⚠️ Password hash visible in JavaScript bundle
- ⚠️ API responses expose sensitive data (Ruckus One creds, PSKs)
- ⚠️ No backend authentication
- ⚠️ No audit logging
- ⚠️ No rate limiting

---

## Phase 1: Quick Wins (Low Effort, High Impact)

**Estimated Time:** 1-2 days

### 1.1 API Response Sanitization
**Problem:** GET requests return sensitive data (passwords, API keys) that's visible in browser DevTools.

**Solution:** Redact secrets in read-only endpoints.

```python
# controller/src/api/ruckus_one.py
@router.get("/status")
async def get_status():
    return {
        "config": {
            "tenant_id": config.tenant_id,
            "client_id": config.client_id,
            "client_secret": "***REDACTED***",  # Don't expose
            "enabled": config.enabled
        },
        ...
    }
```

**Files to modify:**
- `controller/src/api/ruckus_one.py` - Redact client_secret
- `controller/src/api/psk_sets.py` - Optionally redact PSK list (show count only)

### 1.2 Security Headers
**Problem:** Missing security headers (CORS, CSP, X-Frame-Options).

**Solution:** Add nginx security headers.

```nginx
# ui/nginx.conf
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
```

**Files to modify:**
- `ui/nginx.conf`

### 1.3 Audit Logging
**Problem:** No visibility into who changed what and when.

**Solution:** Add structured logging for all write operations.

```python
# controller/src/services/audit_log.py (NEW)
def log_action(action: str, user: str, resource: str, details: dict):
    logger.info(f"AUDIT: {action}", extra={
        "action": action,
        "user": user,
        "resource": resource,
        "details": details,
        "timestamp": datetime.utcnow().isoformat()
    })

# Usage in endpoints:
audit_log.log_action("DELETE_PI", "admin", f"pi/{pi_id}", {"hostname": pi.hostname})
```

**Files to create:**
- `controller/src/services/audit_log.py`

**Files to modify:**
- `controller/src/api/pis.py` - Log deletions
- `controller/src/api/ruckus_one.py` - Log config changes
- `controller/src/api/resident_simulation.py` - Log simulation changes

---

## Phase 2: Backend Authentication (Medium Effort, High Impact)

**Estimated Time:** 3-5 days

### 2.1 Session-Based Authentication
**Problem:** Frontend-only auth allows API access if firewall is bypassed.

**Solution:** Add backend session management.

**Architecture:**
```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ POST /api/auth/login {password}
       ▼
┌─────────────────────────────────────┐
│  Controller (FastAPI)               │
│  ┌──────────────────────────────┐  │
│  │ 1. Validate password hash    │  │
│  │ 2. Create session token      │  │
│  │ 3. Store in Redis/memory     │  │
│  │ 4. Return httpOnly cookie    │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
       │
       ▼ Subsequent requests include cookie
┌─────────────────────────────────────┐
│  Middleware validates session       │
│  - Check cookie                     │
│  - Verify session in store          │
│  - Attach user to request           │
└─────────────────────────────────────┘
```

**Implementation Steps:**
1. Add session storage (in-memory dict or Redis)
2. Create `/api/auth/login` endpoint
3. Create `/api/auth/logout` endpoint
4. Create `/api/auth/me` endpoint (check session)
5. Add FastAPI middleware to validate session on write endpoints
6. Update UI to call login endpoint instead of local password check

**Files to create:**
- `controller/src/api/auth.py` - Login/logout endpoints
- `controller/src/middleware/auth.py` - Session validation middleware
- `controller/src/services/session_manager.py` - Session storage

**Files to modify:**
- `ui/src/context/AuthContext.jsx` - Call backend login API
- `ui/src/api/client.js` - Include credentials in fetch requests
- `controller/src/main.py` - Register auth middleware

### 2.2 API Key for Agent-to-Controller Communication
**Problem:** Any Pi on the network can register as an agent.

**Solution:** Require API key for agent registration and heartbeat.

```python
# Agent sends key in header:
headers = {"X-Agent-Api-Key": AGENT_API_KEY}

# Controller validates:
if request.headers.get("X-Agent-Api-Key") != EXPECTED_KEY:
    raise HTTPException(401, "Invalid API key")
```

**Configuration:**
- Generate API key: `openssl rand -hex 32`
- Set in controller: `AGENT_API_KEY` environment variable
- Set in agent: `agent_config.yaml` or environment variable
- Deployment script passes key during Pi setup

**Files to modify:**
- `controller/src/api/pis.py` - Validate key on registration/heartbeat
- `agent/src/main.py` - Include key in requests
- `scripts/deploy-to-pi.sh` - Accept and configure API key

---

## Phase 3: Enhanced Security (Higher Effort)

**Estimated Time:** 5-10 days

### 3.1 Role-Based Access Control (RBAC)
**Problem:** Only two roles (admin/demo) - no granularity.

**Solution:** Define roles with specific permissions.

**Roles:**
- `viewer` - Read-only access to everything
- `operator` - Can start/stop simulation, view configs (no delete/modify)
- `admin` - Full access

**Permissions:**
- `pis.view`, `pis.delete`
- `simulation.view`, `simulation.modify`
- `ruckus_one.view`, `ruckus_one.configure`

**Implementation:**
```python
# Decorator for permission checks
@require_permission("pis.delete")
async def delete_pi(pi_id: str, user: User = Depends(get_current_user)):
    ...
```

### 3.2 Multi-User Support
**Problem:** Single password shared by all admins.

**Solution:** User accounts with individual credentials.

**Database Schema:**
```python
class UserModel:
    id: UUID
    username: str
    password_hash: str  # bcrypt
    role: str  # viewer, operator, admin
    created_at: datetime
    last_login: datetime
```

**Features:**
- User management UI (admin only)
- Individual login credentials
- Audit trail with usernames (not just "admin")

### 3.3 Rate Limiting
**Problem:** No protection against brute force login attempts.

**Solution:** Rate limit authentication endpoints.

```python
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@router.post("/auth/login")
@limiter.limit("5/minute")  # Max 5 attempts per minute
async def login(credentials: LoginRequest):
    ...
```

**Libraries:**
- `slowapi` for FastAPI rate limiting
- Redis for distributed rate limit tracking (multi-instance)

### 3.4 Secrets Management
**Problem:** Sensitive configs (Ruckus One creds, PSKs) stored in SQLite plaintext.

**Solution:** Encrypt sensitive fields in database.

**Options:**
- **Fernet encryption** (Python `cryptography` library)
- **HashiCorp Vault** (overkill for this scale)
- **Age encryption** (simple file-based encryption)

**Implementation:**
```python
from cryptography.fernet import Fernet

# Derive key from master password or env var
cipher = Fernet(ENCRYPTION_KEY)

# Encrypt before storing:
encrypted = cipher.encrypt(client_secret.encode())
db_model.client_secret_encrypted = encrypted

# Decrypt when reading:
decrypted = cipher.decrypt(db_model.client_secret_encrypted)
```

**Files to modify:**
- `controller/src/models/db_models.py` - Add encrypted fields
- `controller/src/services/ruckus_one.py` - Encrypt/decrypt on read/write
- `controller/src/services/psk_manager.py` - Encrypt PSK lists

---

## Phase 4: Advanced Security (Optional)

**Estimated Time:** 10+ days

### 4.1 HTTPS/TLS
**Problem:** All traffic over HTTP (unencrypted).

**Solution:** Enable HTTPS with certificates.

**Options:**
- **Self-signed certificates** (for internal use)
- **Let's Encrypt** (if exposed to internet)
- **Private CA** (for enterprise environments)

**Implementation:**
```bash
# Generate self-signed cert:
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/wipi.key \
  -out /etc/ssl/certs/wipi.crt

# Update nginx config:
server {
    listen 443 ssl;
    ssl_certificate /etc/ssl/certs/wipi.crt;
    ssl_certificate_key /etc/ssl/private/wipi.key;
    ...
}
```

### 4.2 OAuth2/SSO Integration
**Problem:** Separate credentials from corporate identity system.

**Solution:** Integrate with Google OAuth, Okta, Azure AD, etc.

**Libraries:**
- `authlib` for OAuth2 client
- `python-social-auth` for multiple providers

**Use Cases:**
- Enterprise deployments
- Multi-team access
- Centralized user management

### 4.3 Two-Factor Authentication (2FA)
**Problem:** Password alone can be compromised.

**Solution:** Require TOTP (Google Authenticator, Authy) for admin login.

**Libraries:**
- `pyotp` for TOTP generation/validation
- QR code generation for setup

### 4.4 Security Scanning
**Tools to integrate:**
- **Bandit** - Python security linter
- **Safety** - Check dependencies for known vulnerabilities
- **OWASP ZAP** - Web application security scanner
- **Trivy** - Container image vulnerability scanner

**CI/CD Integration:**
```yaml
# .github/workflows/security.yml
- name: Run Bandit
  run: bandit -r controller/ agent/

- name: Check dependencies
  run: safety check

- name: Scan Docker images
  run: trivy image wipi-controller wipi-ui
```

---

## Implementation Priority Matrix

| Feature | Impact | Effort | Priority | Phase |
|---------|--------|--------|----------|-------|
| API Response Sanitization | High | Low | 🔴 Critical | 1 |
| Audit Logging | High | Low | 🔴 Critical | 1 |
| Security Headers | Medium | Low | 🟡 High | 1 |
| Backend Session Auth | High | Medium | 🟡 High | 2 |
| Agent API Key | Medium | Low | 🟡 High | 2 |
| Rate Limiting | Medium | Low | 🟢 Medium | 3 |
| RBAC | Medium | High | 🟢 Medium | 3 |
| Secrets Encryption | High | Medium | 🟢 Medium | 3 |
| Multi-User Support | Low | High | 🔵 Low | 3 |
| HTTPS/TLS | Medium | Medium | 🔵 Low | 4 |
| OAuth2/SSO | Low | High | 🔵 Low | 4 |
| 2FA | Low | Medium | 🔵 Low | 4 |

---

## Compliance Considerations

If you need to meet specific compliance standards:

### SOC 2 Type II
**Requirements:**
- ✅ Audit logging (Phase 1)
- ✅ Access control (Phase 2-3)
- ✅ Encryption at rest (Phase 3)
- ✅ Encryption in transit (Phase 4 - HTTPS)

### HIPAA (if handling PHI)
**Requirements:**
- ✅ Unique user IDs (Phase 3 - Multi-user)
- ✅ Audit trails (Phase 1)
- ✅ Encryption (Phase 3-4)
- ✅ Access controls (Phase 2-3)
- ✅ Session timeout (Phase 2)

### PCI DSS (if handling payment data)
**Note:** WiPi should **never** handle payment card data. Keep systems separate.

---

## Quick Start: Implement Phase 1 This Week

**Day 1:** API Response Sanitization (2 hours)
- Redact secrets in GET /api/ruckus_one/status
- Redact PSK list (show count only)

**Day 2:** Security Headers (1 hour)
- Update nginx.conf with headers
- Test with security header checker

**Day 3:** Audit Logging (4 hours)
- Create audit_log.py service
- Add logging to Pi deletion
- Add logging to Ruckus One config changes
- Add logging to simulation changes

**Day 4-5:** Testing and Documentation
- Test all changes
- Update CLAUDE.md with security practices
- Document audit log format

---

## Resources

**Learning:**
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security Guide](https://fastapi.tiangolo.com/tutorial/security/)
- [React Security Best Practices](https://snyk.io/learn/react-security/)

**Tools:**
- [Mozilla Observatory](https://observatory.mozilla.org/) - Test security headers
- [SecurityHeaders.com](https://securityheaders.com/) - Check headers
- [Qualys SSL Labs](https://www.ssllabs.com/ssltest/) - Test TLS config (Phase 4)

**Libraries:**
- `passlib` - Password hashing (bcrypt)
- `python-jose` - JWT tokens
- `cryptography` - Encryption
- `slowapi` - Rate limiting

---

## Questions to Consider

Before implementing security changes, answer:

1. **Threat Model:**
   - Who are the attackers? (External hackers? Malicious insiders? Curious employees?)
   - What are they trying to access? (Ruckus One creds? PSK sets? System control?)
   - What's the impact of a breach? (Downtime? Data leak? Compliance violation?)

2. **Compliance:**
   - Any regulatory requirements? (SOC 2, HIPAA, PCI, FedRAMP?)
   - Industry standards? (ISO 27001, NIST?)

3. **User Experience:**
   - How often do admins need access?
   - Can they tolerate 2FA?
   - Shared credentials OK or individual accounts needed?

4. **Operations:**
   - Who manages user accounts?
   - Password reset process?
   - Session timeout acceptable?

5. **Infrastructure:**
   - Can you add Redis for sessions?
   - HTTPS certificates available?
   - Backup/recovery for encrypted data?

---

## Next Steps

1. ✅ Review this roadmap
2. ✅ Determine which phases apply to your use case
3. ✅ Implement Phase 1 (Quick Wins)
4. 🔄 Reassess threat model
5. 🔄 Implement Phase 2 if needed
6. 🔄 Iterate based on requirements

**Last Updated:** 2026-02-11
