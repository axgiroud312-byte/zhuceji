from __future__ import annotations

import asyncio
import base64
import os
import re
import time
import tomllib
from contextlib import contextmanager
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import delete, or_, select, text

from .domain import State
from .models import Job, Proxy, ProxyMeta
from .storage import Storage, StorageError
from .vault import VaultError, _transform

_CHECK_PREFIX = "health-check:"
_CHECK_TIMEOUT_SECONDS = 25
_CHECK_LEASE_TTL_SECONDS = 40
_INLINE_SECRET_PREFIX = "dpapi:v1:"


def _protect_inline(value: str) -> str:
    if not value:
        return ""
    try:
        protected = _transform(value.encode("utf-8"), True)
        return _INLINE_SECRET_PREFIX + base64.b64encode(protected).decode("ascii")
    except (VaultError, ValueError, UnicodeError):
        raise StorageError("无法加密代理凭证；请使用当前 Windows 用户或环境变量。") from None


def _read_inline(value: str) -> str:
    if not value.startswith(_INLINE_SECRET_PREFIX):
        # Read-only compatibility: legacy plaintext is only replaced during an
        # explicit import/update, never by listing or opening an existing pool.
        return value
    try:
        protected = base64.b64decode(value[len(_INLINE_SECRET_PREFIX):], validate=True)
        return _transform(protected, False).decode("utf-8")
    except (VaultError, ValueError, UnicodeError):
        raise StorageError(
            "无法读取代理加密凭证；请使用原 Windows 用户或重新导入该节点。"
        ) from None


def _normalize_host(host: str) -> str:
    if not host or len(host) > 253 or "%" in host:
        raise ValueError("代理主机无效。")
    try:
        return str(ip_address(host))
    except ValueError:
        host = host.encode("idna").decode("ascii").lower()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
            raise ValueError("代理主机无效。") from None
        if any(not part or len(part) > 63 for part in host.split(".")):
            raise ValueError("代理主机无效。")
        return host


def _endpoint(scheme: str, host: str, port: int) -> str:
    host = _normalize_host(host)
    if scheme not in {"http", "https", "socks5"} or not 1 <= port <= 65535:
        raise ValueError("代理协议或端口无效。")
    return f"{scheme}://{'[' + host + ']' if ':' in host else host}:{port}"


class ProxyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80, pattern=r"^[\w.-]+$")
    server: str
    provider: str = ""
    username_env: str = Field(default="", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$|^$")
    password_env: str = Field(default="", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$|^$")

    @model_validator(mode="after")
    def validate_endpoint(self):
        try:
            if any(c.isspace() or ord(c) < 32 for c in self.server):
                raise ValueError
            url = urlsplit(self.server)
            if (
                not url.hostname
                or not url.port
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or url.path not in ("", "/")
            ):
                raise ValueError
            self.server = _endpoint(url.scheme, url.hostname, url.port)
        except (ValueError, UnicodeError):
            raise ValueError("代理需要协议、主机和端口；凭证请使用环境变量引用。") from None
        if bool(self.username_env) != bool(self.password_env):
            raise ValueError("代理用户名和密码引用需要一起填写。")
        if url.scheme == "socks5" and self.username_env:
            raise ValueError("Chromium 不支持带用户名密码的 SOCKS5 代理，请使用获准的 HTTP 代理。")
        return self


def parse_proxy_line(line: str, index: int, provider: str = "") -> dict:
    """Parse credentials for storage only; never return this directly to the Web UI."""
    raw = line.strip()
    if not raw or raw.startswith("#"):
        raise ValueError("EMPTY_LINE")

    proxy_id = ""
    explicit_id = False
    if "|" in raw:
        prefix, rest = raw.split("|", 1)
        if re.fullmatch(r"[\w.-]{1,80}", prefix.strip()):
            proxy_id = prefix.strip()
            explicit_id = True
            raw = rest.strip()

    scheme = "http"
    username = ""
    password = ""
    host = ""
    port = 0

    try:
        if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in raw):
            raise ValueError
        if "://" in raw or "@" in raw:
            candidate = raw if "://" in raw else "http://" + raw
            parsed = urlsplit(candidate)
            if (
                not parsed.hostname
                or not parsed.port
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
            ):
                raise ValueError
            scheme = parsed.scheme
            host = parsed.hostname
            port = parsed.port
            if re.search(r"%(?![0-9a-fA-F]{2})", (parsed.username or "") + (parsed.password or "")):
                raise ValueError
            username = unquote(parsed.username or "", errors="strict")
            password = unquote(parsed.password or "", errors="strict")
        else:
            if raw.startswith("["):
                match = re.fullmatch(r"\[([^]]+)\]:(\d+)(?::([^:]+):(.*))?", raw)
                if not match:
                    raise ValueError
                host, port_str, username, password = match.groups(default="")
            else:
                sep = "----" if "----" in raw else ":"
                parts = raw.split(sep, 3)
                if len(parts) == 2:
                    host, port_str = parts
                elif len(parts) == 4:
                    host, port_str, username, password = parts
                else:
                    raise ValueError
            port = int(port_str)
        if bool(username) != bool(password):
            raise ValueError
        if any(ord(c) < 32 or ord(c) == 127 for c in username + password):
            raise ValueError
        server = _endpoint(scheme, host, port)
    except (ValueError, UnicodeError):
        raise StorageError(
            f"第 {index} 行代理格式无效；请检查协议、主机、端口和认证信息（输入已隐藏）。"
        ) from None

    if scheme == "socks5" and (username or password):
        raise StorageError("Chromium 不支持带账号密码的 SOCKS5 代理，请改用 HTTP/HTTPS 代理。")

    if not proxy_id:
        safe_host = re.sub(r"[^\w.-]", "-", host)[:32]
        proxy_id = f"proxy-{safe_host}-{port}-{index}"
    session_mode = "{session}" in username
    return {
        "id": proxy_id[:80],
        "server": server,
        "provider": provider or "pool",
        "username": username,
        "password": password,
        "session_mode": session_mode,
        "explicit_id": explicit_id,
    }


def _toml_proxies(text_value: str) -> list[ProxyInput]:
    try:
        source = tomllib.loads(text_value)
        if set(source) != {"proxies"} or not isinstance(source["proxies"], list):
            raise ValueError
        values = [ProxyInput.model_validate(item) for item in source["proxies"]]
        if len({p.id for p in values}) != len(values) or not values:
            raise ValueError
        return values
    except (ValueError, TypeError, ValidationError):
        raise StorageError(
            "TOML 代理配置无效或标识重复；只接受 [[proxies]]（输入已隐藏）。"
        ) from None


def preview_proxy_text(
    text_value: str, *, provider: str = "代理池", session_mode: bool = False
) -> dict:
    """Pure, credential-free import preview. Invalid rows never echo their input."""
    if not isinstance(text_value, str):
        return {
            "valid": 0, "invalid": 1, "duplicates": 0, "rows": [],
            "errors": [{"line": 1, "message": "代理内容需要是文本。"}],
        }
    rows = []
    errors = []
    seen = set()
    duplicates = 0
    if "[[proxies]]" in text_value:
        try:
            values = _toml_proxies(text_value)
        except StorageError as error:
            return {
                "valid": 0, "invalid": 1, "duplicates": 0, "rows": [],
                "errors": [{"line": 1, "message": str(error)}],
            }
        parsed_rows = [
            (idx, dict(value.model_dump(), has_auth=bool(value.username_env)))
            for idx, value in enumerate(values, 1)
        ]
    else:
        parsed_rows = []
        for idx, line in enumerate(text_value.splitlines(), 1):
            if not line.strip() or line.strip().startswith("#"):
                continue
            try:
                parsed_rows.append((idx, parse_proxy_line(line, idx, provider)))
            except StorageError as error:
                errors.append({"line": idx, "message": str(error)})
    for idx, item in parsed_rows:
        endpoint = urlsplit(item["server"])
        key = (item["server"], item.get("username", item.get("username_env", "")))
        duplicate = key in seen
        seen.add(key)
        duplicates += int(duplicate)
        rows.append({
            "line": idx,
            "id": item["id"],
            "server": item["server"],
            "scheme": endpoint.scheme,
            "host": endpoint.hostname,
            "port": endpoint.port,
            "has_auth": bool(item.get("username") or item.get("has_auth")),
            "session_mode": bool(item.get("session_mode") or session_mode),
            "duplicate": duplicate,
        })
    return {
        "valid": len(rows), "invalid": len(errors), "duplicates": duplicates,
        "rows": rows, "errors": errors,
    }


class ProxyManager:
    def __init__(self, storage: Storage):
        self.storage = storage

    @contextmanager
    def _transaction(self):
        # SQLite has no SELECT FOR UPDATE. Reserve the writer before reading a
        # lease, so independent Web requests and workers cannot claim one node.
        with self.storage.session.begin() as session:
            session.execute(text("PRAGMA secure_delete=ON"))
            session.execute(text("BEGIN IMMEDIATE"))
            now = time.time()
            for proxy in session.scalars(
                select(Proxy).where(Proxy.leased_job_id.startswith(_CHECK_PREFIX))
            ):
                try:
                    started_at = float(proxy.leased_job_id.split(":", 2)[1])
                except (ValueError, IndexError):
                    started_at = 0
                if now - started_at > _CHECK_LEASE_TTL_SECONDS:
                    proxy.leased_job_id = None
                    proxy.status = "UNHEALTHY"
                    proxy.failures += 1
                    meta = self._ensure_meta(session, proxy.id)
                    meta.last_ip = ""
                    meta.latency_ms = None
            yield session

    @staticmethod
    def _has_binding(session, proxy_id: str, exclude_job_id: str = "") -> bool:
        return session.scalar(
            select(Job.id).where(
                Job.proxy_id == proxy_id,
                Job.submitted_at.is_not(None),
                Job.id != exclude_job_id,
                or_(
                    Job.state.not_in(
                        [State.SUCCEEDED, State.FAILED, State.CANCELLED, State.SKIPPED]
                    ),
                    (Job.state == State.SUCCEEDED) & (Job.error_code == "KEY_PENDING"),
                ),
            ).limit(1)
        ) is not None

    def _assert_mutable(self, session, proxy: Proxy) -> None:
        if proxy.leased_job_id:
            raise StorageError("代理正在使用或检查中，不能修改、切换或删除。")
        if self._has_binding(session, proxy.id):
            raise StorageError("代理绑定了已提交且待核查的任务，不能修改、切换或删除。")

    def _candidates(self, session, *, bound_id: str | None = None, job_id: str = ""):
        query = select(Proxy).where(Proxy.status == "HEALTHY", Proxy.leased_job_id.is_(None))
        if bound_id:
            query = query.where(Proxy.id == bound_id)
        candidates = []
        for proxy in session.scalars(query):
            meta = self._ensure_meta(session, proxy.id)
            if (not bound_id and not meta.enabled) or self._has_binding(session, proxy.id, job_id):
                continue
            candidates.append((meta.generation, proxy.failures, proxy.id, proxy, meta))
        return sorted(candidates, key=lambda item: item[:3])

    def _rotate(self, session, proxy: Proxy, meta: ProxyMeta, *, job_id: str = "") -> None:
        other_generations = [
            row[0] for row in self._candidates(session, job_id=job_id) if row[2] != proxy.id
        ]
        # Generation is also the selection rank. Simply adding one can leave
        # this node ahead of every other node, so move it behind the whole pool.
        meta.generation = max([meta.generation, *other_generations]) + 1
        meta.window_executions = 0
        meta.window_results = 0
        meta.session_sticky_id = uuid4().hex[:8]
        meta.last_rotated_at = time.time()
        meta.last_ip = ""
        meta.latency_ms = None
        proxy.last_checked = None

    @staticmethod
    def _dynamic(
        proxy: Proxy, meta: ProxyMeta, *, enable_session_stickiness: bool = False
    ) -> bool:
        username = (
            os.environ.get(proxy.username_env, "")
            if proxy.username_env else _read_inline(meta.inline_username)
        )
        return bool(username and (
            meta.session_mode or "{session}" in username or enable_session_stickiness
        ))

    def _ensure_meta(self, session, proxy_id: str) -> ProxyMeta:
        meta = session.get(ProxyMeta, proxy_id)
        if not meta:
            meta = ProxyMeta(
                proxy_id=proxy_id,
                generation=0,
                window_executions=0,
                window_results=0,
                total_executions=0,
                total_results=0,
                session_sticky_id=uuid4().hex[:8],
                enabled=True,
            )
            session.add(meta)
            session.flush()
        elif not meta.session_sticky_id:
            meta.session_sticky_id = uuid4().hex[:8]
        return meta

    def import_file(self, path: Path) -> int:
        text = path.read_text(encoding="utf-8-sig")
        if path.suffix.lower() == ".toml":
            _toml_proxies(text)
        return self.import_text(text, initial_status="UNCHECKED")["imported"]

    def import_text(
        self,
        text: str,
        *,
        provider: str = "代理池",
        initial_status: Literal["HEALTHY", "UNCHECKED"] = "HEALTHY",
        session_mode: bool = False,
        clear_existing: bool = False,
    ) -> dict:
        if not isinstance(text, str) or initial_status not in {"HEALTHY", "UNCHECKED"}:
            raise StorageError("代理内容或初始健康状态无效。")
        raw_stripped = text.strip()
        if not raw_stripped:
            raise StorageError("请输入至少一条代理记录。")

        if "[[proxies]]" in raw_stripped:
            values = _toml_proxies(raw_stripped)
            with self._transaction() as session:
                if clear_existing:
                    self._clear_unleased(session)
                for value in values:
                    proxy = session.get(Proxy, value.id)
                    if proxy:
                        self._assert_mutable(session, proxy)
                    if not proxy:
                        proxy = Proxy(id=value.id)
                        session.add(proxy)
                    for name, data in value.model_dump().items():
                        setattr(proxy, name, data)
                    proxy.status = initial_status
                    session.flush()
                    meta = self._ensure_meta(session, proxy.id)
                    meta.inline_username = ""
                    meta.inline_password = ""
                    meta.session_mode = session_mode
                    meta.enabled = True
                    meta.last_ip = ""
                    meta.latency_ms = None
                    meta.session_sticky_id = uuid4().hex[:8]
                    proxy.last_checked = None
            return {"imported": len(values), "status": initial_status}

        parsed_rows = []
        for idx, line in enumerate(raw_stripped.splitlines(), 1):
            if not line.strip() or line.strip().startswith("#"):
                continue
            parsed_rows.append(parse_proxy_line(line, idx, provider=provider))

        if not parsed_rows:
            raise StorageError("没有解析到有效的代理记录。")
        explicit_ids = [item["id"] for item in parsed_rows if item["explicit_id"]]
        if len(set(explicit_ids)) != len(explicit_ids):
            raise StorageError("代理标识重复，请使用不同的 id。")

        with self._transaction() as session:
            if clear_existing:
                self._clear_unleased(session)
            existing_by_server = {}
            for p in session.scalars(select(Proxy)):
                m = self._ensure_meta(session, p.id)
                try:
                    existing_by_server[(p.server, _read_inline(m.inline_username))] = p
                except StorageError:
                    # An explicit ID may replace inaccessible credentials. Do
                    # not block imports of unrelated nodes or expose ciphertext.
                    continue

            imported = duplicates = 0
            seen = set()
            for item in parsed_rows:
                endpoint_key = (item["server"], item["username"])
                if endpoint_key in seen:
                    duplicates += 1
                    continue
                seen.add(endpoint_key)
                match = existing_by_server.get(endpoint_key)
                proxy_id = match.id if match else item["id"]
                proxy = session.get(Proxy, proxy_id)
                if proxy and not match and not item["explicit_id"]:
                    proxy_id = f"{item['id'][:70]}-{uuid4().hex[:6]}"
                    proxy = None
                if proxy:
                    self._assert_mutable(session, proxy)
                if not proxy:
                    while session.get(Proxy, proxy_id):
                        proxy_id = f"{item['id'][:70]}-{uuid4().hex[:6]}"
                    proxy = Proxy(id=proxy_id)
                    session.add(proxy)
                proxy.server = item["server"]
                proxy.provider = item["provider"]
                proxy.username_env = ""
                proxy.password_env = ""
                proxy.status = initial_status
                session.flush()
                meta = self._ensure_meta(session, proxy.id)
                meta.inline_username = _protect_inline(item["username"])
                meta.inline_password = _protect_inline(item["password"])
                meta.session_mode = bool(item["session_mode"] or session_mode)
                meta.enabled = True
                meta.last_ip = ""
                meta.latency_ms = None
                meta.session_sticky_id = uuid4().hex[:8]
                proxy.last_checked = None
                existing_by_server[endpoint_key] = proxy
                imported += 1

        return {"imported": imported, "duplicates": duplicates, "status": initial_status}

    def _clear_unleased(self, session) -> None:
        for proxy in session.scalars(select(Proxy)):
            self._assert_mutable(session, proxy)
        for job in session.scalars(select(Job).where(Job.proxy_id.is_not(None))):
            job.proxy_id = None
        session.execute(delete(ProxyMeta))
        session.execute(delete(Proxy))

    @staticmethod
    def credentials(
        proxy: Proxy,
        meta: ProxyMeta | None = None,
        *,
        session_suffix_template: str = "-session-{session}-time-30",
        enable_session_stickiness: bool = False,
    ) -> dict:
        result = {"server": proxy.server}
        username = ""
        password = ""
        if proxy.username_env:
            username = os.environ.get(proxy.username_env) or ""
            password = os.environ.get(proxy.password_env) or ""
            if not username or not password:
                raise StorageError("代理认证环境变量尚未配置。")
        elif meta and (meta.inline_username or meta.inline_password):
            username = _read_inline(meta.inline_username)
            password = _read_inline(meta.inline_password)

        if username:
            sticky_id = (meta.session_sticky_id if meta else "") or uuid4().hex[:8]
            if "{session}" in username:
                username = username.replace("{session}", sticky_id)
            elif (meta and meta.session_mode) or enable_session_stickiness:
                template = session_suffix_template or "-session-{session}"
                if "{session}" not in template:
                    raise StorageError("动态代理会话后缀需要包含 {session} 占位符。")
                suffix = template.replace("{session}", sticky_id)
                if suffix not in username:
                    username = username + suffix
            result.update(username=username, password=password)
        return result

    async def check(
        self,
        proxy_id: str,
        url: str,
        *,
        session_suffix_template: str = "-session-{session}-time-30",
        enable_session_stickiness: bool = False,
    ) -> dict:
        try:
            endpoint = urlsplit(url)
            if (
                endpoint.scheme not in {"http", "https"}
                or not endpoint.hostname
                or endpoint.username is not None
                or endpoint.password is not None
            ):
                raise ValueError
        except ValueError:
            raise StorageError("健康检查需要不含凭证的 HTTP/HTTPS 地址。") from None
        check_lease = f"{_CHECK_PREFIX}{time.time():.6f}:{uuid4().hex}"
        with self._transaction() as session:
            proxy = session.get(Proxy, proxy_id)
            if not proxy:
                raise StorageError("找不到此代理。")
            self._assert_mutable(session, proxy)
            meta = self._ensure_meta(session, proxy.id)
            credentials = self.credentials(
                proxy, meta,
                session_suffix_template=session_suffix_template,
                enable_session_stickiness=enable_session_stickiness,
            )
            proxy.leased_job_id = check_lease
        auth = (
            (credentials["username"], credentials["password"])
            if "username" in credentials
            else None
        )
        http_status = None
        status = None
        detected_ip = ""
        latency_ms = None
        started = time.perf_counter()
        try:
            try:
                async with asyncio.timeout(_CHECK_TIMEOUT_SECONDS):
                    async with httpx.AsyncClient(
                        proxy=httpx.Proxy(credentials["server"], auth=auth),
                        timeout=15, trust_env=False,
                    ) as client:
                        response = await client.get(url)
                        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
                        http_status = response.status_code
                        status = "HEALTHY" if 200 <= http_status < 400 else "BLOCKED"
                        if status == "HEALTHY":
                            try:
                                ip_resp = await client.get("https://ipinfo.io/ip", timeout=6)
                                if ip_resp.status_code == 200 and len(ip_resp.text.strip()) <= 64:
                                    detected_ip = str(ip_address(ip_resp.text.strip()))
                            except (httpx.HTTPError, ValueError):
                                pass
            except (httpx.HTTPError, OSError, ValueError, TimeoutError):
                status = "UNHEALTHY"
                detected_ip = ""
            if status != "HEALTHY":
                latency_ms = None
        finally:
            # Keep the reservation across the await. Even cancellation must not
            # strand a lease or let a stale check overwrite another execution.
            with self._transaction() as session:
                proxy = session.get(Proxy, proxy_id)
                if proxy and proxy.leased_job_id == check_lease:
                    proxy.leased_job_id = None
                    if status is not None:
                        meta = self._ensure_meta(session, proxy_id)
                        proxy.status = status
                        proxy.last_checked = time.time()
                        meta.last_ip = detected_ip
                        meta.latency_ms = latency_ms
                        if status != "HEALTHY":
                            proxy.failures += 1
        return {
            "proxy_id": proxy_id,
            "status": status,
            "http_status": http_status,
            "ip": detected_ip,
            "latency_ms": latency_ms,
        }

    def acquire(
        self,
        job_id: str,
        bound_id: str | None = None,
        *,
        session_suffix_template: str = "-session-{session}-time-30",
        enable_session_stickiness: bool = False,
    ) -> tuple[str, dict] | None:
        with self._transaction() as session:
            job = session.get(Job, job_id)
            if job and job.submitted_at is not None:
                if not job.proxy_id or (bound_id and job.proxy_id != bound_id):
                    return None
                bound_id = job.proxy_id
            if session.scalar(select(Proxy.id).where(Proxy.leased_job_id == job_id).limit(1)):
                return None
            candidates = self._candidates(session, bound_id=bound_id, job_id=job_id)
            if not candidates:
                return None
            for _, _, _, proxy, meta in candidates:
                try:
                    credentials = self.credentials(
                        proxy,
                        meta,
                        session_suffix_template=session_suffix_template,
                        enable_session_stickiness=enable_session_stickiness,
                    )
                except StorageError:
                    proxy.status = "UNHEALTHY"
                    proxy.failures += 1
                    meta.last_ip = ""
                    meta.latency_ms = None
                    continue
                proxy.leased_job_id = job_id
                return proxy.id, credentials
            return None

    def release(
        self,
        proxy_id: str,
        job_id: str,
        failed: bool = False,
        *,
        result_achieved: bool = False,
        force_rotate: bool = False,
        rotate_every: int = 1,
        rotate_mode: Literal["result_reached", "execution_count", "both"] = "result_reached",
        rotate_executions_limit: int = 3,
        blocked: bool = False,
        preserve_binding: bool | None = None,
        enable_session_stickiness: bool = False,
        execution_started: bool = True,
    ) -> dict:
        if rotate_mode not in {"result_reached", "execution_count", "both"}:
            raise StorageError("代理轮换计数模式无效。")
        rotated = False
        with self._transaction() as session:
            proxy = session.get(Proxy, proxy_id)
            if not proxy or proxy.leased_job_id != job_id:
                return {"released": False, "rotated": False}
            meta = self._ensure_meta(session, proxy.id)
            proxy.leased_job_id = None
            if execution_started:
                meta.total_executions += 1
                meta.window_executions += 1
            if preserve_binding is None:
                preserve_binding = self._has_binding(session, proxy.id)
            else:
                preserve_binding = preserve_binding or self._has_binding(session, proxy.id, job_id)
            dynamic = self._dynamic(
                proxy, meta, enable_session_stickiness=enable_session_stickiness
            )
            if failed or blocked:
                proxy.status = "BLOCKED" if blocked else "UNHEALTHY"
                proxy.failures += 1
                meta.last_ip = ""
                meta.latency_ms = None
            if result_achieved:
                proxy.successes += 1
                meta.total_results += 1
                meta.window_results += 1

            threshold = max(1, int(rotate_every))
            exec_limit = max(1, int(rotate_executions_limit))
            should_rotate = force_rotate or failed or blocked
            if rotate_mode in {"result_reached", "both"}:
                should_rotate |= meta.window_results >= threshold
            if rotate_mode == "execution_count":
                should_rotate |= meta.window_executions >= threshold
            elif rotate_mode == "both":
                should_rotate |= meta.window_executions >= exec_limit
            if should_rotate and not preserve_binding:
                self._rotate(session, proxy, meta, job_id=job_id)
                rotated = True
                # A dynamic tunnel can supply a new session after IP rejection;
                # a disconnected endpoint, or a static blocked IP, cannot.
                if blocked and force_rotate and dynamic and not failed:
                    proxy.status = "HEALTHY"

            return {
                "released": True,
                "rotated": rotated,
                "proxy_id": proxy.id,
                "generation": meta.generation,
                "window_executions": meta.window_executions,
                "window_results": meta.window_results,
                "binding_preserved": bool(preserve_binding),
                "session_changed": bool(rotated and dynamic),
            }

    def rotate_now(self, proxy_id: str | None = None) -> dict:
        with self._transaction() as session:
            if proxy_id:
                proxy = session.get(Proxy, proxy_id)
                if not proxy:
                    raise StorageError("找不到此代理。")
                self._assert_mutable(session, proxy)
                meta = self._ensure_meta(session, proxy.id)
            else:
                candidates = self._candidates(session)
                if not candidates:
                    raise StorageError("没有可切换的空闲健康代理；使用中或待核查的绑定不会被修改。")
                _, _, _, proxy, meta = candidates[0]
            self._rotate(session, proxy, meta)
            next_nodes = self._candidates(session)
            return {
                "rotated": 1,
                "proxy_id": proxy.id,
                "next_proxy_id": next_nodes[0][2] if next_nodes else None,
                "generation": meta.generation,
                "session_changed": self._dynamic(proxy, meta),
            }

    def reset_rotation(self) -> dict:
        with self._transaction() as session:
            proxies = list(session.scalars(select(Proxy)))
            for p in proxies:
                self._assert_mutable(session, p)
            for p in proxies:
                meta = self._ensure_meta(session, p.id)
                meta.generation = 0
                meta.window_executions = 0
                meta.window_results = 0
                meta.total_executions = 0
                meta.total_results = 0
                meta.session_sticky_id = uuid4().hex[:8]
                meta.last_rotated_at = None
                meta.last_ip = ""
                meta.latency_ms = None
                p.status = "HEALTHY"
                p.failures = 0
                p.successes = 0
                p.last_checked = None
        return {"reset": True}

    def set_enabled(self, proxy_id: str, enabled: bool) -> dict:
        with self._transaction() as session:
            proxy = session.get(Proxy, proxy_id)
            if not proxy:
                raise StorageError("找不到此代理。")
            if proxy.leased_job_id:
                raise StorageError("代理正在使用或检查中，不能启用或停用。")
            meta = self._ensure_meta(session, proxy_id)
            meta.enabled = bool(enabled)
            if enabled and proxy.status == "UNCHECKED":
                proxy.status = "HEALTHY"
        return {"proxy_id": proxy_id, "enabled": bool(enabled)}

    def delete_proxy(self, proxy_id: str) -> dict:
        with self._transaction() as session:
            proxy = session.get(Proxy, proxy_id)
            if not proxy:
                raise StorageError("找不到此代理。")
            self._assert_mutable(session, proxy)
            for job in session.scalars(select(Job).where(Job.proxy_id == proxy_id)):
                job.proxy_id = None
            session.execute(delete(ProxyMeta).where(ProxyMeta.proxy_id == proxy_id))
            session.delete(proxy)
        return {"deleted": proxy_id}

    def clear_all(self) -> dict:
        with self._transaction() as session:
            self._clear_unleased(session)
        return {"cleared": True}

    def list(self) -> list[dict]:
        with self._transaction() as session:
            rows = []
            for p in session.scalars(select(Proxy).order_by(Proxy.id)):
                meta = self._ensure_meta(session, p.id)
                bound = self._has_binding(session, p.id)
                checking = bool(p.leased_job_id and p.leased_job_id.startswith(_CHECK_PREFIX))
                rows.append(
                    {
                        "id": p.id,
                        "server": p.server,
                        "provider": p.provider,
                        "status": p.status,
                        "leased": bool(p.leased_job_id),
                        "leased_job_id": "" if checking else (p.leased_job_id or ""),
                        "checking": checking,
                        "binding_preserved": bound,
                        "available": bool(
                            p.status == "HEALTHY" and meta.enabled
                            and not p.leased_job_id and not bound
                        ),
                        "failures": p.failures,
                        "successes": p.successes,
                        "last_checked": p.last_checked,
                        "enabled": meta.enabled,
                        "generation": meta.generation,
                        "window_executions": meta.window_executions,
                        "window_results": meta.window_results,
                        "total_executions": meta.total_executions,
                        "total_results": meta.total_results,
                        "session_mode": meta.session_mode,
                        "session_sticky_id": meta.session_sticky_id,
                        "last_ip": meta.last_ip,
                        "latency_ms": meta.latency_ms,
                        "last_rotated_at": meta.last_rotated_at,
                        "has_auth": bool(p.username_env or meta.inline_username),
                    }
                )
            return rows
