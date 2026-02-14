# Google OAuth Verification Notes

Research on moving past the 100 test user limit.

## Scope Classification

- `https://www.googleapis.com/auth/calendar` is a **sensitive** scope (not restricted)
- Sensitive scopes have a lighter verification process — no CASA security assessment required
- Could narrow to `calendar.events` instead of `calendar` if we don't need calendar deletion

## Verification Requirements

- **Privacy policy URL** — must disclose: what data is accessed (calendar), how it's stored (macOS Keychain), that it's not sold/shared
- **Homepage URL** — the landing page (https://landing-eta-sable.vercel.app) can serve as this
- **Demo video** — showing the full OAuth consent flow

## Action Items

1. Add a `/privacy` page to the landing site with required disclosures
2. Record a demo video of the OAuth flow
3. Submit for verification via Google Cloud Console
4. Verification typically takes **3-5 business days** for sensitive scopes

## References

- [Google OAuth verification FAQ](https://support.google.com/cloud/answer/9110914)
- [OAuth API scopes list](https://developers.google.com/identity/protocols/oauth2/scopes)
