# Outreach drafts

Copy-paste starting points for announcing this and asking for testers.
Fill in `<your repo URL>` everywhere before posting. Adjust tone/length to
the venue — these are drafts, not scripts.

---

## 1. GitHub Discussion on eshaham/israeli-bank-scrapers

Post as a new **Discussion** (not an Issue — this isn't a bug report against
the upstream project) in that repo's Discussions tab.

**Title:** A Python/Playwright port of this project — looking for testers on
untested banks

**Body:**

> Hi all — first, thanks for building and maintaining this. It's saved a lot
> of people a lot of work, myself included.
>
> I needed the same scraping logic for a Python-based project (specifically,
> a Flutter desktop app that shells out to a bundled Python executable), so I
> ported the core architecture and all 18 bank/credit-card scrapers from
> this repo's TypeScript source to Python + Playwright. It's a fairly direct
> translation — Puppeteer and Playwright share almost the same API surface,
> so most of the logic maps close to line-for-line.
>
> Repo: `<your repo URL>`
>
> **Where I need help:** only 3 of 18 companies have actually been confirmed
> against a live site so far (Leumi, Visa Cal, Mercantile) — see the
> [verification table](`<your repo URL>`#verification-status) in the README.
> The rest pass unit tests against synthetic data but haven't touched a real
> bank yet. If you bank with one of the untested ones and are willing to
> spend a few minutes running it locally (with your own credentials, on your
> own machine — nothing leaves it), I'd genuinely appreciate a test run. Full
> instructions and what to report if it fails are in
> [CONTRIBUTING.md](`<your repo URL>`/blob/main/CONTRIBUTING.md).
>
> Full attribution and MIT license carried over, obviously — this only
> exists because of the work already done here. Happy to answer questions
> about the port, and equally happy to hear if this isn't the right venue
> for this kind of post — just let me know and I'll take it down.

---

## 2. Direct outreach to baruchiro/israeli-bank-scrapers-desktop

Open as an **Issue** on that repo (most maintainers treat "hey, related
project" notes as fine there), or find another contact method the
maintainer lists if they'd prefer that.

**Title:** Python/Playwright port of israeli-bank-scrapers — thought this
might be relevant to your project

**Body:**

> Hi — I've been working on a Python port of `israeli-bank-scrapers`
> (`<your repo URL>`) for a Flutter desktop app of my own, and given yours
> solves a very similar problem (bundling this kind of scraper into a
> trustworthy local desktop app), I thought it might be worth a look or a
> mention if it's useful to you or your users.
>
> Same trust model as yours — runs entirely locally, credentials never leave
> the machine, source is fully readable. Currently at full parity with the
> upstream bank list, though only 3 of 18 have been confirmed against a live
> site so far (see the verification table in the README) — still working
> through testing the rest.
>
> No ask here beyond "thought you'd want to know this exists" — feel free to
> ignore if it's not relevant to what you're doing.

---

## Notes on tone

- Don't oversell "full parity" — it's true of the *code*, not of
  *confirmed-working* status. Every draft above says both things
  explicitly, on purpose. Leading with the caveat is what makes the ask for
  help credible.
- Expect scrutiny given this touches bank login — that's appropriate, not
  hostile. Answer plainly rather than defensively if someone questions the
  security model.
