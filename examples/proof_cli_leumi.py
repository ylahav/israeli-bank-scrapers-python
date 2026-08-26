"""One-shot live Leumi CLI proof. Reads LEUMI_USERNAME / LEUMI_PASSWORD from env.
Never prints credentials. Prints progress + account/txn counts only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    user = os.environ.get("LEUMI_USERNAME", "").strip()
    pw = os.environ.get("LEUMI_PASSWORD", "").strip()
    if not user or not pw:
        print(
            "NEED_CREDS: in PowerShell set:\n"
            '  $env:LEUMI_USERNAME = "..."\n'
            '  $env:LEUMI_PASSWORD = "..."\n'
            "then re-run this script."
        )
        return 2

    req = {
        "company_id": "leumi",
        "start_date": (date.today() - timedelta(days=90)).isoformat(),
        "credentials": {"username": user, "password": pw},
        "options": {"show_browser": True},
    }
    print("Starting israeli_bank_scrapers.cli for leumi (show_browser=True)...")
    proc = subprocess.run(
        [sys.executable, "-m", "israeli_bank_scrapers.cli"],
        input=json.dumps(req),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        timeout=300,
    )

    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            print("NON_JSON", line[:80])
            continue
        kind = obj.get("type")
        if kind == "progress":
            print("progress:", obj.get("progress"))
        elif kind == "result":
            ok = obj.get("success")
            print("success:", ok)
            if not ok:
                print("error_type:", obj.get("error_type"))
                print("error_message:", obj.get("error_message"))
            else:
                accounts = obj.get("accounts") or []
                print("accounts:", len(accounts))
                print()
                print("=== Account balances ===")
                for a in accounts:
                    n = str(a.get("account_number") or "")
                    masked = ("*" * max(0, len(n) - 4)) + n[-4:] if n else "?"
                    bal = a.get("balance")
                    bal_s = f"₪{bal:,.2f}" if isinstance(bal, (int, float)) else "n/a"
                    tag = " (savings)" if a.get("savings_account") else ""
                    txns = a.get("txns") or []
                    print(f"  …{masked}{tag}: {bal_s}  ({len(txns)} txns)")
                print("========================")
        elif kind == "fatal_error":
            print("fatal:", obj.get("message"))
        else:
            print("event:", kind)

    err_lines = [l for l in (proc.stderr or "").splitlines() if l.strip()][-20:]
    if err_lines:
        print("--- stderr (tail) ---")
        print("\n".join(err_lines))
    print("exit_code", proc.returncode)
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
