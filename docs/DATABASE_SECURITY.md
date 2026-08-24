# Database Security Configuration

This document outlines the database security hardening required for Tier 1 compliance.

## MongoDB Authentication & TLS

### Connection String Format

Production deployments must use one of these formats:

**Recommended (MongoDB Atlas or self-hosted replica set with SRV records):**
```
mongodb+srv://username:password@cluster.example.com/velar?retryWrites=true&w=majority
```

**Self-hosted with TLS:**
```
mongodb://username:password@mongodb.example.com:27017/velar?ssl=true&tlsCAFile=/path/to/ca.pem
```

### Configuration

The backend enforces:
- `MONGODB_REQUIRE_TLS: bool = True` - All connections must use TLS
- `MONGODB_VALIDATE_TLS_CERTIFICATE: bool = True` - Certificate validation is mandatory
- Connection fails fast if URI doesn't include credentials or TLS markers

### Setting Up MongoDB with TLS (Self-Hosted)

1. **Generate TLS Certificates** (using OpenSSL or Let's Encrypt):
   ```bash
   openssl req -new -x509 -days 365 -nodes -out mongodb.crt -keyout mongodb.key
   cat mongodb.key mongodb.crt > mongodb.pem
   chmod 400 mongodb.pem
   ```

2. **Configure MongoDB Server** (`mongod.conf`):
   ```yaml
   net:
     tls:
       mode: requireTLS
       certificateKeyFile: /etc/mongodb/mongodb.pem
       CAFile: /etc/mongodb/ca.pem
   ```

3. **Create MongoDB User with Authentication**:
   ```javascript
   db.createUser({
       user: "velar_app",
       pwd: "STRONG_PASSWORD_HERE",
       roles: [{role: "readWrite", db: "velar"}]
   })
   ```

4. **Update Backend MONGODB_URI** in `.env`:
   ```
   MONGODB_URI=mongodb://velar_app:STRONG_PASSWORD_HERE@mongodb.example.com:27017/velar?ssl=true&tlsCAFile=/etc/ssl/certs/ca.pem
   ```

## Database Encryption at Rest

### MongoDB Enterprise (Recommended)

MongoDB Enterprise Edition supports WiredTiger encryption at rest:

**Configuration** (`mongod.conf`):
```yaml
security:
  encryption:
    engine: "wiredTiger"
    keyFile: "/etc/mongodb/mongodb-keyfile"
    cacheSizeGB: 1
```

**Key Management:**
- Store keyfile with restricted permissions (`chmod 400`)
- Use AWS KMS, HashiCorp Vault, or Azure Key Vault for key management
- Rotate keys quarterly

### MongoDB Community (Field-Level Encryption)

For self-managed encryption on Community Edition:

**Client-Side Field Level Encryption (CSFLE):**
```python
from pymongo import MongoClient
from pymongo.encryption import ClientEncryption
from pymongo.encryption_shared import Algorithm

# Sensitive fields like passwords, API keys, PII should be encrypted
kms_providers = {"aws": {"accessKeyId": ..., "secretAccessKey": ...}}
key_vault_db = client["admin"]
encrypted_client = MongoClient(..., auto_encryption_opts=AutoEncryptionOpts(...))
```

**Fields to Encrypt:**
- `hashed_password` (User collection)
- `token_hash` (RefreshTokens collection) - already hashed, but consider additional encryption
- Any PII fields (email, full_name, addresses, phone numbers)
- API keys and secrets

## Audit Logging

All database operations are logged through `core/audit_logging.py`:
- Authentication events (login, logout, token refresh)
- Data access patterns
- Privilege changes
- Failed access attempts

Configure MongoDB to log all operations:

**mongod.conf:**
```yaml
operationProfiling:
  mode: all
  slowOpThresholdMs: 100
```

## Secret Management

### Current State
Secrets are loaded from `.env` file during startup:
- `MONGODB_URI` - Connection string with credentials
- `JWT_SECRET_KEY` - Token signing key
- `VELAR_API_KEY` - API authentication
- `ADMIN_API_KEY` - Operator-only key

### Production Requirements
1. **Never commit secrets to version control** (.env is in .gitignore)
2. **Use external secret manager** (AWS Secrets Manager, HashiCorp Vault, etc.)
3. **Rotate secrets quarterly** with no downtime using blue-green deployment
4. **Audit all secret access** with CloudTrail/equivalent logging

### Integration with AWS Secrets Manager (Example)

```python
import boto3
import json

def get_secrets():
    client = boto3.client('secretsmanager')
    secret = client.get_secret_value(SecretId='velar/prod')
    return json.loads(secret['SecretString'])
```

Update `core/config.py` to use this pattern instead of `.env`.

## Monitoring & Alerts

### Key Metrics to Monitor
- MongoDB CPU and memory usage
- Slow query performance (>100ms)
- Replication lag (should be <100ms)
- Failed authentication attempts (set alert on >5/minute)
- TLS handshake errors
- Connection pool exhaustion

### Recommended Tools
- MongoDB Cloud (MongoDB Atlas) - includes automated backups, monitoring, alerting
- Prometheus + Grafana for self-hosted
- DataDog or New Relic for enterprise monitoring

## Backup & Disaster Recovery

### Backup Strategy
- **Frequency:** Daily full backups, hourly incremental
- **Retention:** 30 days
- **Storage:** Off-site (AWS S3, Azure Blob, etc.)
- **Encryption:** Encrypted in transit (TLS) and at rest (server-side encryption)
- **Testing:** Monthly restore tests to verify backup integrity

### MongoDB Atlas Automated Backups
- Enabled by default
- 35-day retention period
- Point-in-time recovery
- Encrypted with customer-managed keys

### Self-Hosted Backup
```bash
mongodump --uri "mongodb+srv://username:password@host/velar" \
          --archive=velar-backup.archive \
          --gzip
```

## Compliance & Auditing

### Regular Security Audits
- **Quarterly:** Review access logs, failed authentication attempts
- **Semi-annually:** External security assessment
- **Annually:** Penetration testing of database security

### Logging Configuration
All audit events captured by `core/audit_logging.py`:
- Event type, user ID, device ID, IP address, timestamp
- Stored in `audit_logs` collection with TTL index (365 days)
- Queryable for compliance reporting and incident response

## Incident Response

### Database Breach Procedure
1. **Immediate:** Rotate all credentials (MONGODB_URI, API keys)
2. **Within 1 hour:** Revoke all active refresh tokens (bulk operation in refresh_tokens collection)
3. **Within 4 hours:** Notify affected users
4. **Within 24 hours:** Forensic analysis and patch deployment
5. **Ongoing:** Audit logs review (see `core/audit_logging.py`)

### Commands
```javascript
// Revoke all refresh tokens
db.refresh_tokens.updateMany({}, {$set: {revoked_at: new Date()}})

// View recent authentication events
db.audit_logs.find({event_type: "login_failed"}).sort({timestamp: -1}).limit(100)
```
