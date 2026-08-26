# Contributing

Thanks for considering testing this against your own bank — that's the most
useful thing anyone can do for this project right now. This doc covers how,
and what to send back.

## Before you start

- **Never share your actual credentials with anyone**, including in a
  GitHub issue, a screenshot, or a debug log. This project never asks for
  them and never needs them — you run everything locally, on your own
  machine, with your own login.
- Read the code first if you're not already comfortable with what it does.
  `israeli_bank_scrapers/scrapers/<your-bank>.py` is the one file that
  matters most — it's the only thing that touches your bank's actual site.
- If your bank isn't in the [Verification status
  table](README.md#verification-status) as "Verified live," go in expecting
  it might not work on the first try. That's normal — see "What a
  productive report looks like" below for how to turn a failure into a
  quick fix.

## How to test

1. Clone the repo and follow **Setup** in the README.
2. Set the environment variables for your bank — copy-paste blocks for
   every company are in [TESTING_COMMANDS.md](TESTING_COMMANDS.md), so you
   don't have to work out field names yourself.
3. Run with the browser visible and debug logging on, so you can see what's
   actually happening instead of guessing:

   ```bash
   IBS_COMPANY=<your_bank> IBS_SHOW_BROWSER=1 IBS_LOG_LEVEL=DEBUG \
     <YOURBANK>_<FIELD>=... python -m examples.scrape
   ```

   (PowerShell: set each as `$env:VAR = "value"` first, then
   `py -m examples.scrape`.)

4. Watch what happens in the browser window alongside the console output.

## If it works

Open an issue (or comment on the relevant "testing wanted" issue) saying
which bank, that it worked, and roughly how many transactions/accounts came
back. That's enough — we'll update the verification table.

## If it fails: what a productive report looks like

The single most useful thing you can send is the **debug log** from a run
with `IBS_LOG_LEVEL=DEBUG` set — paste the full console output. Two things
in particular:

- The last few `DEBUG:israeli_bank_scrapers...` lines before the failure.
- The line that says `no login result matched. final url was: ...` if you
  see one — that URL is often the single most diagnostic piece of
  information in the whole log.

A `failure_screenshot.png` is saved automatically next to the script on any
failure — attach it too.

Also useful, in order of how often it matters:

1. **What you actually saw happen in the browser window** — did a login
   form appear? Did the fields get filled in? Did anything visibly happen
   after you'd expect it to submit?
2. **Whether the final URL looks like the login page or somewhere else** —
   this is often the tell for the specific bug described in the
   Verification status table (an SPA redirect that wasn't waited for
   correctly).
3. Which company, and roughly when you tested (bank sites change their
   pages over time, so "this broke in March" and "this broke today" can
   mean different things even for the same bank).

## What NOT to send

- Real credentials, in any form.
- Your actual account number, balances, or transaction contents — crop or
  redact them out of any screenshot before posting.
- A raw HAR file or full network capture without checking it first — these
  can contain session tokens or other sensitive headers.

## Fixing it yourself

If you're comfortable reading the diff between what a scraper does and what
the actual page looks like, PRs are very welcome. The pattern to check
first, given what's broken so far: does the scraper's login flow call
`wait_for_navigation` (in `helpers/navigation.py`) where the bank's site
does a client-side (SPA) redirect rather than a full page reload? If so,
`wait_for_redirect` is usually the fix — see `scrapers/discount.py` or
`scrapers/visa_cal.py`'s `post_action` for a worked example.
