"""Build the bundled CLI executable for the current OS.

Usage:
    pip install -r requirements.txt -r build/requirements-build.txt
    playwright install chromium   # if not already done
    python build/build.py

Output: dist/israeli-bank-scrapers-cli/ (a folder, not a single file — see
build/cli.spec for why). Copy that whole folder into your Flutter app's
bundled resources for the current platform.

Run this once per target OS on a machine of that OS — Chromium binaries are
platform-specific, and PyInstaller doesn't cross-compile.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    spec_path = ROOT / "build" / "cli.spec"
    print(f"Building with PyInstaller using {spec_path} ...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec_path), "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build" / "work"), "--noconfirm"],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    output_dir = ROOT / "dist" / "israeli-bank-scrapers-cli"
    print(f"\nBuild complete: {output_dir}")
    print("Copy this entire folder into your Flutter app's bundled resources.")


if __name__ == "__main__":
    main()
