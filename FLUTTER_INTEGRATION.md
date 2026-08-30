# Using this from Financial Organizer (Flutter)

Flutter has no way to run Playwright/Chromium directly — this Python package
runs as a **separate bundled process** that your Flutter app launches and
talks to over stdin/stdout. This doc covers the whole path: build → bundle →
call from Dart.

All 18 banks/credit-card companies from the upstream library are supported
(see `israeli_bank_scrapers/credentials.py`'s `CREDENTIALS_CLASSES` for the
full list and each company's required credential fields) — everything below
applies the same way regardless of which company you're calling.

## 0. Skip building it yourself — download a pre-built one

Every tagged release (`v*`) triggers a GitHub Actions workflow
(`.github/workflows/release.yml`) that builds this on real Windows, macOS,
and Linux runners and attaches a ready-to-use zip for each to that
release — no local Python/PyInstaller setup needed at all. Check the
repo's **Releases** page; download the zip matching your OS, unzip it, and
skip straight to **section 2** below.

The known limitation: these pre-built releases bundle plain Chromium only —
Isracard/Amex (which need the separate Camoufox engine, see **Bot
detection: Isracard/Amex** in the main README) won't work from a downloaded
release yet. If you need those two, build locally per section 1 below with
`requirements-camoufox.txt` installed first.

## 1. Build the executable yourself (once per target OS)

```bash
pip install -r requirements.txt -r build/requirements-build.txt
playwright install chromium
python build/build.py
```

**On Windows, if you have more than one Python install** (common if you've
installed Python via more than one route — e.g. python.org installer plus
the Microsoft Store version), make sure every command above uses the *same*
interpreter — the one you `pip install`ed into. `python ...` and `py ...`
can silently resolve to different installs. Safest bet: pick one launcher
(`py` is usually the more reliable pick on Windows) and use it consistently
for every command in this doc — `py -m pip install ...`, `py -m playwright
install chromium`, `py build/build.py`. If a command mysteriously "can't
find" a package you just installed, this mismatch is almost always why —
run `python -c "import sys; print(sys.executable)"` and `py -c "import sys;
print(sys.executable)"` and compare.

This produces `dist/israeli-bank-scrapers-cli/` — a folder (not a single
`.exe`) containing the CLI executable plus a bundled Chromium. It's a folder
rather than a single file on purpose: PyInstaller's single-file mode
re-extracts everything (including the ~150MB browser) to a temp directory on
*every launch*, which is slow. The folder is copied once at install time and
launches instantly after that.

**Run this on a machine of each OS you ship for** — Windows build machine →
Windows executable, macOS → macOS, etc. Chromium binaries aren't
cross-platform, and neither is PyInstaller's output.

Verified in testing: the built executable runs standalone with **no Python
installed** and correctly launches its bundled Chromium — including both the
full build (used for `show_browser: true`) and the separate headless-shell
build Playwright uses by default, which is easy to miss bundling since it's
a second binary under the same cache folder.

**If your app supports Isracard or Amex:** those two need the separate
Camoufox (stealth Firefox) engine to get past Cloudflare Bot Management —
see the main README's "Bot detection: Isracard/Amex" section. `build/cli.spec`
currently only bundles Chromium; if you need Isracard/Amex working in the
packaged app (not just via `examples/scrape.py` locally), the spec needs a
similar `datas` entry for Camoufox's Firefox binary before building. This
hasn't been done yet — flagging it now so it doesn't surprise you later if
those two silently fail in a shipped build while working fine in dev.

## 2. Bundle it into your Flutter app

Copy the whole `dist/israeli-bank-scrapers-cli/` folder into your Flutter
project as a platform-specific bundled resource — e.g.:

```
your_flutter_app/
  windows/
    resources/
      bank-scraper/          <- contents of dist/israeli-bank-scrapers-cli/
  macos/
    Resources/
      bank-scraper/
  linux/
    resources/
      bank-scraper/
```

The exact mechanism depends on your existing Tauri-sidecar-style setup — the
principle is the same one you already use there: ship the folder as a
platform asset, and resolve its path at runtime relative to the app's
install directory (not a hardcoded absolute path, which only works on your
dev machine).

## 3. Call it from Dart

Copy `bank_scraper_service.dart` from this folder into your Flutter app's
`lib/` (e.g. `lib/services/bank_scraper_service.dart`), then:

```dart
final service = BankScraperService(
  executablePath: resolveBundledExecutablePath(), // your own path resolution
);

await for (final event in service.scrape(
  companyId: 'leumi',
  credentials: {'username': user, 'password': pass},
  startDate: DateTime.now().subtract(const Duration(days: 90)),
)) {
  switch (event) {
    case ScrapeProgress p:
      setState(() => statusText = p.progress); // e.g. show "LOGGING_IN" in the UI
    case ScrapeSuccess s:
      // s.accounts is a List<Map<String, dynamic>> — see "Typed models" below
      handleAccounts(s.accounts);
    case ScrapeFailure f:
      showError(f.errorType, f.errorMessage);
  }
}
```

The stream emits zero or more `ScrapeProgress` events, then exactly one
`ScrapeSuccess` or `ScrapeFailure`, then closes. Some scrapers (currently
none shipped, but the plumbing is in place for upcoming insurance-company
support) can also emit `ScrapeOtpRequired` before the terminal event — see
below.

### One-time codes (OTP) — for logins that text/email you a code mid-flow

```dart
case ScrapeOtpRequired o:
  final code = await showOtpDialog(context: this.context, hint: o.context['hint']);
  o.submit(code);
```

The underlying CLI process genuinely pauses here — it's blocked reading
stdin, waiting for your app to call `submit()`. This works because
`BankScraperService` deliberately keeps the process's stdin open across the
whole scrape (not just for the initial request) specifically to support
this pause-and-resume. There's no built-in timeout on this wait; if your
dialog can be dismissed or abandoned, add your own timeout/cancellation
around it — an abandoned `ScrapeOtpRequired` otherwise leaves that CLI
process running indefinitely.

`o.context` always includes `company_id` and may include scraper-specific
hints (e.g. a masked phone number) worth showing the user — check the
specific scraper's code for what it sends.

### Checking the bundled build's version

```dart
final version = await service.getVersion();
```

A fast, one-shot request — the CLI answers with a single line and exits
immediately, without launching a browser at all. Useful for confirming
which version of the executable actually shipped in a given app build, or
for surfacing it in a settings/about screen. Throws `ScraperProcessException`
if the executable can't be started or the response is malformed — same
error type as everything else in this client.

## 4. Credential handling

Pass credentials to `scrape()` as a plain `Map<String, String>` matching the
field names the target company expects — check
`israeli_bank_scrapers/credentials.py`'s `CREDENTIALS_CLASSES` for the exact
field names per company (e.g. Leumi wants `username`/`password`, Isracard
wants `id`/`password`/`card6Digits`).

Credentials go over the CLI's **stdin**, not command-line arguments or
environment variables — this is deliberate: argv is visible in the OS
process list, env vars are marginally better but still process-inspectable.
Piping JSON over stdin, once per invocation, is the safest of the three.

**Storage is on you.** This package has no opinion on how Financial
Organizer stores saved credentials between runs (OS keychain, encrypted
local file, etc.) — that's Flutter/Dart-side application logic, not
something this scraper package should own.

## 5. Typed models instead of raw maps

`ScrapeSuccess.accounts` is currently `List<Map<String, dynamic>>` — the
exact shape matches `israeli_bank_scrapers/serialization.py`'s output
(mirrors the `TransactionsAccount`/`Transaction` dataclasses field-for-field,
enums as their string `.value`). If you'd rather have real typed Dart
classes (`Account`, `Transaction`, ...) instead of raw maps in your app code,
that's a natural next step — happy to generate those to match the JSON shape
exactly whenever useful.

## 6. Error handling shape

Two different failure modes, handled differently:

- **`ScrapeFailure`** — the scraper ran and cleanly reported a failure
  (wrong password, site requires a password change, generic error). Show
  this to the user; it's expected, recoverable behavior.
- **`ScraperProcessException`** (a stream error, not an event) — something
  went wrong *before* the scraper protocol could even produce a result:
  the executable wasn't found at the path you gave it, it crashed outright,
  or it emitted something that wasn't valid JSON. This points at a
  packaging/bundling problem on your end, not a bank-login problem — surface
  it differently (e.g. "something's wrong with the app," not "check your
  password").

## 7. What's not solved yet

- **Camoufox isn't bundled into the packaged executable yet.** Isracard and
  Amex need it (see the note in section 1) — works via `examples/scrape.py`
  locally once you `pip install -r requirements-camoufox.txt` and
  `python -m camoufox fetch`, but `build/cli.spec` doesn't package it into
  the app bundle yet. Needed before shipping those two companies to users.
- **Auto-updating the bundled scraper.** If a bank changes its site and a
  scraper needs a selector fix, that's a new Python build + a new app
  release under this setup — there's no separate update channel for just
  the scraper binary. Worth designing later if that cadence becomes painful.
- **Persisting the browsers across app versions.** Each rebuild currently
  re-bundles Chromium from scratch. If your installer size becomes a
  concern, downloading Chromium on first run (with a "setting up..."
  first-launch screen) instead of bundling is the usual trade-off — smaller
  installer, worse first-run experience, needs network access.
- **Real-world testing coverage.** Leumi, Visa Cal, Mercantile, Hapoalim,
  and Amex have been confirmed against live sites (Isracard shares Amex's
  exact code and is very likely fine too, but untested separately). The
  remaining companies pass unit tests against synthetic data but haven't
  been confirmed live yet. Debug with `IBS_SHOW_BROWSER=1`
  and `IBS_LOG_LEVEL=DEBUG` via `examples/scrape.py` before wiring a new
  company into the app.
- **The OTP round-trip plumbing exists but no insurance scraper does yet.**
  `BaseScraper.otp_provider`/`request_otp_code()`, `OtpStep` in
  `LoginOptions`, and the CLI's `otp_required`/`otp_code` NDJSON messages
  are all built and unit-tested — but they've never driven a real scraper
  end-to-end, since insurance companies (unlike every bank in this port)
  have no upstream TypeScript reference to translate from. Building the
  first one is genuinely new development, not a port.
- **`bank_scraper_service.dart` couldn't be compile-checked.** This
  sandbox has no Dart toolchain — every change to that file was verified by
  careful manual read-through only (which did catch one real null-safety
  bug), not `dart analyze` or an actual build. Run one before shipping,
  especially after the OTP-support changes.
