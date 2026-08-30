# Per-bank test commands

Copy-paste PowerShell blocks for testing each company via `examples/scrape.py`. Every env var name here is generated directly from `israeli_bank_scrapers/credentials.py`'s `CREDENTIALS_CLASSES` registry, so it's guaranteed to match what the code actually expects — if it ever looks wrong, the registry (not this file) is the source of truth; regenerate this file rather than hand-editing it.

**Never commit real credentials.** If you fill in real values below for your own testing, keep that copy local and untracked — don't paste real values into this file in the repo.

Add these two lines to any block below to watch the browser live and see step-by-step debug output:
```powershell
$env:IBS_SHOW_BROWSER = "1"
$env:IBS_LOG_LEVEL = "DEBUG"
```

**Isracard and Amex need an extra one-time setup step** before testing — they sit behind Cloudflare Bot Management and need the Camoufox engine (see README's "Bot detection: Isracard/Amex"):
```bash
pip install -r requirements-camoufox.txt
python -m camoufox fetch
```

## Testing checklist

| Company | Tested? | Result |
|---|---|---|
| Bank Leumi (`leumi`) | ☐ | |
| Bank Hapoalim (`hapoalim`) | ☐ | |
| Discount Bank (`discount`) | ☐ | |
| Mercantile Bank (`mercantile`) | ☐ | |
| Isracard (`isracard`) | ☐ | |
| Amex (`amex`) | ☐ | |
| Max (`max`) | ☐ | |
| Visa Cal (`visaCal`) | ☐ | |
| Mizrahi Bank (`mizrahi`) | ☐ | |
| Union (`union`) | ☐ | |
| Beinleumi (`beinleumi`) | ☐ | |
| Massad (`massad`) | ☐ | |
| Bank Yahav (`yahav`) | ☐ | |
| One Zero (`oneZero`) | ☐ | |
| Bank Otsar Hahayal (`otsarHahayal`) | ☐ | |
| Pagi (`pagi`) | ☐ | |
| Behatsdaa (`behatsdaa`) | ☐ | |
| Beyahad Bishvilha (`beyahadBishvilha`) | ☐ | |

## Commands

### Bank Leumi — `leumi`

```powershell
$env:IBS_COMPANY = "leumi"
$env:LEUMI_USERNAME = "..."
$env:LEUMI_PASSWORD = "..."
py -m examples.scrape
```

### Bank Hapoalim — `hapoalim`

```powershell
$env:IBS_COMPANY = "hapoalim"
$env:HAPOALIM_USERCODE = "..."
$env:HAPOALIM_PASSWORD = "..."
py -m examples.scrape
```

### Discount Bank — `discount`

```powershell
$env:IBS_COMPANY = "discount"
$env:DISCOUNT_ID = "..."
$env:DISCOUNT_PASSWORD = "..."
$env:DISCOUNT_NUM = "..."
py -m examples.scrape
```

### Mercantile Bank — `mercantile`

```powershell
$env:IBS_COMPANY = "mercantile"
$env:MERCANTILE_ID = "..."
$env:MERCANTILE_PASSWORD = "..."
$env:MERCANTILE_NUM = "..."
py -m examples.scrape
```

### Isracard — `isracard`

```powershell
$env:IBS_COMPANY = "isracard"
$env:ISRACARD_ID = "..."
$env:ISRACARD_PASSWORD = "..."
$env:ISRACARD_CARD6DIGITS = "..."
py -m examples.scrape
```

### Amex — `amex`

```powershell
$env:IBS_COMPANY = "amex"
$env:AMEX_ID = "..."
$env:AMEX_PASSWORD = "..."
$env:AMEX_CARD6DIGITS = "..."
py -m examples.scrape
```

### Max — `max`

```powershell
$env:IBS_COMPANY = "max"
$env:MAX_USERNAME = "..."
$env:MAX_PASSWORD = "..."
py -m examples.scrape
```

### Visa Cal — `visaCal`

```powershell
$env:IBS_COMPANY = "visaCal"
$env:VISACAL_USERNAME = "..."
$env:VISACAL_PASSWORD = "..."
py -m examples.scrape
```

### Mizrahi Bank — `mizrahi`

```powershell
$env:IBS_COMPANY = "mizrahi"
$env:MIZRAHI_USERNAME = "..."
$env:MIZRAHI_PASSWORD = "..."
py -m examples.scrape
```

### Union — `union`

```powershell
$env:IBS_COMPANY = "union"
$env:UNION_USERNAME = "..."
$env:UNION_PASSWORD = "..."
py -m examples.scrape
```

### Beinleumi — `beinleumi`

```powershell
$env:IBS_COMPANY = "beinleumi"
$env:BEINLEUMI_USERNAME = "..."
$env:BEINLEUMI_PASSWORD = "..."
py -m examples.scrape
```

### Massad — `massad`

```powershell
$env:IBS_COMPANY = "massad"
$env:MASSAD_USERNAME = "..."
$env:MASSAD_PASSWORD = "..."
py -m examples.scrape
```

### Bank Yahav — `yahav`

```powershell
$env:IBS_COMPANY = "yahav"
$env:YAHAV_USERNAME = "..."
$env:YAHAV_PASSWORD = "..."
$env:YAHAV_NATIONALID = "..."
py -m examples.scrape
```

### One Zero — `oneZero`

```powershell
$env:IBS_COMPANY = "oneZero"
$env:ONEZERO_EMAIL = "..."
$env:ONEZERO_PASSWORD = "..."
py -m examples.scrape
```

### Bank Otsar Hahayal — `otsarHahayal`

```powershell
$env:IBS_COMPANY = "otsarHahayal"
$env:OTSARHAHAYAL_USERNAME = "..."
$env:OTSARHAHAYAL_PASSWORD = "..."
py -m examples.scrape
```

### Pagi — `pagi`

```powershell
$env:IBS_COMPANY = "pagi"
$env:PAGI_USERNAME = "..."
$env:PAGI_PASSWORD = "..."
py -m examples.scrape
```

### Behatsdaa — `behatsdaa`

```powershell
$env:IBS_COMPANY = "behatsdaa"
$env:BEHATSDAA_ID = "..."
$env:BEHATSDAA_PASSWORD = "..."
py -m examples.scrape
```

### Beyahad Bishvilha — `beyahadBishvilha`

```powershell
$env:IBS_COMPANY = "beyahadBishvilha"
$env:BEYAHADBISHVILHA_ID = "..."
$env:BEYAHADBISHVILHA_PASSWORD = "..."
py -m examples.scrape
```
