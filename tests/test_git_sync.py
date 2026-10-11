from __future__ import annotations

import subprocess
from pathlib import Path

from open_strix.app import _git_sync


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _set_identity(repo: Path, email: str, name: str) -> None:
    """Pin identity and disable signing so tests ignore the user's global git config."""
    _git(repo, "config", "user.email", email)
    _git(repo, "config", "user.name", name)
    _git(repo, "config", "commit.gpgsign", "false")


def _init_home_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create an agent home tracking a bare remote. Return (home, bare)."""
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(bare))

    home = tmp_path / "home"
    _git(tmp_path, "init", "-b", "main", str(home))
    _set_identity(home, "agent@example.test", "agent")
    (home / "state.md").write_text("seed\n", encoding="utf-8")
    _git(home, "add", "-A")
    _git(home, "commit", "-m", "seed")
    _git(home, "remote", "add", "origin", str(bare))
    _git(home, "push", "-u", "origin", "main")
    return home, bare


def _remote_commit(tmp_path: Path, bare: Path, name: str, content: str) -> None:
    """Simulate a PR merge: push a commit to the remote from a second clone."""
    other = tmp_path / name
    _git(tmp_path, "clone", str(bare), str(other))
    _set_identity(other, "pr@example.test", "pr")
    (other / name).write_text(content, encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-m", f"remote {name}")
    _git(other, "push", "origin", "main")


def test_sync_merges_remote_commit_before_push(tmp_path: Path) -> None:
    home, bare = _init_home_with_remote(tmp_path)
    _remote_commit(tmp_path, bare, "pr_change.md", "merged\n")
    (home / "state.md").write_text("agent edit\n", encoding="utf-8")

    result = _git_sync(home)

    assert result == "ok: committed and pushed"
    assert _git(home, "rev-parse", "HEAD") == _git(home, "rev-parse", "origin/main")
    assert (home / "pr_change.md").read_text(encoding="utf-8") == "merged\n"
    assert _git(home, "status", "--porcelain") == ""


def test_sync_reports_merge_failure_and_leaves_tree_clean(tmp_path: Path) -> None:
    home, bare = _init_home_with_remote(tmp_path)
    _remote_commit(tmp_path, bare, "state.md", "remote version\n")
    (home / "state.md").write_text("agent version\n", encoding="utf-8")

    result = _git_sync(home)

    assert result.startswith("git merge failed:"), result
    assert _git(home, "status", "--porcelain") == ""
    merge_head = home / ".git" / "MERGE_HEAD"
    assert not merge_head.exists()


def test_sync_skips_git_when_nothing_changed(tmp_path: Path) -> None:
    home, _bare = _init_home_with_remote(tmp_path)

    assert _git_sync(home) == "clean: no changes"


def test_sync_pushes_stranded_local_commit_when_tree_is_clean(tmp_path: Path) -> None:
    home, bare = _init_home_with_remote(tmp_path)
    (home / "state.md").write_text("stranded\n", encoding="utf-8")
    _git(home, "add", "-A")
    _git(home, "commit", "-m", "stranded from an earlier failed push")

    result = _git_sync(home)

    assert result == "ok: pushed"
    assert _git(bare, "rev-parse", "main") == _git(home, "rev-parse", "HEAD")


def test_sync_skips_when_home_is_not_a_repo(tmp_path: Path) -> None:
    assert _git_sync(tmp_path) == "skip: not a git repo"
