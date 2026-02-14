# TODO

## Bugs

- [ ] **Google auth cancellation crashes app** — Backing out of the OAuth flow (closing browser, denying access) causes an unhandled exception. Should fail gracefully and return to the Google Account step.

- [x] **Duplicate calls synced in a single run** — Fixed: added `GROUP BY` in SQL query + `seen` set dedup in sync_service.

- [ ] **Contacts not detected on macOS 14.7.1** — Setup wizard shows "requires macOS 14.1+" even though the machine is on 14.7.1. The version check or pyobjc Contacts framework detection is broken. Fix and confirm it works.

## UX Improvements

- [ ] **Use iPhone-style call direction icons** — Replace `↑`/`↓` with the standard iPhone call log arrow icons (or closest Unicode equivalents) for incoming/outgoing calls.

- [ ] **Auto-request Full Disk Access** — Instead of making users search through System Settings, trigger the system permission dialog automatically. Research how to do this (may need to attempt to read the CallHistory DB to trigger the prompt).

- [ ] **Remove verbose pre-instruction popups** — The permission approval messagebox before Google sign-in is unnecessary friction. Remove or simplify to just proceed directly.

- [ ] **Show "Open Google Calendar" button after sync** — After syncing events, show a button to open Google Calendar in the browser (or open it automatically).

- [ ] **Add "Sync All Events" button** — In addition to "Sync Last 30 Days", add a button to sync the full call history.

- [ ] **Non-blocking sync with progress bar** — Syncing calendar events should happen in a background thread with a progress bar. No spinning wheel / app freeze during event creation.

## Google Developer Console

- [ ] **Hide developer email from users** — The Google OAuth consent screen currently shows the developer's personal email. Configure the consent screen to hide this or use a different contact email.

- [ ] **Move past 100 test user limit** — App is published but still limited to 100 test users. Need to submit for Google OAuth verification. See [docs/oauth-verification.md](docs/oauth-verification.md) for research notes and action items.
