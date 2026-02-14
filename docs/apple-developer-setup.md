# Apple Developer ID Setup for macOS App Distribution

One-time setup for signing and notarizing macOS apps for distribution outside the App Store.

## Prerequisites

- Apple Developer account ($99/year) — https://developer.apple.com
- Your Team ID (find at developer.apple.com/account → Membership Details)

## 1. Create the signing certificate

```bash
# Generate private key + certificate signing request
openssl req -new -newkey rsa:2048 -nodes \
  -keyout ~/Desktop/devid.key \
  -out ~/Desktop/devid.csr \
  -subj "/emailAddress=YOUR_EMAIL/CN=YOUR_NAME"

# Import private key into keychain
security import ~/Desktop/devid.key -k ~/Library/Keychains/login.keychain-db

# Back up devid.key to 1Password, then delete from Desktop
```

## 2. Apple Developer portal

1. Go to https://developer.apple.com/account/resources/certificates/add
2. Select **Developer ID Application** → Continue
3. Select **G2 Sub-CA** → Continue
4. Upload `devid.csr`
5. Download the `.cer` file
6. Double-click to install

## 3. Install the intermediate certificate

This is required or signing will silently fail validation.

```bash
curl -sO https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer
sudo security add-certificates -k /Library/Keychains/System.keychain DeveloperIDG2CA.cer
rm DeveloperIDG2CA.cer
```

## 4. Verify

```bash
security find-identity -v -p codesigning
# Should show: "Developer ID Application: Your Name (TEAMID)"
```

## 5. Create app-specific password for notarization

1. Go to https://appleid.apple.com
2. Sign-In and Security → App-Specific Passwords
3. Generate one, name it "notarization"
4. Save the password

## 6. Configure your project

Create `.env` in your project root:

```
APPLE_ID=your@email.com
TEAM_ID=YOUR_TEAM_ID
APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
DEVELOPER_ID=Developer ID Application: Your Name (TEAMID)
```

## Troubleshooting

```bash
# Show all identities (including invalid, with error codes)
security find-identity -p codesigning

# Check why a cert is invalid
security find-certificate -c "Developer ID Application" -p ~/Library/Keychains/login.keychain-db > /tmp/cert.pem
security verify-cert -c /tmp/cert.pem
# CSSMERR_TP_NOT_TRUSTED = missing intermediate cert in System keychain

# Verify key matches cert (hashes must match)
openssl x509 -inform DER -noout -modulus -in cert.cer | openssl md5
openssl rsa -noout -modulus -in devid.key | openssl md5
```
