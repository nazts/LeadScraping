# LeadScraping — Dental Clinics Without a Website

A Python script that searches Google Places for **dental clinics in Europe that do not have a website**, then saves their **name**, **phone number** (WhatsApp-compatible international format), and **Google Maps link** to a CSV file.

> Only leads with **all three fields present** are saved — no partial records.  
> If you request 100 leads the script will collect **exactly 100** before stopping.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Configuration — API Keys](#configuration--api-keys)
4. [Usage](#usage)
5. [Modes: Standard vs AI-Enhanced](#modes-standard-vs-ai-enhanced)
6. [Output Format](#output-format)
7. [How the Script Works (Code Walkthrough)](#how-the-script-works-code-walkthrough)
8. [Important Notes and Limitations](#important-notes-and-limitations)
9. [FAQ](#faq)

---

## Requirements

| Dependency       | Version   | Purpose                                             |
|------------------|-----------|-----------------------------------------------------|
| Python           | ≥ 3.9     | Runtime                                             |
| `googlemaps`     | ≥ 4.10.0  | Official Google Maps Services Python client         |
| `python-dotenv`  | ≥ 1.0.0   | Loads API keys from `.env` without exposing them    |
| `openai`         | ≥ 1.0.0   | *(Optional)* AI-enhanced mode (`--use-ai`)          |

---

## Installation

### 1 — Clone the repository

```bash
git clone https://github.com/nazts/LeadScraping.git
cd LeadScraping
```

### 2 — Create and activate a virtual environment *(recommended)*

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

### 3 — Install dependencies

```bash
pip install -r requirements.txt
```

If you only want the standard (non-AI) mode you can skip the `openai` package:

```bash
pip install googlemaps python-dotenv
```

---

## Configuration — API Keys

### Google Places API *(required)*

The script uses the **Google Places API (legacy)** through the official
[`googlemaps`](https://github.com/googlemaps/google-maps-services-python) Python library.

**Why Google Places?**  
It is the official Google API for business search. The free tier provides
**$200 USD of free credit per month**, which covers approximately:

- ~6 000 Text Search requests, **or**
- ~11 700 Place Details requests

That is more than enough to collect hundreds of leads each month at no cost.

**Steps to get a key:**

1. Go to <https://console.cloud.google.com/> and sign in.
2. Create a new project (or use an existing one).
3. Navigate to **APIs & Services → Library**.
4. Search for **"Places API"** and click **Enable**.
5. Go to **APIs & Services → Credentials → Create Credentials → API Key**.
6. *(Recommended)* Restrict the key to the **Places API** only.

### OpenAI API *(optional — for `--use-ai`)*

1. Sign up at <https://platform.openai.com/>.
2. Go to **API Keys** and create a new secret key.
3. The script uses `gpt-3.5-turbo` to keep token costs minimal.

### Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder values:

```dotenv
GOOGLE_API_KEY=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ1234567
OPENAI_API_KEY=sk-proj-...   # leave blank or delete line if not using AI
```

> **Security:** `.env` is listed in `.gitignore` and will never be committed.

---

## Usage

```
python lead_scraper.py --count N [OPTIONS]
```

### Arguments

| Argument      | Type    | Required | Default              | Description                                          |
|---------------|---------|----------|----------------------|------------------------------------------------------|
| `--count N`   | int     | ✔        | —                    | Exact number of leads to collect                     |
| `--niche`     | string  | ✗        | `"dental clinic"`    | Business type to search for                          |
| `--use-ai`    | flag    | ✗        | off                  | Enable AI-enhanced mode (requires `OPENAI_API_KEY`)  |
| `--output`    | string  | ✗        | `leads_TIMESTAMP.csv`| Custom output filename                               |
| `--quiet`     | flag    | ✗        | off                  | Suppress progress output                             |

### Examples

```bash
# Find 50 dental clinics without a website (standard mode)
python lead_scraper.py --count 50

# Find 100 leads with AI-enhanced search and validation
python lead_scraper.py --count 100 --use-ai

# Save to a custom file
python lead_scraper.py --count 30 --output my_leads.csv

# Search for a different niche
python lead_scraper.py --count 40 --niche "veterinary clinic"

# Silent mode — only the final summary is printed
python lead_scraper.py --count 20 --quiet
```

---

## Modes: Standard vs AI-Enhanced

### Standard mode *(default)*

- Uses a built-in list of **60+ European cities**.
- Uses a built-in list of **15 search queries** in multiple European languages
  (English, Spanish, French, German, Dutch, Polish, Italian, Portuguese, Greek, Hungarian).
- Iterates city × query pairs until the exact count is reached.
- No OpenAI key required.

### AI-Enhanced mode (`--use-ai`)

Activates two extra AI steps:

1. **Query generation** — OpenAI (`gpt-3.5-turbo`) generates 15 diverse,
   multilingual search queries tailored to the requested niche, improving
   coverage across different European languages and naming conventions.

2. **Phone validation** — Each collected lead is passed through OpenAI to:
   - Verify the data looks plausible.
   - Normalise the phone number to **E.164 international format**
     (e.g. `+34 91 123 45 67`) which is directly usable for WhatsApp.

**Automatic fallback:** If `OPENAI_API_KEY` is missing, the `openai` package
is not installed, or any API call fails, the script **automatically falls back
to standard mode** without crashing.

---

## Output Format

Results are saved as a **UTF-8 CSV** file with four columns:

| Column        | Description                                      | Example                                   |
|---------------|--------------------------------------------------|-------------------------------------------|
| `name`        | Business name as listed on Google Maps           | `Clínica Dental Sonrisa`                  |
| `phone`       | Contact number in international format           | `+34 91 123 45 67`                        |
| `google_maps` | Direct Google Maps link to the business          | `https://maps.google.com/?cid=123456789`  |
| `city`        | City / country used in the search query          | `Madrid, Spain`                           |

The phone number is stored in international format so it can be used directly
with WhatsApp (open `https://wa.me/<phone_digits_only>` in a browser).

---

## How the Script Works (Code Walkthrough)

### `load_environment()`

Reads `GOOGLE_API_KEY` and `OPENAI_API_KEY` from the `.env` file using
`python-dotenv`.  The script exits immediately with a clear error message if
the mandatory Google key is absent.

### `_get_place_details(gmaps, place_id)`

Calls the **Place Details** endpoint for a single business, requesting only
the five fields we need (`name`, `formatted_phone_number`,
`international_phone_number`, `website`, `url`).  This minimises API credit
usage. A place is **rejected** (returns `None`) when:

- `name`, `phone`, or `url` is missing — *incomplete data, never saved*.
- `website` is present — *the business already has a website, skip it*.

### `_text_search_city(gmaps, query, city, found_ids)`

Runs a **Text Search** (`gmaps.places`) for a query + city combination.
Follows pagination (up to 3 pages × 20 results = 60 per query) with the
required 2-second delay between pages.  A shared `found_ids` set prevents the
same business from being added twice across different city/query combinations.

### `search_leads_standard(gmaps, niche, target_count)`

Outer loop over `EUROPEAN_CITIES` × `DEFAULT_QUERIES`.  Stops as soon as
`target_count` unique leads have been collected and returns exactly that many.

### `search_leads_with_ai(gmaps, openai_client, niche, target_count)`

Same outer loop but:
1. Calls `_ai_generate_queries()` first to get a better query list.
2. After collection, calls `_ai_validate_lead()` on each lead to normalise the
   phone number and discard any lead OpenAI flags as invalid.

### `save_to_csv(leads, filename)`

Writes the list of lead dicts to a CSV using `csv.DictWriter`.  Missing keys
are written as empty strings (safety net — in practice all saved leads have
complete data).

---

## Important Notes and Limitations

1. **Google API quota** — The $200/month free credit is typically sufficient
   for hundreds of leads.  Heavy use (thousands of leads per day) may incur
   small charges.  Monitor your usage in Google Cloud Console.

2. **Phone number availability** — Not every business on Google Maps has a
   phone number listed.  Businesses without a phone are silently skipped.
   This is intentional — every saved lead has a verified phone number.

3. **Rate limiting** — The script includes short delays between API calls to
   stay within Google's rate limits.  Do not remove these.

4. **Pagination limit** — Google Text Search returns at most 60 results
   (3 pages) per query.  The script compensates by searching across many
   cities and query variations.

5. **"Europe" is searched city by city** — Google Places does not accept
   "Europe" as a single location; the script iterates through 60+ major
   European cities.  If you need a specific country, pass it as `--niche`
   or modify `EUROPEAN_CITIES` directly.

6. **WhatsApp compatibility** — The international phone format (e.g.
   `+34911234567`) is directly usable with WhatsApp.  Construct a link as:
   `https://wa.me/34911234567` (drop the leading `+`).

7. **AI mode costs** — `gpt-3.5-turbo` is used to keep token costs very low.
   Generating queries costs ~1 call; validation costs 1 call per lead.  For
   100 leads this is typically less than $0.10.

---

## FAQ

**Q: The script found fewer leads than I requested. What do I do?**  
A: The search space for that city/query combination may be exhausted.
Re-run the script — it will start from the beginning and may find different
results, or add more cities to `EUROPEAN_CITIES` in `lead_scraper.py`.

**Q: Can I use this for a niche other than dental clinics?**  
A: Yes — use `--niche "your niche"`.  The built-in multilingual queries will
still work, but the AI mode will generate niche-specific queries automatically.

**Q: How do I know the phone numbers are accurate?**  
A: They come directly from Google Maps (Google's own data quality controls
apply).  In AI mode, OpenAI further normalises them to international format.
Expect >80% data completeness as a rule — Google typically has phone numbers
for established brick-and-mortar businesses.

**Q: Is this legal?**  
A: The script only reads publicly available data from Google Maps via the
official API, complying with Google's Terms of Service.  Always ensure your
use of the collected data complies with local data-protection laws (GDPR in
Europe).
