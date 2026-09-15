#!/usr/bin/env python3
"""
Genera publications.bib a partire dai works del record ORCID pubblico.

Flusso:
  1. Legge la lista dei works da https://pub.orcid.org/v3.0/{ORCID}/works
  2. Per ogni work con DOI -> BibTeX da Crossref (content negotiation su doi.org)
  3. Per i works senza DOI -> usa la citation BibTeX salvata su ORCID, se presente
  4. Fallback: entry @misc costruita dai metadati ORCID
  5. Cache su disco (cache.json) per non richiamare Crossref ogni volta

Uso:
  ORCID_ID=0000-0000-0000-0000 python scripts/orcid_to_bib.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ORCID_ID = os.environ.get("ORCID_ID", "").strip()
OUT_FILE = Path(os.environ.get("OUT_FILE", "publications.bib"))
CACHE_FILE = Path(os.environ.get("CACHE_FILE", "cache.json"))
MAILTO = os.environ.get("CROSSREF_MAILTO", "")  # cortesia verso Crossref, opzionale

if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", ORCID_ID):
    sys.exit("Imposta la variabile d'ambiente ORCID_ID (es. 0000-0002-1825-0097)")

ORCID_API = f"https://pub.orcid.org/v3.0/{ORCID_ID}"
HEADERS_ORCID = {"Accept": "application/json"}
UA = f"orcid-to-bibbase (mailto:{MAILTO})" if MAILTO else "orcid-to-bibbase"


def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))


def get_works_summary() -> list:
    r = requests.get(f"{ORCID_API}/works", headers=HEADERS_ORCID, timeout=30)
    r.raise_for_status()
    return r.json().get("group", [])


def get_work_detail(put_code: int) -> dict:
    r = requests.get(f"{ORCID_API}/work/{put_code}", headers=HEADERS_ORCID, timeout=30)
    r.raise_for_status()
    return r.json()


def extract_doi(summary: dict) -> str | None:
    for eid in summary.get("external-ids", {}).get("external-id", []) or []:
        if eid.get("external-id-type", "").lower() == "doi":
            doi = (eid.get("external-id-normalized") or {}).get("value") or eid.get("external-id-value")
            if doi:
                return doi.strip().lower()
    return None


def crossref_bibtex(doi: str) -> str | None:
    r = requests.get(
        f"https://doi.org/{doi}",
        headers={"Accept": "application/x-bibtex", "User-Agent": UA},
        timeout=30,
        allow_redirects=True,
    )
    if r.status_code == 200 and r.text.lstrip().startswith("@"):
        return r.text.strip()
    return None


def orcid_bibtex(put_code: int) -> str | None:
    detail = get_work_detail(put_code)
    cit = detail.get("citation") or {}
    if (cit.get("citation-type") or "").lower() == "bibtex":
        val = (cit.get("citation-value") or "").strip()
        if val.startswith("@"):
            return val
    return None


def fallback_entry(summary: dict, put_code: int) -> str:
    title = ((summary.get("title") or {}).get("title") or {}).get("value", "Untitled")
    year = ((summary.get("publication-date") or {}).get("year") or {}).get("value", "")
    journal = (summary.get("journal-title") or {}).get("value", "")
    url = (summary.get("url") or {}).get("value", "")
    key = f"orcid{put_code}"
    fields = [f"  title = {{{title}}}"]
    if year:
        fields.append(f"  year = {{{year}}}")
    if journal:
        fields.append(f"  howpublished = {{{journal}}}")
    if url:
        fields.append(f"  url = {{{url}}}")
    fields.append(f"  note = {{Imported from ORCID {ORCID_ID}}}")
    return "@misc{" + key + ",\n" + ",\n".join(fields) + "\n}"


def normalize_key(bib: str, suggested: str) -> str:
    """Sostituisce la chiave BibTeX con una chiave stabile (evita collisioni tra sorgenti)."""
    return re.sub(r"^(@\w+\{)[^,]*,", lambda m: f"{m.group(1)}{suggested},", bib, count=1, flags=re.M)


def main() -> None:
    cache = load_cache()
    groups = get_works_summary()
    print(f"Trovati {len(groups)} works su ORCID {ORCID_ID}")

    entries: dict[str, str] = {}  # dedup-key -> bibtex
    for g in groups:
        summaries = g.get("work-summary", [])
        if not summaries:
            continue
        # il primo summary del gruppo e' la versione preferita/visibile
        s = summaries[0]
        put_code = s["put-code"]
        doi = extract_doi(s)
        dedup = doi or f"putcode:{put_code}"
        if dedup in entries:
            continue

        if dedup in cache:
            entries[dedup] = cache[dedup]
            continue

        bib = None
        if doi:
            try:
                bib = crossref_bibtex(doi)
            except requests.RequestException as e:
                print(f"  [warn] Crossref fallito per {doi}: {e}")
            time.sleep(0.3)
        if not bib:
            try:
                bib = orcid_bibtex(put_code)
            except requests.RequestException as e:
                print(f"  [warn] ORCID detail fallito per {put_code}: {e}")
        if not bib:
            bib = fallback_entry(s, put_code)
            print(f"  [info] fallback @misc per put-code {put_code}")

        key = re.sub(r"[^A-Za-z0-9]", "_", doi) if doi else f"orcid{put_code}"
        bib = normalize_key(bib, key)
        entries[dedup] = bib
        cache[dedup] = bib

    save_cache(cache)

    header = (
        f"% Generato automaticamente da ORCID {ORCID_ID} il "
        f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n"
        "% Non modificare a mano: le modifiche verranno sovrascritte.\n\n"
    )
    OUT_FILE.write_text(header + "\n\n".join(entries.values()) + "\n", encoding="utf-8")
    print(f"Scritte {len(entries)} entry in {OUT_FILE}")


if __name__ == "__main__":
    main()
