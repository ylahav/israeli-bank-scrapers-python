---
name: Scraper failure report
about: A bank/credit-card scraper doesn't work
title: "[bank name] doesn't work: <short description>"
labels: bug, needs-testing
---

<!--
Before filling this out: never include real credentials, account numbers,
balances, or transaction contents anywhere in this issue. Crop or redact
anything sensitive out of screenshots. See CONTRIBUTING.md if you haven't
already.
-->

**Company / bank:** <!-- e.g. hapoalim, mizrahi -->

**What happened:**
<!-- One or two sentences. e.g. "Login appears to succeed in the browser
window but the script reports LOGIN_FAILED with UNKNOWN_ERROR." -->

**Debug log:**
<!-- Run with IBS_LOG_LEVEL=DEBUG and paste the relevant portion below —
especially the last few lines before the failure, and any line starting
with "no login result matched. final url was: ...". Full logs are fine;
more context rarely hurts. -->

```
paste debug log here
```

**Screenshot:**
<!-- failure_screenshot.png is saved automatically next to examples/scrape.py
on any failure. Attach it here — crop out anything sensitive first. -->

**What you saw in the browser window (with IBS_SHOW_BROWSER=1):**
<!-- e.g. "Login form appeared, fields filled in correctly, clicked submit,
page just sat there" or "got a 2FA prompt the script doesn't handle" -->

**Environment:**
- OS:
- Python version:
- Approximate date tested:
