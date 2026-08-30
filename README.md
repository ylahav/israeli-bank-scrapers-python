# israeli-bank-scrapers (Python port)

A Python/[Playwright](https://playwright.dev/python/) port of the core of
[eshaham/israeli-bank-scrapers](https://github.com/eshaham/israeli-bank-scrapers),
a Node.js/Puppeteer library that scrapes transaction data from Israeli banks
and credit-card companies.

**This runs entirely on your own machine.** It automates a real browser to
log into your bank's actual website — exactly the same pages you'd click
through yourself — and reads the page/API responses locally. Nothing is sent
to any third-party server; the only network traffic this makes is directly
to your bank's own site. Read the code — that's the whole point of it being
open source.

**Testers wanted, especially for banks marked "unverified" below.** Only 3
of 18 companies have actually been confirmed against a live site so far —
see [Verification status](#verification-status). If you bank with one of
the unverified ones and are willing to test, see
[CONTRIBUTING.md](CONTRIBUTING.md) for how to do it and what to report.

## What's here

- **`get_version()`** (`israeli_bank_scrapers.get_version()`, also
  `israeli_bank_scrapers.__version__`) — reads the installed package's
  version from its own metadata, so `pyproject.toml` stays the single
  source of truth rather than a version string duplicated in code. Also
  reachable through the CLI without a full scrape or browser launch — send
  `{"type": "version"}` instead of a scrape request; see `cli.py`'s module
  docstring. The Dart client's `getVersion()` wraps this for a Flutter app
  that wants to confirm which build it's actually running.
- **Full core architecture**: `BaseScraper` / `BaseScraperWithBrowser`
  (`israeli_bank_scrapers/scrapers/base_scraper*.py`) — the login-flow state
  machine, progress events, browser lifecycle, error handling.
- **OTP (one-time-code) support**: `BaseScraper.otp_provider` /
  `request_otp_code()` and `OtpStep` (in `LoginOptions`) let a scraper pause
  mid-login for a texted/emailed code, and resume once it's supplied — the
  CLI protocol (`otp_required`/`otp_code`) and Dart client already support
  this. No scraper currently uses it (previously built out for insurance
  companies that have since been removed from this port — see
  `CONTRIBUTING.md`/git history if you want that code back) — it's kept as
  general-purpose infrastructure for any future bank/card company whose
  login needs a mid-flow code.
- **Full shared helpers** (`israeli_bank_scrapers/helpers/`): element waiting
  and interaction, navigation, in-page `fetch()`, transaction post-processing
  (installment date-fixing, filtering, sorting), month-range calculation,
  chunking, session storage access.
- **All 18 banks/credit-card companies from the upstream library** — full
  parity, wired up via `factory.py`'s `create_scraper()`:
  - **Bank Leumi** — DOM login + in-page `fetch()` for transactions.
  - **Bank Hapoalim** — DOM login + in-page `fetch()`, includes the
    optional "extra scrap" per-transaction enrichment call.
  - **Discount Bank** / **Mercantile Bank** — DOM login + in-page `fetch()`
    against Discount's Titan API (Mercantile is a one-line subclass of
    Discount with a different login URL).
  - **Isracard** / **Amex** — API-driven login (no DOM form at all — it's
    all `fetch()` calls) via a shared base class, since both card companies
    run on the same backend with different base URLs/company codes. Both
    sit behind Cloudflare Bot Management, which blocks vanilla Chromium
    automation — see **Bot detection: Isracard/Amex** below.
  - **Max** — DOM login (multi-step popup/tab flow) + in-page `fetch()`,
    including plan-type classification and category loading.
  - **Visa Cal** — login happens inside an iframe, and the scraper has to
    intercept an outgoing SSO request to read its Authorization header
    before making plain (out-of-page) HTTP calls against the card API.
  - **Mizrahi** — intercepts a live network request the page itself makes
    to steal its POST body and a custom XSRF header before replaying it.
  - **Union Bank** — DOM table scraping, including a quirky
    "expanded description" row-merge behavior in the transaction table.
  - **Beinleumi** / **Massad** / **Otsar Hahayal** / **Pagi** — share one
    base class (`base_beinleumi_group.py`) covering both an "old" and "new"
    UI on the FIBI banking group's shared platform; each subclass differs
    only by base URL.
  - **Yahav** — multi-portfolio account switching with a custom
    date-picker navigation flow.
  - **One Zero** — the only scraper that never launches a browser at all
    (`BaseScraper`, not `BaseScraperWithBrowser`) — pure GraphQL/REST API
    client, with full OTP/2FA support (phone-based trigger or a
    previously-obtained long-term token).
  - **Behatsdaa** — API-driven, reads an auth token out of local storage.
  - **Beyahad Bishvilha** — DOM scraping of a card balance/transactions page.
- **A factory** (`factory.py`) wiring all 18 into `create_scraper()`, plus a
  matching **credentials registry** (`credentials.py`) so any caller that
  receives credential fields as a plain dict (the CLI, eventually anything
  else) can build the right dataclass without a big if/elif chain.

## Verification status

Publishing this openly means being precise about what's actually been proven
against a live bank site versus what only passes unit tests against
synthetic data. These are meaningfully different confidence levels — please
read this table before relying on an "unverified" row for anything real.

| Company | Status | Notes |
|---|---|---|
| Leumi | ✅ Verified live | Confirmed working end-to-end |
| Visa Cal | ✅ Verified live | Needed two real fixes during testing (see git history: nonexistent Playwright API call, SPA navigation-detection gap) |
| Mercantile | ✅ Verified live | Needed one real fix (same SPA navigation-detection bug as Visa Cal) |
| Hapoalim | ✅ Verified live | Needed one real fix (API returns integer date fields; Python's strptime is stricter than JS's moment()) |
| Amex | ✅ Verified live | Needed two real fixes: Cloudflare Bot Management required switching to the Camoufox engine (see below), then a string-vs-number amount-field bug once past login |
| Discount | ⚠️ Untested live, fix applied | Shares Mercantile's scraper code — the same fix likely resolves it, but it hasn't been separately confirmed |
| Isracard | ⚠️ Untested live, fixes applied | Shares Amex's exact scraper code (same base class) — both of Amex's fixes apply here too, but not yet separately confirmed |
| Max | ⚠️ Unverified live | Passes unit tests against synthetic data only |
| Mizrahi | ⚠️ Unverified live | Most structurally complex remaining scraper — network-request interception, likely to need a fix |
| Union Bank | ⚠️ Unverified live | Passes unit tests against synthetic data only |
| Beinleumi | ⚠️ Unverified live | Passes unit tests against synthetic data only |
| Massad | ⚠️ Unverified live | Shares Beinleumi's scraper code |
| Otsar Hahayal | ⚠️ Unverified live | Shares Beinleumi's scraper code |
| Pagi | ⚠️ Unverified live | Shares Beinleumi's scraper code |
| Yahav | ⚠️ Unverified live | Multi-portfolio flow, likely to need a fix |
| One Zero | ⚠️ Unverified live | Pure API client, no browser — different failure mode than the rest |
| Behatsdaa | ⚠️ Unverified live | Passes unit tests against synthetic data only |
| Beyahad Bishvilha | ⚠️ Unverified live | Passes unit tests against synthetic data only |

**A recurring bug class worth knowing about if you're testing an
"unverified" row:** three scrapers so far (Visa Cal, Discount, Mercantile)
hit the same bug — a helper that checks "is the current page loaded"
instead of actually waiting for a client-side (SPA) redirect to finish,
so the login result gets checked before the real redirect happens. The
symptom is a login that looks like it should have worked, but reports
`UNKNOWN_ERROR` with a final URL that's still the login page. If you hit
that pattern, check whether the scraper's `post_action` uses
`wait_for_navigation` (suspect) vs. `wait_for_redirect` (the fix) in
`helpers/navigation.py`.

**A second recurring bug class:** APIs that return numeric fields as strings
(or vice versa in spirit), which JavaScript coerces silently but Python does
not. Hapoalim returned date fields as raw integers where `datetime.strptime()`
needs a string (fixed there, and proactively in Discount/Mercantile). Amex
returned amount fields (`dealSum`, `paymentSum`) as strings where Python's
unary `-` needs a number — worse, a boolean-ish field (`dealSumOutbound`)
arrived as the string `"0"`, which is truthy to Python's `bool()` even
though it numerically means "false" (JS's `Boolean("0")` is *also* `true`,
so this exact case doesn't even match JS's own semantics — the original TS
likely never received a string here). If a scraper fails with `str, not int`,
`str, not float`, or an operator error on a field pulled straight from an
API response, this class of bug is the first thing to check — search for
where that field is used and add explicit `str()`/`float()` coercion, and
double-check any truthiness check derived from it.

## Bot detection: Isracard/Amex

Both card companies sit behind Cloudflare Bot Management, which has been
blocking automated scraping badly enough — since early 2026 — that it's a
known, industry-wide problem, not something specific to this port. The
upstream JS library's own mitigation (masked user-agent, blocking a
bot-detection script) is faithfully ported here and is the same thing that
fails; regular Chromium automation, Puppeteer or Playwright, apparently
isn't enough against Cloudflare's current detection tier for these two.

**The fix implemented here:** [Camoufox](https://camoufox.com/), a hardened
Firefox build with built-in, statistically-realistic fingerprint spoofing
(this is the same approach the most actively-maintained fork of the
original JS library switched to for the same reason). `IsracardAmexBaseScraper`
now defaults to `browser_engine="camoufox"` — everything else about how you
call it is unchanged.

To use it:
```bash
pip install -r requirements-camoufox.txt
python -m camoufox fetch   # downloads Camoufox's Firefox binary, one-time
```

If you don't install `camoufox`, calling `create_scraper()` for Isracard or
Amex will fail with a clear error telling you to — every other company is
unaffected and keeps using plain Chromium.

**Confirmed working against a live site (Amex).** Camoufox got past
Cloudflare's block, and a follow-up bug (string-vs-number amount fields —
see the recurring-bug notes above) was found and fixed once real transaction
data started coming back. Isracard shares the exact same scraper code and
almost certainly benefits from both fixes, but hasn't been separately
tested — if you use Isracard, please report back either way (see
CONTRIBUTING.md).

## Why Playwright, not Selenium

Puppeteer and Playwright share the same automation model (page/frame,
`$eval`-style DOM queries, `waitForSelector`, request/response interception),
so most of the original code translates near line-for-line. Selenium's API
and execution model differ enough (no first-class frame/page objects tied to
a single browser context in the same way, weaker network-request hooks) that
the port would look less like the source material and be harder to keep in
sync if the upstream JS library changes.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

Only needed if you're using Isracard or Amex (see **Bot detection:
Isracard/Amex** above) — everything else uses plain Chromium:
```bash
pip install -r requirements-camoufox.txt
python -m camoufox fetch
```

**Using this from a Flutter app instead of directly as a Python library?**
See [FLUTTER_INTEGRATION.md](FLUTTER_INTEGRATION.md) — it covers building a
bundled executable with Chromium included (so end users need nothing
installed), the stdin/stdout NDJSON protocol it speaks
(`israeli_bank_scrapers/cli.py`), and a ready-to-use Dart client. **Pre-built
executables for Windows/macOS/Linux are also published automatically on
every tagged release** — check the repo's Releases page before building
one yourself.

### Running the example script

`python examples/scrape.py` on its own will fail with
`ModuleNotFoundError: No module named 'israeli_bank_scrapers'` — running a
script directly only puts *that script's own folder* on Python's import
path, not the project root next to it where the package actually lives.
Two fixes, pick one:

**Run it as a module** (from the project root, i.e. `C:\projects\python\ibs_py`
or wherever you cloned this):
```powershell
python -m examples.scrape
```

**Or install the package** (once), then run the script however you like:
```powershell
pip install -e .
python examples/scrape.py
```

### Setting the credential environment variables (Windows PowerShell)

Every company's exact env var names are in
[TESTING_COMMANDS.md](TESTING_COMMANDS.md) — copy-paste blocks for all 18.
Leumi, for example:

```powershell
$env:IBS_COMPANY = "leumi"
$env:LEUMI_USERNAME = "your_username"
$env:LEUMI_PASSWORD = "your_password"
python -m examples.scrape
```

These only last for the current PowerShell session. Don't put real
credentials in a script you might commit — if you want something more
durable than retyping them each session, load a local (git-ignored) `.env`
file via `python-dotenv` instead of hardcoding or permanently exporting them.

```bash
IBS_COMPANY=leumi LEUMI_USERNAME=... LEUMI_PASSWORD=... python -m examples.scrape
```


## Testing

Testing splits into three layers, from cheapest/safest to most realistic.

### 1. Unit tests — no browser, no network

Pure-logic tests for the transaction post-processing (installment date
shifting, filtering, sorting) and the polling/timeout helper.

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/test_helpers_pure_logic.py tests/test_factory.py -v
```

### 2. Browser smoke tests — real Chromium, local HTML fixture, no network

This is the layer that actually validates the Puppeteer → Playwright
translation of the DOM-interaction helpers (`fill_input`, `click_button`,
`wait_until_element_found`, `dropdown_select`, ...) — the part of a port
like this most likely to have a subtle bug. It launches a real (headless)
Chromium against a bundled local HTML fixture (`tests/fixtures/fake_login_page.html`)
that mimics the shape of a bank login form, so it never touches a real site.

```bash
playwright install chromium   # one-time
pytest tests/test_browser_smoke.py -v
```

Run everything together with `pytest -v`.

### 3. Live scraper test — your own bank, run locally, never in a shared/hosted environment

This is the only layer that proves an actual bank scraper (e.g. `leumi.py`)
still matches the bank's real, current site. There's no way to automate this
safely on your behalf — it needs your real credentials against your real
bank account — so it's on you to run locally:

```bash
IBS_COMPANY=leumi LEUMI_USERNAME=... LEUMI_PASSWORD=... python -m examples.scrape
```

Tips for this layer:
- Set `IBS_SHOW_BROWSER=1` so you can watch it and catch a stale selector
  immediately instead of staring at a timeout.
- Set `IBS_LOG_LEVEL=DEBUG` for step-by-step logs from every `debug.debug(...)`
  call in the scraper — this found and fixed several real bugs during
  development (see Verification status above).
- A `failure_screenshot.png` is saved automatically next to the script on
  any failure.
- If it breaks, it's very likely a selector or URL change on the bank's
  side (see "Honest caveats" below) — diff against the current
  `src/scrapers/<bank>.ts` in the upstream repo to see what changed, and
  update the matching constant/selector here.

## Honest caveats

- **These sites change their DOM/selectors without notice.** The upstream JS
  repo has a constant stream of "bank X changed their login page" fixes —
  expect the same here. Treat `leumi.py`'s selectors as a snapshot, not a
  guarantee.
- **Bot detection.** Some of these institutions actively try to block
  headless automation. `show_browser=True` (a visible, non-headless browser)
  is the most reliable workaround during development; this port also
  approximates `israeli-bank-scrapers`' user-agent override and cache-disable
  behavior via Chrome DevTools Protocol calls (see the docstring in
  `base_scraper_with_browser.py` for the exact limitations vs. the original
  Puppeteer calls).
- **Terms of service.** Automating login to your own bank account is between
  you and your bank's ToS — same legal footing as the original JS library,
  which this doesn't change.
- **Credentials never leave your machine** in this code — everything runs
  locally against your own Playwright browser instance, same trust model as
  upstream.
- **A general `fill_input()` improvement, from cross-referencing a sibling
  project**: some frameworks' form validation appears sensitive to typing
  *speed*, not just the event mechanism — Playwright's default `.type()`
  fires keystrokes essentially instantly with uniform timing, which certain
  Angular reactive forms may reject even though the events themselves look
  correct. `fill_input()` retries with a realistic ~45ms per-character
  delay before falling back to the more mechanical `page.fill()` /
  native-setter tiers. Confirmed via mocks that the tiers fire in the right
  order with the right parameters. This was built and tested while
  developing insurance-company scrapers that have since been removed from
  this port, but the fix itself is generic and worth keeping — any
  bank/card scraper with a stubborn Angular field could hit the same class
  of issue.
- Phoenix, and every insurance/pension/investment company previously
  explored in this port (Harel, Migdal, Menora, Clal), are not part of this
  codebase — removed at the maintainer's request after being built and, in
  some cases, confirmed working live. If you want to rebuild any of these,
  the general architecture (OTP support, the `fill_input` retry tiers) is
  still here to build on; see CONTRIBUTING.md.

## Porting another bank

1. Open the original `src/scrapers/<bank>.ts` in the upstream repo.
2. Create `israeli_bank_scrapers/scrapers/<bank>.py`, using `leumi.py` as
   the structural template:
   - a `<Bank>Credentials` dataclass for its login fields (see
     `definitions.py`'s `SCRAPERS` dict for what each bank expects),
   - module-level constants for URLs/selectors/error-message strings
     (translate verbatim — these are the bank's actual DOM/text),
   - a `_get_possible_login_results()` function,
   - a `<Bank>Scraper(BaseScraperWithBrowser[<Bank>Credentials])` class
     implementing `get_login_options()` and `fetch_data()`.
3. Register it in `factory.py`.
4. The helper functions in `helpers/elements_interactions.py`,
   `helpers/navigation.py`, and `helpers/fetch.py` cover essentially every
   DOM operation the original scrapers use — you shouldn't need new
   primitives for most banks.

## License

MIT — see [LICENSE](LICENSE). This is a derivative work of
`eshaham/israeli-bank-scrapers` (also MIT), and the LICENSE file here
carries that attribution forward.
