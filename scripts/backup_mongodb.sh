#!/bin/bash
#
# MongoDB Backup Script with GPG Encryption
# Backs up MongoDB and optionally encrypts with GPG or KMS
# Usage: ./backup_mongodb.sh [--encrypt] [--kms-key-id KEY_ID]
#

set -euo pipefail

# Configuration (override via environment variables)
MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
ENCRYPT_BACKUPS="${ENCRYPT_BACKUPS:-false}"
KMS_KEY_ID="${KMS_KEY_ID:-}"
GPG_RECIPIENT="${GPG_RECIPIENT:-}"
LOG_FILE="${LOG_FILE:-./backups.log}"

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --encrypt)
            ENCRYPT_BACKUPS="true"
            shift
            ;;
        --kms-key-id)
            KMS_KEY_ID="$2"
            shift 2
            ;;
        --gpg-recipient)
            GPG_RECIPIENT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Timestamp for this backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="velar_backup_${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Starting MongoDB backup..." | tee -a "$LOG_FILE"

# Create backup dump
if ! mongodump --uri="$MONGODB_URI" --out="$BACKUP_PATH"; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: mongodump failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "[$(date +'%Y-%m-%d %H:%M:%S')] MongoDB dump completed to $BACKUP_PATH" | tee -a "$LOG_FILE"

# Create tar archive
ARCHIVE_PATH="${BACKUP_PATH}.tar.gz"
if ! tar -czf "$ARCHIVE_PATH" -C "$BACKUP_DIR" "$BACKUP_NAME"; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: tar compression failed" | tee -a "$LOG_FILE"
    rm -rf "$BACKUP_PATH"
    exit 1
fi

rm -rf "$BACKUP_PATH"
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Compressed backup to $ARCHIVE_PATH" | tee -a "$LOG_FILE"

# Encrypt if requested
if [ "$ENCRYPT_BACKUPS" = "true" ]; then
    if [ -n "$KMS_KEY_ID" ]; then
        # AWS KMS encryption
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] Encrypting with AWS KMS key $KMS_KEY_ID..." | tee -a "$LOG_FILE"

        # Encrypt the archive (requires AWS CLI and KMS permissions)
        if command -v aws &> /dev/null; then
            ENCRYPTED_PATH="${ARCHIVE_PATH}.kms"
            if aws kms encrypt \
                --key-id "$KMS_KEY_ID" \
                --plaintext "fileb://${ARCHIVE_PATH}" \
                --output text \
                --query CiphertextBlob | base64 -d > "$ENCRYPTED_PATH"; then
                rm "$ARCHIVE_PATH"
                ARCHIVE_PATH="$ENCRYPTED_PATH"
                echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup encrypted with KMS" | tee -a "$LOG_FILE"
            else
                echo "[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: KMS encryption failed, backup not encrypted" | tee -a "$LOG_FILE"
            fi
        else
            echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: AWS CLI not found" | tee -a "$LOG_FILE"
            exit 1
        fi
    elif [ -n "$GPG_RECIPIENT" ]; then
        # GPG encryption
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] Encrypting with GPG key $GPG_RECIPIENT..." | tee -a "$LOG_FILE"

        if ! gpg --encrypt --recipient "$GPG_RECIPIENT" --output "${ARCHIVE_PATH}.gpg" "$ARCHIVE_PATH"; then
            echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: GPG encryption failed" | tee -a "$LOG_FILE"
            exit 1
        fi
        rm "$ARCHIVE_PATH"
        ARCHIVE_PATH="${ARCHIVE_PATH}.gpg"
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup encrypted with GPG" | tee -a "$LOG_FILE"
    else
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: --encrypt specified but no KMS_KEY_ID or GPG_RECIPIENT provided" | tee -a "$LOG_FILE"
        exit 1
    fi
fi

# Calculate backup size
BACKUP_SIZE=$(du -h "$ARCHIVE_PATH" | cut -f1)
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup completed: $ARCHIVE_PATH ($BACKUP_SIZE)" | tee -a "$LOG_FILE"

# Cleanup old backups (older than RETENTION_DAYS)
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Cleaning up backups older than $RETENTION_DAYS days..." | tee -a "$LOG_FILE"

if command -v find &> /dev/null; then
    DELETED_COUNT=$(find "$BACKUP_DIR" -name "velar_backup_*.tar.gz*" -mtime "+$RETENTION_DAYS" -type f -delete | wc -l)
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Deleted $DELETED_COUNT old backups" | tee -a "$LOG_FILE"
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: find command not available, skipping cleanup" | tee -a "$LOG_FILE"
fi

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup process completed successfully" | tee -a "$LOG_FILE"
