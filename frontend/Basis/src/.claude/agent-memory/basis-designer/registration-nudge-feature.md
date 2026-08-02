---
name: registration-nudge-feature
description: Site-wide "please register" communication (TopNav login button, landing FINAL CTA, delayed toast) — where the pieces live and the delay/cooldown values chosen
metadata:
  type: project
---

Built 2026-08-02 per owner brief: increase registrations without a hard gate and without steering
users toward a specific feature (Portfolio/Assistant) — owner explicitly rejected that framing as a
wrong prior hypothesis (real visitors read/verify, they don't "manage a position").

Three pieces, all gated on `!token` (never shown to logged-in users):

1. **TopNav "Войти" button** — `frontend/Basis/src/App.js`, `TopNav` component (`topnav-actions`
   div). New props `isAuthenticated` / `onOpenAuth` threaded from `App()` (`!!token` /
   `() => setShowAuthModal(true)`). Rendered only when `!isAuthenticated`, `Button variant="secondary"
   size="md"` with a `User` icon; label text wrapped in `<span className="topnav-login-label">` so
   `styles/mobile-nav.css` (≤760px block) can hide it and leave icon-only (aria-label carries the
   name for a11y). This was the first-ever login entry point in the top chrome — previously only
   `TOPNAV_ITEMS`'s "Профиль" existed, which routes into the profile view, not the auth form.

2. **Landing FINAL CTA** — `frontend/Basis/src/market/landingHtml.js`, `<section class="final">`
   (end of file, before `<footer>`). Added a `.final-reg` block AFTER the existing two buttons
   (`Открыть платформу` / `Пример — Роснефть`), not a third button of equal weight — a short note
   paragraph + a `.feat-link` (the same arrow-link pattern already used in every `band` section) with
   `data-route="login"` → wired through the ALREADY-EXISTING `LandingNeo.jsx` click delegation (no JS
   changes needed there, `data-route="login"` → `onShowAuth()` already existed, unused until now).
   CSS in `styles/landing.css` right after `.final .hero-actions`.

3. **Delayed toast** — new `frontend/Basis/src/account/RegisterNudge.jsx` (+
   `styles/register-nudge.css`), mounted in `App.js` next to `<AuthModal>` as
   `{!token && !showAuthModal && <RegisterNudge onOpenAuth={...} />}`. Self-contained: owns its own
   `setTimeout` + localStorage cooldown, no App-level state needed beyond the token/showAuthModal
   gate. Chosen values (documented in-file):
   - `SHOW_DELAY_MS = 50_000` (50s after mount — mid-point of the owner's 45–60s range).
   - `COOLDOWN_MS = 5 days` — stamped in `localStorage["basis_reg_nudge_dismissed_at"]` **at the
     moment the toast becomes visible** (not only on explicit close-click), so "already seen this
     session" is covered even if the user never interacts with it and just navigates away.
   - Fixed-position corner toast, `z-index: 120` (above the mobile bottom tab bar's `z-index: 100`,
     below `AuthModal`'s `z-index: 200`). Mobile override (≤760px) lives in the SAME CSS file as the
     base rule (not in `mobile-nav.css`) — see [[css-comment-slash-trap-in-my-own-comments]] for why
     that file-colocation choice matters for cascade predictability.

If a future task wants to tune the delay/cooldown or add a "не сейчас" secondary dismiss link, start
in `RegisterNudge.jsx` — both constants are named and commented at the top of the file.
