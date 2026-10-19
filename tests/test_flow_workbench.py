from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.async_api import Error as BrowserError

from agnes_provisioner.agnes import AgnesAdapter, borrow_page
from agnes_provisioner.config import (
    KEY_STAGES,
    LOGIN_STAGES,
    REGISTRATION_STAGES,
    FlowStep,
    KeyFlow,
    LoginFlow,
    RegistrationFlow,
    Settings,
    VerificationFlow,
    load_settings,
    save_settings,
)
from agnes_provisioner.domain import State, Task
from agnes_provisioner.vault import Vault

ORIGIN = "http://127.0.0.1:18765"
PASSWORD = "LocalFlowTest123!"
RESULT = "result_OnlyThisUser123"


def task_for(phase="PREPARE"):
    return Task(
        "job", "batch", "user", "user@example.com", "测试用户", "user", False, 1,
        phase, None if phase == "PREPARE" else 1.0, None,
    )


def local_settings(**kwargs):
    return Settings(
        headless=True, browser_timeout_ms=1000, base_url=ORIGIN,
        allow_custom_base_url=True, cache_public_assets=False, **kwargs,
    )


def local_vault(tmp_path):
    vault = Vault(tmp_path / "test-flow.dpapi")
    vault.set("user", {"email": "user@example.com", "agnes_password": PASSWORD})
    return vault


def script_step(stage, script, **kwargs):
    return FlowStep(stage=stage, action="evaluate_js", value=script, optional=False, **kwargs)


async def fulfill_html(route, html):
    await route.fulfill(body=html, content_type="text/html; charset=utf-8")


def test_flow_steps_roundtrip_order_enabled_and_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        database=Path("data/jobs.db"), vault=Path("data/vault.dpapi"),
        registration_flow=RegistrationFlow(custom_steps=[
            FlowStep(stage="before_code", action="check", selector="#agree", note='同意 "条款"'),
            FlowStep(stage="before_code", action="click", enabled=False),
            FlowStep(stage="before_code", action="wait_ms", value="10"),
        ]),
        login_flow=LoginFlow(custom_steps=[
            FlowStep(stage="before_submit", action="fill", selector="#alias", value="{email}")
        ]),
    )
    path = tmp_path / "config" / "config.local.toml"
    save_settings(settings, path)
    restored = load_settings(path)
    assert restored.database == (tmp_path / "data/jobs.db").resolve()
    assert restored.vault == (tmp_path / "data/vault.dpapi").resolve()
    assert restored.registration_flow == settings.registration_flow
    assert restored.login_flow == settings.login_flow
    assert [s.enabled for s in restored.registration_flow.custom_steps] == [True, False, True]
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))

    # Repeated writes from loaded absolute paths must not relocate the credential store.
    save_settings(restored, path)
    assert load_settings(path).vault == restored.vault


def test_save_settings_uses_relative_paths_inside_config_directory(tmp_path):
    settings = Settings(database=tmp_path / "data/jobs.db", vault=tmp_path / "data/vault.dpapi")
    path = tmp_path / "config.local.toml"
    save_settings(settings, path)
    assert 'database = "data/jobs.db"' in path.read_text("utf-8")
    assert load_settings(path).database == settings.database


def test_save_settings_replace_failure_preserves_original(tmp_path, monkeypatch):
    path = tmp_path / "config.local.toml"
    save_settings(Settings(), path)
    original = path.read_bytes()

    def fail_replace(source, destination):
        assert Path(source).parent == path.parent
        assert Path(destination) == path
        assert Path(source).read_text("utf-8")
        raise PermissionError("simulated locked destination")

    monkeypatch.setattr("agnes_provisioner.config.os.replace", fail_replace)
    with pytest.raises(PermissionError):
        save_settings(Settings(concurrency=2), path)
    assert path.read_bytes() == original
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_save_settings_validation_failure_preserves_original(tmp_path):
    path = tmp_path / "config.local.toml"
    settings = Settings()
    save_settings(settings, path)
    original = path.read_bytes()
    settings.verification.code_pattern = "["
    with pytest.raises(ValueError, match="正则表达式无效"):
        save_settings(settings, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("model,field", [(VerificationFlow, "code_pattern"), (KeyFlow, "pattern")])
@pytest.mark.parametrize("pattern", ["[", "(?P<bad", "", ".*", "a{99999999999999999999999}"])
def test_invalid_patterns_are_value_errors(model, field, pattern):
    with pytest.raises(ValueError, match="正则表达式无效|不能匹配空文本"):
        model(**{field: pattern})


@pytest.mark.parametrize("action", [
    "click", "check", "fill", "press", "wait_selector", "extract_text",
])
def test_selector_actions_require_selector_but_disabled_drafts_are_retained(action):
    with pytest.raises(ValueError, match="selector"):
        FlowStep(action=action)
    assert not FlowStep(action=action, enabled=False).enabled
    assert FlowStep(action=action, selector="none").enabled


@pytest.mark.parametrize("action", ["goto", "extract_storage", "evaluate_js"])
def test_value_actions_require_a_value(action):
    with pytest.raises(ValueError, match="value"):
        FlowStep(action=action)


@pytest.mark.parametrize("value", ["-1", "60001", "nan", "inf", "not-a-number"])
def test_wait_ms_validation(value):
    with pytest.raises(ValueError, match="毫秒数"):
        FlowStep(action="wait_ms", value=value)


@pytest.mark.parametrize("value", ["javascript:alert(1)", "file:///etc/passwd", "https:/invalid"])
def test_goto_rejects_invalid_or_executable_urls(value):
    with pytest.raises(ValueError, match="http/https"):
        FlowStep(action="goto", value=value)


@pytest.mark.parametrize("model,stages", [
    (RegistrationFlow, REGISTRATION_STAGES), (LoginFlow, LOGIN_STAGES), (KeyFlow, KEY_STAGES),
])
def test_only_executable_flow_stages_are_accepted(model, stages):
    assert model(custom_steps=[FlowStep(stage=s, action="wait_ms") for s in stages])
    wrong = "extract" if model is not KeyFlow else "before_submit"
    with pytest.raises(ValueError, match="不支持阶段"):
        model(custom_steps=[FlowStep(stage=wrong, action="wait_ms")])
    with pytest.raises(ValueError):
        FlowStep(stage="typo", action="wait_ms")


def test_extraction_source_configuration_is_explicit():
    assert KeyFlow(enabled=True, extract_mode="network_json", target_url="/results")
    assert KeyFlow(enabled=True, extract_mode="clipboard_copy", copy_selector="#copy")
    assert KeyFlow(enabled=True, extract_mode="local_storage", storage_key="result")
    assert KeyFlow(enabled=True, extract_mode="dom_regex", value_selector="#value")
    assert KeyFlow(enabled=True, custom_steps=[script_step("extract", "() => 'a result'")])
    for mode, field in [
        ("dom_regex", "value_selector"), ("clipboard_copy", "copy_selector"),
        ("local_storage", "storage_key"),
    ]:
        with pytest.raises(ValueError, match=field):
            KeyFlow(enabled=True, extract_mode=mode, **{field: "none"})
    with pytest.raises(ValueError, match="提取源"):
        KeyFlow(enabled=True, target_url="/results")
    with pytest.raises(ValueError, match="提取源"):
        KeyFlow(enabled=True, custom_steps=[script_step("extract", "() => 'x'", enabled=False)])
    with pytest.raises(ValueError, match="token_storage_key"):
        LoginFlow(verify_mode="url_or_token", token_storage_key="none")


async def test_custom_step_actions_templates_order_optional_and_enabled(tmp_path):
    adapter = AgnesAdapter(local_settings(), local_vault(tmp_path))
    html = """<input id="email"><input id="code"><input id="enter">
    <input id="agree" type="checkbox"><button id="click" onclick="window.clicked=true">点我</button>
    <script>document.querySelector('#enter').onkeydown=e=>window.pressed=e.key;</script>"""
    steps = [
        FlowStep(action="goto", value="/actions"),
        FlowStep(action="fill", selector="#email", value="{email}:{user_id}:{password}"),
        FlowStep(action="fill", selector="#code", value="{code}"),
        FlowStep(action="check", selector="#agree"),
        FlowStep(action="press", selector="#enter", value="Enter"),
        FlowStep(action="click", selector="#click"),
        FlowStep(action="wait_selector", selector="#agree"),
        FlowStep(action="wait_ms", value="1"),
        FlowStep(action="click", selector="#does-not-exist", enabled=False, optional=False),
        FlowStep(action="click", selector="none", optional=False),
        FlowStep(action="evaluate_js", value="none", optional=False),
        script_step(
            "after_submit", "() => {localStorage.setItem('result','stored'); return 'js';}"
        ),
        FlowStep(action="extract_text", selector="#email"),
        FlowStep(action="extract_storage", value="result"),
        script_step("after_submit", "() => { throw new Error('optional'); }").model_copy(
            update={"optional": True}
        ),
    ]
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, html))
            values = await adapter._run_custom_steps(
                page, steps, "after_submit", task=task_for(), password=PASSWORD, code="123456"
            )
            assert values == ["js", f"user@example.com:user:{PASSWORD}", "stored"]
            assert await page.locator("#code").input_value() == "123456"
            assert await page.locator("#agree").is_checked()
            assert await page.evaluate("window.clicked && window.pressed === 'Enter'")
            with pytest.raises(BrowserError):
                await adapter._run_custom_steps(page, [
                    script_step("after_submit", "() => {throw new Error('required');}")
                ], "after_submit")
    finally:
        await adapter.close()


async def test_no_verification_registration_runs_every_stage_and_checkpoints_before_submit(
    tmp_path, monkeypatch
):
    steps = [
        script_step("before_open", "() => {window.trace=['before_open'];}"),
        script_step("before_fill", "() => {window.trace.push('before_fill');}"),
        script_step("before_code", f"""() => {{
          if(document.querySelector('#email').value !== 'user@example.com' ||
             document.querySelector('#password').value !== '{PASSWORD}') throw Error('order');
          window.trace.push('before_code'); }}"""),
        FlowStep(stage="before_code", action="check", selector="#agree", optional=False),
        FlowStep(stage="before_code", action="click", selector="#missing", enabled=False),
        FlowStep(stage="before_submit", action="fill", selector="#code", value="{code}"),
        script_step("before_submit", "() => {window.trace.push('before_submit');}"),
        script_step("after_submit", "() => {window.trace.push('after_submit');}"),
    ]
    settings = local_settings(
        verification=VerificationFlow(mode="none"), manual_verification=True,
        registration_flow=RegistrationFlow(
            entry_path="/signup", open_register_selector="none", email_selector="#email",
            password_selector="#password", confirm_password_selector="none",
            send_code_ready_selector="#must-not-wait", send_code_click_selector="#must-not-send",
            submit_button_selector="#submit", custom_steps=steps,
        ),
        key_flow=KeyFlow(require_key=False),
    )
    html = """<input id="email"><input id="password"><input id="code" value="untouched">
    <input id="agree" type="checkbox"><button id="submit" onclick="
      if(!document.querySelector('#agree').checked) throw Error('agreement');
      window.submitted=true;history.pushState({},'', '/home');
      document.querySelector('#identity').textContent='user@example.com';">注册</button>
    <div id="identity"></div><button>退出登录</button>"""
    vault = local_vault(tmp_path)
    adapter = AgnesAdapter(settings, vault)
    phases = []
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, html))
            monkeypatch.setattr(adapter.browser, "page", lambda *a, **k: borrow_page(page))

            async def checkpoint(phase):
                assert not await page.evaluate("Boolean(window.submitted)")
                phases.append(phase)

            result = await adapter.execute(task_for(), None, checkpoint)
            assert result.state == State.SUCCEEDED
            assert phases == ["REGISTRATION_SUBMITTED"]
            assert await page.evaluate("window.trace") == list(REGISTRATION_STAGES)
            assert await page.locator("#code").input_value() == ""
            assert vault.get("user")["activated"]
            assert not vault.get("user").get("api_key")
    finally:
        await adapter.close()


async def test_none_skips_all_registration_selectors_without_default_fallback(
    tmp_path, monkeypatch
):
    settings = local_settings(
        verification=VerificationFlow(mode="none"),
        registration_flow=RegistrationFlow(
            entry_path="/signup", open_register_selector="none", email_selector="none",
            password_selector="none", confirm_password_selector="none",
            send_code_ready_selector="none", send_code_click_selector="none",
            code_input_selector="none", submit_button_selector="none",
            success_url_not_contains="none", custom_steps=[
                FlowStep(stage="after_submit", action="goto", value="/home", optional=False)
            ],
        ),
        key_flow=KeyFlow(require_key=False),
    )
    adapter = AgnesAdapter(settings, local_vault(tmp_path))
    html = "<div>user@example.com</div><button>退出登录</button>"
    phases = []
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, html))
            monkeypatch.setattr(adapter.browser, "page", lambda *a, **k: borrow_page(page))

            async def checkpoint(phase):
                phases.append(phase)

            result = await adapter.execute(task_for(), None, checkpoint)
            assert result.state == State.SUCCEEDED
            assert phases == ["REGISTRATION_SUBMITTED"]
            assert page.url == ORIGIN + "/home"
    finally:
        await adapter.close()


async def test_login_stages_run_before_token_wait_and_extract_from_existing_account(
    tmp_path, monkeypatch
):
    settings = local_settings(
        account_identity_selector="#identity", authenticated_selector="#logout",
        login_flow=LoginFlow(
            login_path="/signin", email_selector="#email", password_selector="#password",
            submit_selector="#submit", login_api_path="none", post_login_path="none",
            custom_steps=[
                script_step("before_open", "() => {window.trace=['before_open'];}"),
                script_step("before_fill", "() => {window.trace.push('before_fill');}"),
                script_step("before_submit", f"""() => {{
                  if(document.querySelector('#email').value !== 'user@example.com' ||
                     document.querySelector('#password').value !== '{PASSWORD}')
                    throw Error('order');
                  window.trace.push('before_submit'); }}"""),
                FlowStep(stage="before_submit", action="check", selector="#agree", optional=False),
                script_step("after_submit", f"""() => {{
                  window.trace.push('after_submit');localStorage.setItem('token','logged-in');
                  localStorage.setItem('result','{RESULT}'); }}"""),
            ],
        ),
        key_flow=KeyFlow(enabled=True, extract_mode="local_storage", storage_key="result",
                         pattern=r"result_[A-Za-z0-9]+"),
    )
    html = """<input id="email"><input id="password"><input id="agree" type="checkbox">
    <button id="submit" onclick="if(!document.querySelector('#agree').checked)throw Error('order');
      history.pushState({},'', '/home');document.querySelector('#identity').hidden=false;
      document.querySelector('#logout').hidden=false;">登录</button>
    <div id="identity" hidden>user@example.com</div><button id="logout" hidden>退出登录</button>"""
    vault = local_vault(tmp_path)
    adapter = AgnesAdapter(settings, vault)
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, html))
            monkeypatch.setattr(adapter.browser, "page", lambda *a, **k: borrow_page(page))

            async def no_mutation(phase):
                pytest.fail(f"Existing account must not register/create: {phase}")

            result = await adapter.execute(task_for("REGISTRATION_SUBMITTED"), None, no_mutation)
            assert result.state == State.SUCCEEDED and result.code == "ACTIVATED_WITH_KEY"
            assert await page.evaluate("window.trace") == list(LOGIN_STAGES)
            assert vault.get("user")["api_key"] == RESULT
            assert "session_state" not in vault.get("user")
    finally:
        await adapter.close()


async def test_login_none_selectors_support_a_custom_login_without_default_waits(
    tmp_path, monkeypatch
):
    settings = local_settings(
        login_flow=LoginFlow(
            login_path="/signin", email_selector="none", password_selector="none",
            submit_selector="none", token_storage_key="none", post_login_path="none",
            custom_steps=[FlowStep(stage="after_submit", action="goto", value="/home")],
        ),
        key_flow=KeyFlow(require_key=False),
    )
    vault = local_vault(tmp_path)
    vault.set("user", {"email": "user@example.com"})
    adapter = AgnesAdapter(settings, vault)
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(
                route, "<div>user@example.com</div><button>退出登录</button>"
            ))
            monkeypatch.setattr(adapter.browser, "page", lambda *a, **k: borrow_page(page))

            async def no_mutation(phase):
                pytest.fail(phase)

            result = await adapter.reconcile(task_for("REGISTRATION_SUBMITTED"), None, no_mutation)
            assert result.state == State.SUCCEEDED
    finally:
        await adapter.close()


@pytest.mark.parametrize("status,code,expected", [
    (200, 200, "ACTIVATED_WITH_KEY"), (200, 401, "LOGIN_REJECTED"),
    (403, 403, "SECURITY_CHECK"), (429, 429, "RATE_LIMIT"),
])
async def test_configured_login_api_respects_business_and_http_rejections(
    tmp_path, monkeypatch, status, code, expected
):
    settings = local_settings(
        login_flow=LoginFlow(
            login_path="/signin", email_selector="#email", password_selector="#password",
            submit_selector="#submit", token_storage_key="none", post_login_path="none",
        ),
        key_flow=KeyFlow(require_key=False),
    )
    html = """<input id="email"><input id="password"><button id="submit" onclick="
      fetch('/api/user/login',{method:'POST'}).then(r=>r.json()).then(data=>{
      if(data.code===200){history.pushState({},'', '/home');
      document.querySelector('#identity').hidden=false;
      document.querySelector('#logout').hidden=false;}});">登录</button>
      <div id="identity" hidden>user@example.com</div>
      <button id="logout" hidden>退出登录</button>"""
    adapter = AgnesAdapter(settings, local_vault(tmp_path))
    try:
        async with adapter.browser.page() as page:
            async def route(interception):
                if urlsplit(interception.request.url).path == "/api/user/login":
                    await interception.fulfill(status=status, json={"code": code})
                else:
                    await fulfill_html(interception, html)

            await page.route("**/*", route)
            monkeypatch.setattr(adapter.browser, "page", lambda *a, **k: borrow_page(page))

            async def no_mutation(phase):
                pytest.fail(phase)

            result = await adapter.reconcile(task_for("REGISTRATION_SUBMITTED"), None, no_mutation)
            assert result.code == expected
            assert bool(adapter.vault.get("user").get("activated")) == (code == 200)
    finally:
        await adapter.close()


async def test_login_verification_modes_never_accept_redirect_alone_or_foreign_origin(tmp_path):
    settings = local_settings(
        account_identity_selector="#identity", authenticated_selector="#logout"
    )
    adapter = AgnesAdapter(settings, local_vault(tmp_path))
    cases = [
        ("strict_identity", ORIGIN + "/home", "user@example.com", True, "", True),
        ("strict_identity", ORIGIN + "/home", "other@example.com", True, "token", False),
        ("strict_identity", ORIGIN + "/home", "user@example.com", False, "token", False),
        ("selector_only", ORIGIN + "/home", "other@example.com", True, "", True),
        ("selector_only", ORIGIN + "/home", "user@example.com", False, "token", False),
        ("url_or_token", ORIGIN + "/home", "", False, "", False),
        ("url_or_token", ORIGIN + "/home", "", False, "   ", False),
        ("url_or_token", ORIGIN + "/home", "", False, "token", True),
        ("url_or_token", ORIGIN + "/signin/error", "", True, "token", False),
        ("url_or_token", "http://127.0.0.1:18766/home", "", True, "token", False),
        ("selector_only", "http://other.example/home", "user@example.com", True, "token", False),
    ]
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, "<div></div>"))
            for mode, url, email, marker, token, expected in cases:
                settings.login_flow = LoginFlow(verify_mode=mode, login_path="/signin")
                await page.goto(url)
                await page.set_content(
                    f'<div id="identity">{email}</div>'
                    f'<button id="logout" {"" if marker else "hidden"}>退出登录</button>'
                )
                await page.evaluate("t => localStorage.setItem('token', t)", token)
                assert await adapter._identity_confirmed(page, task_for()) is expected, (mode, url)
    finally:
        await adapter.close()


async def test_strict_identity_rejects_duplicate_and_hidden_email_evidence(tmp_path):
    settings = local_settings(
        account_identity_selector="#identity", authenticated_selector="#logout"
    )
    adapter = AgnesAdapter(settings, local_vault(tmp_path))
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, "<div></div>"))
            await page.goto(ORIGIN + "/home")
            await page.set_content(
                '<div id="identity">user@example.com</div>'
                '<div id="identity">other@example.com</div>'
                '<button id="logout">退出登录</button>'
            )
            assert not await adapter._identity_confirmed(page, task_for())
            await page.set_content(
                '<input id="identity" value="user@example.com" hidden>'
                '<button id="logout">退出登录</button>'
            )
            assert not await adapter._identity_confirmed(page, task_for())
    finally:
        await adapter.close()


@pytest.mark.parametrize("mode", [
    "dom_regex", "network_json", "clipboard_copy", "local_storage", "auto",
])
@pytest.mark.parametrize("with_confirm", [False, True])
async def test_key_modes_and_stages_after_creation_without_reload(tmp_path, mode, with_confirm):
    flow = KeyFlow(
        enabled=True, target_url="/results", extract_mode=mode,
        create_selector="#create", confirm_selector="#confirm" if with_confirm else "none",
        name_selector="#name" if with_confirm else "none",
        value_selector="#value", copy_selector="#copy", storage_key="result",
        pattern=r"result_[A-Za-z0-9]+",
        custom_steps=[
            script_step(
                "before_navigate", "() => {localStorage.setItem('trace','before_navigate');}"
            ),
            script_step("before_extract", "() => {localStorage.trace += ',before_extract';}"),
            script_step("after_create", "() => {localStorage.trace += ',after_create';}"),
            script_step("extract", "() => {localStorage.trace += ',extract';}"),
        ],
    )
    adapter = AgnesAdapter(local_settings(key_flow=flow), local_vault(tmp_path))
    finish = "document.querySelector('#dialog').hidden=false" if with_confirm else "finish()"
    dom_result = RESULT if mode in {"dom_regex", "auto"} else "result_WrongDom"
    storage_result = RESULT if mode in {"local_storage", "auto"} else "result_WrongStorage"
    copy_result = RESULT if mode in {"clipboard_copy", "auto"} else "result_WrongClipboard"
    network_result = RESULT if mode in {"network_json", "auto"} else "result_WrongNetwork"
    html = f"""<div class="ant-modal">Not an Agnes modal; never wait for this to close</div>
    <div id="value">masked</div><button id="create" onclick="{finish}">创建</button>
    <div id="dialog" hidden><input id="name">
      <button id="confirm" onclick="finish()">确认</button></div>
    <button id="copy" hidden onclick="navigator.clipboard.writeText('{copy_result}')">复制</button>
    <script>window.created=0;function finish(){{
      window.created++;document.querySelector('#value').textContent='{dom_result}';
      localStorage.setItem('result','{storage_result}');document.querySelector('#copy').hidden=false;
      fetch('/key',{{method:'POST'}}); }}</script>"""
    phases = []
    loads = []
    try:
        async with adapter.browser.page() as page:
            async def route(interception):
                if urlsplit(interception.request.url).path == "/key":
                    await interception.fulfill(json={"data": {"secret": network_result}})
                else:
                    loads.append(interception.request.url)
                    await fulfill_html(interception, html)

            await page.route("**/*", route)
            await page.goto(ORIGIN + "/home")

            async def checkpoint(phase):
                assert await page.evaluate("window.created") == 0
                assert not adapter.vault.get("user").get("api_key_creation_started")
                phases.append(phase)

            assert await adapter.collect_key(task_for(), page, checkpoint) == RESULT
            assert phases == ["KEY_REQUESTED"]
            assert adapter.vault.get("user")["api_key_creation_started"]
            assert await page.evaluate("window.created") == 1
            assert await page.evaluate("localStorage.trace") == (
                "before_navigate,before_extract,extract,after_create,extract"
            )
            assert loads == [ORIGIN + "/home", ORIGIN + "/results"]
            if with_confirm:
                assert await page.locator("#name").input_value() == "Agnes Provisioner user"
    finally:
        await adapter.close()


@pytest.mark.parametrize("stage", KEY_STAGES)
async def test_custom_key_extraction_outputs_from_every_stage_are_used(tmp_path, stage):
    flow = KeyFlow(
        enabled=True, target_url="none", navigation_selector="none", create_selector="#create",
        pattern=r"result_[A-Za-z0-9]+", custom_steps=[script_step(stage, f"() => '{RESULT}'")],
    )
    adapter = AgnesAdapter(local_settings(key_flow=flow), local_vault(tmp_path))
    phases = []
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(
                route, '<button id="create" onclick="window.created=true">创建</button>'
            ))
            await page.goto(ORIGIN + "/results")

            async def checkpoint(phase):
                phases.append(phase)

            assert await adapter.collect_key(task_for(), page, checkpoint) == RESULT
            assert phases == (["KEY_REQUESTED"] if stage == "after_create" else [])
            assert await page.evaluate("Boolean(window.created)") == (stage == "after_create")
    finally:
        await adapter.close()


@pytest.mark.parametrize("reason", ["phase", "vault", "ambiguous", "another_user"])
async def test_key_recovery_and_ambiguous_results_never_create_again(tmp_path, reason):
    flow = KeyFlow(
        enabled=True, value_selector="#value", create_selector="#create",
        confirm_selector="#confirm", copy_selector="none", pattern=r"result_[A-Za-z0-9]+",
    )
    vault = local_vault(tmp_path)
    if reason == "vault":
        record = vault.get("user")
        vault.set("user", {**record, "api_key_creation_started": True})
    elif reason == "another_user":
        vault.set("other", {"api_key": RESULT})
    text = f"{RESULT} result_AnotherSecret" if reason == "ambiguous" else (
        RESULT if reason == "another_user" else "masked"
    )
    adapter = AgnesAdapter(local_settings(key_flow=flow), vault)
    task = replace(task_for(), phase="KEY_REQUESTED") if reason == "phase" else task_for()
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, f"""
                <div id="value">{text}</div>
                <button id="create" onclick="window.created=true">创建</button>
                <button id="confirm" onclick="window.confirmed=true">确认</button>"""))
            await page.goto(ORIGIN + "/results")

            async def no_mutation(phase):
                pytest.fail(f"Must be extraction-only: {phase}")

            assert await adapter.collect_key(task, page, no_mutation) is None
            assert not await page.evaluate("Boolean(window.created || window.confirmed)")
    finally:
        await adapter.close()


async def test_key_auto_ambiguity_across_sources_does_not_create(tmp_path):
    flow = KeyFlow(
        enabled=True, value_selector="#value", storage_key="result", create_selector="#create",
        pattern=r"result_[A-Za-z0-9]+",
    )
    adapter = AgnesAdapter(local_settings(key_flow=flow), local_vault(tmp_path))
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, f"""
                <div id="value">{RESULT}</div>
                <button id="create" onclick="window.created=true">创建</button>"""))
            await page.goto(ORIGIN + "/results")
            await page.evaluate("localStorage.setItem('result','result_DifferentAccount')")

            async def no_mutation(phase):
                pytest.fail(phase)

            assert await adapter.collect_key(task_for(), page, no_mutation) is None
            assert not await page.evaluate("Boolean(window.created)")
    finally:
        await adapter.close()


@pytest.mark.parametrize("failure", ["checkpoint", "vault"])
async def test_key_creation_does_not_click_when_persisting_boundary_fails(
    tmp_path, monkeypatch, failure
):
    flow = KeyFlow(enabled=True, value_selector="#value", create_selector="#create")
    adapter = AgnesAdapter(local_settings(key_flow=flow), local_vault(tmp_path))
    try:
        async with adapter.browser.page() as page:
            await page.route("**/*", lambda route: fulfill_html(route, """
                <div id="value"></div>
                <button id="create" onclick="window.created=true">创建</button>
            """))
            await page.goto(ORIGIN + "/results")

            def fail_vault(*args):
                raise RuntimeError("simulated persist failure")

            async def checkpoint(phase):
                assert phase == "KEY_REQUESTED"
                if failure == "checkpoint":
                    raise RuntimeError("simulated persist failure")

            if failure == "vault":
                monkeypatch.setattr(adapter.vault, "set", fail_vault)
            with pytest.raises(RuntimeError, match="persist failure"):
                await adapter.collect_key(task_for(), page, checkpoint)
            assert not await page.evaluate("Boolean(window.created)")
    finally:
        await adapter.close()
