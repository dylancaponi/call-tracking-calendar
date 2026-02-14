# Lessons Learned

## Apple Developer ID Certificate Setup (macOS Code Signing)

### The correct process (do this, skip everything else)

**Do NOT use Keychain Access Certificate Assistant to generate the CSR.** It silently fails to create the private key on some machines — no error, no warning. Use openssl instead.

```bash
# 1. Generate private key + CSR via openssl
openssl req -new -newkey rsa:2048 -nodes \
  -keyout ~/Desktop/devid.key \
  -out ~/Desktop/devid.csr \
  -subj "/emailAddress=YOUR_EMAIL/CN=Your Name"

# 2. Import private key into login keychain
security import ~/Desktop/devid.key -k ~/Library/Keychains/login.keychain-db

# 3. Upload devid.csr to Apple Developer portal:
#    Certificates → + → Developer ID Application → G2 Sub-CA → upload CSR

# 4. Download the .cer file, double-click to install

# 5. CRITICAL: Install the Developer ID G2 intermediate cert into SYSTEM keychain
#    (This is the step that wastes hours if you miss it)
curl -sO https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer
sudo security add-certificates -k /Library/Keychains/System.keychain DeveloperIDG2CA.cer

# 6. Verify
security find-identity -v -p codesigning
# Should show: "Developer ID Application: Your Name (TEAMID)"
```

### What goes wrong and why

1. **Keychain Access CSR generation silently fails** — The GUI completes without error but no private key is created. This is a known bug. Always use openssl for CSR generation.

2. **`security find-identity` shows 0 valid identities even though cert + key are paired** — This means the trust chain is broken. The fix is installing the **Developer ID G2 intermediate certificate** into the **System keychain** (not login keychain). Without it, macOS finds the identity but can't validate it.

3. **Developer ID certs cannot be revoked via the portal** — There's no revoke button. You'd have to email product-security@apple.com. But you can just create additional certs alongside old ones.

4. **`handoff-own-encryption-key`** in Keychain Access is an Apple Handoff system key, unrelated to code signing. Ignore it.

5. **Charles Proxy root certs** in keychain are unrelated to code signing. Ignore them.

### Debugging commands

```bash
# Show ALL identities (including invalid ones, with error codes)
security find-identity -p codesigning

# Show only valid identities
security find-identity -v -p codesigning

# Check WHY a cert is invalid (trust chain)
security find-certificate -c "Developer ID Application" -p ~/Library/Keychains/login.keychain-db > /tmp/cert.pem
security verify-cert -c /tmp/cert.pem
# Look for: CSSMERR_TP_NOT_TRUSTED = missing intermediate

# Verify key matches cert (hashes must be identical)
openssl x509 -inform DER -noout -modulus -in cert.cer | openssl md5
openssl rsa -noout -modulus -in devid.key | openssl md5

# Check what intermediate certs exist in System keychain
security find-certificate -a -c "Developer ID" /Library/Keychains/System.keychain | grep "alis"
```

### Files to keep

- `devid.key` — your private key backup. Store securely. Already in keychain but keep a copy.
- `devid.csr` — can delete after cert is created, it's single-use.
- `DeveloperIDG2CA.cer` — can delete after installing to System keychain.

## Core Data SQLite: ZUNIQUE_ID Is Not Unique

Apple's `ZCALLRECORD.ZUNIQUE_ID` column has no SQL `UNIQUE` constraint. The `Z` prefix is Core Data's auto-naming convention — every entity table gets `Z` + uppercase entity name, every attribute gets `Z` + uppercase attribute name. Core Data manages uniqueness through its object graph (`Z_PK` + `Z_ENT`), not through SQL constraints on custom attributes.

Since we read the SQLite file directly (bypassing Core Data), we see raw rows including duplicates. This caused duplicate calendar events being created for the same call.

**Fix:** Deduplicate in two layers:
1. `call_database.py` — `GROUP BY ZUNIQUE_ID` in the SQL query (prevents dupes from leaving the DB layer)
2. `sync_service.py` — `seen` set when filtering `calls_to_sync` (prevents dupes within a batch even if the query layer changes)

**How we verified:** Wrote regression tests first, confirmed they fail against the old code (`calls_synced == 2` when it should be 1), applied the fix, confirmed they pass. The tests stay in the suite permanently.

**Reference:** https://fatbobman.com/en/posts/tables_and_fields_of_coredata/ — detailed breakdown of Core Data's SQLite schema conventions.

## PyInstaller macOS Gotchas

1. **Relative imports break at runtime** — PyInstaller runs entry points as top-level scripts, not package modules. `from .module import X` fails with "attempted relative import with no known parent package". Fix: create thin launcher stubs outside the package that use absolute imports (`from src.main import main`).

2. **`--osx-info-plist` doesn't exist in PyInstaller 6.x** — Use post-build `PlistBuddy` commands to merge custom Info.plist keys into the PyInstaller-generated plist.

3. **Resource paths break** — `Path(__file__)` points to a temp directory in frozen apps. Use `sys._MEIPASS` when `sys.frozen` is True.

4. **Unsigned apps can't access macOS Keychain** — Error: "Security Auth Failure: make sure executable is signed with codesign util". Ad-hoc signing (`codesign -s -`) fixes this for testing, or use proper Developer ID signing for distribution.

5. **Notarization requires ALL binaries signed** — Do NOT sign individual .dylib/.so files manually with `find`. Use `codesign --deep` on the .app bundle — it recursively signs everything inside. Manual per-file signing misses files and wastes time.

6. **The correct codesign command for notarization:**
   ```bash
   codesign --deep --force --options runtime --timestamp \
       --entitlements entitlements.plist \
       --sign "Developer ID Application: Name (TEAMID)" \
       YourApp.app
   ```
   All five flags are required: `--deep` (recursive), `--force` (replace existing), `--options runtime` (hardened runtime), `--timestamp` (secure timestamp), `--entitlements` (allow unsigned memory for Python).

7. **Duplicate certs cause "ambiguous" codesign errors** — If you created multiple certs with the same name, delete the extras: `security delete-certificate -Z <SHA1_HASH> ~/Library/Keychains/login.keychain-db`

## Claude Code Sandbox & Git Pitfalls

### Sandbox stdout restriction
Git, pytest, and python commands fail with walls of `/usr/bin/base64: /dev/stdout: Operation not permitted` when run in default sandbox mode. **Always use `dangerouslyDisableSandbox: true`** for these commands. Don't run one without it, see the error, then retry — that's two wasted calls.

### Know the repo root before running git
The git repo is `app/`, not the parent directory. The system prompt says "Is a git repository: false" for the parent — read and trust it. Running `git log` from the parent gives `fatal: not a git repository`. Running `git add app/src/file.py` from inside `app/` gives `fatal: pathspec did not match` because paths are relative to the repo root you're already in.

### Commit in one shot
Don't split git add, git commit, and git status into separate calls. Chain them: `git add <files> && git commit -m "msg" && git status`. A commit operation should be exactly 3 Bash calls total:
1. `git status` + `git diff` + `git log` (parallel, for context)
2. `git add <files> && git commit && git status` (one chained call)

That's it. Not 6+ calls with `pwd` and retries in between.

## Meta: How to Not Waste Time

### Use Perplexity FIRST, not after 5 failed attempts
When dealing with Apple/macOS tooling (codesign, notarization, keychain, certificates), ALWAYS search Perplexity before trying anything. Apple's tooling has undocumented requirements, silent failures, and error messages that don't tell you the actual problem. Don't guess — research first.

### The certificate setup should have been 5 minutes, not 2 hours
What went wrong and how to skip to the answer next time:

1. **Started with Keychain Access GUI** → should have used openssl from the start. Perplexity would have warned about the silent failure bug.

2. **0 valid identities — tried 6 different theories** before finding it was the missing intermediate cert. Should have immediately run `security verify-cert` to get the actual error (`CSSMERR_TP_NOT_TRUSTED`) which directly points to missing intermediate. Next time: run `security verify-cert` FIRST when identities show as invalid.

3. **Notarization failed twice** — first tried signing individual files with `find`, then tried again. Should have searched Perplexity first: "PyInstaller notarization signing" immediately returns "use `--deep`". One search would have saved two 10-minute notarization round trips.

### Pattern: when something fails on macOS
1. Get the EXACT error (run verbose/diagnostic commands, not just retry)
2. Search Perplexity with the exact error message
3. Don't guess at multiple theories — find the diagnostic command that tells you the specific cause
4. For `security find-identity` showing invalid: `security verify-cert -c cert.pem` gives the real error
5. For notarization failures: `xcrun notarytool log <submission-id>` gives the exact file paths and reasons

### macOS Keychain in signed apps — the full picture

**Problem 1: Keychain prompts on every launch (4+ prompts before UI appears)**

Root cause: `is_setup_complete()` called `GoogleCalendar.is_authenticated` → `keyring.get_password()` (prompt #1). If creds were expired, it refreshed → `keyring.set_password()` (prompt #2). Then setup wizard created a *new* GoogleCalendar instance and checked `is_authenticated` again (prompts #3-4).

Fix: **Never use keychain for flow control.** Use a SQLite flag (`setup_complete=true`) to decide whether to show the setup wizard. Only touch the keychain when the user explicitly clicks "Sign in with Google".

Rule: **Trace every `keyring.*` call site before shipping.** The first fix attempt only reordered checks — it should have eliminated the keychain call entirely from startup. Partial fixes waste a full rebuild + notarize cycle (~10 min each).

**Problem 2: Error -25244 storing credentials after Google OAuth**

Root cause: Old keychain items from previous unsigned/ad-hoc builds have ACLs tied to that build's code signing identity. The new Developer ID signed app has a different identity → macOS blocks writes. `logout()` tried to delete the old item first, but `keyring.delete_password()` also failed (same ACL mismatch) → `keyring.set_password()` fails because a duplicate exists that it can't overwrite.

Fix: Added `_force_delete_keychain_item()` that shells out to `security delete-generic-password` as a fallback. The `security` CLI is an Apple-signed system binary with broader keychain access than the app itself, so it can delete items regardless of ACL.

```python
def _force_delete_keychain_item(self):
    subprocess.run(
        ["security", "delete-generic-password", "-s", SERVICE, "-a", ACCOUNT],
        capture_output=True,
    )
```

Also manually deleted the old item: `security delete-generic-password -s "CallTrackingCalendar" -a "google_oauth"`

**How to solve both on the first try next time:**

Generic rules for macOS keychain in signed/notarized apps:
1. **Never access keychain at startup.** Use cheap checks (DB flags, file existence) for app flow decisions.
2. **Assume signing identity will change between builds.** Every rebuild with a different identity (unsigned → ad-hoc → Developer ID) creates an ACL conflict with existing keychain items.
3. **Always have a `security` CLI fallback** for keyring operations. The Python `keyring` library can't handle ACL mismatches — it just throws an opaque error.
4. **Before testing a new signed build**, delete old keychain items: `security delete-generic-password -s "YourService" -a "YourAccount"`
5. **Trace every `keyring.*` call** in the codebase before shipping. Search for `keyring.get_password`, `keyring.set_password`, `keyring.delete_password`, and `.is_authenticated`.
6. **Search Perplexity for the exact error code** (`-25244`, `-25293`, etc.) immediately — don't guess at theories.

Why this took too many credits: The first fix attempt was partial (reordered checks but left keychain in `is_setup_complete()`). Should have traced all call sites, eliminated unnecessary keychain access, AND added the security CLI fallback — all in one pass. Each incomplete fix burned a full build + notarize cycle.

## Contacts Framework on macOS: Two Silent Failures

### 1. Don't version-gate the Contacts framework import

The code originally required macOS 14.1+ to use the PyObjC Contacts framework, falling back to the legacy AddressBook SQLite DB. This was wrong for two reasons:
- PyObjC 12.x works fine on macOS 13.x (Ventura)
- The legacy AddressBook DB (`~/Library/Application Support/AddressBook/AddressBook-v22.abcddb`) exists but is **empty** on modern macOS — contacts are stored in CloudKit, not the legacy DB

**Fix:** Just try `import Contacts` directly. If it works, use it. No version check needed.

### 2. CNContactPhoneNumbersKey MUST be in fetch keys for phone predicate

When looking up contacts by phone number using `predicateForContactsMatchingPhoneNumber_`, the fetch keys passed to `unifiedContactsMatchingPredicate_keysToFetch_error_` must include `CNContactPhoneNumbersKey` — not just the name keys.

Without it, the framework throws `CNPropertyNotFetchedException`. The `except Exception` handler silently catches this and returns `None`, making it look like no contacts matched.

**How this manifested:** All 92 calls synced with raw phone numbers instead of contact names. The contacts module reported `backend=addressbook_db`, `authorized=True`, but the DB had 0 entries. After fixing the version gate → `backend=framework`, `authorized=True`, but all lookups returned `None`. Only by removing the `except Exception` temporarily did the real error surface.

**How to debug next time:**
1. Check `_CONTACTS_BACKEND` — should be `'framework'`, not `'addressbook_db'`
2. Check authorization status — should be `3` (authorized)
3. Test a raw predicate lookup outside the try/except to see actual errors
4. The `except Exception` in `_lookup_contact_via_framework` hides everything — temporarily disable it when debugging

**The test that prevents regression:** `test_includes_phone_numbers_key_in_fetch` verifies `CNContactPhoneNumbersKey` is always in the fetch keys list.
