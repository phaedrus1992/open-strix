from __future__ import annotations

import subprocess
from pathlib import Path

from open_strix.cli import _push_initial_history


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _set_identity(repo: Path) -> None:
    """Pin identity and disable signing so tests ignore the user's global git config."""
    _git(repo, "config", "user.email", "setup@example.test")
    _git(repo, "config", "user.name", "setup")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit_file(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", f"add {name}")


def _remote_with_history(tmp_path: Path, file_name: str, content: str) -> Path:
    """Create a bare remote whose main branch already has one commit."""
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "-b", "main", str(seed))
    _set_identity(seed)
    _commit_file(seed, file_name, content)
    bare = tmp_path / "remote.git"
    _git(tmp_path, "clone", "--bare", str(seed), str(bare))
    return bare


def _local_repo_with_commit(tmp_path: Path, file_name: str, content: str) -> Path:
    """Create a local repo with its own, unrelated first commit on main."""
    home = tmp_path / "home"
    _git(tmp_path, "init", "-b", "main", str(home))
    _set_identity(home)
    _commit_file(home, file_name, content)
    return home


def test_initial_push_to_empty_remote_is_plain_push(tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    home = _local_repo_with_commit(tmp_path, "agent.md", "agent\n")
    _git(home, "remote", "add", "origin", str(bare))

    proc = _push_initial_history(home)

    assert proc.returncode == 0, proc.stderr
    assert _git(bare, "rev-parse", "main") == _git(home, "rev-parse", "HEAD")


def test_initial_push_merges_unrelated_remote_history(tmp_path: Path) -> None:
    bare = _remote_with_history(tmp_path, "readme.md", "existing repo\n")
    home = _local_repo_with_commit(tmp_path, "agent.md", "agent\n")
    _git(home, "remote", "add", "origin", str(bare))

    proc = _push_initial_history(home)

    assert proc.returncode == 0, proc.stderr
    assert _git(bare, "show", "main:readme.md") == "existing repo"
    assert _git(bare, "show", "main:agent.md") == "agent"


def test_initial_push_reports_conflicting_history_and_aborts(tmp_path: Path) -> None:
    bare = _remote_with_history(tmp_path, "shared.md", "remote version\n")
    home = _local_repo_with_commit(tmp_path, "shared.md", "local version\n")
    _git(home, "remote", "add", "origin", str(bare))

    proc = _push_initial_history(home)

    assert proc.returncode != 0
    assert "shared.md" in proc.stdout + proc.stderr
    assert not (home / ".git" / "MERGE_HEAD").exists()
    assert _git(home, "status", "--porcelain") == ""
