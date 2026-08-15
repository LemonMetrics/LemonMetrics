"""Automated macOS ``powermetrics`` privilege setup.

``powermetrics`` requires root, which normally means asking users to edit
sudoers by hand.  Instead :func:`ensure_powermetrics_access` grants the
current user passwordless sudo for **only** the ``powermetrics`` binary:

1. **Fast path** -- if ``sudo -n powermetrics`` already works, do nothing.
2. **GUI path** -- run a setup script through AppleScript's
   ``with administrator privileges``.  macOS shows the native password dialog
   and authenticates via Authorization Services; the harness never sees or
   stores the password.
3. **TTY path** -- if the dialog is unavailable (SSH / headless), fall back to
   ``sudo`` and let it prompt on the terminal.

The installed sudoers rule is scoped to the invoking user and the exact
resolved binary path, is validated with ``visudo -c`` before activation, and
is written via a temp file so a bad write can never lock sudo.
"""

from __future__ import annotations

import base64
import getpass
import os
import platform
import shutil
import subprocess
import sys


def powermetrics_bin() -> str | None:
    """Resolve the absolute path to ``powermetrics``, if present."""
    return shutil.which("powermetrics")


def _current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER") or "root"


def powermetrics_accessible() -> bool:
    """True if ``sudo -n powermetrics`` runs without a password on this host."""
    bin_path = powermetrics_bin()
    if not bin_path:
        return False
    try:
        proc = subprocess.run(
            ["sudo", "-n", bin_path, "-n", "1", "-i", "100"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _setup_script() -> str:
    """Root shell script that installs the scoped, validated sudoers rule."""
    bin_path = powermetrics_bin() or "powermetrics"
    rule = f"{_current_user()} ALL=(root) NOPASSWD: {bin_path}"
    return "\n".join(
        [
            "set -e",
            f"rule='{rule}'",
            "dir=/etc/sudoers.d",
            'tmp="$(mktemp "${dir}/lemonmetrics.XXXXXX")"',
            "trap 'rm -f \"${tmp}\"' EXIT",
            'printf \'%s\\n\' "${rule}" > "${tmp}"',
            'chown root:wheel "${tmp}"',
            'chmod 0440 "${tmp}"',
            'if ! visudo -c -f "${tmp}" >/dev/null 2>&1; then exit 1; fi',
            'mv "${tmp}" "/etc/sudoers.d/lemonmetrics"',
            "trap - EXIT",
        ]
    )


def _encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-8")).decode("ascii")


def _run_gui() -> bool | None:
    """Install the sudoers rule via the native macOS admin dialog.

    Returns True on success, False when the user cancelled the dialog, and
    None when the dialog could not be used at all (headless / no GUI session).
    """
    applescript = (
        'do shell script "echo %s | base64 -d | /bin/sh" '
        "with administrator privileges" % _encode(_setup_script())
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 0:
        return True
    lowered = (proc.stderr or "").lower()
    if "cancel" in lowered or "-128" in lowered:
        return False
    return None


def _run_tty() -> bool:
    """Install the sudoers rule via ``sudo`` so it can prompt on the terminal."""
    try:
        proc = subprocess.run(
            [
                "sudo",
                "-p",
                "Password for powermetrics access (once, scoped to /usr/bin/powermetrics): ",
                "/bin/sh",
            ],
            input=_setup_script(),
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def ensure_powermetrics_access(*, allow_prompt: bool = True) -> bool:
    """Make ``powermetrics`` usable without a password on macOS.

    Returns True when powermetrics is accessible (or not applicable on this
    platform) and False when it could not be configured.  Never raises: a
    declined prompt degrades to the ``null`` sampler upstream.
    """
    if os.environ.get("LEMONMETRICS_NO_SUDO"):
        allow_prompt = False
    if platform.system() != "Darwin":
        return True
    if powermetrics_accessible():
        return True
    if not allow_prompt:
        print(
            "note: powermetrics access not configured (prompts disabled); "
            "power will be marked unavailable",
            file=sys.stderr,
        )
        return False

    print(
        "powermetrics needs administrator access to read your Mac's power. "
        "Lemon Metrics will request it once via a system dialog.",
        file=sys.stderr,
    )
    gui = _run_gui()
    if gui is True:
        return True
    if gui is False:
        print(
            "powermetrics access declined; power will be marked unavailable. "
            "Re-run `lemonmetrics setup` to grant access later.",
            file=sys.stderr,
        )
        return False
    print(
        "could not show the system dialog; trying terminal sudo instead (Ctrl-C to skip)",
        file=sys.stderr,
    )
    if _run_tty():
        return True
    print(
        "error: could not configure powermetrics access; "
        "power will be marked unavailable (see docs/run-it-yourself.md)",
        file=sys.stderr,
    )
    return False
