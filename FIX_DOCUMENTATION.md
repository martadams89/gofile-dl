# Fix for GoFile `error-notPremium` (2026)

## Symptom

Free/guest downloads fail. The `/contents/{id}` API returns:

```json
{ "status": "error-notPremium", "data": {} }
```

## Root cause (corrected)

This is **not** a premium-only restriction. GoFile changed how the
`X-Website-Token` (`wt`) is produced:

- **Before:** a static token was published in `gofile.io/dist/js/config.js`
  (`appdata.wt = "..."`). Clients scraped and sent it.
- **Now:** that static value is a **decoy**. The real token is generated
  client-side in `gofile.io/dist/js/wt.obf.js` (an obfuscated script) and the
  server recomputes and validates it. Sending the stale static token is
  rejected as `error-notPremium`.

The generation algorithm (reverse-engineered from `wt.obf.js`) is:

```
wt = sha256(f"{userAgent}::{language}::{accountToken}::{window}::{salt}")
window = floor(unix_time / 14400)   # rotating 4-hour bucket
salt   = secret string embedded in wt.obf.js (e.g. "9844d94d963d30")
```

Because the server recomputes the token, the `User-Agent` and `X-BL`
(language) headers on the request **must match** the values hashed into the
token.

### How this was verified

- A Python reimplementation of the formula reproduces the exact token emitted
  by GoFile's own `wt.obf.js` for the same inputs (byte-for-byte SHA-256 match).
- Sending the **static** token returns `error-notPremium`; sending the
  **generated** token returns `error-rateLimit` instead — i.e. the token is
  accepted and the request passes the premium gate, only hitting GoFile's
  guest rate limiter.

## Solution implemented (`run.py`)

- `generate_website_token()` / `GoFile.website_token()` compute the token as
  above. The user agent, language and salt are constants overridable via the
  `GOFILE_USER_AGENT`, `GOFILE_LANGUAGE` and `GOFILE_WT_SALT` env vars.
- `GoFile.fetch_contents()` performs the content request with the correct
  headers and the query params GoFile's web client now sends
  (`contentFilter`, `page`, `pageSize`, `sortField`, `sortDirection`). It:
  - retries `error-rateLimit` with backoff,
  - retries `error-notPremium` once with the previous 4-hour window (covers a
    clock-boundary mismatch), then falls back to web scraping,
  - retries timeouts.
- The old singleton metaclass was removed so each download task uses its own
  token (fixes premium-token bleed and cross-thread token sharing).

## If it breaks again

`error-notPremium` returning in the future almost always means GoFile rotated
the salt in `wt.obf.js`. Recover without a code change by setting
`GOFILE_WT_SALT` to the new value. To find it, load `wt.obf.js` in a browser/
Node context and observe the string hashed by `generateWT` (the segment after
the time window). A premium token also bypasses the whole mechanism.
