# Security Policy

## What counts as a security issue here

This project automates logging into your own bank/credit-card accounts. A
**security issue** is a bug in the code that could put credentials, data, or
your machine at risk beyond what you'd expect from running it as documented
— for example:

- Credentials being logged, written to disk, or sent anywhere other than
  the target bank's own site.
- Code that executes untrusted input (e.g. anything from a bank's response
  being `eval`'d rather than parsed as data).
- A dependency with a known vulnerability that this project actually
  exercises in a way that matters.

**Not a security issue** (open a normal GitHub issue instead — see
CONTRIBUTING.md):

- A bank blocking the scraper, a selector breaking, or Cloudflare/bot
  detection.
- "Is it safe to give this my bank password?" — see the trust statement at
  the top of the README; that's a design question, not a vulnerability
  report, and is welcome as a normal discussion.

## How to report

**Do not open a public GitHub issue for a genuine vulnerability** — that
tells anyone who reads it before a fix ships exactly how to exploit it.

Instead, use GitHub's private vulnerability reporting: go to this repo's
**Security** tab → **Report a vulnerability**. If that's not available for
some reason, open an issue asking for a private contact channel without
describing the vulnerability itself, and we'll follow up.

Please include:
- What you found and why it's a security issue (not just "X seems risky").
- Steps to reproduce, if applicable.
- What you think the impact is (credential exposure, code execution, etc.).

## What to expect

This is a community-maintained open-source project, not a company with a
dedicated security team — response time depends on maintainer availability.
A genuine report will be taken seriously and credited (if you want) once
fixed; there's no bug bounty.
