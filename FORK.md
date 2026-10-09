# Fork policy

This is a fork of [tkellogg/open-strix](https://github.com/tkellogg/open-strix) for the robo-phaedrus agent.
Design: RoboPhaedrus1992/agent `docs/superpowers/specs/2026-10-09-fork-harness-setup-design.md`.

## Where code goes

- Fork-only logic goes in `open_strix/robo/`, with its tests in `tests/robo/`.
- An upstream file changes only at a seam: a call of a few lines into `open_strix/robo/`.
- A generic change (useful to any open-strix user) uses upstream style, keeps the upstream behavior when its config is unset, and goes upstream as a PR.
- Do not reformat or lint upstream files. Strict ruff and ty apply to `open_strix/robo/` and `tests/robo/` only.

## What goes upstream

- Bug fixes in upstream code.
- Generic seams, such as the Discord channel allowlist.
- Nothing that names this agent, its accounts, or its hosts.

## Upstream sync

- The `sync-upstream` workflow runs every Monday.
- If upstream has new commits, it merges `upstream/main` into a `sync/upstream-YYYYMMDD` branch, runs CI on it, and opens an "Upstream sync ready" issue with a link to open the PR.
- The workflow does not open the PR itself. That needs the setting "Allow GitHub Actions to create and approve pull requests", which would let a write-access account approve its own PR. Keep that setting off.
- If the merge conflicts, it opens an issue that lists the conflicting files. Resolve the conflict in a branch by hand, with a merge commit.
- Never rebase `main` and never force-push.

## Review

- Every PR needs ranger's approval and green CI before it merges.
- RoboPhaedrus1992 has write access: it can push branches and open PRs, but it cannot merge to `main` or change branch protection.
- The PyPI release workflows from upstream are disabled in this fork.
