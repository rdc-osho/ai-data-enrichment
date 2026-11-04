#!/usr/bin/env python3
"""AI assisted company data enrichment with human review.

Reads a CSV of company names, asks an AI assistant for a few public facts
about each company, checks every answer, and flags anything uncertain so a
person can review it before it is used.

Privacy by design
  * Only facts about companies are collected. No names, emails or phone
    numbers of individuals are requested or stored.
  * The API key is read from the environment (.env), never from the code.
  * Nothing is written to any live system. Results go to a local CSV first.

How to run
  python enrich.py companies.csv           uses the Claude API
  python enrich.py companies.csv --mock    offline demo, no key needed
"""
import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

FIELDS = ["sector", "regulator", "headquarters_city", "website", "confidence", "notes"]
ALLOWED_SECTORS = {"Energy supply", "Water", "Energy networks", "Other"}
ALLOWED_REGULATORS = {"Ofgem", "Ofwat", "Both", "Unknown"}
PERSONAL_DATA = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s]{8,}\d")  # emails and phone numbers

PROMPT = """You are helping a B2B publisher keep an accurate list of UK utility companies.
For the company below, return ONLY a JSON object with these keys:
  sector: one of "Energy supply", "Water", "Energy networks", "Other"
  regulator: one of "Ofgem", "Ofwat", "Both", "Unknown"
  headquarters_city: UK city of the head office, or "Unknown"
  website: the main public website domain, e.g. "example.co.uk", or "Unknown"
  confidence: "high", "medium" or "low"
  notes: one short sentence on anything uncertain
Do not include any names, emails or phone numbers of individuals.
If you are not sure, say "Unknown" and set confidence to "low". Do not guess.

Company: {name}"""

# Offline answers so the tool can be shown and tested without a key
MOCK = {
    "Octopus Energy": ["Energy supply", "Ofgem", "London", "octopus.energy", "high", ""],
    "Thames Water": ["Water", "Ofwat", "Reading", "thameswater.co.uk", "high", ""],
    "National Grid": ["Energy networks", "Ofgem", "London", "nationalgrid.com", "medium",
                      "Group operates in the UK and US"],
}


def load_env(path=".env"):
    """Small .env loader so python dotenv is optional."""
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def ask_claude(name, key, model):
    import requests
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": 1024,
              "messages": [{"role": "user", "content": PROMPT.format(name=name)}]},
        timeout=60,
    )
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except ValueError:
            msg = r.text[:200]
        raise RuntimeError(f"API error {r.status_code}: {msg}")
    body = r.json()
    # Newer models can return more than one content block, so join only the text blocks
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    usage = body.get("usage", {})
    match = re.search(r"\{.*\}", text, re.S)
    data = json.loads(match.group(0)) if match else {}
    return data, usage.get("input_tokens", 0) + usage.get("output_tokens", 0)


def ask_mock(name):
    values = MOCK.get(name, ["Other", "Unknown", "Unknown", "Unknown", "low", "No mock data"])
    return dict(zip(FIELDS, values)), 0


def validate(row):
    """Return a list of reasons this row needs a human to check it."""
    reasons = []
    if row.get("sector") not in ALLOWED_SECTORS:
        reasons.append("sector not in allowed list")
    if row.get("regulator") not in ALLOWED_REGULATORS:
        reasons.append("regulator not in allowed list")
    site = row.get("website", "")
    if site != "Unknown" and not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", site.lower()):
        reasons.append("website is not a plain domain")
    if row.get("confidence") != "high":
        reasons.append(f"confidence {row.get('confidence', 'missing')}")
    if any(v == "Unknown" for v in (row.get("regulator"), row.get("headquarters_city"), site)):
        reasons.append("contains Unknown")
    if row.get("sector") == "Water" and row.get("regulator") == "Ofgem":
        reasons.append("water company with energy regulator")
    if any(PERSONAL_DATA.search(str(v)) for v in row.values()):
        reasons.append("possible personal data removed")
        for k, v in row.items():
            row[k] = PERSONAL_DATA.sub("[removed]", str(v))
    return reasons


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--out", default="output/enriched.csv")
    ap.add_argument("--mock", action="store_true", help="run offline with sample answers")
    ap.add_argument("--manual-minutes", type=float, default=4.0,
                    help="your estimate of minutes to research one company by hand")
    args = ap.parse_args()

    load_env()
    key, model = os.environ.get("ANTHROPIC_API_KEY"), os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
    if not args.mock and (not key or key == "your-key-here"):
        raise SystemExit("No API key found. Add it to .env (see .env.example) or run with --mock.")

    with open(args.input, newline="") as f:
        names = [r["company_name"].strip() for r in csv.DictReader(f) if r["company_name"].strip()]

    rows, tokens, start, failures = [], 0, time.time(), []
    for name in names:
        try:
            data, used = ask_mock(name) if args.mock else ask_claude(name, key, model)
        except Exception as e:  # keep going and record the failure for review
            data, used = {"notes": f"lookup failed: {e}"}, 0
            failures.append(str(e))
        tokens += used
        row = {"company_name": name, **{k: str(data.get(k, "Unknown")) for k in FIELDS}}
        reasons = validate(row)
        row["needs_review"] = "yes" if reasons else "no"
        row["review_reasons"] = "; ".join(reasons)
        rows.append(row)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["company_name", *FIELDS, "needs_review", "review_reasons"])
        w.writeheader()
        w.writerows(rows)

    if failures:
        print(f"WARNING: {len(failures)} of {len(rows)} lookups failed. First error: {failures[0]}")
    review = sum(r["needs_review"] == "yes" for r in rows)
    secs = time.time() - start
    manual = len(rows) * args.manual_minutes
    print(f"Enriched {len(rows)} companies in {secs:.0f}s. {review} flagged for human review.")
    print(f"Tokens used: {tokens:,}")
    print(f"Time check: about {manual:.0f} min by hand (at your {args.manual_minutes:g} min estimate) "
          f"vs {secs/60:.1f} min automated plus review of {review} rows.")
    print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()
