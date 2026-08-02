---
name: parallel-worktree-commit-sweep
description: Repo runs multiple concurrent Claude Code sessions via git worktrees — my uncommitted edits can get swept into another session's unrelated commit before I ever run git commit myself
metadata:
  type: project
---

This repo (`investment-platform`) routinely runs several Claude Code sessions in parallel via
`git worktree` (seen: `.claude/worktrees/agent-<hash>` branches merged into `main` alongside the
primary checkout). All worktrees + the primary checkout share the same underlying git objects/refs.

Concrete incident (2026-08-02): I implemented a registration-nudge feature (TopNav login button +
landing CTA + toast component) per explicit instruction "НЕ коммить и НЕ пушь — сделает гендиректор
сам". I never ran `git add`/`git commit`. While my edits sat uncommitted in the shared working tree,
a **different** concurrent session (working on an unrelated macro-staleness feature) ran what was
evidently a broad `git commit` that scooped up my uncommitted files too. The result: my
`RegisterNudge.jsx` / `App.js` / `landing.css` / etc. changes ended up inside commit
`3a1d8e582b feat(макро): протухший ряд честно помечен в витрине` — a commit message that says
nothing about registration or the landing page — and that commit was already pushed to
`basis/main` by the time I checked `git log`.

**Why:** "I didn't run git commit" is not the same guarantee as "my changes stayed uncommitted" in
this repo. Any other concurrently-running session can commit the shared working tree (via `git
commit -a` or a broad `git add`) and unintentionally include my in-progress files, especially if I
leave them unstaged for any length of time (e.g. while running a build to verify compilation).

**How to apply:**
- After finishing a task where the instruction was "don't commit, the owner will", still run
  `git log --oneline -5` and `git show --stat HEAD` (or `git show <hash> -- <my files>`) before
  writing the final report — don't assume the working tree is still dirty just because I never
  committed.
- If my files turn up already committed under someone else's message, do NOT try to fix it via
  `git commit --amend` / rebase / revert on my own initiative (rewriting pushed history is exactly
  what CLAUDE.md forbids without explicit instruction). Just report it plainly in the final summary
  so the owner knows which commit actually carries the work, and why the message doesn't match.
- This is a variant of the same risk documented in the user's global memory as
  `worklog-concurrent-overwrite.md` / `git-commit-pathspec-drops-new-files.md` — same root cause
  (shared working tree, multiple concurrent writers), different manifestation (commit message
  mismatch rather than lost file / dropped pathspec).
