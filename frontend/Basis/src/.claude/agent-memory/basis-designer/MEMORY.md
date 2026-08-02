# Project Memory

- [Registration nudge feature](registration-nudge-feature.md) — TopNav login button/landing CTA/delayed toast: file locations, 50s delay, 5-day cooldown
- [Parallel worktree commit sweep](parallel-worktree-commit-sweep.md) — uncommitted edits can get swept into another concurrent session's unrelated commit; verify git log even when told not to commit
- [CSS comment slash trap in my own comments](css-comment-slash-trap-in-my-own-comments.md) — `--bs-*/word` inside a comment silently closes it early; plain postcss.parse misses it, must run cssnano to catch
