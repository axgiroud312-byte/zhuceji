"""Legacy API/CLI compatibility; runtime browser acceptance lives in test_runtime_ui.py.

ISS-006 supersedes the old five-view/node-editor DOM assertions. Keep the backend
regressions here without preserving obsolete product entry points in the new UI.
"""
from __future__ import annotations

import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from agnes_provisioner.config import Settings, save_settings
from agnes_provisioner.proxy import ProxyManager
from agnes_provisioner.storage import Storage
from agnes_provisioner.users import import_accounts_flexible, parse_accounts_text
from agnes_provisioner.vault import Vault
from agnes_provisioner.web import WebAppController, make_handler


@pytest.fixture
def workbench(tmp_path):
    config = tmp_path / "config.local.toml"
    save_settings(
        Settings(mode="mock", database=tmp_path / "jobs.db", vault=tmp_path / "vault.dpapi",
                 per_minute=100000, retry_delay_seconds=0), config
    )
    controller = WebAppController(config)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(controller))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with httpx.Client(base_url=base, trust_env=False, timeout=15) as client:
            yield controller, client, base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def import_demo(controller, batch="demo", content=None):
    controller.import_accounts({
        "content": content or "alice@example.com----Pass1!\nbob@example.com----Pass2!",
        "batch_id": batch,
    })
    return controller.list_jobs(batch, reveal_secrets=True)["jobs"]


def test_api_privacy_validation_and_consistent_backup(workbench):
    controller, client, _ = workbench
    jobs = import_demo(controller)
    job_id = jobs[0]["job_id"]
    masked = client.get("/api/jobs").json()["jobs"][0]
    assert masked["raw_email"] == masked["agnes_password"] == masked["api_key"] == ""
    assert "Pass1!" not in client.get("/api/overview").text
    search = client.get("/api/jobs?search=alice@example.com").json()["jobs"]
    assert len(search) == 1 and search[0]["raw_email"] == ""
    assert client.post("/api/batches/control", json={"action": "run"}).status_code == 400
    assert client.post("/api/batches/control", json={
        "action": "run", "batch_id": "missing"
    }).status_code == 400
    assert client.post("/api/batches/control", json={
        "action": "run", "batch_id": "demo", "limit": -1
    }).status_code == 400
    password = '  Pa\'ss"<>&!  '
    response = client.post("/api/jobs/action", json={
        "action": "set_password", "job_id": job_id, "agnes_password": password,
    })
    assert response.status_code == 200
    revealed = client.get(f"/api/jobs?job_id={job_id}&reveal_secrets=1").json()["jobs"]
    assert len(revealed) == 1 and revealed[0]["agnes_password"] == password
    raw_db = controller.get_settings().database.read_bytes()
    assert password.encode() not in raw_db
    assert client.post("/api/jobs/action", json={
        "action": "requeue", "job_ids": [job_id]
    }).status_code == 400
    assert client.post("/api/config", json={"key_flow": {"pattern": "["}}).status_code == 400
    assert client.post("/api/config", json=[], headers={
        "Origin": "https://untrusted.example"
    }).status_code == 403
    assert client.post("/api/config", json=[]).status_code == 400
    assert client.post("/api/config", json={"approval": "invalid"}).status_code == 400
    assert client.post("/api/accounts/import", json={"content": None}).status_code == 400
    assert client.get("/api/overview", headers={"Host": "malicious.example"}).status_code == 403
    export = client.get("/api/export?format=csv&batch=demo")
    assert export.status_code == 200 and password not in export.text
    backup = client.post("/api/backup", json={}).json()
    folder = Path(backup["directory"])
    assert (folder / "credentials.dpapi").exists()
    with sqlite3.connect(folder / "agnes.db") as db:
        assert db.execute("SELECT count(*) FROM registration_jobs").fetchone()[0] == 2


def test_csv_retains_credentials_and_source_row_errors(tmp_path):
    text = ('\ufeffuser_id,email,mailbox_password,agnes_password,client_id,refresh_token\n'
            'csv-user,alice@example.com,"mail,pass","platform""pass",client,token\n'
            'bad,not-email,secret,secret,,\n')
    parsed = parse_accounts_text(text)
    assert parsed[0]["mailbox_password"] == "mail,pass"
    assert parsed[0]["agnes_password"] == 'platform"pass'
    assert parsed[1]["row"] == 3 and parsed[1]["error"]
    storage = Storage(tmp_path / "csv.db")
    storage.initialize()
    vault = Vault(tmp_path / "csv.dpapi")
    try:
        report = import_accounts_flexible(storage, vault, text, batch_id="verify-only-batch",
                                         provider="mock", import_mode="existing_login")
        assert report["imported"] == 1 and report["rejected"] == 1
        job = storage.jobs()[0]
        assert job["state"] == "PENDING_VERIFY"
        assert job["phase"] == "REGISTRATION_SUBMITTED"
        record = vault.get(job["secret_ref"])
        assert record["agnes_password"] == 'platform"pass'
        assert record["refresh_token"] == "token"
        assert storage.events(job["job_id"])[-1]["code"] == "EXISTING_ACCOUNT_IMPORT"
        assert parse_accounts_text("a@example.com----p", format_hint="four_part")[0]["error"]
        assert parse_accounts_text("a@example.com----p--------")[0]["error"]
        combined = import_accounts_flexible(
            storage, vault,
            "duplicate@example.com----mail----client----refresh\n"
            "duplicate@example.com----platform", provider="mock",
        )
        assert combined["imported"] == combined["updated"] == 1
        merged = vault.get(combined["user_ids"][0])
        assert merged["refresh_token"] == "refresh" and merged["agnes_password"] == "platform"
    finally:
        storage.close()


def test_recovery_does_not_clear_health_checks_or_other_batches(workbench):
    controller, _, _ = workbench
    first_jobs = import_demo(controller, "one")
    second_jobs = import_demo(controller, "two", "c@example.com----Pass3!")
    storage = Storage(controller.get_settings().database)
    manager = ProxyManager(storage)
    try:
        manager.import_text("one|127.0.0.1:8101\ntwo|127.0.0.1:8102\ncheck|127.0.0.1:8103")
        assert manager.acquire(first_jobs[0]["job_id"], "one")
        assert manager.acquire(second_jobs[0]["job_id"], "two")
        assert manager.acquire(f"health-check:{time.time():.6f}:fixture", "check")
        storage.recover("one")
        rows = {p["id"]: p for p in manager.list()}
        assert not rows["one"]["leased"]
        assert rows["two"]["leased"] and rows["check"]["leased"]
        overview = controller.overview()
        assert overview["proxy_summary"]["next_proxy_id"] == "one"
        assert controller.overview("two")["summary"]["total"] == 1
    finally:
        storage.close()


def test_selected_mock_verification_runs_only_selected_account(workbench):
    controller, client, _ = workbench
    jobs = import_demo(controller)
    response = client.post("/api/jobs/action", json={
        "action": "verify", "job_id": jobs[1]["job_id"]
    })
    assert response.status_code == 200
    deadline = time.monotonic() + 10
    while controller.runner_running and time.monotonic() < deadline:
        time.sleep(.05)
    assert not controller.runner_running and not controller.last_error
    final = controller.list_jobs("demo")["jobs"]
    assert final[0]["state"] == "PENDING"
    assert final[1]["state"] != "PENDING"


def test_web_cli_startup_is_ready_and_shuts_down(tmp_path):
    config = tmp_path / "config.local.toml"
    save_settings(Settings(database=tmp_path / "jobs.db", vault=tmp_path / "vault.dpapi"), config)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-c", "from agnes_provisioner.cli import main;main()",
         "--config", str(config), "web", "--port", str(port), "--no-browser"],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            deadline = time.monotonic() + 15
            while True:
                try:
                    response = client.get("/api/overview")
                    break
                except httpx.ConnectError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise AssertionError("Web CLI did not become ready") from None
                    time.sleep(.05)
            assert response.status_code == 200
            assert response.json()["summary"]["total"] == 0
            assert "Runtime · 脚本运行工作台" in client.get("/").text
    finally:
        process.terminate()
        process.communicate(timeout=10)
        assert process.poll() is not None
