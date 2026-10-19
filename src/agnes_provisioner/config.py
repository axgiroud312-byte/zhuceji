from __future__ import annotations

import math
import os
import re
import tempfile
import tomllib
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

REGISTRATION_STAGES = (
    "before_open", "before_fill", "before_code", "before_submit", "after_submit"
)
LOGIN_STAGES = ("before_open", "before_fill", "before_submit", "after_submit")
KEY_STAGES = ("before_navigate", "before_extract", "after_create", "extract")


def configured(value: str) -> str:
    """An empty value uses a default where one exists; literal `none` skips it."""
    text = value.strip()
    return "" if text.casefold() == "none" else text


def _validate_steps(steps: list[FlowStep], stages: tuple[str, ...], flow: str) -> None:
    for step in steps:
        if step.stage not in stages:
            raise ValueError(f"{flow} 不支持阶段 {step.stage}；可用阶段：{', '.join(stages)}。")


def _validate_pattern(pattern: str, field: str) -> None:
    try:
        compiled = re.compile(pattern)
    except (re.error, OverflowError, RecursionError) as error:
        raise ValueError(f"{field} 正则表达式无效：{error}") from error
    if compiled.search("") is not None:
        raise ValueError(f"{field} 不能匹配空文本。")


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = ""
    concurrency: int = Field(default=1, ge=1, le=100)
    per_minute: float = Field(default=1, gt=0, le=1000000)
    proxies_allowed: bool = False


class FlowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: Literal[
        "before_open", "before_fill", "before_code", "before_submit", "after_submit",
        "before_navigate", "before_extract", "after_create", "extract",
    ] = "after_submit"
    action: Literal[
        "click",
        "fill",
        "goto",
        "wait_selector",
        "wait_ms",
        "press",
        "check",
        "extract_text",
        "extract_storage",
        "evaluate_js",
    ] = "click"
    selector: str = ""
    value: str = ""
    enabled: bool = True
    optional: bool = True
    note: str = ""

    @model_validator(mode="after")
    def validate_action(self):
        # Disabled cards may remain incomplete while the user edits the workbench.
        if not self.enabled:
            return self
        selector_actions = {
            "click", "fill", "wait_selector", "press", "check", "extract_text"
        }
        if self.action in selector_actions and not self.selector.strip():
            raise ValueError(f"{self.action} 动作需要 selector（跳过请填 none 或禁用步骤）。")
        if self.action in {"goto", "extract_storage", "evaluate_js"} and not self.value.strip():
            raise ValueError(f"{self.action} 动作需要 value。")
        if self.action == "wait_ms":
            try:
                milliseconds = float(self.value.strip() or "500")
            except ValueError as error:
                raise ValueError("wait_ms 的 value 需要是 0–60000 的毫秒数。") from error
            if not math.isfinite(milliseconds) or not 0 <= milliseconds <= 60000:
                raise ValueError("wait_ms 的 value 需要是 0–60000 的毫秒数。")
        if self.action == "goto" and configured(self.value):
            url = urlsplit(self.value.strip())
            if url.scheme and (url.scheme not in {"http", "https"} or not url.hostname):
                raise ValueError("goto 仅支持 http/https 地址或站内路径。")
        return self


class RegistrationFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_path: str = "/login"
    open_register_selector: str = ""
    email_selector: str = ""
    password_selector: str = ""
    confirm_password_selector: str = ""
    send_code_ready_selector: str = ""
    send_code_click_selector: str = ""
    code_input_selector: str = ""
    submit_button_selector: str = ""
    success_url_not_contains: str = "/login"
    custom_steps: list[FlowStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_steps(self):
        _validate_steps(self.custom_steps, REGISTRATION_STAGES, "registration_flow")
        return self


class VerificationFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["auto_mailbox", "manual", "none"] = "auto_mailbox"
    sender_domain: str = "agnes-ai.com"
    code_pattern: str = r"(?<!\d)\d{6}(?!\d)"
    imap_host: str = "outlook.office365.com"
    imap_port: int = Field(default=993, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_pattern(self):
        _validate_pattern(self.code_pattern, "verification.code_pattern")
        return self


class LoginFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login_path: str = "/login"
    email_selector: str = ""
    password_selector: str = ""
    submit_selector: str = ""
    login_api_path: str = "/api/user/login"
    token_storage_key: str = "token"
    post_login_path: str = "/settings/apiKeys"
    verify_mode: Literal["strict_identity", "selector_only", "url_or_token"] = "strict_identity"
    custom_steps: list[FlowStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_steps(self):
        _validate_steps(self.custom_steps, LOGIN_STAGES, "login_flow")
        # Despite the legacy name, this mode requires BOTH a non-login URL and a token.
        if self.verify_mode == "url_or_token" and not configured(self.token_storage_key):
            raise ValueError("url_or_token 核验需要 token_storage_key，不能只凭页面跳转确认登录。")
        return self


class ProxyPoolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rotate_every: int = Field(default=1, ge=1, le=10000)
    rotate_mode: Literal["result_reached", "execution_count", "both"] = "result_reached"
    rotate_executions_limit: int = Field(default=3, ge=1, le=10000)
    auto_switch_on_ip_limit: bool = True
    session_suffix_template: str = "-session-{session}-time-30"
    enable_session_stickiness: bool = False


class KeyFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    require_key: bool = True
    target_url: str = ""
    navigation_selector: str = ""
    create_selector: str = ""
    name_selector: str = ""
    name_template: str = "Agnes Provisioner {user_id}"
    confirm_selector: str = ""
    value_selector: str = ""
    copy_selector: str = ""
    storage_key: str = ""
    extract_mode: Literal[
        "auto", "dom_regex", "network_json", "clipboard_copy", "local_storage"
    ] = "auto"
    pattern: str = r"sk-[A-Za-z0-9_-]{16,}"
    custom_steps: list[FlowStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selectors(self):
        _validate_pattern(self.pattern, "key_flow.pattern")
        _validate_steps(self.custom_steps, KEY_STAGES, "key_flow")
        if not self.enabled:
            return self
        sources = {
            "dom_regex": configured(self.value_selector),
            "clipboard_copy": configured(self.copy_selector),
            "local_storage": configured(self.storage_key),
        }
        if self.extract_mode in sources and not sources[self.extract_mode]:
            required = {
                "dom_regex": "value_selector",
                "clipboard_copy": "copy_selector",
                "local_storage": "storage_key",
            }[self.extract_mode]
            raise ValueError(f"key_flow 的 {self.extract_mode} 模式需要 {required}。")
        custom_extract = any(
            step.enabled
            and step.action in {"extract_text", "extract_storage", "evaluate_js"}
            and configured(step.selector if step.action == "extract_text" else step.value)
            for step in self.custom_steps
        )
        if self.extract_mode == "auto" and not (any(sources.values()) or custom_extract):
            raise ValueError("key_flow 启用后需要文本/复制/Storage 提取源或自定义提取动作。")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database: Path = Path("data/agnes.db")
    vault: Path = Path("data/credentials.dpapi")
    mode: Literal["mock", "agnes"] = "mock"
    concurrency: int = Field(default=1, ge=1, le=100)
    per_minute: float = Field(default=1, gt=0, le=1000000)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_delay_seconds: float = Field(default=5, ge=0)
    headless: bool = False
    browser_channel: str | None = "chrome"
    browser_timeout_ms: int = Field(default=30000, ge=1000, le=120000)
    cache_public_assets: bool = True
    block_analytics: bool = True
    verification_timeout_seconds: int = Field(default=120, ge=5, le=900)
    manual_verification: bool = False
    identity_navigation_selector: str = ""
    account_identity_selector: str = ""
    authenticated_selector: str = ""
    proxy_required: bool = False
    allow_custom_base_url: bool = False
    base_url: str = "https://platform.agnes-ai.com"
    proxy_check_url: str = "https://platform.agnes-ai.com/login"
    approval: Approval = Field(default_factory=Approval)
    key_flow: KeyFlow = Field(default_factory=KeyFlow)
    registration_flow: RegistrationFlow = Field(default_factory=RegistrationFlow)
    verification: VerificationFlow = Field(default_factory=VerificationFlow)
    login_flow: LoginFlow = Field(default_factory=LoginFlow)
    proxy_pool: ProxyPoolConfig = Field(default_factory=ProxyPoolConfig)

    @model_validator(mode="after")
    def validate_live(self):
        if self.mode == "agnes":
            manual = self.verification.mode == "manual" or (
                self.manual_verification and self.verification.mode != "none"
            )
            if manual and self.headless:
                raise ValueError("人工验证码需要可见浏览器，请设置 headless = false。")
            if not self.approval.reference.strip():
                raise ValueError("真实执行需要在 approval.reference 记录本次开户授权。")
            if self.concurrency > self.approval.concurrency:
                raise ValueError("concurrency 超出 approval.concurrency。")
            if self.per_minute > self.approval.per_minute:
                raise ValueError("per_minute 超出 approval.per_minute。")
            target = urlsplit(self.base_url)
            if self.allow_custom_base_url:
                if target.scheme not in ("http", "https") or not target.hostname:
                    raise ValueError("base_url 需要包含有效的 http/https 协议和域名。")
            elif (
                target.scheme != "https"
                or target.hostname != "platform.agnes-ai.com"
                or target.username
                or target.password
                or target.port not in (None, 443)
                or target.path not in ("", "/")
                or target.query
                or target.fragment
            ):
                raise ValueError("真实适配器的 base_url 必须是 https://platform.agnes-ai.com。")
            if self.proxy_required and not self.approval.proxies_allowed:
                raise ValueError("proxy_required 需要 approval.proxies_allowed。")
        return self


def _toml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Path):
        value = value.as_posix()
    text = str(value or "")
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def dump_settings_toml(settings: Settings, root: Path | None = None) -> str:
    data = settings.model_dump()
    if root is not None:
        for key in ("database", "vault"):
            p = Path(data[key])
            try:
                data[key] = p.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                data[key] = p.resolve().as_posix()
    else:
        for key in ("database", "vault"):
            data[key] = Path(data[key]).as_posix()

    sections = (
        "approval",
        "key_flow",
        "registration_flow",
        "verification",
        "login_flow",
        "proxy_pool",
    )
    lines: list[str] = []
    for key, val in data.items():
        if key in sections or val is None:
            continue
        lines.append(f"{key} = {_toml_scalar(val)}")

    for sec in sections:
        sec_data = data.get(sec) or {}
        lines.append("")
        lines.append(f"[{sec}]")
        steps = sec_data.get("custom_steps")
        for k, v in sec_data.items():
            if k == "custom_steps" or v is None:
                continue
            lines.append(f"{k} = {_toml_scalar(v)}")
        if steps:
            for step in steps:
                lines.append("")
                lines.append(f"[[{sec}.custom_steps]]")
                for sk, sv in step.items():
                    if sv is None:
                        continue
                    lines.append(f"{sk} = {_toml_scalar(sv)}")
    return "\n".join(lines) + "\n"


def save_settings(settings: Settings, path: Path) -> None:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dump_settings_toml(settings, root=path.parent)
    Settings.model_validate(tomllib.loads(content))
    temporary: Path | None = None
    try:
        # A unique sibling file makes concurrent writers safe from partial/truncated TOML.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_settings(path: Path | None) -> Settings:
    if path is None:
        return Settings()
    with path.open("rb") as handle:
        settings = Settings.model_validate(tomllib.load(handle))
    root = path.resolve().parent
    settings.database = (root / settings.database).resolve()
    settings.vault = (root / settings.vault).resolve()
    return settings
