# Outreach drafts

Copy-paste starting points for announcing this and asking for testers.
Repo URL is already filled in below
(`https://github.com/ylahav/israeli-bank-scrapers-python`) — double-check it
before posting in case the repo ever moves or gets renamed. Adjust
tone/length to the venue — these are drafts, not scripts.

---

## 1. GitHub Issue on eshaham/israeli-bank-scrapers

That repo doesn't have GitHub Discussions enabled (checked — no
Discussions tab exists there), so post this as a regular **Issue** instead.
It's not a bug report, so consider adding a `question` label if one's
available when you create it (the repo already uses that label on similar
non-bug issues) — otherwise an unlabeled issue is completely fine too.

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
> Repo: https://github.com/ylahav/israeli-bank-scrapers-python
>
> **Where I need help:** only 5 of 18 companies have actually been confirmed
> against a live site so far (Leumi, Visa Cal, Mercantile, Hapoalim, Amex) — see the
> [verification table](https://github.com/ylahav/israeli-bank-scrapers-python#verification-status) in the README.
> The rest pass unit tests against synthetic data but haven't touched a real
> bank yet. If you bank with one of the untested ones and are willing to
> spend a few minutes running it locally (with your own credentials, on your
> own machine — nothing leaves it), I'd genuinely appreciate a test run. Full
> instructions and what to report if it fails are in
> [CONTRIBUTING.md](https://github.com/ylahav/israeli-bank-scrapers-python/blob/main/CONTRIBUTING.md).
>
> Full attribution and MIT license carried over, obviously — this only
> exists because of the work already done here. Happy to answer questions
> about the port, and equally happy to hear if this isn't the right venue
> for this kind of post — just let me know and I'll take it down.

---

## 2. Direct outreach to brafdlog/budget-tracking (formerly israeli-bank-scrapers-desktop)

This project appears to have moved/evolved from `baruchiro/israeli-bank-scrapers-desktop`
to `brafdlog/budget-tracking` (also known as Caspion) — same problem space
(a downloadable desktop app for automated Israeli bank/budget tracking,
built on the original JS `israeli-bank-scrapers`), different current
maintainer. That project has an active Discord community (badge on its
README) — worth checking whether Discord or a GitHub issue is the better
fit before posting; a GitHub issue is the safer default if unsure.

Open as an **Issue** on that repo (most maintainers treat "hey, related
project" notes as fine there), or find another contact method the
maintainer lists if they'd prefer that.

**Title:** Python/Playwright port of israeli-bank-scrapers — thought this
might be relevant to your project

**Body:**

> Hi — I've been working on a Python port of `israeli-bank-scrapers`
> (https://github.com/ylahav/israeli-bank-scrapers-python) for a Flutter desktop app of my own, and given yours
> solves a very similar problem (bundling this kind of scraper into a
> trustworthy local desktop app), I thought it might be worth a look or a
> mention if it's useful to you or your users.
>
> Same trust model as yours — runs entirely locally, credentials never leave
> the machine, source is fully readable. Currently at full parity with the
> upstream bank list, though only 5 of 18 have been confirmed against a live
> site so far (see the verification table in the README) — still working
> through testing the rest.
>
> No ask here beyond "thought you'd want to know this exists" — feel free to
> ignore if it's not relevant to what you're doing.

### 2b. If posting to their Discord instead — Hebrew draft

Their Discord community runs primarily in Hebrew — use this instead of a
translated version of the English draft above. Discord is a more casual
register than a GitHub issue, so this is written shorter and more
conversationally on purpose, not just translated word-for-word.

> היי כולם,
> בניתי פורט לפייתון (עם Playwright) לספרייה israeli-bank-scrapers המקורית — הייתי צריך את זה לפרויקט Flutter משלי (אפליקציית דסקטופ שמפעילה תהליך פייתון נפרד ברקע). זה בעיקר תרגום ישיר יחסית — הלוגיקה כמעט זהה, רק Puppeteer הוחלף ב-Playwright.
>
> הריפו: https://github.com/ylahav/israeli-bank-scrapers-python
>
> חשבתי שזה יכול להיות רלוונטי גם כאן, מאחר שאתם פותרים בעיה דומה — עטיפת סקרייפר בתוך אפליקציית דסקטופ אמינה. מודל האמון זהה: הכל רץ לוקאלית על המחשב שלך, שום credential לא נשלח לשום מקום חוץ מהאתר של הבנק עצמו.
>
> חשוב לציין בכנות: רק 5 מתוך 18 בנקים/חברות אשראי אומתו בפועל מול אתר חי עד עכשיו (יש טבלת סטטוס מפורטת ב-README) — עדיין בתהליך של בדיקת השאר.
>
> בכל מקרה, אם זה לא רלוונטי לכם — אין בעיה להתעלם 🙂

---

## Notes on tone

- Don't oversell "full parity" — it's true of the *code*, not of
  *confirmed-working* status. Every draft above says both things
  explicitly, on purpose. Leading with the caveat is what makes the ask for
  help credible.
- Expect scrutiny given this touches bank login — that's appropriate, not
  hostile. Answer plainly rather than defensively if someone questions the
  security model.
- Match the venue's actual language and register — a GitHub issue reads
  fine in English even to a Hebrew-speaking maintainer, but a community
  chat/Discord that operates in Hebrew needs a genuinely Hebrew message,
  not an English draft the reader has to translate themselves. Check before
  assuming English is fine everywhere.
