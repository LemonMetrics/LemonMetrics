"""Tests for automated powermetrics privilege setup on macos."""

import subprocess

from lemonmetrics.power import privileges


def _proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_setup_script_is_scoped_and_validated(monkeypatch):
    monkeypatch.setattr(privileges, "_current_user", lambda: "testuser")
    monkeypatch.setattr(privileges, "powermetrics_bin", lambda: "/usr/bin/powermetrics")
    script = privileges._setup_script()
    assert "testuser ALL=(root) NOPASSWD: /usr/bin/powermetrics" in script
    assert "visudo -c" in script
    assert "chmod 0440" in script
    assert "mktemp" in script
    assert "lemonmetrics" in script


def test_powermetrics_accessible_ok(monkeypatch):
    calls = {}

    def fake_run(cmd, **_kwargs):
        calls["cmd"] = cmd
        return _proc(0)

    monkeypatch.setattr(privileges.shutil, "which", lambda name: "/usr/bin/powermetrics")
    monkeypatch.setattr(privileges.subprocess, "run", fake_run)
    assert privileges.powermetrics_accessible() is True
    assert calls["cmd"][0] == "sudo"
    assert "-n" in calls["cmd"]
    assert calls["cmd"][2] == "/usr/bin/powermetrics"


def test_powermetrics_accessible_fails(monkeypatch):
    monkeypatch.setattr(privileges.shutil, "which", lambda name: "/usr/bin/powermetrics")
    monkeypatch.setattr(privileges.subprocess, "run", lambda *a, **k: _proc(1))
    assert privileges.powermetrics_accessible() is False


def test_powermetrics_accessible_missing_bin(monkeypatch):
    monkeypatch.setattr(privileges.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        privileges.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    assert privileges.powermetrics_accessible() is False


def test_ensure_fast_path_never_prompts(monkeypatch):
    monkeypatch.setattr(privileges.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(privileges, "powermetrics_accessible", lambda: True)
    gui_called = []

    def fake_gui():
        gui_called.append(True)
        return True

    monkeypatch.setattr(privileges, "_run_gui", fake_gui)
    assert privileges.ensure_powermetrics_access() is True
    assert gui_called == []


def test_ensure_gui_success(monkeypatch, capsys):
    monkeypatch.setattr(privileges.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(privileges, "powermetrics_accessible", lambda: False)
    gui_called = []

    def fake_gui():
        gui_called.append(True)
        return True

    tty_called = []

    def fake_tty():
        tty_called.append(True)
        return False

    monkeypatch.setattr(privileges, "_run_gui", fake_gui)
    monkeypatch.setattr(privileges, "_run_tty", fake_tty)
    assert privileges.ensure_powermetrics_access() is True
    assert len(gui_called) == 1
    assert tty_called == []


def test_ensure_gui_cancel_does_not_fallback_to_tty(monkeypatch):
    monkeypatch.setattr(privileges.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(privileges, "powermetrics_accessible", lambda: False)
    monkeypatch.setattr(privileges, "_run_gui", lambda: False)
    tty_called = []
    monkeypatch.setattr(privileges, "_run_tty", lambda: tty_called.append(True))
    assert privileges.ensure_powermetrics_access() is False
    assert tty_called == []


def test_ensure_gui_unavailable_falls_back_to_tty(monkeypatch):
    monkeypatch.setattr(privileges.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(privileges, "powermetrics_accessible", lambda: False)
    monkeypatch.setattr(privileges, "_run_gui", lambda: None)
    monkeypatch.setattr(privileges, "_run_tty", lambda: True)
    assert privileges.ensure_powermetrics_access() is True


def test_ensure_non_darwin_is_noop(monkeypatch):
    monkeypatch.setattr(privileges.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        privileges,
        "powermetrics_accessible",
        lambda: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    assert privileges.ensure_powermetrics_access() is True


def test_ensure_prompts_disabled(monkeypatch, capsys):
    monkeypatch.setattr(privileges.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(privileges, "powermetrics_accessible", lambda: False)
    monkeypatch.setattr(
        privileges,
        "_run_gui",
        lambda _script: (_ for _ in ()).throw(AssertionError("should not prompt")),
    )
    assert privileges.ensure_powermetrics_access(allow_prompt=False) is False


def test_ensure_env_var_disables_prompt(monkeypatch, capsys):
    monkeypatch.setattr(
        privileges.os.environ, "get", lambda key: "1" if key == "LEMONMETRICS_NO_SUDO" else ""
    )
    monkeypatch.setattr(privileges.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(privileges, "powermetrics_accessible", lambda: False)
    monkeypatch.setattr(
        privileges,
        "_run_gui",
        lambda _script: (_ for _ in ()).throw(AssertionError("should not prompt")),
    )
    assert privileges.ensure_powermetrics_access() is False


def test_run_gui_parses_cancel(monkeypatch):
    monkeypatch.setattr(
        privileges.subprocess,
        "run",
        lambda *a, **k: _proc(1, stderr="User canceled."),
    )
    assert privileges._run_gui() is False


def test_run_gui_other_failure_is_none(monkeypatch):
    monkeypatch.setattr(
        privileges.subprocess,
        "run",
        lambda *a, **k: _proc(1, stderr="execution error"),
    )
    assert privileges._run_gui() is None
