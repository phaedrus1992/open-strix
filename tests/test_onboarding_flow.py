from __future__ import annotations

import os
import signal
import subprocess
import threading
from pathlib import Path

import yaml

NO_TOKEN_WEB_UI = "No Discord token configured. Local web UI available at"


def _run(cmd: list[str], cwd: Path, env: dict[str, str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        check=True,
    )


def _run_until(cmd: list[str], cwd: Path, env: dict[str, str], marker: str, timeout: float = 120.0) -> str:
    """Run a long-lived command until it prints marker, then stop it.

    With no Discord token, open-strix serves the web UI until it is killed,
    so the test cannot wait for it to exit.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    lines: list[str] = []
    done = threading.Event()

    def _read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if marker in line:
                done.set()
        done.set()

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()
    done.wait(timeout)
    # Signal the whole group: `uv run` starts open-strix as a child process.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    reader.join(timeout=5)
    output = "".join(lines)
    assert marker in output, f"{marker!r} not printed within {timeout}s. Output:\n{output}"
    return output


def test_onboarding_flow_bootstraps_expected_home_repo(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    home = tmp_path / "new-agent"
    home.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    # Force no-Discord path to verify first-run local onboarding behavior.
    env.pop("DISCORD_TOKEN", None)

    _run(["uv", "init", "--python", "3.11", "--no-readme"], cwd=home, env=env)
    _run(["uv", "add", "--editable", str(repo_root)], cwd=home, env=env)
    _run_until(["uv", "run", "open-strix"], cwd=home, env=env, marker=NO_TOKEN_WEB_UI)

    expected_paths = [
        home / "state" / ".gitkeep",
        home / "skills" / ".gitkeep",
        home / "blocks" / ".gitkeep",
        home / "logs" / "events.jsonl",
        home / "logs" / "journal.jsonl",
        home / "logs" / "chat-history.jsonl",
        home / "scheduler.yaml",
        home / "config.yaml",
        home / "checkpoint.md",
        home / "scripts" / "pre_commit.py",
        home / ".open_strix_builtin_skills" / "scripts" / "prediction_review_log.py",
        home / ".open_strix_builtin_skills" / "scripts" / "memory_dashboard.py",
        home / ".open_strix_builtin_skills" / "scripts" / "file_frequency_report.py",
        home / ".git" / "hooks" / "pre-commit",
        home / "blocks" / "init.yaml",
    ]
    missing = [path for path in expected_paths if not path.exists()]
    assert not missing, f"missing onboarding files: {missing}"

    hook_text = (home / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    assert "scripts/pre_commit.py" in hook_text
    assert "command -v uv" in hook_text
    assert ".venv/bin/uv" in hook_text

    gitignore_lines = {
        line.strip()
        for line in (home / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    assert "logs/" in gitignore_lines
    assert "logs/chat-history.jsonl" in gitignore_lines
    assert ".env" in gitignore_lines
    assert "*.png" in gitignore_lines
    assert "*.jpg" in gitignore_lines
    assert "*.jpeg" in gitignore_lines

    config_text = (home / "config.yaml").read_text(encoding="utf-8")
    assert "model: MiniMax-M2.5" in config_text
    assert "model_max_retries: 6" in config_text
    assert "model_request_timeout_seconds: 600" in config_text
    assert "always_respond_bot_ids: []" in config_text
    assert "default_reply_channel" not in config_text
    assert "state_dir" not in config_text
    assert "git_sync_before_send" not in config_text
    assert "git_sync_after_turn" not in config_text
    assert "skills_sources" not in config_text

    scheduler_text = (home / "scheduler.yaml").read_text(encoding="utf-8")
    assert "prediction-review-twice-daily" in scheduler_text
    assert 'cron: "0 9,21 * * *"' in scheduler_text

    init_block = yaml.safe_load((home / "blocks" / "init.yaml").read_text(encoding="utf-8"))
    assert init_block["name"] == "init"
    assert "onboarding" in init_block["text"].lower()

    # Second run should be idempotent and still work.
    _run_until(["uv", "run", "open-strix"], cwd=home, env=env, marker=NO_TOKEN_WEB_UI)
