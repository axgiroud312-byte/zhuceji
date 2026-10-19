from __future__ import annotations

import email
import html
import imaplib
import re
import time
from email.utils import parseaddr
from urllib.parse import quote

import httpx

from .vault import Vault


class MailboxError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class OutlookMailbox:
    """只读 IMAP / Graph，只解析本次收到的发件域验证码。"""

    def __init__(
        self,
        vault: Vault,
        secret_ref: str,
        *,
        sender_domain: str = "agnes-ai.com",
        code_pattern: str = r"(?<!\d)\d{6}(?!\d)",
        imap_host: str = "outlook.office365.com",
        imap_port: int = 993,
    ):
        self.vault = vault
        self.secret_ref = secret_ref
        self.access_token = ""
        self.folders = ("INBOX", "Junk")
        self.sender_domain = (sender_domain or "").strip().casefold()
        self.code_pattern = code_pattern or r"(?<!\d)\d{6}(?!\d)"
        self.imap_host = imap_host or "outlook.office365.com"
        self.imap_port = imap_port or 993

    def _domain_matches(self, domain: str) -> bool:
        domain = (domain or "").casefold()
        if not self.sender_domain or self.sender_domain == "*":
            return True
        targets = [d.strip() for d in self.sender_domain.split(",") if d.strip()]
        return any(domain == t or domain.endswith("." + t) for t in targets)

    def refresh(self, scope: str | None = None) -> None:
        record = self.vault.get(self.secret_ref)
        if not record.get("mailbox_authorized"):
            raise MailboxError("MAILBOX_NOT_AUTHORIZED", "需要此用户的邮箱验证授权。")
        if not record.get("client_id") or not record.get("refresh_token"):
            raise MailboxError("MAILBOX_CREDENTIALS_MISSING", "此用户没有完整的邮箱 OAuth 凭证。")
        try:
            with httpx.Client(timeout=25, trust_env=False) as client:
                response = client.post(
                    "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                    data={
                        "client_id": record["client_id"],
                        "grant_type": "refresh_token",
                        "refresh_token": record["refresh_token"],
                        "scope": scope
                        or (
                            "https://graph.microsoft.com/.default"
                            if record.get("mailbox_transport") == "graph"
                            else "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
                        ),
                    },
                )
        except httpx.HTTPError as error:
            raise MailboxError(
                "MAILBOX_NETWORK", "无法连接 Outlook 授权服务，请检查网络。"
            ) from error
        try:
            payload = response.json()
        except ValueError as error:
            raise MailboxError("MAILBOX_RESPONSE", "Outlook 授权服务未返回有效响应。") from error
        if response.status_code != 200 or "access_token" not in payload:
            category = payload.get("error", "unknown")
            if category == "invalid_grant":
                raise MailboxError(
                    "MAILBOX_TOKEN_INVALID", "Outlook 登录令牌已失效，需要重新授权。"
                )
            if category in {"invalid_scope", "unauthorized_client", "invalid_client"}:
                raise MailboxError(
                    "MAILBOX_OAUTH_CONFIG", "邮箱 OAuth 应用或授权范围不能用于 IMAP。"
                )
            raise MailboxError("MAILBOX_AUTH", "Outlook 拒绝了邮箱授权，请重新授权后再试。")
        self.access_token = payload["access_token"]
        if payload.get("refresh_token"):
            record["refresh_token"] = payload["refresh_token"]
            self.vault.set(self.secret_ref, record)

    def _connect(self) -> imaplib.IMAP4_SSL:
        record = self.vault.get(self.secret_ref)
        use_password = record.get("mailbox_transport") == "imap_password" or (
            not record.get("client_id")
            and not record.get("refresh_token")
            and bool(record.get("mailbox_password"))
            and record.get("mailbox_transport") != "graph"
        )
        if not use_password and not self.access_token:
            self.refresh()
        connection = None
        host = record.get("imap_host") or self.imap_host
        port = int(record.get("imap_port") or self.imap_port)
        try:
            connection = imaplib.IMAP4_SSL(host, port, timeout=20)
            if use_password:
                connection.login(record["email"], record["mailbox_password"])
            else:
                auth = f"user={record['email']}\x01auth=Bearer {self.access_token}\x01\x01".encode()
                connection.authenticate("XOAUTH2", lambda _: auth)
            return connection
        except (OSError, imaplib.IMAP4.error) as error:
            if connection:
                try:
                    connection.logout()
                except (OSError, imaplib.IMAP4.error):
                    pass
            raise MailboxError("MAILBOX_IMAP", "无法以只读方式连接邮箱。") from error

    def _graph_get(self, path: str, params: dict | None = None) -> dict:
        if not self.access_token:
            self.refresh("https://graph.microsoft.com/.default")
        try:
            with httpx.Client(timeout=25, trust_env=False) as client:
                response = client.get(
                    "https://graph.microsoft.com/v1.0/" + path,
                    params=params,
                    headers={
                        "Authorization": "Bearer " + self.access_token,
                        "Prefer": 'outlook.body-content-type="text"',
                    },
                )
            if response.status_code != 200:
                raise MailboxError("MAILBOX_GRAPH", "Microsoft Graph 无法读取此邮箱，请检查授权。")
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise MailboxError("MAILBOX_NETWORK", "无法读取 Outlook 邮箱，请检查网络。") from error

    def _graph_recent(self) -> list[dict]:
        messages = []
        for folder in ("inbox", "junkemail"):
            messages.extend(
                self._graph_get(
                    f"me/mailFolders/{folder}/messages",
                    {
                        "$top": "30",
                        "$select": "id,from,receivedDateTime,toRecipients",
                        "$orderby": "receivedDateTime desc",
                    },
                ).get("value", [])
            )
        return messages

    def baseline(self) -> dict:
        if self.vault.get(self.secret_ref).get("mailbox_transport") == "graph":
            return {"transport": "graph", "seen": [m["id"] for m in self._graph_recent()]}
        connection = self._connect()
        baseline = {}
        try:
            for folder in self.folders:
                status, _ = connection.select(folder, readonly=True)
                if status != "OK":
                    continue
                status, values = connection.uid("search", None, "ALL")
                if status == "OK":
                    ids = [int(v) for v in (values[0] or b"").split()]
                    baseline[folder] = max(ids, default=0)
            if "INBOX" not in baseline:
                raise MailboxError("MAILBOX_INBOX", "无法读取邮箱收件箱。")
            return baseline
        except (OSError, imaplib.IMAP4.error) as error:
            raise MailboxError("MAILBOX_IMAP", "邮箱连接中断，请重新检查连接。") from error
        finally:
            try:
                connection.logout()
            except (OSError, imaplib.IMAP4.error):
                pass

    @staticmethod
    def _payload(values) -> bytes:
        return b"".join(v[1] for v in values if isinstance(v, tuple))

    def find_code(self, baseline: dict) -> str | None:
        if baseline.get("transport") == "graph":
            for message in self._graph_recent():
                if message["id"] in baseline["seen"]:
                    continue
                sender = message.get("from", {}).get("emailAddress", {}).get("address", "")
                domain = sender.rpartition("@")[2].casefold()
                if not self._domain_matches(domain):
                    continue
                expected = self.vault.get(self.secret_ref)["email"].casefold()
                recipients = {
                    r.get("emailAddress", {}).get("address", "").casefold()
                    for r in message.get("toRecipients", [])
                }
                if expected not in recipients:
                    continue
                value = self._graph_get(
                    "me/messages/" + quote(message["id"], safe=""), {"$select": "body"}
                )
                text = html.unescape(
                    re.sub(r"<[^>]+>", " ", value.get("body", {}).get("content", ""))
                )
                codes = list(dict.fromkeys(re.findall(self.code_pattern, text)))
                if len(codes) == 1:
                    return codes[0]
            return None
        connection = self._connect()
        try:
            for folder, last_uid in baseline.items():
                if connection.select(folder, readonly=True)[0] != "OK":
                    continue
                status, values = connection.uid("search", None, "UID", f"{last_uid + 1}:*")
                if status != "OK":
                    continue
                ids = [int(v) for v in (values[0] or b"").split() if int(v) > last_uid]
                for uid in reversed(ids[-30:]):
                    status, header_data = connection.uid(
                        "fetch", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT)])"
                    )
                    if status != "OK":
                        continue
                    header = email.message_from_bytes(self._payload(header_data))
                    sender = parseaddr(header.get("From", ""))[1].casefold()
                    domain = sender.rpartition("@")[2]
                    if not self._domain_matches(domain):
                        continue
                    status, message_data = connection.uid("fetch", str(uid), "(BODY.PEEK[])")
                    if status != "OK":
                        continue
                    message = email.message_from_bytes(self._payload(message_data))
                    pieces = []
                    for part in message.walk():
                        if part.get_content_type() not in {"text/plain", "text/html"}:
                            continue
                        body = part.get_payload(decode=True) or b""
                        text = body.decode(part.get_content_charset() or "utf-8", errors="replace")
                        pieces.append(html.unescape(re.sub(r"<[^>]+>", " ", text)))
                    text = " ".join(pieces)
                    codes = list(dict.fromkeys(re.findall(self.code_pattern, text)))
                    if len(codes) == 1:
                        return codes[0]
            return None
        except (OSError, imaplib.IMAP4.error) as error:
            raise MailboxError("MAILBOX_IMAP", "读取验证码时邮箱连接中断。") from error
        finally:
            try:
                connection.logout()
            except (OSError, imaplib.IMAP4.error):
                pass

    def wait_code(self, baseline: dict, timeout: int = 120) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            code = self.find_code(baseline)
            if code:
                return code
            time.sleep(min(3, max(0, deadline - time.monotonic())))
        return None
