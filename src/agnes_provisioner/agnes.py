from __future__ import annotations

import asyncio
import re
import time
from contextlib import asynccontextmanager
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from playwright.async_api import Error as BrowserError
from playwright.async_api import TimeoutError as BrowserTimeout

from .browser import BrowserManager
from .config import FlowStep, Settings, configured
from .domain import Checkpoint, Result, State, Task
from .mailbox import MailboxError, OutlookMailbox
from .vault import Vault


def retry_after(value: str | None) -> float:
    if not value:
        return 60
    try:
        return max(1, float(value))
    except ValueError:
        try:
            return max(1, parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return 60


@asynccontextmanager
async def borrow_page(page):
    yield page


class AgnesAdapter:
    """开发者平台邮箱注册与结果提取；支持可配置注册流程、登录核验流程与最终结果提取流程。"""

    CONFIRM_NAME = re.compile(r"请(再次输入|确认您的)密码")

    def __init__(self, settings: Settings, vault: Vault):
        self.settings = settings
        self.vault = vault
        self.browser = BrowserManager(settings)
        self.ui_step = "PREPARE"

    def _base_host(self) -> str:
        return (urlsplit(self.settings.base_url).hostname or "platform.agnes-ai.com").casefold()

    def _root_domain(self) -> str:
        host = self._base_host()
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    def _host_matches(self, url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        target_host = self._base_host()
        root_domain = self._root_domain()
        return bool(host) and (
            host == target_host or host == root_domain or host.endswith("." + root_domain)
        )

    def _resolve_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        base = self.settings.base_url.rstrip("/")
        suffix = path_or_url if path_or_url.startswith("/") else "/" + path_or_url
        return base + suffix

    def _trusted_page(self, page_url: str) -> bool:
        """Identity and secrets must stay on the configured origin, not sibling sites."""
        try:
            actual = urlsplit(page_url)
            target = urlsplit(self.settings.base_url)
            actual_port = actual.port or (443 if actual.scheme == "https" else 80)
            target_port = target.port or (443 if target.scheme == "https" else 80)
            return (
                actual.scheme in {"http", "https"}
                and actual.scheme == target.scheme
                and actual.hostname == target.hostname
                and actual_port == target_port
                and not actual.username
                and not actual.password
            )
        except ValueError:
            return False

    def _on_login_page(self, page_url: str) -> bool:
        login_path = urlsplit(self._resolve_url(self.settings.login_flow.login_path or "/login"))
        path = urlsplit(page_url).path.rstrip("/") or "/"
        prefix = login_path.path.rstrip("/") or "/"
        return path == prefix or (prefix != "/" and path.startswith(prefix + "/"))

    def _verification_mode(self) -> str:
        if self.settings.verification.mode == "none":
            return "none"
        return "manual" if self.settings.manual_verification else self.settings.verification.mode

    @staticmethod
    def _flow_locator(page, selector: str, default):
        if selector.strip().casefold() == "none":
            return None
        return page.locator(selector.strip()) if selector.strip() else default()

    def _confirm_box(self, page):
        return self._flow_locator(
            page, self.settings.registration_flow.confirm_password_selector,
            lambda: page.get_by_role("textbox", name=self.CONFIRM_NAME).or_(
                page.get_by_placeholder(self.CONFIRM_NAME)
            ),
        )

    def _send_ready(self, page):
        return self._flow_locator(
            page, self.settings.registration_flow.send_code_ready_selector,
            lambda: page.locator('img[alt="can send"]'),
        )

    def _send_trigger(self, page):
        return self._flow_locator(
            page, self.settings.registration_flow.send_code_click_selector,
            lambda: self._send_ready(page),
        )

    def _email_box(self, page):
        return self._flow_locator(
            page, self.settings.registration_flow.email_selector,
            lambda: page.get_by_role("textbox", name="邮箱", exact=True),
        )

    def _password_box(self, page):
        return self._flow_locator(
            page, self.settings.registration_flow.password_selector,
            lambda: page.get_by_role("textbox", name="密码", exact=True),
        )

    def _code_box(self, page):
        return self._flow_locator(
            page, self.settings.registration_flow.code_input_selector,
            lambda: page.get_by_role("textbox", name="验证码", exact=True),
        )

    def _submit_button(self, page):
        return self._flow_locator(
            page, self.settings.registration_flow.submit_button_selector,
            lambda: page.get_by_role("button", name=re.compile(r"继\s*续")),
        )

    def _step_timeout(self, milliseconds: int) -> int:
        return min(milliseconds, self.settings.browser_timeout_ms)

    @staticmethod
    def _render_template(
        template: str, task: Task | None, password: str = "", code: str = ""
    ) -> str:
        text = template or ""
        if task is not None:
            text = (
                text.replace("{email}", task.email)
                .replace("{user_id}", task.user_id)
                .replace("{display_name}", task.display_name or task.user_id)
            )
        return text.replace("{password}", password).replace("{code}", code)

    async def _run_custom_steps(
        self,
        page,
        steps: list[FlowStep],
        stage: str,
        *,
        task: Task | None = None,
        password: str = "",
        code: str = "",
    ) -> list[str]:
        extracted: list[str] = []
        for step in steps:
            if not step.enabled or step.stage != stage:
                continue
            val = self._render_template(step.value, task, password, code)
            sel = self._render_template(step.selector, task, password, code)
            if step.action in {
                "click", "fill", "wait_selector", "press", "check", "extract_text"
            } and not configured(sel):
                continue
            if step.action in {"goto", "extract_storage", "evaluate_js"} and not configured(val):
                continue
            timeout = self._step_timeout(8000)
            try:
                if step.action == "goto" and val:
                    await page.goto(self._resolve_url(val), wait_until="domcontentloaded")
                elif step.action == "wait_ms":
                    ms = max(0, min(60000, int(float(val or "500"))))
                    await page.wait_for_timeout(ms)
                elif step.action == "wait_selector" and sel:
                    await page.locator(sel).first.wait_for(state="visible", timeout=timeout)
                elif step.action == "click" and sel:
                    await page.locator(sel).first.click(timeout=timeout)
                elif step.action == "check" and sel:
                    await page.locator(sel).first.check(timeout=timeout)
                elif step.action == "fill" and sel:
                    await page.locator(sel).first.fill(val, timeout=timeout)
                elif step.action == "press" and sel:
                    await page.locator(sel).first.press(val or "Enter", timeout=timeout)
                elif step.action == "extract_text" and sel:
                    loc = page.locator(sel)
                    if await loc.count() > 0:
                        raw = await loc.first.evaluate(
                            "e => e.value === undefined ? e.textContent : e.value"
                        )
                        if raw and str(raw).strip():
                            extracted.append(str(raw).strip())
                elif step.action == "extract_storage" and val:
                    raw = await page.evaluate("(k) => localStorage.getItem(k) || ''", val)
                    if raw and str(raw).strip():
                        extracted.append(str(raw).strip())
                elif step.action == "evaluate_js" and val:
                    raw = await page.evaluate(val)
                    if raw and str(raw).strip():
                        extracted.append(str(raw).strip())
            except (BrowserError, BrowserTimeout, ValueError):
                if not step.optional:
                    raise
        return extracted

    async def _open_registration(
        self, page, responses, task: Task | None = None, *, password: str = ""
    ):
        """SSR links may be visible before hydration; confirm the form before filling."""
        reg = self.settings.registration_flow
        open_sel = reg.open_register_selector.strip()
        if open_sel.lower() == "none":
            link = None
        elif open_sel:
            link = page.locator(open_sel)
        else:
            link = page.get_by_role("link", name="注册", exact=True)

        entry_url = self._resolve_url(reg.entry_path or "/login")
        for attempt in range(2):
            try:
                self.ui_step = "PUBLIC_LOGIN_LOAD"
                if attempt == 0 or (link is not None and not await link.is_visible()):
                    await page.goto(entry_url, wait_until="domcontentloaded")
                await self._run_custom_steps(
                    page, reg.custom_steps, "before_open", task=task, password=password
                )
                limited = self._http_result(responses)
                if limited:
                    return limited
                if await self._security_check(page):
                    return Result(
                        State.NEEDS_REVIEW, "SECURITY_CHECK", "公共入口要求安全验证", pause=True
                    )
                if link is not None:
                    self.ui_step = "REGISTRATION_LINK"
                    await link.click(timeout=self._step_timeout(20000))
                await self._run_custom_steps(
                    page, reg.custom_steps, "before_fill", task=task, password=password
                )
                self.ui_step = "REGISTRATION_FORM_READY"
                ready_target = next(
                    (target for target in (
                        self._confirm_box(page), self._email_box(page),
                        self._password_box(page), self._submit_button(page),
                    ) if target is not None), None,
                )
                if ready_target is not None:
                    await ready_target.wait_for(
                        state="visible", timeout=self._step_timeout(15000)
                    )
                return None
            except BrowserTimeout:
                limited = self._http_result(responses)
                if limited:
                    return limited
                if await self._security_check(page):
                    return Result(
                        State.NEEDS_REVIEW, "SECURITY_CHECK", "公共入口要求安全验证", pause=True
                    )
                if attempt:
                    raise
        return None

    async def _fill_registration_form(
        self, page, email: str, password: str, task: Task | None = None
    ):
        """Fill the form and wait until Agnes enables the verification-code icon."""
        reg = self.settings.registration_flow
        self.ui_step = "REGISTRATION_FIELDS"
        email_box = self._email_box(page)
        if email_box is not None:
            await email_box.fill(email)
        password_box = self._password_box(page)
        if password_box is not None:
            await password_box.fill(password)
        confirm_box = self._confirm_box(page)
        if confirm_box is not None:
            await confirm_box.fill(password)
        await self._run_custom_steps(
            page, reg.custom_steps, "before_code", task=task, password=password
        )
        if self._verification_mode() == "none":
            return None
        self.ui_step = "SEND_CODE_READY"
        send = self._send_ready(page)
        trigger = self._send_trigger(page)
        if trigger is None:
            return None
        if send is None:
            send = trigger
        timeout = self._step_timeout(8000)
        if email_box is not None:
            await email_box.blur()
        try:
            await send.wait_for(state="visible", timeout=timeout)
            return trigger
        except BrowserTimeout:
            if email_box is None:
                raise
        await email_box.click()
        await email_box.fill("")
        await email_box.press_sequentially(email, delay=20)
        await email_box.press("Tab")
        await send.wait_for(state="visible", timeout=timeout)
        return trigger

    @staticmethod
    async def _security_check(page) -> bool:
        frames = page.locator(
            "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], "
            "iframe[src*='challenges.cloudflare.com']"
        )
        for index in range(await frames.count()):
            if await frames.nth(index).is_visible():
                return True
        return False

    @staticmethod
    def _http_result(responses) -> Result | None:
        for response in reversed(responses):
            if response.status == 403:
                return Result(
                    State.NEEDS_REVIEW, "SECURITY_CHECK", "平台要求安全核查，批次已暂停", pause=True
                )
            if response.status == 429:
                return Result(
                    State.RETRY_WAIT,
                    "RATE_LIMIT",
                    "平台限流，按等待时间暂停提交",
                    retry_after=retry_after(response.headers.get("retry-after")),
                    pause=True,
                    retry_known=bool(response.headers.get("retry-after")),
                )
        return None

    async def _save_session(self, task: Task, page, **updates) -> None:
        record = self.vault.get(task.secret_ref)
        record.update(updates)
        record["session_state"] = await page.context.storage_state()
        record["session_saved_at"] = time.time()
        self.vault.set(task.secret_ref, record)

    async def _identity_confirmed(self, page, task: Task) -> bool:
        if not self._trusted_page(page.url) or self._on_login_page(page.url):
            return False

        verify_mode = self.settings.login_flow.verify_mode
        if verify_mode == "url_or_token":
            # This opt-in, weaker mode does not bind the token to an email. A redirect
            # alone is never evidence: require a nonempty token AND a trusted non-login URL.
            token_key = configured(self.settings.login_flow.token_storage_key)
            if not token_key:
                return False
            return await page.evaluate(
                "(k) => Boolean((localStorage.getItem(k) || '').trim())", token_key
            )

        navigation = configured(self.settings.identity_navigation_selector)
        if navigation:
            await page.locator(navigation).click()
            await page.wait_for_timeout(500)
            if not self._trusted_page(page.url) or self._on_login_page(page.url):
                return False

        marker = self._flow_locator(
            page, self.settings.authenticated_selector,
            lambda: page.get_by_text(re.compile(r"^(退出登录|Log out|Sign out)$", re.I)),
        )
        if marker is None:
            return False
        marker_visible = bool(await marker.count()) and await marker.first.is_visible()
        if verify_mode == "selector_only":
            return marker_visible

        if self.settings.account_identity_selector.strip().casefold() == "none":
            return False
        identity_selector = configured(self.settings.account_identity_selector)
        if identity_selector:
            identity = page.locator(identity_selector)
            try:
                await identity.first.wait_for(
                    state="visible", timeout=self.settings.browser_timeout_ms
                )
            except BrowserTimeout:
                return False
            if await identity.count() != 1:
                return False
            value = await identity.evaluate("e => e.value === undefined ? e.textContent : e.value")
            email_matches = str(value).strip().casefold() == task.email.casefold()
        else:
            identity = page.get_by_text(task.email, exact=True)
            if navigation:
                try:
                    await identity.first.wait_for(
                        state="visible", timeout=self.settings.browser_timeout_ms
                    )
                except BrowserTimeout:
                    return False
            email_matches = await identity.count() == 1 and await identity.first.is_visible()
        return email_matches and marker_visible

    @staticmethod
    async def _business_error(page) -> Result | None:
        messages = [
            (
                "Registration is not allowed for this email domain",
                "EMAIL_DOMAIN_BLOCKED",
                "Agnes 不允许此邮箱域名注册",
                State.NEEDS_REVIEW,
                True,
            ),
            (
                "Too many registration attempts from this IP. Please try again later",
                "IP_REGISTRATION_LIMIT",
                "平台已限制此出口 IP 的注册请求，本批已暂停",
                State.NEEDS_REVIEW,
                True,
            ),
            (
                "Invalid verification code",
                "VERIFY_INVALID",
                "验证码无效，请重新核查验证步骤",
                State.PENDING_VERIFY,
                False,
            ),
            (
                "Email already exists",
                "DUPLICATE_EMAIL",
                "邮箱已存在，请核查已有账号",
                State.NEEDS_REVIEW,
                False,
            ),
        ]
        for text, code, message, state, pause in messages:
            locator = page.get_by_text(text, exact=True)
            if await locator.count() and await locator.first.is_visible():
                return Result(state, code, message, pause=pause)
        return None

    @staticmethod
    async def _response_business_error(responses) -> Result | None:
        for response in reversed(responses):
            if response.request.resource_type not in {"xhr", "fetch"}:
                continue
            try:
                payload = await asyncio.wait_for(response.json(), timeout=2)
            except (BrowserError, ValueError, asyncio.TimeoutError):
                continue
            if isinstance(payload, dict) and str(payload.get("code")) in {"403", "429"}:
                limited = str(payload.get("code")) == "429"
                return Result(
                    State.NEEDS_REVIEW,
                    "RATE_LIMIT" if limited else "SECURITY_CHECK",
                    "平台业务响应要求暂停",
                    pause=True,
                    retry_after=retry_after(response.headers.get("retry-after")),
                    retry_known=bool(response.headers.get("retry-after")),
                )
            if isinstance(payload, dict) and payload.get("message") == (
                "Too many registration attempts from this IP. Please try again later"
            ):
                return Result(
                    State.NEEDS_REVIEW,
                    "IP_REGISTRATION_LIMIT",
                    "平台已限制此出口 IP 的注册请求，本批已暂停",
                    pause=True,
                    retry_after=retry_after(response.headers.get("retry-after")),
                    retry_known=bool(response.headers.get("retry-after")),
                )
        return None

    def _build_mailbox(self, secret_ref: str) -> OutlookMailbox:
        v = self.settings.verification
        return OutlookMailbox(
            self.vault,
            secret_ref,
            sender_domain=v.sender_domain,
            code_pattern=v.code_pattern,
            imap_host=v.imap_host,
            imap_port=v.imap_port,
        )

    async def execute(
        self, task: Task, proxy: dict | None, checkpoint: Checkpoint, *, prepared_mailbox=None
    ) -> Result:
        record = self.vault.get(task.secret_ref)
        if not record or record.get("email", "").casefold() != task.email.casefold():
            return Result(State.NEEDS_REVIEW, "CREDENTIALS_MISSING", "此用户没有匹配的本地加密凭证")
        password = self.vault.ensure_account_password(task.secret_ref)
        if task.submitted_at is not None and task.phase not in {"PREPARE", "EMAIL_REQUESTED"}:
            return await self.reconcile(task, proxy, checkpoint)

        verify_mode = self._verification_mode()
        mailbox = None
        baseline = None
        if verify_mode == "none":
            pass
        elif prepared_mailbox is not None:
            mailbox, baseline = prepared_mailbox
        elif task.mailbox_authorized and record.get("mailbox_authorized"):
            mailbox = self._build_mailbox(task.secret_ref)
            try:
                baseline = await asyncio.to_thread(mailbox.baseline)
            except MailboxError as error:
                if verify_mode != "manual":
                    return Result(State.NEEDS_REVIEW, error.code, str(error))
        elif verify_mode != "manual":
            return Result(
                State.NEEDS_REVIEW,
                "VERIFY_AUTH_REQUIRED",
                "请启用人工验证，或配置此用户获准使用的邮箱验证工作流",
            )
        responses = []
        submitted = False
        registration_attempted = False
        reg_flow = self.settings.registration_flow
        try:
            async with self.browser.page(proxy) as page:

                def capture(response):
                    if self._host_matches(response.url) and (
                        response.request.resource_type in {"document", "xhr", "fetch"}
                    ):
                        responses.append(response)

                page.on("response", capture)
                entry_error = await self._open_registration(
                    page, responses, task=task, password=password
                )
                if entry_error:
                    return entry_error
                send_code = await self._fill_registration_form(
                    page, task.email, password, task=task
                )
                if await self._security_check(page):
                    return Result(
                        State.NEEDS_REVIEW, "SECURITY_CHECK", "注册页面要求人工安全验证", pause=True
                    )
                limited = self._http_result(responses)
                if limited:
                    return limited

                code = ""
                if verify_mode != "none" and send_code is not None:
                    await checkpoint("EMAIL_REQUESTED")
                    submitted = True
                    await send_code.click()
                    await page.wait_for_timeout(1200)
                    feedback = await self._business_error(
                        page
                    ) or await self._response_business_error(responses)
                    if feedback:
                        return feedback
                    limited = self._http_result(responses)
                    if limited:
                        await self._save_session(task, page, mailbox_baseline=baseline)
                        return limited
                    if await self._security_check(page):
                        return Result(
                            State.NEEDS_REVIEW,
                            "SECURITY_CHECK",
                            "验证码请求需要人工安全验证",
                            pause=True,
                        )
                    if mailbox and baseline:
                        try:
                            code = await asyncio.to_thread(
                                mailbox.wait_code,
                                baseline,
                                self.settings.verification_timeout_seconds,
                            )
                        except MailboxError as error:
                            await self._save_session(task, page, mailbox_baseline=baseline)
                            return Result(State.PENDING_VERIFY, error.code, str(error))
                    code_box = self._code_box(page)
                    if code and code_box is not None:
                        await code_box.fill(code)
                    elif verify_mode == "manual" and code_box is not None:
                        deadline = time.monotonic() + self.settings.verification_timeout_seconds
                        code_pat = self.settings.verification.code_pattern or r"\d{6}"
                        while time.monotonic() < deadline:
                            code = await code_box.input_value()
                            if code and re.search(code_pat, code):
                                break
                            await asyncio.sleep(0.5)
                    if not code and code_box is not None:
                        await self._save_session(task, page, mailbox_baseline=baseline)
                        return Result(
                            State.PENDING_VERIFY, "VERIFY_TIMEOUT", "验证码未到达，保留任务等待验证"
                        )

                await self._run_custom_steps(
                    page,
                    reg_flow.custom_steps,
                    "before_submit",
                    task=task,
                    password=password,
                    code=code or "",
                )
                await checkpoint("REGISTRATION_SUBMITTED")
                submitted = True
                registration_attempted = True
                submit_button = self._submit_button(page)
                if submit_button is not None:
                    await submit_button.click()
                await page.wait_for_timeout(1500)
                await self._run_custom_steps(
                    page,
                    reg_flow.custom_steps,
                    "after_submit",
                    task=task,
                    password=password,
                    code=code or "",
                )
                await self._save_session(task, page)
                feedback = (
                    await self._response_business_error(responses)
                    or await self._business_error(page)
                )
                if feedback:
                    return feedback
                limited = self._http_result(responses)
                if limited:
                    await self._save_session(task, page)
                    return limited
                not_contains = configured(reg_flow.success_url_not_contains)
                if not_contains:
                    try:
                        await page.wait_for_url(
                            lambda url: not_contains not in urlsplit(url).path,
                            timeout=min(10000, self.settings.browser_timeout_ms),
                        )
                    except BrowserTimeout:
                        return await self.reconcile(task, proxy, checkpoint, existing_page=page)
                await self._save_session(task, page)
                if not await self._identity_confirmed(page, task):
                    return await self.reconcile(task, proxy, checkpoint, existing_page=page)
                record = self.vault.get(task.secret_ref)
                record["activated"] = True
                self.vault.set(task.secret_ref, record)
                key = await self.collect_key(task, page, checkpoint)
                if key:
                    record = self.vault.get(task.secret_ref)
                    record.update(api_key=key, activated=True)
                    record.pop("session_state", None)
                    record.pop("mailbox_baseline", None)
                    self.vault.set(task.secret_ref, record)
                    return Result(
                        State.SUCCEEDED,
                        "ACTIVATED_WITH_KEY",
                        "账号和目标结果（API Key）已获取",
                        account_id="",
                        evidence="邮箱验证完成，登录后的结果页面已核验",
                    )
                if not self.settings.key_flow.enabled and not self.settings.key_flow.require_key:
                    return Result(
                        State.SUCCEEDED,
                        "ACTIVATED_WITH_KEY",
                        "账号注册与登录身份已确认（无需提取额外 Key）",
                        account_id="",
                        evidence="邮箱验证完成，登录后的账户界面已核验",
                    )
                return Result(
                    State.SUCCEEDED,
                    "KEY_PENDING",
                    "账号已登录，API Key 等待页面核验",
                    account_id="",
                    evidence="邮箱验证完成，登录后的账户界面显示匹配邮箱",
                )
        except BrowserTimeout:
            if registration_attempted:
                return await self.reconcile(task, proxy, checkpoint)
            return Result(
                State.UNKNOWN if submitted else State.NEEDS_REVIEW,
                "RESULT_TIMEOUT" if submitted else "SELECTOR_CHANGED",
                "提交后的结果未能确认" if submitted else "页面步骤超时：" + self.ui_step,
                pause=False,
            )
        except BrowserError as error:
            network = any(
                word in str(error)
                for word in (
                    "ERR_PROXY",
                    "ERR_TUNNEL",
                    "ERR_CONNECTION",
                    "ERR_NAME_NOT_RESOLVED",
                    "ERR_TIMED_OUT",
                )
            )
            return Result(
                State.UNKNOWN
                if submitted
                else (State.RETRY_WAIT if network else State.NEEDS_REVIEW),
                "NETWORK" if network else "BROWSER_FLOW",
                "网络连接失败" if network else "浏览器步骤无法完成，请检查页面流程",
                pause=False,
                proxy_failed=network and proxy is not None,
            )

    async def reconcile(
        self, task: Task, proxy: dict | None, checkpoint: Checkpoint, *, existing_page=None
    ) -> Result:
        record = self.vault.get(task.secret_ref)
        if not record or record.get("email", "").casefold() != task.email.casefold():
            return Result(State.NEEDS_REVIEW, "CREDENTIALS_MISSING", "此用户没有匹配的本地加密凭证")
        login_cfg = self.settings.login_flow
        login_path = login_cfg.login_path or "/login"
        password = record.get("agnes_password", "")
        try:
            context = self.browser.page(proxy, None) if existing_page is None else borrow_page(
                existing_page
            )
            async with context as page:
                already_inside = (
                    existing_page is not None
                    and self._trusted_page(page.url)
                    and not self._on_login_page(page.url)
                )
                if not already_inside:
                    response = await page.goto(
                        self._resolve_url(login_path), wait_until="domcontentloaded"
                    )
                    if response and response.status == 403:
                        return Result(
                            State.NEEDS_REVIEW, "SECURITY_CHECK", "登录核查被平台阻止", pause=True
                        )
                    if response and response.status == 429:
                        return Result(
                            State.NEEDS_REVIEW,
                            "RATE_LIMIT",
                            "登录核查限流，等待平台恢复",
                            retry_after=retry_after(response.headers.get("retry-after")),
                        )
                    await self._run_custom_steps(
                        page, login_cfg.custom_steps, "before_open", task=task, password=password
                    )
                    await self._run_custom_steps(
                        page, login_cfg.custom_steps, "before_fill", task=task, password=password
                    )
                    email_field = self._flow_locator(
                        page, login_cfg.email_selector,
                        lambda: page.get_by_role("textbox", name="邮箱", exact=True),
                    )
                    if email_field is not None:
                        ready = {
                            asyncio.create_task(email_field.wait_for(state="visible")),
                            asyncio.create_task(page.wait_for_url(
                                lambda url: not self._on_login_page(str(url)),
                                timeout=self.settings.browser_timeout_ms,
                            )),
                        }
                        try:
                            done, _ = await asyncio.wait(
                                ready, return_when=asyncio.FIRST_COMPLETED
                            )
                            if not any(item.exception() is None for item in done):
                                next(iter(done)).result()
                        finally:
                            for waiting in ready:
                                if not waiting.done():
                                    waiting.cancel()
                            await asyncio.gather(*ready, return_exceptions=True)
                    form_visible = email_field is None or (
                        await email_field.count() and await email_field.first.is_visible()
                    )
                    if form_visible:
                        if email_field is not None:
                            await email_field.fill(task.email)
                        pwd_field = self._flow_locator(
                            page, login_cfg.password_selector,
                            lambda: page.get_by_placeholder("请输入密码", exact=True),
                        )
                        if pwd_field is not None:
                            if not password:
                                return Result(
                                    State.NEEDS_REVIEW, "CREDENTIALS_MISSING",
                                    "未保存此用户的平台登录密码",
                                )
                            await pwd_field.fill(password)
                        await self._run_custom_steps(
                            page, login_cfg.custom_steps, "before_submit", task=task,
                            password=password,
                        )
                        submit_btn = self._flow_locator(
                            page, login_cfg.submit_selector,
                            lambda: page.get_by_role("button", name=re.compile(r"登\s*录")),
                        )
                        api_path = configured(login_cfg.login_api_path)
                        if api_path and submit_btn is not None:
                            async with page.expect_response(
                                lambda item: self._trusted_page(item.url)
                                and urlsplit(item.url).path == urlsplit(api_path).path
                                and item.request.method == "POST"
                            ) as login_response:
                                await submit_btn.click()
                            response = await login_response.value
                            limited = self._http_result([response])
                            if limited:
                                return limited
                            payload = await response.json()
                            if not isinstance(payload, dict) or str(payload.get("code")) != "200":
                                return Result(
                                    State.SKIPPED,
                                    "LOGIN_REJECTED",
                                    "登录被平台拒绝，按稳定优先原则放弃该账号",
                                )
                        elif submit_btn is not None:
                            await submit_btn.click()
                        # This stage can dismiss overlays or populate storage needed below.
                        await self._run_custom_steps(
                            page, login_cfg.custom_steps, "after_submit", task=task,
                            password=password,
                        )
                        token_key = configured(login_cfg.token_storage_key)
                        if token_key:
                            await page.wait_for_function(
                                "(k) => Boolean((localStorage.getItem(k) || '').trim())",
                                arg=token_key,
                            )
                        post_path = configured(login_cfg.post_login_path)
                        if post_path:
                            await page.goto(
                                self._resolve_url(post_path),
                                wait_until="domcontentloaded",
                            )
                    else:
                        await self._run_custom_steps(
                            page, login_cfg.custom_steps, "after_submit", task=task,
                            password=password,
                        )
                    await page.wait_for_url(
                        lambda url: not self._on_login_page(str(url)),
                        timeout=self.settings.browser_timeout_ms,
                    )
                if await self._security_check(page):
                    return Result(
                        State.NEEDS_REVIEW, "SECURITY_CHECK", "账号登录需要人工安全验证", pause=True
                    )
                if not await self._identity_confirmed(page, task):
                    await self._save_session(task, page)
                    return Result(
                        State.NEEDS_REVIEW,
                        "IDENTITY_NOT_CONFIRMED",
                        "页面已跳转，但尚未核验登录用户身份；请检查账户身份标记",
                    )
                record = self.vault.get(task.secret_ref)
                record["activated"] = True
                self.vault.set(task.secret_ref, record)
                await self._save_session(task, page)
                key = await self.collect_key(task, page, checkpoint)
                if key:
                    record = self.vault.get(task.secret_ref)
                    record["api_key"] = key
                    record.pop("session_state", None)
                    record.pop("mailbox_baseline", None)
                    self.vault.set(task.secret_ref, record)
                    return Result(
                        State.SUCCEEDED,
                        "ACTIVATED_WITH_KEY",
                        "账号和 API Key 已获取",
                        account_id="",
                        evidence="登录界面匹配邮箱，API Key 页面已核验",
                    )
                if not self.settings.key_flow.enabled and not self.settings.key_flow.require_key:
                    return Result(
                        State.SUCCEEDED,
                        "ACTIVATED_WITH_KEY",
                        "账号登录已核验通过（无需提取额外 Key）",
                        account_id="",
                        evidence="登录后的账户界面显示匹配邮箱",
                    )
                return Result(
                    State.SUCCEEDED,
                    "KEY_PENDING",
                    "账号已登录，API Key 等待页面核验",
                    account_id="",
                    evidence="登录后的账户界面显示匹配邮箱",
                )
        except BrowserTimeout:
            if record.get("activated"):
                return Result(
                    State.SUCCEEDED,
                    "KEY_PENDING",
                    "账号已激活，页面核查超时，等待后续重试获取 API Key",
                    account_id="",
                    evidence="本地凭证已确认账号激活",
                )
            return Result(
                State.UNKNOWN,
                "LOGIN_CHECK_FAILED",
                "登录核查页面响应超时，保留待后续重试",
                pause=False,
            )
        except (BrowserError, ValueError):
            return Result(
                State.UNKNOWN, "LOGIN_CHECK_FAILED", "浏览器登录核查未能完成", pause=False
            )

    def _key_used_elsewhere(self, task: Task, key: str | None) -> bool:
        if not key or not hasattr(self.vault, "snapshot"):
            return False
        for ref, record in self.vault.snapshot().items():
            if ref != task.secret_ref and record.get("api_key") == key:
                return True
        return False

    async def collect_key(self, task: Task, page, checkpoint: Checkpoint) -> str | None:
        record = self.vault.get(task.secret_ref)
        if record.get("api_key"):
            return record["api_key"]
        flow = self.settings.key_flow
        if not flow.enabled:
            return None

        captured = []
        custom_values: list[str] = []
        ambiguous = False

        def capture(response):
            if self._host_matches(response.url) and (
                response.request.resource_type in {"xhr", "fetch"}
            ):
                captured.append(response)

        page.on("response", capture)
        try:
            async def run_stage(stage):
                custom_values.extend(await self._run_custom_steps(
                    page, flow.custom_steps, stage, task=task,
                    password=record.get("agnes_password", ""),
                ))

            await run_stage("before_navigate")
            target_url = configured(flow.target_url)
            navigation_selector = configured(flow.navigation_selector)
            if target_url:
                await page.goto(
                    self._resolve_url(target_url), wait_until="domcontentloaded"
                )
                await page.wait_for_timeout(500)
            elif navigation_selector:
                await page.locator(self._render_template(navigation_selector, task)).click()
                await page.wait_for_timeout(500)
            if not self._trusted_page(page.url):
                return None

            await run_stage("before_extract")

            def matches(values):
                return {
                    match.group(0)
                    for value in values if value is not None
                    for match in re.finditer(flow.pattern, str(value))
                    if match.group(0)
                }

            async def read_storage():
                storage_key = configured(flow.storage_key)
                if not storage_key:
                    return set()
                raw = await page.evaluate("(k) => localStorage.getItem(k) || ''", storage_key)
                return matches([raw])

            async def read_dom():
                value_selector = configured(flow.value_selector)
                if not value_selector:
                    return set()
                target = page.locator(self._render_template(value_selector, task))
                values = await target.evaluate_all(
                    "es => es.map(e => e.value === undefined ? e.textContent : e.value)"
                )
                return matches(values)

            async def read_network():
                found = set()
                for response in list(captured):
                    if not 200 <= response.status < 300:
                        continue
                    try:
                        payload = await asyncio.wait_for(response.json(), timeout=2)
                    except (BrowserError, ValueError, asyncio.TimeoutError):
                        continue
                    stack = [payload]
                    while stack:
                        item = stack.pop()
                        if isinstance(item, str):
                            found.update(matches([item.strip()]))
                        elif isinstance(item, dict):
                            stack.extend(item.values())
                        elif isinstance(item, list):
                            stack.extend(item)
                return found

            async def read_copy():
                copy_selector = configured(flow.copy_selector)
                if not copy_selector:
                    return set()
                selector = self._render_template(copy_selector, task)
                target = page.locator(selector)
                if await target.count() != 1 or not await target.is_visible():
                    return set()
                try:
                    await page.context.grant_permissions(
                        ["clipboard-read", "clipboard-write"], origin=page.url
                    )
                except BrowserError:
                    pass
                await page.evaluate(
                    """() => {
                      window.__agnesCopiedKey = '';
                      const clipboard = navigator.clipboard;
                      if (clipboard && !clipboard.__agnesHooked) {
                        clipboard.__agnesHooked = true;
                        const original = clipboard.writeText.bind(clipboard);
                        clipboard.writeText = async (text) => {
                          window.__agnesCopiedKey = String(text || '');
                          try { return await original(text); } catch { return; }
                        };
                      }
                      if (!document.__agnesCopyHooked) {
                        document.__agnesCopyHooked = true;
                        document.addEventListener('copy', (event) => {
                          const board = event.clipboardData;
                          if (!board || board.__agnesHooked) return;
                          board.__agnesHooked = true;
                          const original = board.setData.bind(board);
                          board.setData = (type, value) => {
                            if (value) window.__agnesCopiedKey = String(value);
                            return original(type, value);
                          };
                        }, true);
                        const originalExec = document.execCommand.bind(document);
                        document.execCommand = (command, ...args) => {
                          if (String(command).toLowerCase() === 'copy') {
                            const selected = window.getSelection()
                              ? window.getSelection().toString() : '';
                            const active = document.activeElement;
                            const fromActive = active && (active.value || active.textContent);
                            const value = selected || fromActive || '';
                            if (value) window.__agnesCopiedKey = value;
                          }
                          try { return originalExec(command, ...args); } catch { return false; }
                        };
                      }
                    }"""
                )
                await target.click()
                deadline = time.monotonic() + self._step_timeout(2000) / 1000
                while time.monotonic() < deadline:
                    hooked = await page.evaluate("window.__agnesCopiedKey || ''")
                    found = matches([hooked])
                    if found:
                        await page.evaluate("window.__agnesCopiedKey = ''")
                        try:
                            await page.evaluate("navigator.clipboard.writeText('')")
                        except BrowserError:
                            pass
                        return found
                    await asyncio.sleep(0.2)
                return set()

            async def try_extract():
                nonlocal ambiguous
                if not self._trusted_page(page.url):
                    return None
                mode = flow.extract_mode
                found = matches(custom_values)
                for source_mode, reader in (
                    ("local_storage", read_storage), ("dom_regex", read_dom),
                    ("network_json", read_network), ("clipboard_copy", read_copy),
                ):
                    if mode in {"auto", source_mode}:
                        found.update(await reader())
                if len(found) > 1:
                    ambiguous = True
                if len(found) != 1:
                    return None
                candidate = next(iter(found))
                if self._key_used_elsewhere(task, candidate):
                    ambiguous = True
                    return None
                return candidate

            # Custom extraction is honored even when a create button is configured or
            # the built-in extractor already has a candidate.
            await run_stage("extract")
            candidate = await try_extract()
            if candidate:
                return candidate
            if ambiguous:
                return None
            create_selector = configured(flow.create_selector)
            creation_started = (
                record.get("api_key_creation_started") or task.phase == "KEY_REQUESTED"
            )
            if create_selector and not creation_started:
                await page.locator(create_selector).wait_for(state="visible")
                # Persist the boundary before the FIRST potentially mutating click.
                await checkpoint("KEY_REQUESTED")
                record = self.vault.get(task.secret_ref)
                record["api_key_creation_started"] = True
                if hasattr(self.vault, "set"):
                    self.vault.set(task.secret_ref, record)
                await page.locator(create_selector).click()
                name_selector = configured(flow.name_selector)
                if name_selector:
                    await page.locator(name_selector).fill(self._render_template(
                        flow.name_template or "Agnes Provisioner {user_id}", task
                    ))
                confirm_selector = configured(flow.confirm_selector)
                if confirm_selector:
                    await page.locator(confirm_selector).click()
                await run_stage("after_create")
                await run_stage("extract")
            # Do not reload or assume Agnes modal selectors: one-time secrets may only
            # exist on this page. A resumed creation is extraction-only, never recreated.
            deadline = time.monotonic() + self.settings.browser_timeout_ms / 1000
            while time.monotonic() < deadline:
                key = await try_extract()
                if key:
                    return key
                if ambiguous:
                    return None
                if not self._trusted_page(page.url):
                    return None
                await asyncio.sleep(0.25)
            return None
        finally:
            try:
                page.remove_listener("response", capture)
            except Exception:
                pass

    async def close(self) -> None:
        await self.browser.close()
