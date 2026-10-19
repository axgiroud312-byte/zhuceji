"""Versioned resources; only Vault references cross the runtime storage boundary.

The service holds RunLock for save/check/recover and for the entire execution.
SQLite IMMEDIATE transactions additionally serialize concurrent worker claims.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from email_validator import EmailNotValidError, validate_email

from .bulk_relay import MeteredRelay
from .config import load_settings
from .mailbox import MailboxError, OutlookMailbox
from .proxy import ProxyManager, parse_proxy_line
from .vault import Vault, VaultError


class ResourceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _site(value: str) -> str:
    # The old adapter called this provider agnes-api, not a separate website.
    return "agnes" if value in {"agnes", "agnes-api", "agnes-ai"} else value


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fail(code: str, message: str):
    raise ResourceError(code, message)


def _url(value: str, *, local=False) -> str:
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or any(c.isspace() for c in value) or parsed.fragment):
            raise ValueError
        if local and (parsed.scheme != "http" or not parsed.port
                      or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                      or parsed.path not in {"", "/"} or parsed.query):
            raise ValueError
    except (ValueError, TypeError):
        _fail("RESOURCE_CONFIG", "连接地址无效；地址中不能包含凭证。")
    return value


class RuntimeMailbox:
    """Async script API backed by the existing read-only Outlook implementation."""

    def __init__(self, vault: Vault, email: str, secret_ref: str):
        self.email, self.secret_ref = email, secret_ref
        self.client = OutlookMailbox(vault, secret_ref)

    def configure(self, *, sender_domain: str, code_pattern: str):
        try:
            pattern = re.compile(code_pattern)
            if pattern.search(""):
                raise ValueError
        except (re.error, ValueError, TypeError):
            _fail("MAILBOX_PATTERN", "验证码匹配规则无效。")
        self.client.sender_domain = sender_domain.strip().casefold()
        self.client.code_pattern = code_pattern

    async def baseline(self):
        return await self._call(self.client.baseline)

    async def find_code(self, baseline):
        return await self._call(self.client.find_code, baseline)

    @staticmethod
    async def _call(function, *args):
        pending = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            # A token-refresh thread must finish before its mailbox is released.
            try:
                await pending
            finally:
                raise


@dataclass
class ResourceLease:
    task_id: str
    site_id: str
    mailbox: RuntimeMailbox | None = None
    proxy: dict | None = None
    session_id: str = ""
    egress_ip: str = ""
    created_at: float = field(default_factory=time.time)
    _relay: MeteredRelay | None = field(default=None, repr=False)
    _proxy_config: dict | None = field(default=None, repr=False)

    async def validate_proxy(self):
        """Check the pinned session; never rotate/fall back during a task."""
        if self.proxy is None:
            return
        if time.time() - self.created_at >= 29 * 60:
            _fail("PROXY_SESSION_EXPIRED", "当前代理会话已过期；任务不能切换出口继续提交。")
        ip = await _probe_proxy(self.proxy, self._proxy_config["check_url"])
        if self.egress_ip and ip != self.egress_ip:
            _fail("EGRESS_CHANGED", "代理会话出口发生变化；当前任务已停止。")
        self.egress_ip = ip


async def _probe_proxy(proxy: dict, url: str) -> str:
    auth = (proxy["username"], proxy["password"]) if proxy.get("username") else None
    try:
        async with httpx.AsyncClient(
            proxy=httpx.Proxy(proxy["server"], auth=auth), timeout=25, trust_env=False,
        ) as client:
            response = await client.get(url)
        if response.status_code != 200:
            raise ValueError
        return str(ipaddress.ip_address(response.text.strip()))
    except (httpx.HTTPError, OSError, ValueError):
        _fail("PROXY_UNAVAILABLE", "代理连接或出口 IP 检查失败；没有改用直连。")


class ResourceManager:
    def __init__(self, settings):
        self.settings = settings
        self.vault = Vault(settings.vault)
        Path(settings.database).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS resource_settings (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
                    revision TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS resource_revisions (
                    id TEXT PRIMARY KEY, resource_id TEXT NOT NULL, config_ref TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'UNKNOWN', summary TEXT NOT NULL,
                    checked_at REAL, error_code TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS resource_mailboxes (
                    revision TEXT NOT NULL, email TEXT NOT NULL, secret_ref TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'UNKNOWN', error_code TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(revision,email));
                CREATE TABLE IF NOT EXISTS resource_snapshots (
                    id TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS resource_leases (
                    task_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, site_id TEXT NOT NULL,
                    email TEXT, secret_ref TEXT, origin_ref TEXT, proxy_revision TEXT,
                    session_id TEXT NOT NULL, created_at REAL NOT NULL,
                    submitted INTEGER NOT NULL DEFAULT 0, succeeded INTEGER NOT NULL DEFAULT 0,
                    released INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS resource_active_mailbox
                    ON resource_leases(email) WHERE released=0 AND email IS NOT NULL;
                CREATE TABLE IF NOT EXISTS resource_submissions (
                    site_id TEXT NOT NULL, email TEXT NOT NULL, task_id TEXT NOT NULL,
                    submitted_at REAL NOT NULL, PRIMARY KEY(site_id,email));
            """)

    @contextmanager
    def _connection(self, *, write=False):
        db = sqlite3.connect(self.settings.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _record(record: dict, *, transport="graph", host="outlook.office365.com", port=993):
        try:
            email = validate_email(
                record.get("email", ""), check_deliverability=False,
            ).normalized.casefold()
        except (EmailNotValidError, TypeError):
            _fail("MAILBOX_CONFIG", "邮箱格式无效（输入已隐藏）。")
        mode = record.get("mailbox_transport", transport)
        if mode == "imap":
            mode = "imap_oauth"
        if mode not in {"graph", "imap_oauth", "imap_password"}:
            _fail("MAILBOX_CONFIG", "仅支持现有 Outlook Graph、IMAP OAuth 或 IMAP 密码接入。")
        result = {k: record[k] for k in ("mailbox_password", "client_id", "refresh_token")
                  if record.get(k)}
        if mode == "imap_password":
            valid = bool(result.get("mailbox_password"))
        else:
            valid = bool(result.get("client_id") and result.get("refresh_token"))
        if not valid or any(not isinstance(v, str) for v in result.values()):
            _fail("MAILBOX_CONFIG", "邮箱凭证不完整（输入已隐藏）。")
        result.update(email=email, mailbox_authorized=True, mailbox_transport=mode,
                      imap_host=record.get("imap_host", host),
                      imap_port=record.get("imap_port", port))
        return result

    def _legacy_exclusions(self, db):
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "users" in tables:
            records = self.vault.snapshot()
            confirmed = []
            for user in db.execute("SELECT email,secret_ref FROM users"):
                record = records.get(user["secret_ref"], {})
                if (record.get("email", "").casefold() == user["email"].casefold()
                        and (record.get("activated") or record.get("api_key"))):
                    confirmed.append((user["email"].casefold(), "legacy-vault", time.time()))
            db.executemany("INSERT OR IGNORE INTO resource_submissions VALUES('agnes',?,?,?)",
                           confirmed)
        if {"users", "registration_jobs"} <= tables:
            rows = db.execute("""
                SELECT u.email,j.id,COALESCE(j.submitted_at,j.created_at) AS at
                FROM registration_jobs j JOIN users u ON u.id=j.user_id
                WHERE j.provider IN ('agnes','agnes-api','agnes-ai')
                  AND (j.submitted_at IS NOT NULL OR j.state='SUCCEEDED'
                   OR j.phase IN ('REGISTRATION_SUBMITTED','KEY_REQUESTED'))
            """)
            db.executemany("INSERT OR IGNORE INTO resource_submissions VALUES('agnes',?,?,?)",
                           [(r["email"].casefold(), r["id"], r["at"]) for r in rows])
        if {"bulk_requests", "registration_jobs", "users"} <= tables:
            rows = db.execute("""
                SELECT u.email,j.id,r.at FROM bulk_requests r
                JOIN registration_jobs j ON j.id=r.job_id JOIN users u ON u.id=j.user_id
                WHERE j.provider IN ('agnes','agnes-api','agnes-ai')
                  AND r.kind IN ('REGISTRATION_SUBMITTED','KEY_REQUESTED')
            """)
            db.executemany("INSERT OR IGNORE INTO resource_submissions VALUES('agnes',?,?,?)",
                           [(r["email"].casefold(), r["id"], r["at"]) for r in rows])

    def _mailbox_config(self, config):
        allowed = {"source", "transport", "accounts", "imap_host", "imap_port", "config_path"}
        if set(config) - allowed:
            _fail("MAILBOX_CONFIG", "邮箱配置包含不支持的字段。")
        source = config.get("source", "outlook")
        if source == "legacy":
            source_settings = self.settings
            if config.get("config_path"):
                try:
                    source_settings = load_settings(Path(config["config_path"]))
                except (OSError, ValueError, TypeError):
                    _fail("LEGACY_CONFIG", "旧配置无法读取，请选择已有的 TOML 配置文件。")
            if not Path(source_settings.database).is_file():
                _fail("MAILBOX_EMPTY", "旧配置对应的数据库不存在。")
            originals = Vault(source_settings.vault).snapshot()
            try:
                source_db = sqlite3.connect(Path(source_settings.database).as_uri() + "?mode=ro",
                                            uri=True, timeout=30)
            except sqlite3.Error:
                _fail("LEGACY_DATABASE", "旧数据库无法只读打开，请检查配置和文件状态。")
            source_db.row_factory = sqlite3.Row
            exclusions = []
            try:
                db = source_db
                exists = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'",
                ).fetchone()
                if not exists:
                    _fail("MAILBOX_EMPTY", "当前数据库没有旧邮箱记录。")
                users = list(db.execute("SELECT email,secret_ref FROM users"))
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master "
                                                  "WHERE type='table'")}
                if "registration_jobs" in tables:
                    exclusions.extend(r[0].casefold() for r in db.execute("""
                        SELECT u.email FROM registration_jobs j JOIN users u ON u.id=j.user_id
                        WHERE j.provider IN ('agnes','agnes-api','agnes-ai')
                          AND (j.submitted_at IS NOT NULL OR j.state='SUCCEEDED'
                           OR j.phase IN ('REGISTRATION_SUBMITTED','KEY_REQUESTED'))
                    """))
                if {"bulk_requests", "registration_jobs"} <= tables:
                    exclusions.extend(r[0].casefold() for r in db.execute("""
                        SELECT u.email FROM bulk_requests r
                        JOIN registration_jobs j ON j.id=r.job_id JOIN users u ON u.id=j.user_id
                        WHERE j.provider IN ('agnes','agnes-api','agnes-ai')
                          AND r.kind IN ('REGISTRATION_SUBMITTED','KEY_REQUESTED')
                    """))
            except sqlite3.Error:
                _fail("LEGACY_DATABASE", "旧数据库结构不兼容或损坏，请先检查来源。")
            finally:
                source_db.close()
            rows = []
            for user in users:
                record = dict(originals.get(user["secret_ref"], {}))
                if record.get("email", "").casefold() != user["email"].casefold():
                    _fail("MAILBOX_CREDENTIALS", "旧邮箱凭证引用缺失或身份不匹配。")
                # Legacy unspecified transport uses the same inference as OutlookMailbox.
                if not record.get("mailbox_transport"):
                    record["mailbox_transport"] = (
                        "imap_oauth" if record.get("client_id") else "imap_password"
                    )
                rows.append(record)
                if record.get("activated") or record.get("api_key"):
                    exclusions.append(user["email"].casefold())
        elif source == "outlook":
            raw = config.get("accounts", "")
            exclusions = []
            if isinstance(raw, str):
                rows = []
                for line in raw.splitlines():
                    if not line.strip() or line.strip() == "卡密导出":
                        continue
                    fields = line.strip().split("----")
                    if len(fields) not in {2, 4}:
                        _fail("MAILBOX_CONFIG", "每行需要邮箱----密码----应用 ID----刷新令牌。")
                    rows.append(dict(zip(
                        ("email", "mailbox_password", "client_id", "refresh_token"), fields,
                        strict=False,
                    )))
            elif isinstance(raw, list) and all(isinstance(row, dict) for row in raw):
                rows = raw
            else:
                _fail("MAILBOX_CONFIG", "邮箱列表需要是文本或对象数组。")
        else:
            _fail("MAILBOX_CONFIG", "邮箱来源无效。")
        if not rows:
            _fail("MAILBOX_EMPTY", "请提供至少一个邮箱。")
        host, port = config.get("imap_host", "outlook.office365.com"), config.get("imap_port", 993)
        if (not isinstance(host, str) or not host.strip() or isinstance(port, bool)
                or not isinstance(port, int) or not 1 <= port <= 65535):
            _fail("MAILBOX_CONFIG", "IMAP 主机或端口无效。")
        records = [self._record(r, transport=config.get("transport", "graph"), host=host,
                                port=port) for r in rows]
        if len({r["email"] for r in records}) != len(records):
            _fail("MAILBOX_DUPLICATE", "资源中存在重复邮箱；请去重后保存。")
        return records, exclusions

    def _proxy_config(self, config):
        allowed = {"source", "server", "username", "password", "upstream",
                   "session_suffix_template", "check_url", "vault_path", "secret_ref"}
        if set(config) - allowed:
            _fail("PROXY_CONFIG", "代理配置包含不支持的字段。")
        source = config.get("source", "dynamic")
        if source == "legacy_bulk":
            if not config.get("vault_path") or not config.get("secret_ref"):
                _fail("PROXY_CONFIG", "导入旧代理需要凭证库路径和记录引用。")
            original = Vault(Path(config["vault_path"])).get(config["secret_ref"])
            if not original:
                _fail("PROXY_CONFIG", "旧代理凭证引用不存在。")
        elif source == "dynamic":
            original = config
        else:
            _fail("PROXY_CONFIG", "代理来源无效。")
        server = original.get("server", "")
        username, password = original.get("username", ""), original.get("password", "")
        try:
            parsed = parse_proxy_line(server, 1)
            if parsed["username"] or parsed["password"]:
                raise ValueError
            if bool(username) != bool(password):
                raise ValueError
            if any(ord(c) < 32 for c in username + password):
                raise ValueError
            if parsed["server"].startswith("socks5:"):
                raise ValueError
        except (RuntimeError, ValueError, TypeError):
            _fail("PROXY_CONFIG", "请提供 HTTP/HTTPS 代理地址，并单独填写完整认证信息。")
        template = config.get("session_suffix_template", "-session-{session}-time-30")
        if (not isinstance(template, str) or "{session}" not in template
                or any(ord(c) < 32 for c in template)):
            _fail("PROXY_CONFIG", "动态代理会话后缀必须包含 {session}。")
        upstream = config.get("upstream", "")
        if upstream:
            _url(upstream, local=True)
            if not server.startswith("http://"):
                _fail("PROXY_CONFIG", "现有双层中继只支持 HTTP 供应商网关。")
        return {"server": parsed["server"], "username": username, "password": password,
                "upstream": upstream, "session_suffix_template": template,
                "check_url": _url(config.get("check_url", "https://ipinfo.io/ip"))}

    def save(self, payload) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"id", "name", "kind", "config"}:
            _fail("RESOURCE_CONFIG", "资源配置格式无效。")
        name, kind, config = payload.get("name"), payload.get("kind"), payload.get("config")
        if (not isinstance(name, str) or not name.strip() or len(name) > 100
                or kind not in {"mailbox", "proxy"} or not isinstance(config, dict)):
            _fail("RESOURCE_CONFIG", "请填写资源名称、类型和连接配置。")
        rid = payload.get("id") or uuid4().hex
        if not isinstance(rid, str) or not re.fullmatch(r"[\w.-]{1,100}", rid):
            _fail("RESOURCE_CONFIG", "资源标识无效。")
        revision = uuid4().hex
        config_ref = "resource-config-" + revision
        additions, mailbox_rows, exclusions = {}, [], []
        if kind == "mailbox":
            records, exclusions = self._mailbox_config(config)
            for record in records:
                ref = "resource-mailbox-" + uuid4().hex
                additions[ref] = record
                mailbox_rows.append((revision, record["email"], ref))
            summary = {"total": len(records), "supply": "Outlook Graph / IMAP"}
            additions[config_ref] = {"mailboxes": len(records)}
        else:
            proxy = self._proxy_config(config)
            additions[config_ref] = proxy
            summary = {"supply": "每任务固定动态会话", "via_upstream": bool(proxy["upstream"])}
        with self._connection(write=True) as db:
            existing = db.execute(
                "SELECT kind FROM resource_settings WHERE id=?", (rid,),
            ).fetchone()
            if payload.get("id") and existing is None:
                _fail("RESOURCE_NOT_FOUND", "找不到要更新的资源。")
            if existing and existing[0] != kind:
                _fail("RESOURCE_KIND", "不能更改已有资源的类型。")
            # Vault first: failure leaves old DB bindings intact; orphaned records are harmless.
            self.vault.set_many(additions)
            db.execute("INSERT INTO resource_revisions(id,resource_id,config_ref,summary) "
                       "VALUES(?,?,?,?)", (revision, rid, config_ref, _json(summary)))
            db.executemany(
                "INSERT INTO resource_mailboxes(revision,email,secret_ref) VALUES(?,?,?)",
                mailbox_rows,
            )
            db.execute("INSERT INTO resource_settings VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE "
                       "SET name=excluded.name,revision=excluded.revision",
                       (rid, name.strip(), kind, revision))
            self._legacy_exclusions(db)
            db.executemany("INSERT OR IGNORE INTO resource_submissions VALUES('agnes',?,?,?)",
                           [(email, "legacy-vault", time.time()) for email in exclusions])
        return next(r for r in self.list() if r["id"] == rid)

    def list(self) -> list[dict]:
        with self._connection() as db:
            result = []
            for row in db.execute("SELECT s.*,r.status,r.summary,r.checked_at,r.error_code "
                                  "FROM resource_settings s JOIN resource_revisions r "
                                  "ON r.id=s.revision ORDER BY s.name,s.id"):
                summary = json.loads(row["summary"])
                if row["kind"] == "mailbox":
                    states = dict(db.execute(
                        "SELECT status,count(*) FROM resource_mailboxes "
                        "WHERE revision=? GROUP BY status", (row["revision"],),
                    ))
                    summary.update(healthy=states.get("HEALTHY", 0),
                                   unknown=states.get("UNKNOWN", 0),
                                   unavailable=states.get("UNHEALTHY", 0))
                    summary["in_use"] = db.execute(
                        "SELECT count(*) FROM resource_mailboxes m JOIN resource_leases l "
                        "ON l.email=m.email AND l.released=0 WHERE m.revision=?",
                        (row["revision"],),
                    ).fetchone()[0]
                result.append({"id": row["id"], "name": row["name"], "kind": row["kind"],
                               "status": row["status"], "summary": summary,
                               "checked_at": row["checked_at"], "error_code": row["error_code"]})
            return result

    def _health(self, revision, status, code="", *, email=None):
        with self._connection(write=True) as db:
            if email is not None:
                db.execute("UPDATE resource_mailboxes SET status=?,error_code=? "
                           "WHERE revision=? AND email=?", (status, code, revision, email))
                states = {r[0] for r in db.execute(
                    "SELECT status FROM resource_mailboxes WHERE revision=?", (revision,),
                )}
                status = next(iter(states)) if len(states) == 1 else "DEGRADED"
                failure = db.execute(
                    "SELECT error_code FROM resource_mailboxes WHERE revision=? "
                    "AND error_code!='' ORDER BY email LIMIT 1", (revision,),
                ).fetchone()
                code = failure[0] if failure else ""
            db.execute(
                "UPDATE resource_revisions SET status=?,error_code=?,checked_at=? WHERE id=?",
                (status, code, time.time(), revision),
            )

    async def _open_proxy(self, config, lease):
        server = config["server"]
        if config["upstream"]:
            relay = MeteredRelay(config["upstream"], server, lambda *_: None)
            await relay.__aenter__()
            lease._relay = relay
            server = relay.url
        lease._proxy_config = config
        lease.proxy = ProxyManager.credentials(
            SimpleNamespace(server=server, username_env="", password_env=""),
            SimpleNamespace(inline_username=config["username"], inline_password=config["password"],
                            session_sticky_id=lease.session_id, session_mode=True),
            session_suffix_template=config["session_suffix_template"],
        )
        await lease.validate_proxy()

    async def _check_proxy(self, config):
        lease = ResourceLease("check", "", session_id=uuid4().hex[:12])
        try:
            await self._open_proxy(config, lease)
        finally:
            if lease._relay:
                await lease._relay.__aexit__(None, None, None)

    def check(self, resource_id) -> dict:
        with self._connection() as db:
            row = db.execute("SELECT s.kind,r.* FROM resource_settings s JOIN resource_revisions r "
                             "ON r.id=s.revision WHERE s.id=?", (resource_id,)).fetchone()
            if row is None:
                _fail("RESOURCE_NOT_FOUND", "资源不存在。")
            mailboxes = list(db.execute("SELECT * FROM resource_mailboxes WHERE revision=?",
                                       (row["id"],)))
        if row["kind"] == "proxy":
            try:
                asyncio.run(self._check_proxy(self.vault.get(row["config_ref"])))
                self._health(row["id"], "HEALTHY")
            except (ResourceError, VaultError, OSError, KeyError):
                self._health(row["id"], "UNHEALTHY", "PROXY_UNAVAILABLE")
        else:
            for mailbox in mailboxes:
                try:
                    OutlookMailbox(self.vault, mailbox["secret_ref"]).baseline()
                    self._health(row["id"], "HEALTHY", email=mailbox["email"])
                except (MailboxError, VaultError, OSError, KeyError) as error:
                    code = error.code if isinstance(error, MailboxError) else "MAILBOX_CREDENTIALS"
                    self._health(row["id"], "UNHEALTHY", code, email=mailbox["email"])
        return next(r for r in self.list() if r["id"] == resource_id)

    @staticmethod
    def _available(db, revision, site_id):
        return list(db.execute("""
            SELECT m.* FROM resource_mailboxes m WHERE m.revision=? AND m.status!='UNHEALTHY'
            AND NOT EXISTS (SELECT 1 FROM resource_submissions s
                WHERE s.email=m.email AND s.site_id=?)
            AND NOT EXISTS (SELECT 1 FROM resource_leases l WHERE l.email=m.email AND l.released=0)
            ORDER BY m.email
        """, (revision, site_id)))

    def snapshot(self, bindings: dict, requirements: dict, count: int, site_id: str) -> dict:
        if (not isinstance(count, int) or isinstance(count, bool) or count < 1
                or not isinstance(site_id, str) or not site_id.strip()):
            _fail("RESOURCE_COUNT", "任务数量和网站标识无效。")
        if (not isinstance(bindings, dict) or not isinstance(requirements, dict)
                or set(bindings) - {"mailbox", "proxy"}):
            _fail("RESOURCE_BINDINGS", "资源绑定格式无效。")
        document = {"id": uuid4().hex, "site_id": _site(site_id), "count": count, "bindings": {}}
        with self._connection(write=True) as db:
            self._legacy_exclusions(db)
            for kind in ("mailbox", "proxy"):
                rid = bindings.get(kind)
                if not rid:
                    if requirements.get(kind):
                        _fail("RESOURCE_REQUIRED", "请绑定邮箱资源。" if kind == "mailbox"
                              else "请绑定代理资源；此脚本不能直连。")
                    continue
                row = db.execute("SELECT s.kind,r.* FROM resource_settings s "
                                 "JOIN resource_revisions r ON r.id=s.revision WHERE s.id=?",
                                 (rid,)).fetchone()
                if row is None or row["kind"] != kind:
                    _fail("RESOURCE_NOT_FOUND", "绑定资源不存在或类型不匹配。")
                if kind == "mailbox":
                    if len(self._available(db, row["id"], document["site_id"])) < count:
                        _fail("MAILBOX_EXHAUSTED",
                              "可分配邮箱不足；已排除同网站提交、占用和检查失败邮箱。")
                elif row["status"] == "UNHEALTHY":
                    _fail("PROXY_UNAVAILABLE", "代理检查失败；请修复后重新检查。")
                document["bindings"][kind] = {"resource_id": rid, "revision": row["id"],
                                              "config_ref": row["config_ref"]}
            db.execute("INSERT INTO resource_snapshots VALUES(?,?)",
                       (document["id"], _json(document)))
        return document

    async def acquire(self, snapshot, site_id, task_id) -> ResourceLease:
        lease = ResourceLease(task_id, _site(site_id), session_id=uuid4().hex[:12])
        with self._connection(write=True) as db:
            saved = db.execute("SELECT document FROM resource_snapshots WHERE id=?",
                               (snapshot.get("id"),)).fetchone()
            if (saved is None or saved[0] != _json(snapshot)
                    or snapshot["site_id"] != lease.site_id):
                _fail("RESOURCE_SNAPSHOT", "资源绑定快照不匹配，不能更换运行配置。")
            if db.execute("SELECT 1 FROM resource_leases WHERE task_id=?", (task_id,)).fetchone():
                _fail("RESOURCE_TASK_REPLAY", "此任务已领取过资源，不能重复执行。")
            used = db.execute("SELECT count(*) FROM resource_leases WHERE snapshot_id=?",
                              (snapshot["id"],)).fetchone()[0]
            if used >= snapshot["count"]:
                _fail("RESOURCE_COUNT", "任务数已达到此绑定快照的上限。")
            mailbox = snapshot["bindings"].get("mailbox")
            origin_ref = email = secret_ref = None
            if mailbox:
                rows = self._available(db, mailbox["revision"], lease.site_id)
                if not rows:
                    _fail("MAILBOX_EXHAUSTED", "邮箱已耗尽或被其他任务占用。")
                selected = rows[0]
                email, origin_ref = selected["email"], selected["secret_ref"]
                secret_ref = "resource-task-" + uuid4().hex
                record = self.vault.get(origin_ref)
                if record.get("email") != email:
                    _fail("MAILBOX_CREDENTIALS", "邮箱凭证引用缺失或不匹配。")
                self.vault.set(secret_ref, record)
                lease.mailbox = RuntimeMailbox(self.vault, email, secret_ref)
            proxy = snapshot["bindings"].get("proxy")
            db.execute("""INSERT INTO resource_leases
                (task_id,snapshot_id,site_id,email,secret_ref,origin_ref,proxy_revision,
                 session_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                       (task_id, snapshot["id"], lease.site_id, email, secret_ref, origin_ref,
                        proxy["revision"] if proxy else None, lease.session_id, lease.created_at))
        try:
            if proxy:
                try:
                    await self._open_proxy(self.vault.get(proxy["config_ref"]), lease)
                    self._health(proxy["revision"], "HEALTHY")
                except (ResourceError, VaultError, OSError, KeyError):
                    self._health(proxy["revision"], "UNHEALTHY", "PROXY_UNAVAILABLE")
                    _fail("PROXY_UNAVAILABLE", "代理连接或出口检查失败；没有改用直连。")
            if lease.mailbox:
                try:
                    await lease.mailbox.baseline()
                    self._health(mailbox["revision"], "HEALTHY", email=email)
                except (MailboxError, VaultError, OSError, KeyError) as error:
                    code = error.code if isinstance(error, MailboxError) else "MAILBOX_CREDENTIALS"
                    self._health(mailbox["revision"], "UNHEALTHY", code, email=email)
                    _fail(code, "邮箱连接或凭证检查失败；未提交注册。")
            return lease
        except BaseException:
            await self.release(lease, submitted=False, succeeded=False)
            raise

    def mark_submitted(self, lease: ResourceLease) -> None:
        """Must run before the mutating request, including before the task-store marker."""
        with self._connection(write=True) as db:
            row = db.execute(
                "SELECT * FROM resource_leases WHERE task_id=?", (lease.task_id,),
            ).fetchone()
            if row is None or row["released"] or row["site_id"] != lease.site_id:
                _fail("RESOURCE_LEASE", "当前资源租约已失效，不能提交。")
            db.execute("UPDATE resource_leases SET submitted=1 WHERE task_id=?", (lease.task_id,))
            if row["email"]:
                db.execute("INSERT OR IGNORE INTO resource_submissions VALUES(?,?,?,?)",
                           (row["site_id"], row["email"], lease.task_id, time.time()))

    def _return_token(self, row):
        if row["secret_ref"] and row["origin_ref"]:
            record, original = self.vault.get(row["secret_ref"]), self.vault.get(row["origin_ref"])
            if record.get("refresh_token") and original:
                original["refresh_token"] = record["refresh_token"]
                self.vault.set(row["origin_ref"], original)

    async def release(self, lease: ResourceLease, *, submitted: bool, succeeded: bool) -> None:
        try:
            with self._connection(write=True) as db:
                row = db.execute("SELECT * FROM resource_leases WHERE task_id=?",
                                 (lease.task_id,)).fetchone()
                if row is None or row["released"]:
                    return
                # Success is evidence of submission even if a script forgot its marker.
                submitted = bool(submitted or succeeded or row["submitted"])
                if submitted and row["email"]:
                    db.execute("INSERT OR IGNORE INTO resource_submissions VALUES(?,?,?,?)",
                               (row["site_id"], row["email"], lease.task_id, time.time()))
                db.execute("UPDATE resource_leases SET submitted=?,succeeded=?,released=1 "
                           "WHERE task_id=?", (submitted, succeeded, lease.task_id))
            # Preserve the durable submission even when returning a refreshed token fails.
            self._return_token(row)
        finally:
            if lease._relay:
                await lease._relay.__aexit__(None, None, None)
                lease._relay = None

    def recover(self) -> None:
        """Call only after acquiring the shared RunLock (no live workers)."""
        with self._connection(write=True) as db:
            self._legacy_exclusions(db)
            rows = list(db.execute("SELECT * FROM resource_leases WHERE released=0"))
            for row in rows:
                if row["submitted"] and row["email"]:
                    db.execute("INSERT OR IGNORE INTO resource_submissions VALUES(?,?,?,?)",
                               (row["site_id"], row["email"], row["task_id"], row["created_at"]))
            db.execute("UPDATE resource_leases SET released=1 WHERE released=0")
        for row in rows:
            self._return_token(row)
