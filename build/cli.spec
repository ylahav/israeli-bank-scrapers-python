# PyInstaller spec for the israeli-bank-scrapers CLI.
#
# Produces a single-folder (not single-file — see note below) distributable
# containing:
#   - the CLI executable itself
#   - a bundled Chromium browser (so end users need nothing installed)
#
# Build with:
#   pyinstaller build/cli.spec
#
# Output lands in dist/israeli-bank-scrapers-cli/ — ship that whole folder
# alongside your Flutter app (e.g. under its own resources/ directory) and
# have Dart invoke the executable inside it (see FLUTTER_INTEGRATION.md).
#
# NOTE ON --onefile: PyInstaller's single-EXE mode extracts everything to a
# temp directory on *every launch*, which is slow and awkward with a ~150MB
# Chromium payload. --onedir (the default here) is the right choice for a
# bundled Chromium — the folder is copied once at install time, launches are
# instant, and Chromium's files don't need re-extracting per run.

import os
import sys
import glob

block_cipher = None

# Locate the Playwright-managed Chromium install on THIS build machine so it
# can be bundled into the output. Build this on each target OS separately
# (Windows build machine -> Windows Chromium, etc.) — Chromium binaries are
# not cross-platform.
def _find_playwright_browsers_dir():
    env_override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    candidates = [env_override] if env_override else []

    if sys.platform == "win32":
        candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright"))
    elif sys.platform == "darwin":
        candidates.append(os.path.expanduser("~/Library/Caches/ms-playwright"))
    else:
        candidates.append(os.path.expanduser("~/.cache/ms-playwright"))

    for c in candidates:
        if c and os.path.isdir(c):
            return c
    raise SystemExit(
        "Could not find the Playwright browsers directory (checked $PLAYWRIGHT_BROWSERS_PATH and the "
        "default OS cache location). Run `python -m playwright install chromium` first, then re-run this build."
    )


browsers_dir = _find_playwright_browsers_dir()

# Playwright ships two separate binaries under the same cache root: the full
# "chromium-*" build (used for headed / show_browser=True runs) and a
# lighter "chromium_headless_shell-*" build (used for headless runs, which
# is the default). Bundle both — missing either one breaks exactly one of
# the two run modes, which is an easy thing to not notice until later.
datas = []
for pattern in ("chromium-*", "chromium_headless_shell-*"):
    matches = sorted(glob.glob(os.path.join(browsers_dir, pattern)))
    if not matches:
        raise SystemExit(
            f"No {pattern} folder found under {browsers_dir}. Run `python -m playwright install chromium`."
        )
    newest = matches[-1]  # newest version if multiple are cached
    datas.append((newest, os.path.join("ms-playwright", os.path.basename(newest))))

a = Analysis(
    ["../israeli_bank_scrapers/cli.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=["playwright.async_api", "httpx"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="israeli-bank-scrapers-cli",
    debug=False,
    strip=False,
    upx=False,
    console=True,  # this is a stdio-protocol CLI, never hide the console subsystem
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="israeli-bank-scrapers-cli",
)
