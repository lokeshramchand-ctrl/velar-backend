# Backup and Retention Management

This guide covers backup procedures, encryption, and automated data retention/deletion.

## Automated Backups

### MongoDB Backup Script

The `scripts/backup_mongodb.sh` script provides automated MongoDB backup with optional encryption.

#### Basic Usage

```bash
# Standard unencrypted backup (daily via cron)
./scripts/backup_mongodb.sh

# Encrypt backup with GPG
ENCRYPT_BACKUPS=true GPG_RECIPIENT="ops@velar.com" ./scripts/backup_mongodb.sh

# Encrypt backup with AWS KMS
ENCRYPT_BACKUPS=true KMS_KEY_ID="arn:aws:kms:us-east-1:123456789:key/12345" ./scripts/backup_mongodb.sh
```

#### Configuration

Environment variables control backup behavior:

- `MONGODB_URI`: MongoDB connection string (default: `mongodb://localhost:27017`)
- `BACKUP_DIR`: Directory to store backups (default: `./backups`)
- `RETENTION_DAYS`: Days to retain backups (default: 30)
- `ENCRYPT_BACKUPS`: Enable encryption (`true`/`false`, default: `false`)
- `KMS_KEY_ID`: AWS KMS key ID for encryption
- `GPG_RECIPIENT`: GPG key recipient for encryption (email or key ID)
- `LOG_FILE`: Path to backup log (default: `./backups.log`)

#### Scheduling with Cron

Add to crontab to run daily encrypted backups:

```bash
# Daily backup at 2 AM with KMS encryption
0 2 * * * cd /opt/velar && ENCRYPT_BACKUPS=true KMS_KEY_ID="arn:aws:kms:..." ./scripts/backup_mongodb.sh >> /var/log/velar-backup.log 2>&1
```

#### Docker Compose Setup

For production, create a backup service or sidecar:

```yaml
velar-backup:
  image: mongo:latest
  entrypoint: /bin/bash
  command:
    - -c
    - |
      while true; do
        mongodump --uri="mongodb://velar-backend:27017" --out=/backups/dump_$(date +%s)
        tar -czf /backups/dump_$(date +%s).tar.gz -C /backups dump_$(date +%s)
        find /backups -name 'dump_*' -mtime +30 -delete
        sleep 86400
      done
  volumes:
    - backup_volume:/backups
  depends_on:
    - mongodb
```

#### Restore from Backup

To restore a backup:

```bash
# Extract backup
tar -xzf velar_backup_20240101_120000.tar.gz

# Restore to MongoDB
mongorestore --uri="mongodb://localhost:27017" ./velar_backup_20240101_120000/velar/

# If encrypted with GPG:
gpg --decrypt velar_backup_20240101_120000.tar.gz.gpg > backup.tar.gz
tar -xzf backup.tar.gz
mongorestore --uri="mongodb://localhost:27017" ./velar_backup_20240101_120000/velar/

# If encrypted with AWS KMS:
aws kms decrypt --ciphertext-blob fileb://velar_backup_20240101_120000.tar.gz.kms --output text --query Plaintext | base64 -d > backup.tar.gz
tar -xzf backup.tar.gz
mongorestore --uri="mongodb://localhost:27017" ./velar_backup_20240101_120000/velar/
```

## Automated Retention and Deletion

The backend includes a `RetentionManager` that handles automatic cleanup of expired data.

### Data Retention Policies

| Data Type | Retention Period | Policy |
|-----------|------------------|--------|
| PDFs | `PDF_RETENTION_DAYS` (default: 90) | Auto-deleted via MongoDB TTL or scheduled job |
| Audit Logs | 90 days | Auto-deleted via scheduled job |
| Request Nonces | 5 minutes (TTL) | Auto-deleted via MongoDB TTL index |
| Revoked Refresh Tokens | 7 days | Auto-deleted via scheduled job |
| User Data | Indefinite (soft-delete only) | Never auto-deleted; admins control retention |

### Triggering Cleanup

#### Manual Cleanup via Admin API

Trigger cleanup immediately:

```bash
curl -X POST https://api.velar.local/admin/retention/cleanup \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "X-Velar-Admin-Key: <ADMIN_API_KEY>" \
  -H "X-Velar-API-Key: <VELAR_API_KEY>"
```

Response:

```json
{
  "status": "success",
  "message": "Retention cleanup completed",
  "results": {
    "pdfs_deleted": 42,
    "audit_logs_deleted": 1234,
    "nonces_deleted": 5678,
    "revoked_tokens_deleted": 89
  }
}
```

#### Scheduled Cleanup via Cron

Add a cron job to trigger cleanup daily:

```bash
# Daily cleanup at 3 AM
0 3 * * * curl -X POST https://api.velar.local/admin/retention/cleanup \
  -H "Authorization: Bearer $(cat /etc/velar/admin_token)" \
  -H "X-Velar-Admin-Key: $(cat /etc/velar/admin_key)" \
  -H "X-Velar-API-Key: $(cat /etc/velar/api_key)"
```

### Automatic TTL-Based Cleanup

MongoDB TTL indexes automatically delete documents when they expire:

- **Request Nonces**: `request_nonces` collection has TTL index on `expires_at` (5 minutes)
- **Refresh Tokens** (Optional): Can add TTL index to `refresh_tokens` for non-revoked tokens

To add TTL index for refresh tokens:

```javascript
db.refresh_tokens.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 })
```

This automatically deletes tokens after their `expires_at` time.

## Compliance and Data Protection

### GDPR/Data Retention

- **User Requests**: Implement data subject access request (DSAR) flow to export user data
- **Soft Deletion**: User accounts are marked `is_active=False` rather than hard-deleted for audit trail
- **Hard Deletion**: Implement hard-delete flow for users who request complete data removal
- **Data Minimization**: PDFs auto-delete after retention period; audit logs retained for compliance

### Backup Encryption

All backups should be encrypted:

- **At Rest**: Encrypt backup files with GPG or AWS KMS
- **In Transit**: Use TLS for backup transfers (sftp, S3, etc.)
- **Key Management**: Store encryption keys separately from backups

### Testing Restores

Regularly test backup restore procedures to ensure RPO/RTO targets:

```bash
# Test restore to a temporary MongoDB instance
docker run -d -p 27018:27017 --name test-mongo mongo:latest
mongorestore --uri="mongodb://localhost:27018" <backup_path>
# Run smoke tests
docker stop test-mongo
```

## Monitoring

### Backup Logs

Monitor backup script logs for failures:

```bash
# Follow backup logs
tail -f backups.log

# Check for errors
grep -i "error" backups.log

# Report on backup sizes
du -h backups/
```

### Audit Logs

Query audit logs for retention/deletion events:

```bash
# In MongoDB shell
db.audit_logs.find({
  event_type: "ADMIN_ACTION",
  "details.activity": "retention_cleanup"
}).sort({ timestamp: -1 }).limit(10)
```

### Metrics

Expose backup metrics via Prometheus:

- `backup_size_bytes`: Size of latest backup
- `backup_duration_seconds`: Time taken for backup
- `backup_timestamp`: Unix timestamp of latest backup
- `retention_cleanup_items_deleted`: Count of items deleted in cleanup
