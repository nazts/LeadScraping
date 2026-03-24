#!/usr/bin/env python3
"""
Lead Scraping Tool — Dental Clinics in Europe
==============================================
Searches Google Places API for dental clinics that do NOT have a website.
Saves: business name, contact phone number, and Google Maps link.

Modes:
  - Standard : uses Google Places API directly with built-in query list.
  - AI-Enhanced: uses OpenAI to generate richer search queries and
                 validate / reformat phone numbers before saving.

Usage:
  python lead_scraper.py --count 50
  python lead_scraper.py --count 100 --use-ai
  python lead_scraper.py --count 20 --output results.csv --niche "veterinary clinic"

Required env variable  : GOOGLE_API_KEY
Optional env variable  : OPENAI_API_KEY  (only needed for --use-ai)
"""

import os
import csv
import sys
import time
import json
import argparse
from datetime import datetime

import googlemaps
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Major cities spread across as many European countries as possible.
# Adding more cities increases the chance of reaching the requested quota.
EUROPEAN_CITIES = [
    # Iberian Peninsula
    "Madrid, Spain", "Barcelona, Spain", "Valencia, Spain",
    "Seville, Spain", "Zaragoza, Spain", "Málaga, Spain",
    "Lisbon, Portugal", "Porto, Portugal", "Braga, Portugal",
    # Italy
    "Rome, Italy", "Milan, Italy", "Naples, Italy",
    "Turin, Italy", "Palermo, Italy", "Bologna, Italy",
    # France
    "Paris, France", "Lyon, France", "Marseille, France",
    "Toulouse, France", "Nice, France", "Nantes, France",
    # Germany
    "Berlin, Germany", "Hamburg, Germany", "Munich, Germany",
    "Cologne, Germany", "Frankfurt, Germany", "Stuttgart, Germany",
    # Poland
    "Warsaw, Poland", "Kraków, Poland", "Łódź, Poland",
    "Wrocław, Poland", "Poznań, Poland",
    # Romania
    "Bucharest, Romania", "Cluj-Napoca, Romania", "Iași, Romania",
    # Netherlands
    "Amsterdam, Netherlands", "Rotterdam, Netherlands", "The Hague, Netherlands",
    # Belgium
    "Brussels, Belgium", "Antwerp, Belgium", "Ghent, Belgium",
    # Austria
    "Vienna, Austria", "Graz, Austria", "Linz, Austria",
    # Hungary
    "Budapest, Hungary", "Debrecen, Hungary", "Miskolc, Hungary",
    # Czech Republic
    "Prague, Czech Republic", "Brno, Czech Republic", "Ostrava, Czech Republic",
    # Bulgaria
    "Sofia, Bulgaria", "Plovdiv, Bulgaria", "Varna, Bulgaria",
    # Greece
    "Athens, Greece", "Thessaloniki, Greece", "Patras, Greece",
    # Sweden
    "Stockholm, Sweden", "Gothenburg, Sweden", "Malmö, Sweden",
    # Denmark
    "Copenhagen, Denmark", "Aarhus, Denmark",
    # Norway
    "Oslo, Norway", "Bergen, Norway",
    # Finland
    "Helsinki, Finland", "Tampere, Finland",
    # Switzerland
    "Zurich, Switzerland", "Geneva, Switzerland", "Basel, Switzerland",
    # Croatia
    "Zagreb, Croatia", "Split, Croatia",
    # Serbia
    "Belgrade, Serbia", "Novi Sad, Serbia",
    # Ukraine
    "Kyiv, Ukraine", "Kharkiv, Ukraine", "Odessa, Ukraine",
    # Baltic States
    "Vilnius, Lithuania", "Riga, Latvia", "Tallinn, Estonia",
    # Slovakia
    "Bratislava, Slovakia", "Košice, Slovakia",
    # Slovenia
    "Ljubljana, Slovenia",
    # North Macedonia
    "Skopje, North Macedonia",
    # Albania
    "Tirana, Albania",
    # Bosnia
    "Sarajevo, Bosnia and Herzegovina",
    # Ireland
    "Dublin, Ireland", "Cork, Ireland",
    # Scotland / UK
    "London, United Kingdom", "Birmingham, United Kingdom",
    "Manchester, United Kingdom", "Edinburgh, United Kingdom",
    # Others
    "Nicosia, Cyprus", "Valletta, Malta",
    "Luxembourg City, Luxembourg",
    "Reykjavik, Iceland",
]

# Default search queries used in standard (non-AI) mode.
# Multi-language queries improve recall across different countries.
DEFAULT_QUERIES = [
    "dental clinic",
    "dentist",
    "dental office",
    "clinica dental",      # Spanish
    "dentiste",            # French
    "Zahnarzt",            # German
    "tandarts",            # Dutch
    "dentysta",            # Polish
    "стоматология",        # Ukrainian/Bulgarian
    "οδοντίατρος",         # Greek
    "Studio dentistico",   # Italian
    "clínica dentária",    # Portuguese
    "fogászat",            # Hungarian
    "stomatolog",          # Various Slavic languages
    "tandartsenpraktijk",  # Dutch alternative
]

# ---------------------------------------------------------------------------
# Environment / configuration helpers
# ---------------------------------------------------------------------------


def load_environment():
    """
    Load API keys from the .env file (or real environment variables).

    Returns
    -------
    tuple[str, str | None]
        (google_api_key, openai_api_key)
    """
    # python-dotenv looks for a .env file in the current directory
    load_dotenv()

    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print(
            "ERROR: GOOGLE_API_KEY not found.\n"
            "Create a .env file from .env.example and add your key."
        )
        sys.exit(1)

    openai_api_key = os.getenv("OPENAI_API_KEY")  # Optional — only needed for --use-ai
    return google_api_key, openai_api_key


# ---------------------------------------------------------------------------
# Google Places helpers
# ---------------------------------------------------------------------------


def _get_place_details(gmaps, place_id):
    """
    Retrieve the fields we care about for a single place.

    We request only the fields we need to minimise API credit usage:
      - name                     : business name
      - formatted_phone_number   : local format
      - international_phone_number : E.164 / international format (better for WhatsApp)
      - website                  : used as an EXCLUSION filter (we want NO website)
      - url                      : the canonical Google Maps link

    Returns a dict ``{name, phone, google_maps}`` or ``None`` when the place
    fails any of the required-data checks.
    """
    try:
        details = gmaps.place(
            place_id,
            fields=[
                "name",
                "formatted_phone_number",
                "international_phone_number",
                "website",
                "url",
            ],
        )
    except Exception as exc:
        # Network / quota errors — skip and continue
        print(f"    ⚠  Could not fetch details for {place_id}: {exc}")
        return None

    result = details.get("result", {})

    name = result.get("name")
    # Prefer the international format (starts with country code) for WhatsApp
    # compatibility. If unavailable, fall back to the local formatted number;
    # in AI mode the phone will be normalised to E.164 in the validation step.
    phone = result.get("international_phone_number") or result.get("formatted_phone_number")
    maps_url = result.get("url")
    website = result.get("website")

    # ── All three fields must be present ──────────────────────────────────────
    if not name or not phone or not maps_url:
        return None

    # ── Must NOT have a website — that is the whole point of this tool ────────
    if website:
        return None

    return {"name": name, "phone": phone, "google_maps": maps_url}


def _text_search_city(gmaps, query, city, found_ids, max_per_city=60):
    """
    Run a Google Places Text Search for ``query`` in ``city`` and collect
    qualifying leads (no website, phone present).

    The Places Text Search API returns up to 60 results across 3 pages
    (20 per page).  We iterate all pages until we have enough candidates or
    run out of results.

    Parameters
    ----------
    gmaps        : googlemaps.Client
    query        : str   — search term, e.g. "dental clinic"
    city         : str   — location string, e.g. "Madrid, Spain"
    found_ids    : set   — already-seen place_ids (avoids duplicates across cities)
    max_per_city : int   — stop after collecting this many from one city/query pair

    Returns
    -------
    list[dict]  — each item has keys: name, phone, google_maps, city
    """
    candidates = []

    try:
        # First page
        response = gmaps.places(query=f"{query} in {city}")

        while True:
            for place in response.get("results", []):
                if len(candidates) >= max_per_city:
                    break

                place_id = place["place_id"]
                if place_id in found_ids:
                    continue  # Already collected — skip duplicate

                details = _get_place_details(gmaps, place_id)
                if details:
                    details["city"] = city
                    candidates.append(details)
                    found_ids.add(place_id)

            # Follow pagination token if more pages exist and we still need more
            next_token = response.get("next_page_token")
            if not next_token or len(candidates) >= max_per_city:
                break

            # Google requires a short delay before using a page token
            time.sleep(2)
            response = gmaps.places(query=f"{query} in {city}", page_token=next_token)

    except Exception as exc:
        print(f"    ⚠  Search error in {city} for '{query}': {exc}")

    return candidates


# ---------------------------------------------------------------------------
# Standard (non-AI) search
# ---------------------------------------------------------------------------


def search_leads_standard(gmaps, niche, target_count, verbose=True):
    """
    Collect *exactly* ``target_count`` leads using the built-in city list and
    default query list.  No AI involved.

    Strategy
    --------
    Iterate European cities × search queries until the quota is filled.
    A ``set`` of already-seen ``place_id`` values prevents duplicates.
    """
    leads = []
    found_ids = set()

    if verbose:
        print(f"\n[Mode: Standard]  Target: {target_count} leads\n{'─'*60}")

    for city in EUROPEAN_CITIES:
        if len(leads) >= target_count:
            break

        for query in DEFAULT_QUERIES:
            if len(leads) >= target_count:
                break

            if verbose:
                print(
                    f"  🔍  '{query}' in {city}  "
                    f"({len(leads)}/{target_count} collected)"
                )

            new_leads = _text_search_city(gmaps, query, city, found_ids)
            leads.extend(new_leads)

            if new_leads and verbose:
                print(f"      ✔  +{len(new_leads)} leads  (total {len(leads)})")

            # Polite rate-limiting between requests
            time.sleep(0.2)

    return leads[:target_count]


# ---------------------------------------------------------------------------
# AI-enhanced search (requires OPENAI_API_KEY)
# ---------------------------------------------------------------------------


def _ai_generate_queries(openai_client, niche):
    """
    Ask OpenAI to produce a diverse set of search queries for ``niche`` in
    multiple European languages to improve coverage.

    Returns a list of query strings, or falls back to DEFAULT_QUERIES on any
    error.
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate concise Google Maps search queries. "
                        "Respond with one query per line — no numbering, no extra text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Generate 15 search query variations for finding '{niche}' "
                        "businesses across Europe. Include queries in Spanish, Italian, "
                        "French, German, Dutch, Polish, Portuguese, Greek, and Hungarian."
                    ),
                },
            ],
            max_tokens=400,
            temperature=0.7,
        )
        queries = [
            q.strip()
            for q in response.choices[0].message.content.strip().splitlines()
            if q.strip()
        ]
        return queries if queries else DEFAULT_QUERIES

    except Exception as exc:
        print(f"  ⚠  AI query generation failed ({exc}). Using default queries.")
        return DEFAULT_QUERIES


def _ai_validate_lead(openai_client, lead):
    """
    Ask OpenAI to validate a single lead entry and normalise the phone number
    to international (WhatsApp-compatible) format.

    Returns the (possibly modified) lead dict, or the original if AI fails.
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a data validation assistant. "
                        "Always respond with valid JSON only — no markdown, no extra text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Validate this business lead and respond with JSON:\n"
                        f"Name: {lead['name']}\n"
                        f"Phone: {lead['phone']}\n"
                        f"Maps URL: {lead['google_maps']}\n\n"
                        'JSON schema: {"valid": true/false, "phone_e164": "+XXXXXXXXXXX", "notes": "..."}\n'
                        "phone_e164 must be the phone in E.164 international format."
                    ),
                },
            ],
            max_tokens=150,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        if data.get("valid", True) and data.get("phone_e164"):
            lead["phone"] = data["phone_e164"]
        return lead

    except Exception:
        # If AI validation errors out, keep the original lead unchanged
        return lead


def search_leads_with_ai(gmaps, openai_client, niche, target_count, verbose=True):
    """
    Collect ``target_count`` leads using AI-generated queries and optional
    per-lead phone validation.

    Falls back gracefully to standard queries if the AI call fails.
    """
    leads = []
    found_ids = set()

    if verbose:
        print(f"\n[Mode: AI-Enhanced]  Target: {target_count} leads\n{'─'*60}")
        print("  🤖  Generating search queries via AI …")

    queries = _ai_generate_queries(openai_client, niche)

    if verbose:
        print(f"  ✔  {len(queries)} queries ready\n{'─'*60}")

    for city in EUROPEAN_CITIES:
        if len(leads) >= target_count:
            break

        for query in queries:
            if len(leads) >= target_count:
                break

            if verbose:
                print(
                    f"  🔍  '{query}' in {city}  "
                    f"({len(leads)}/{target_count} collected)"
                )

            new_leads = _text_search_city(gmaps, query, city, found_ids)
            leads.extend(new_leads)

            if new_leads and verbose:
                print(f"      ✔  +{len(new_leads)} leads  (total {len(leads)})")

            time.sleep(0.2)

    # Trim to requested count before validation to avoid wasting tokens
    leads = leads[:target_count]

    # ── AI phone-number validation pass ───────────────────────────────────────
    if leads and verbose:
        print(f"\n  🤖  Validating {len(leads)} leads via AI …")

    validated = []
    for lead in leads:
        validated.append(_ai_validate_lead(openai_client, lead))

    return validated


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def save_to_csv(leads, filename=None):
    """
    Write leads to a CSV file.

    Columns: name, phone, google_maps, city

    Parameters
    ----------
    leads    : list[dict]
    filename : str | None  — auto-generated timestamped name if omitted

    Returns
    -------
    str  — path of the written file
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leads_{timestamp}.csv"

    fieldnames = ["name", "phone", "google_maps", "city"]

    with open(filename, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        # Ensure every row has all keys (city may be absent in some edge cases)
        for lead in leads:
            writer.writerow({k: lead.get(k, "") for k in fieldnames})

    return filename


def print_summary(leads, target_count, output_file):
    """Print a formatted summary table to stdout."""
    print(f"\n{'='*60}")
    print("  Results Summary")
    print(f"{'='*60}")
    print(f"  Leads collected : {len(leads)}")
    print(f"  Target          : {target_count}")
    effectiveness = (len(leads) / target_count * 100) if target_count else 0
    print(f"  Effectiveness   : {effectiveness:.1f}%")
    print(f"  Saved to        : {output_file}")
    print(f"{'='*60}")

    if leads:
        print("\n  Preview (first 5 leads):")
        print(f"  {'Name':<35} {'Phone':<20} City")
        print(f"  {'─'*35} {'─'*20} {'─'*25}")
        for lead in leads[:5]:
            print(
                f"  {lead.get('name','')[:35]:<35} "
                f"{lead.get('phone','')[:20]:<20} "
                f"{lead.get('city','')}"
            )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="lead_scraper",
        description="Find dental clinics in Europe without a website using Google Places API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  # Find 50 leads without AI
  python lead_scraper.py --count 50

  # Find 100 leads with AI-enhanced search
  python lead_scraper.py --count 100 --use-ai

  # Custom niche, custom output file
  python lead_scraper.py --count 30 --niche "veterinary clinic" --output vets.csv

  # Silent mode (no progress output)
  python lead_scraper.py --count 20 --quiet
        """,
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        metavar="N",
        help="Exact number of leads to collect.",
    )
    parser.add_argument(
        "--niche",
        type=str,
        default="dental clinic",
        metavar="NICHE",
        help="Business type to search for. Default: 'dental clinic'.",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        help=(
            "Enable AI-enhanced mode (requires OPENAI_API_KEY). "
            "Generates richer queries and validates phone numbers. "
            "Falls back to standard mode automatically if the key is missing or the API fails."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="Output CSV filename. Default: leads_YYYYMMDD_HHMMSS.csv",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages (only errors and the final summary are shown).",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be a positive integer.")

    # ── Load API keys ──────────────────────────────────────────────────────────
    google_api_key, openai_api_key = load_environment()

    # ── Initialise Google Maps client ──────────────────────────────────────────
    # The googlemaps library handles retries and rate-limit back-off internally.
    gmaps = googlemaps.Client(key=google_api_key)

    verbose = not args.quiet

    if verbose:
        print("\nLead Scraping Tool")
        print(f"{'='*60}")
        print(f"  Niche    : {args.niche}")
        print(f"  Region   : Europe")
        print(f"  Target   : {args.count} leads")
        print(f"  Mode     : {'AI-Enhanced' if args.use_ai else 'Standard'}")
        print(f"{'='*60}")

    # ── Run the appropriate search mode ───────────────────────────────────────
    if args.use_ai:
        if not openai_api_key:
            print(
                "⚠  --use-ai requested but OPENAI_API_KEY is not set. "
                "Falling back to standard mode."
            )
            leads = search_leads_standard(gmaps, args.niche, args.count, verbose)
        else:
            try:
                # Import lazily so the script still works without openai installed
                from openai import OpenAI  # noqa: PLC0415

                openai_client = OpenAI(api_key=openai_api_key)
                leads = search_leads_with_ai(
                    gmaps, openai_client, args.niche, args.count, verbose
                )
            except ImportError:
                print(
                    "⚠  'openai' package not installed (pip install openai). "
                    "Falling back to standard mode."
                )
                leads = search_leads_standard(gmaps, args.niche, args.count, verbose)
            except Exception as exc:
                print(f"⚠  AI mode failed ({exc}). Falling back to standard mode.")
                leads = search_leads_standard(gmaps, args.niche, args.count, verbose)
    else:
        leads = search_leads_standard(gmaps, args.niche, args.count, verbose)

    # ── Warn if we fell short of the target ───────────────────────────────────
    if len(leads) < args.count:
        print(
            f"\n⚠  Only {len(leads)} leads found (requested {args.count}). "
            "The search space may be exhausted — try a broader niche or re-run."
        )

    # ── Save and report ────────────────────────────────────────────────────────
    if leads:
        output_file = save_to_csv(leads, args.output)
        print_summary(leads, args.count, output_file)
    else:
        print("\n✗  No leads found. Check your GOOGLE_API_KEY and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
