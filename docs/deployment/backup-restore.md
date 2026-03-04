# TotalReclaw Database Backup & Restore

This guide covers how to back up and restore the TotalReclaw PostgreSQL database.

---

## Quick Reference

```bash
# Create a backup
./scripts/backup.sh

# Create a backup to a specific directory
./scripts/backup.sh /path/to/backups

# Restore from a backup
./scripts/restore.sh backups/totalreclaw_backup_2026-02-24_030000.sql.gz

# Restore without confirmation prompt
./scripts/restore.sh backups/totalreclaw_backup_2026-02-24_030000.sql.gz --force
```

---

## Manual Backups

### Prerequisites

- Docker is installed and running
- The `totalreclaw-db` container is running (`docker-compose up -d`)

### Running a Backup

From the `server/` directory:

```bash
./scripts/backup.sh
```

This will:
1. Run `pg_dump` inside the `totalreclaw-db` Docker container
2. Compress the output with gzip
3. Save it to `server/backups/totalreclaw_backup_YYYY-MM-DD_HHMMSS.sql.gz`
4. Remove old backups beyond the retention limit (default: 7)

### Custom Output Directory

```bash
./scripts/backup.sh /mnt/external/totalreclaw-backups
```

### Custom Retention

Keep the last 30 backups instead of 7:

```bash
BACKUP_RETAIN=30 ./scripts/backup.sh
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTAINER_NAME` | `totalreclaw-db` | Name of the PostgreSQL Docker container |
| `POSTGRES_USER` | `totalreclaw` | Database user |
| `POSTGRES_DB` | `totalreclaw` | Database name |
| `BACKUP_RETAIN` | `7` | Number of backups to keep |

---

## Restoring from Backup

**WARNING: Restore will DROP and recreate the database, destroying all existing data.**

### Running a Restore

```bash
./scripts/restore.sh backups/totalreclaw_backup_2026-02-24_030000.sql.gz
```

You will be prompted to confirm before any data is deleted.

### Skipping Confirmation

For use in scripts or automation:

```bash
./scripts/restore.sh backups/totalreclaw_backup_2026-02-24_030000.sql.gz --force
```

### Supported Formats

- `.sql.gz` -- Gzip-compressed SQL dump (default backup format)
- `.sql` -- Uncompressed SQL dump

### What Restore Does

1. Terminates active connections to the database
2. Drops the existing database
3. Creates a fresh empty database
4. Loads the backup SQL within a single transaction
5. Verifies tables were created successfully

---

## Automated Daily Backups

### Setting Up Cron

1. Copy the example cron configuration:
   ```bash
   cp scripts/backup-cron.example /tmp/totalreclaw-cron
   ```

2. Edit paths to match your installation:
   ```bash
   vim /tmp/totalreclaw-cron
   ```

3. Install the cron job:
   ```bash
   crontab /tmp/totalreclaw-cron
   ```

### Example Cron Entry

Run daily at 3 AM, keep 7 backups:

```
0 3 * * * /home/deploy/totalreclaw/server/scripts/backup.sh /home/deploy/backups >> /var/log/totalreclaw-backup.log 2>&1
```

### Monitoring Cron Backups

Check the log:
```bash
tail -20 /var/log/totalreclaw-backup.log
```

Verify the latest backup exists and has a reasonable size:
```bash
ls -lh /home/deploy/backups/totalreclaw_backup_*.sql.gz | tail -3
```

---

## Backup Retention Policy Recommendations

| Environment | Retention | Frequency | Off-site |
|-------------|-----------|-----------|----------|
| Development | 3 backups | On demand | No |
| Staging | 7 backups | Daily | Optional |
| Production | 30 backups | Daily | Yes |

For production, also consider:
- **Weekly full backups** stored separately with longer retention (90 days)
- **Off-site replication** using `rclone`, `aws s3 cp`, or `rsync`
- **Backup encryption** for off-site copies (use `gpg` or similar)

---

## Production Recommendations

### Managed Database Snapshots vs pg_dump

For production deployments, managed database services offer better backup solutions:

| Approach | Pros | Cons |
|----------|------|------|
| **pg_dump (this script)** | Simple, portable, works anywhere | Locks during dump, slow for large DBs |
| **Managed DB snapshots** (RDS, Cloud SQL, etc.) | Instant, no locks, point-in-time recovery | Vendor-specific, harder to migrate |
| **WAL archiving** (continuous) | Zero data loss, point-in-time recovery | Complex setup, requires storage |

**Recommendation by deployment size:**

- **Small (<100K memories)**: pg_dump is sufficient. Use these scripts.
- **Medium (100K-1M memories)**: Use managed DB with automated snapshots + pg_dump for portability.
- **Large (>1M memories)**: Managed DB with continuous WAL archiving + daily pg_dump for disaster recovery.

### Managed Database Services

If you deploy on a managed PostgreSQL provider, use their native backup tools:

- **AWS RDS**: Automated snapshots + point-in-time recovery
- **Google Cloud SQL**: Automated backups with configurable retention
- **Railway**: Built-in database backups
- **Supabase**: Daily backups (Pro plan) or point-in-time recovery (Team plan)

Even with managed backups, keep periodic pg_dump exports for portability (vendor lock-in protection).

### Off-Site Backup Example

After the daily backup, sync to remote storage:

```bash
# AWS S3
aws s3 sync /path/to/backups s3://my-bucket/totalreclaw-backups/ --delete

# rclone (supports many providers)
rclone sync /path/to/backups remote:totalreclaw-backups/

# rsync to another server
rsync -avz /path/to/backups/ backup-server:/backups/totalreclaw/
```

---

## Troubleshooting

### "Container is not running"

Start the database container:
```bash
cd server && docker-compose up -d postgres
```

### "pg_dump failed"

Check the container logs:
```bash
docker logs totalreclaw-db --tail 50
```

### "Backup file is empty"

This usually means the database credentials are wrong. Verify:
```bash
docker exec totalreclaw-db psql -U totalreclaw -d totalreclaw -c "SELECT 1;"
```

### "Restore failed -- inconsistent state"

If restore fails mid-transaction, the database may be empty. Re-run the restore:
```bash
./scripts/restore.sh backups/your_backup.sql.gz --force
```

If that also fails, manually recreate the schema:
```bash
docker exec -i totalreclaw-db psql -U totalreclaw -d totalreclaw < src/db/schema.sql
```
