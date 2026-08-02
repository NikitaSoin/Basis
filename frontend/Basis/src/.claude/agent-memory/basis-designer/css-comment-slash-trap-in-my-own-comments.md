---
name: css-comment-slash-trap-in-my-own-comments
description: When writing CSS comments that mention token names like --bs-*, a trailing */ immediately after the asterisk silently closes the comment early — cssnano fails with a useless "Expected an opening parenthesis" pointing at the wrong line
metadata:
  type: feedback
---

Hit this myself while writing a comment (not copying old code): `--bs-*/cc- через tokens.css` inside
a `/* ... */` block comment. The `*` (wildcard glob marker, meant colloquially — "the --bs- family of
tokens") directly followed by `/` (start of the next word/path) forms `*/`, which is a real CSS
comment terminator. The block comment closes several lines early; everything after becomes literal
CSS, and postcss/cssnano (via `postcss-selector-parser`, during `craco build`'s minify step) throws
`Error: Expected an opening parenthesis.` with a line:col pointing at the FIRST place the leftover
text looks like a broken selector — nowhere near the actual `*/` that caused it. `postcss.parse()`
alone does NOT catch this (only cssnano's stricter pipeline does), so a quick syntax sanity check
with plain postcss gives a false "OK".

**Why:** This is the same class of bug as the user's global memory `css-comment-star-slash-trap` (a
prior incident with `--bs-*/tokens.css`), but that one was in someone else's already-written code
I was reading past. This time I introduced it fresh while writing my OWN comment prose describing
token names — proof the pattern is easy to reintroduce even knowing about it, because in Russian
prose "--bs-* через ..." or "--bs-*/cc-" reads naturally as normal punctuation.

**How to apply:**
- Never write `*` immediately followed by `/` inside a CSS comment, even mid-sentence. If a token
  glob (`--bs-*`) is followed by a slash-separated word (`/cc-`, `/tokens.css`), insert a space:
  `--bs-* / cc-` or rephrase to avoid the adjacency entirely (e.g. drop the trailing `*`).
  See [[parallel-worktree-commit-sweep]] for the incident this surfaced during (registration-nudge
  build verification, 2026-08-02).
- To actually catch this before a full `craco build` (which is slow), run cssnano directly on the
  changed CSS file(s):
  `node -e "const postcss=require('postcss'); const fs=require('fs'); postcss([require('cssnano')({preset:'default'})]).process(fs.readFileSync('FILE.css','utf8'),{from:'FILE.css'}).then(()=>console.log('OK')).catch(e=>console.log('ERROR:',e.message))"`
  — plain `postcss.parse()` is NOT sufficient, it misses this class of error.
- If a `craco build` fails at the "Css Minimizer plugin" stage with a cryptic parenthesis/selector
  error and no useful line reference, suspect a `*/`-in-comment issue in a file changed in this
  session FIRST, before assuming it's a real selector bug.
