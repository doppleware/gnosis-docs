#!/usr/bin/env python3
"""Bootstrap `gnosis`: install uv if missing, then install gnosis as an isolated uv tool.

Designed to be invoked by a parent application as a one-time setup step. Works on
Linux, macOS, and Windows. Requires Python 3.8+ (gnosis itself needs 3.12+, but
the bootstrap is kept permissive so the parent can run it with whatever Python
happens to be on the user's system).

What it does:
  1. Look for an existing `uv` on PATH and at the standard install locations.
  2. If missing, run astral's official installer:
        Linux/macOS:  curl -LsSf https://astral.sh/uv/install.sh | sh
        Windows:      powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  3. Run `uv tool install` to put gnosis in an isolated venv under uv's tool store.
     Installs the released `gnosis-air` package from PyPI by default; --gnosis-ref
     installs a git build instead. Pass --reinstall to force a full rebuild of
     gnosis AND all its dependencies (the repair path for an env left incomplete
     by a partial/interrupted install; also how an existing install is moved to
     the latest PyPI release).
  4. Verify the install by importing gnosis's LLM entry chain in the tool venv, so a
     partial download (e.g. a missing compiled dep) fails here, not at runtime.
  5. Print the resolved gnosis binary path to stdout (last line) so the parent
     app can capture it directly. Progress messages go to stderr.

Everything (uv's own output, exit code, resolved path, verification result) is also
written to a timestamped log under <tempdir>/gnosis/gnosis-bootstrap__<ts>.log so a
failed install is inspectable after the subprocess exits.

After completion, the binary lives at a predictable location and the parent
app should subprocess it directly — no shell, no PATH lookup needed.

Exit codes:
   0  Success — gnosis installed, verified, and the binary path printed to stdout.
   1  Bootstrap failed — see stderr / the bootstrap log for the specific step that broke.

Usage from a parent application:
    result = subprocess.run(
        [sys.executable, "bootstrap.py", "--gnosis-ref", "v0.3.0"],
        capture_output=True, text=True, check=True,
    )
    gnosis_path = result.stdout.strip().splitlines()[-1]
    # cache gnosis_path; subprocess it for every invocation thereafter
"""

from __future__ import annotations

import argparse
import datetime
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Defaults — override via CLI flags.
# Primary distribution is the released PyPI package; --gnosis-ref switches to a
# git build (dev/pinned escape hatch). NOTE: the PyPI name is `gnosis-air` — the
# bare `gnosis` project on pypi.org is an unrelated package.
GNOSIS_PACKAGE = "gnosis-air"
GNOSIS_GIT_URL = "git+https://github.com/JetBrains/air-trajectory-analysis"
DEFAULT_PYTHON_VERSION = "3.12"

# Astral's official installer URLs (one-line invocation; no third-party host).
UV_INSTALL_SH = "https://astral.sh/uv/install.sh"
UV_INSTALL_PS1 = "https://astral.sh/uv/install.ps1"

# Set by setup_logging(); every log() line is mirrored here so a broken install
# leaves an inspectable trace (the parent app streams stderr, but a persisted log
# survives after the subprocess exits — the missing 'uuid_utils' class of failure
# was previously invisible until runtime).
_LOG_PATH: Path | None = None


def is_windows() -> bool:
    return sys.platform == "win32"


def setup_logging() -> Path:
    """Open a timestamped bootstrap log under the OS temp dir; return its path.

    Colocated with gnosis's own runtime logs ($TMPDIR/gnosis/) so operators have
    one place to look. Best-effort: if the dir can't be created we fall back to
    stderr-only logging (log() tolerates a None/closed path).
    """
    global _LOG_PATH
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        log_dir = Path(tempfile.gettempdir()) / "gnosis"
        log_dir.mkdir(parents=True, exist_ok=True)
        _LOG_PATH = log_dir / f"gnosis-bootstrap__{ts}.log"
        _LOG_PATH.write_text(f"[bootstrap] log started {ts}\n", encoding="utf-8")
    except OSError as e:
        _LOG_PATH = None
        print(f"[bootstrap] could not open log file ({e}); logging to stderr only.", file=sys.stderr)
    return _LOG_PATH  # may be None


def log(msg: str) -> None:
    """Progress goes to stderr AND the persisted log; stdout is reserved for the final path."""
    print(f"[bootstrap] {msg}", file=sys.stderr, flush=True)
    if _LOG_PATH is not None:
        try:
            with _LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(f"[bootstrap] {msg}\n")
        except OSError:
            pass  # never let logging break the install


def find_uv() -> str | None:
    """Locate uv on disk. Checks PATH first, then astral's standard install paths."""
    found = shutil.which("uv")
    if found:
        return found
    home = Path.home()
    exe = "uv.exe" if is_windows() else "uv"
    candidates = [
        home / ".local" / "bin" / exe,
        home / ".cargo" / "bin" / exe,  # legacy install location
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def install_uv() -> str:
    """Run astral's official installer; return the resulting uv path."""
    log("uv not found; installing via astral's official script...")
    if is_windows():
        # PowerShell one-liner — same as `irm https://astral.sh/uv/install.ps1 | iex`.
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"irm {UV_INSTALL_PS1} | iex",
        ]
    else:
        # POSIX shell + curl. Available on every Linux/macOS install.
        cmd = ["sh", "-c", f"curl -LsSf {UV_INSTALL_SH} | sh"]
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as e:
        sys.exit(
            f"[bootstrap] required tool missing: {e.filename}. "
            f"On Linux/macOS, install curl. On Windows, ensure PowerShell is on PATH."
        )
    except subprocess.CalledProcessError as e:
        sys.exit(
            f"[bootstrap] astral's uv installer failed (exit {e.returncode}). "
            f"Check network access (corporate proxy?), then retry."
        )
    uv = find_uv()
    if uv is None:
        sys.exit(
            "[bootstrap] uv install completed but the binary wasn't found. "
            "The installer writes to ~/.local/bin (Unix) or %USERPROFILE%\\.local\\bin "
            "(Windows) — inspect that directory."
        )
    log(f"uv installed at: {uv}")
    return uv


def install_gnosis(uv: str, ref: str | None, python_version: str, reinstall: bool) -> None:
    """Install gnosis as a uv tool.

    Idempotent by default (a no-op if gnosis is already installed). When
    `reinstall` is set, passes uv's `--reinstall`, which reinstalls the tool AND
    all of its dependencies — the recovery path for an env left incomplete by a
    partial/interrupted download (e.g. a missing compiled transitive dep).

    uv's stdout+stderr are captured and written to the persisted log so the exact
    resolution/download outcome is inspectable after the fact.
    """
    # Both paths resolve from public PyPI alone: the one JetBrains-index-only
    # dependency was vendored into the package (labs/branch_review/code_methods),
    # so no extras or extra indexes are ever needed.
    spec = f"{GNOSIS_PACKAGE} @ {GNOSIS_GIT_URL}@{ref}" if ref else GNOSIS_PACKAGE
    cmd = [uv, "tool", "install", "--python", python_version]
    if reinstall:
        cmd.append("--reinstall")
    cmd.append(spec)
    log(f"{'reinstalling' if reinstall else 'installing'} gnosis: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # Mirror uv's own output into the log (and echo to stderr) regardless of outcome.
    for stream_name, content in (("stdout", proc.stdout), ("stderr", proc.stderr)):
        if content:
            log(f"uv {stream_name}:\n{content.rstrip()}")
    log(f"uv tool install exited with code {proc.returncode}")
    if proc.returncode != 0:
        sys.exit(f"[bootstrap] uv tool install failed (exit {proc.returncode}). See log: {_LOG_PATH}")


def resolve_gnosis_binary(uv: str) -> Path:
    """Ask uv where it stores tools, then construct the binary path.

    Avoids hardcoding XDG_DATA_HOME / LOCALAPPDATA logic — uv's `tool dir`
    accounts for env-var overrides and per-platform conventions.
    """
    try:
        result = subprocess.run([uv, "tool", "dir"], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(f"[bootstrap] could not resolve uv tool dir (exit {e.returncode}).")
    tool_dir = Path(result.stdout.strip())
    # uv names the tool venv after the PACKAGE (gnosis-air); the executable inside
    # keeps the console-script name (gnosis).
    if is_windows():
        return tool_dir / GNOSIS_PACKAGE / "Scripts" / "gnosis.exe"
    return tool_dir / GNOSIS_PACKAGE / "bin" / "gnosis"


def verify_install(binary: Path) -> None:
    """Smoke-test the freshly installed env by importing the LLM entry chain.

    A successful `uv tool install` exit code does NOT guarantee a complete env: an
    interrupted or proxy-blocked download can leave a compiled transitive dep
    (e.g. `uuid_utils`, pulled by `langchain_core`) missing while every pure-Python
    package is present — the failure then surfaces only at runtime as
    "No module named 'uuid_utils'". Reproduce that exact import here so a partial
    install fails loudly at bootstrap time and is captured in the log.

    Uses the tool venv's own interpreter (sibling of the gnosis binary), so it
    exercises the installed env, not the bootstrap's Python.
    """
    py = binary.parent / ("python.exe" if is_windows() else "python")
    if not py.is_file():
        log(f"WARNING: could not find the tool venv interpreter at {py}; skipping import verification.")
        return
    probe = "import langchain_core.callbacks.manager"
    log(f"verifying install: {py} -c '{probe}'")
    proc = subprocess.run([str(py), "-c", probe], capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        log(f"import verification FAILED:\n{detail}")
        sys.exit(
            f"[bootstrap] gnosis installed but its dependencies are incomplete "
            f"(import probe failed): {detail.splitlines()[-1] if detail else 'unknown error'}. "
            f"Re-run with --reinstall to rebuild the environment. See log: {_LOG_PATH}"
        )
    log("import verification passed — LLM entry chain imports cleanly.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install uv (if missing) and gnosis as a uv tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit 0 prints the installed gnosis binary path on the last stdout line.\n"
            "Pass that path to subprocess.run([...]) on every subsequent gnosis invocation."
        ),
    )
    parser.add_argument(
        "--gnosis-ref",
        default=None,
        help=(
            "Install a git build at this ref (tag, branch, or commit) instead of the "
            "released PyPI package. Default: latest gnosis-air release from PyPI."
        ),
    )
    parser.add_argument(
        "--python-version",
        default=DEFAULT_PYTHON_VERSION,
        help=f"Python version uv should use for the gnosis venv. Default: {DEFAULT_PYTHON_VERSION}.",
    )
    parser.add_argument(
        "--reinstall",
        "--force",
        dest="reinstall",
        action="store_true",
        help=(
            "Force a full reinstall of gnosis and ALL its dependencies (passes uv's "
            "--reinstall). Use this to repair an env left incomplete by a partial or "
            "network-interrupted install. (--force is a back-compat alias.)"
        ),
    )
    args = parser.parse_args()

    log_path = setup_logging()
    if log_path is not None:
        log(f"bootstrap log: {log_path}")

    uv = find_uv() or install_uv()
    install_gnosis(uv, args.gnosis_ref, args.python_version, args.reinstall)
    binary = resolve_gnosis_binary(uv)
    if not binary.is_file():
        sys.exit(
            f"[bootstrap] expected gnosis at {binary} but it wasn't found. "
            f"`uv tool install` succeeded but the binary path differs from convention."
        )
    verify_install(binary)
    log(f"gnosis installed at: {binary}")
    # Final stdout line — easy to capture from the parent.
    print(binary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
