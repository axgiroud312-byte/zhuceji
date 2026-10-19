"""Additive SQLite runtime storage; legacy tables are never rewritten."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .script_contract import validate_package, validate_results
from .vault import Vault


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class RuntimeStore:
    def __init__(self, database: Path, vault: Vault):
        self.database, self.vault = Path(database), vault
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS rt_scripts (
                    id TEXT, version TEXT, site_id TEXT NOT NULL, manifest TEXT NOT NULL,
                    source TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(id,version));
                CREATE TABLE IF NOT EXISTS rt_batches (
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE, script_id TEXT NOT NULL,
                    version TEXT NOT NULL, site_id TEXT NOT NULL, state TEXT NOT NULL,
                    count INTEGER NOT NULL, created_at REAL NOT NULL, snapshot TEXT NOT NULL,
                    fields TEXT NOT NULL, parameters_ref TEXT NOT NULL, stop INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS rt_tasks (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    state TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'queued',
                    message TEXT NOT NULL DEFAULT '', submitted INTEGER NOT NULL DEFAULT 0,
                    results TEXT NOT NULL DEFAULT '{}', secret_ref TEXT NOT NULL DEFAULT '',
                    UNIQUE(batch_id,ordinal));
                CREATE TABLE IF NOT EXISTS rt_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL,
                    task_id TEXT NOT NULL, at REAL NOT NULL, stage TEXT NOT NULL,
                    level TEXT NOT NULL, message TEXT NOT NULL, details TEXT NOT NULL DEFAULT '');
                CREATE INDEX IF NOT EXISTS rt_events_task ON rt_events(task_id,id);
                CREATE INDEX IF NOT EXISTS rt_events_batch ON rt_events(batch_id,id);
                CREATE INDEX IF NOT EXISTS rt_tasks_batch ON rt_tasks(batch_id,state);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_package(self, package):
        manifest, source = validate_package(package)
        with self.connect() as db:
            other = db.execute("SELECT site_id FROM rt_scripts WHERE id=? LIMIT 1",
                               (manifest.id,)).fetchone()
            if other and other[0] != manifest.site_id:
                raise ValueError("同一脚本 ID 更新不能更改网站标识。")
            try:
                db.execute("INSERT INTO rt_scripts VALUES (?,?,?,?,?,?)", (
                    manifest.id, manifest.version, manifest.site_id,
                    encode(manifest.model_dump()), source, time.time(),
                ))
            except sqlite3.IntegrityError:
                raise ValueError("该脚本版本已经存在；更新请使用新的 version。") from None
        return manifest.model_dump()

    def scripts(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT manifest FROM rt_scripts ORDER BY created_at DESC")]

    def script(self, script_id, version):
        with self.connect() as db:
            row = db.execute("SELECT * FROM rt_scripts WHERE id=? AND version=?",
                             (script_id, version)).fetchone()
        if not row:
            raise ValueError("找不到所选脚本版本，请重新选择。")
        return json.loads(row["manifest"]), row["source"]

    @staticmethod
    def public_batch(row):
        if row is None:
            return None
        result = {k: row[k] for k in ("id", "script_id", "version", "site_id", "state",
                                     "count", "created_at")}
        if row["state"] == "RUNNING" and row["stop"]:
            result["state"] = "STOPPING"
        return result

    def batches(self):
        with self.connect() as db:
            return [self.public_batch(r) for r in db.execute(
                "SELECT * FROM rt_batches ORDER BY created_at DESC")]

    def request_batch(self, request_id):
        with self.connect() as db:
            return self.public_batch(db.execute(
                "SELECT * FROM rt_batches WHERE request_id=?", (request_id,)).fetchone())

    def batch(self, batch_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM rt_batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            raise ValueError("找不到该批次。")
        return dict(row)

    def create_batch(self, batch_id, request_id, manifest, count, snapshot, parameters):
        ref = "runtime-parameters:" + batch_id
        self.vault.set(ref, parameters)
        try:
            with self.connect() as db:
                db.execute("INSERT INTO rt_batches VALUES (?,?,?,?,?,?,?,?,?,?,?,0)", (
                    batch_id, request_id, manifest["id"], manifest["version"],
                    manifest["site_id"], "RUNNING", count, time.time(), encode(snapshot),
                    encode(manifest["result_fields"]), ref,
                ))
                db.executemany(
                    "INSERT INTO rt_tasks (id,batch_id,ordinal,state) VALUES (?,?,?,?)",
                    [(f"{batch_id}-{i:04d}", batch_id, i, "PENDING")
                     for i in range(1, count + 1)],
                )
        except Exception:
            self.vault.delete(ref)
            raise

    def event(self, batch_id, task_id, stage, level, message, details=""):
        with self.connect() as db:
            db.execute("INSERT INTO rt_events "
                       "(batch_id,task_id,at,stage,level,message,details) VALUES (?,?,?,?,?,?,?)",
                       (batch_id, task_id, time.time(), stage[:80], level[:20],
                        message[:2000], details[:4000]))
            if task_id:
                db.execute("UPDATE rt_tasks SET stage=? WHERE id=?", (stage[:80], task_id))

    def task_state(self, task_id, state, message=""):
        with self.connect() as db:
            db.execute("UPDATE rt_tasks SET state=?,message=? WHERE id=?",
                       (state, message[:2000], task_id))

    def submitted(self, task_id):
        with self.connect() as db:
            db.execute("UPDATE rt_tasks SET submitted=1 WHERE id=?", (task_id,))

    def save_results(self, task_id, fields, values):
        validate_results(fields, values)
        secret_keys = {f["key"] for f in fields if f.get("sensitive")}
        secret = {k: v for k, v in values.items() if k in secret_keys}
        public = {k: v for k, v in values.items() if k not in secret_keys}
        ref = "runtime-result:" + task_id
        if secret:
            self.vault.set(ref, secret)
        with self.connect() as db:
            db.execute("UPDATE rt_tasks SET results=?,secret_ref=? WHERE id=?",
                       (encode(public), ref if secret else "", task_id))

    def finish(self, batch_id):
        with self.connect() as db:
            db.execute("UPDATE rt_batches SET state=CASE WHEN stop=1 THEN 'STOPPED' "
                       "ELSE 'COMPLETED' END WHERE id=?", (batch_id,))

    def stop(self, batch_id):
        self.batch(batch_id)
        with self.connect() as db:
            db.execute("UPDATE rt_batches SET stop=1 WHERE id=? AND state='RUNNING'", (batch_id,))

    def recover(self):
        """Caller MUST own RunLock. Never requeue a possibly submitted task."""
        with self.connect() as db:
            db.execute("UPDATE rt_tasks SET state=CASE WHEN submitted=1 THEN 'UNKNOWN' "
                       "ELSE 'CANCELLED' END,message='运行中断；未自动重新执行',"
                       "stage='interrupted' "
                       "WHERE state IN ('RUNNING','PENDING') AND batch_id IN "
                       "(SELECT id FROM rt_batches WHERE state='RUNNING')")
            db.execute("UPDATE rt_batches SET state='INTERRUPTED' WHERE state='RUNNING'")

    def tasks(self, batch_id, *, state="", search="", offset=0, limit=50, reveal=False):
        batch = self.batch(batch_id)
        offset, limit = max(0, int(offset)), max(1, min(200, int(limit)))
        where, args = "batch_id=?", [batch_id]
        if state:
            where += " AND state=?"
            args.append(state)
        if search:
            where += " AND (id LIKE ? OR message LIKE ? OR results LIKE ?)"
            args.extend(["%" + search + "%"] * 3)
        with self.connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM rt_tasks WHERE {where}", args).fetchone()[0]
            rows = db.execute(f"SELECT * FROM rt_tasks WHERE {where} ORDER BY ordinal LIMIT ? "
                              "OFFSET ?", [*args, limit, offset]).fetchall()
            counts = dict(db.execute("SELECT state,COUNT(*) FROM rt_tasks WHERE batch_id=? "
                                     "GROUP BY state", (batch_id,)).fetchall())
        fields = json.loads(batch["fields"])
        tasks = []
        for row in rows:
            task = {k: row[k] for k in ("id", "state", "stage", "message", "submitted")}
            task["index"] = row["ordinal"]
            values = json.loads(row["results"])
            if row["secret_ref"]:
                secrets = self.vault.get(row["secret_ref"])
                values.update(secrets if reveal else {k: "••••••" for k in secrets})
            task["results"] = values
            tasks.append(task)
        summary = {s: counts.get(s.upper(), 0) for s in
                   ("succeeded", "failed", "running", "pending", "unknown", "cancelled")}
        summary["total"] = batch["count"]
        return {"tasks": tasks, "total": total, "fields": fields, "summary": summary,
                "batch": self.public_batch(batch)}

    def events(self, batch_id="", task_id="", after=0, limit=100):
        where, args = "id>?", [max(0, int(after))]
        if batch_id:
            where += " AND batch_id=?"
            args.append(batch_id)
        if task_id:
            where += " AND task_id=?"
            args.append(task_id)
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(
                f"SELECT * FROM rt_events WHERE {where} ORDER BY id LIMIT ?",
                [*args, max(1, min(500, int(limit)))],
            )]
        return {"events": rows, "cursor": rows[-1]["id"] if rows else int(after)}

    def export_csv(self, batch_id, include_secrets=False):
        batch = self.batch(batch_id)
        fields = json.loads(batch["fields"])
        keys = [f["key"] for f in fields]
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["task_id", "site_id", "script_id", "version", "state", "reason", *keys])
        offset = 0
        while True:
            page = self.tasks(batch_id, offset=offset, limit=200, reveal=include_secrets)
            for row in page["tasks"]:
                cells = [row["id"], batch["site_id"], batch["script_id"], batch["version"],
                         row["state"], row["message"], *[row["results"].get(k, "") for k in keys]]
                # CSV opened by spreadsheet software must not execute formulas.
                writer.writerow(["'" + v if isinstance(v, str) and
                                 v.lstrip().startswith(("=", "+", "-", "@")) else v for v in cells])
            offset += len(page["tasks"])
            if offset >= page["total"]:
                break
        return ("\ufeff" + output.getvalue()).encode("utf-8")
