"""Idempotent, additive legacy history import. Caller owns the database RunLock."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from .privacy import redact
from .runtime_store import encode

LEGACY_FIELDS = [
    {"key": "email", "label": "邮箱", "type": "string", "required": False, "sensitive": True},
    {"key": "password", "label": "网站密码", "type": "string", "required": False,
     "sensitive": True},
    {"key": "api_key", "label": "API Key", "type": "string", "required": False,
     "sensitive": True},
]


def migrate_legacy(store, *, fail_after=None):
    """Copy historical interpretation, not runnable queues; leave all originals untouched."""
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='registration_jobs'").fetchone():
            return {"imported": 0, "backup": ""}
        rows = db.execute(
            "SELECT j.*,u.email,u.secret_ref FROM registration_jobs j "
            "JOIN users u ON u.id=j.user_id ORDER BY j.batch_id,j.created_at,j.id"
        ).fetchall()
        existing = {r[0] for r in db.execute("SELECT id FROM rt_tasks WHERE id LIKE 'legacy-%'")}
    pending = [r for r in rows if "legacy-" + r["id"] not in existing]
    if not pending:
        return {"imported": 0, "backup": ""}
    backup_dir = store.database.parent / "runtime-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    # First successful backup remains the original recovery point, never replaced on retry.
    database_backup = backup_dir / (store.database.name + ".pre-runtime.sqlite3")
    if not database_backup.exists():
        temp = database_backup.with_suffix(".tmp")
        with closing(sqlite3.connect(store.database)) as source, \
                closing(sqlite3.connect(temp)) as destination:
            source.backup(destination)
        temp.replace(database_backup)
    vault_backup = backup_dir / (store.vault.path.name + ".pre-runtime.dpapi")
    if store.vault.path.exists() and not vault_backup.exists():
        shutil.copy2(store.vault.path, vault_backup)
    grouped = {}
    for row in rows:
        grouped.setdefault(row["batch_id"], []).append(row)
    new_records = {}
    imported = 0
    with store.connect() as db:
        for old_batch, jobs in grouped.items():
            batch_id = "legacy-" + hashlib.sha256(old_batch.encode()).hexdigest()[:20]
            provider = jobs[0]["provider"]
            site_id = "agnes" if provider in {"agnes", "agnes-api"} else "legacy-" + provider
            db.execute("INSERT OR IGNORE INTO rt_batches VALUES (?,?,?,?,?,?,?,?,?,?,?,0)", (
                batch_id, "migration:" + batch_id, "legacy-" + provider, "legacy",
                site_id, "ARCHIVED", len(jobs), min(r["created_at"] for r in jobs),
                encode({"legacy_batch": old_batch}), encode(LEGACY_FIELDS), "",
            ))
            for index, row in enumerate(jobs, 1):
                task_id = "legacy-" + row["id"]
                if task_id in existing:
                    continue
                record = store.vault.get(row["secret_ref"]) if row["secret_ref"] else {}
                result = {"email": row["email"]}
                if record.get("agnes_password"):
                    result["password"] = record["agnes_password"]
                if record.get("api_key"):
                    result["api_key"] = record["api_key"]
                ref = "runtime-result:" + task_id
                new_records[ref] = result
                state = row["state"]
                if state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    state = "UNKNOWN" if row["submitted_at"] is not None else "CANCELLED"
                message = "旧任务只读归档；不会重新进入注册队列。"
                db.execute("INSERT INTO rt_tasks VALUES (?,?,?,?,?,?,?,?,?)", (
                    task_id, batch_id, index, state, "legacy", message,
                    int(row["submitted_at"] is not None), "{}", ref,
                ))
                for event in db.execute("SELECT * FROM job_events WHERE job_id=? ORDER BY id",
                                        (row["id"],)).fetchall():
                    text = event["message"]
                    for secret in record.values():
                        if isinstance(secret, str) and secret:
                            text = text.replace(secret, "[已隐藏]")
                    db.execute("INSERT INTO rt_events (batch_id,task_id,at,stage,level,message) "
                               "VALUES (?,?,?,?,?,?)", (batch_id, task_id, event["at"], "legacy",
                                                       "info", redact(text)))
                imported += 1
                if fail_after is not None and imported >= fail_after:
                    raise RuntimeError("INJECTED_MIGRATION_FAILURE")
        # Add-only Vault write precedes SQLite commit. A failed commit leaves harmless new refs;
        # retry overwrites those same deterministic refs, never the original credentials.
        store.vault.set_many(new_records)
    return {"imported": imported, "backup": str(Path(database_backup))}
