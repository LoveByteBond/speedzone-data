#!/usr/bin/env python3
"""
SpeedZonePro data scraper.

Crawls YolRadar.com route guide pages, extracts the speed corridor list
from each, geocodes the corridor names to coordinates via Nominatim (OSM),
deduplicates across routes, and writes a zones.json file ready to be
consumed by the iOS app over HTTPS via GitHub Pages.

Works on Windows, macOS, and Linux. Run with:

    python scraper.py

On Windows: either double-click run-scraper.bat, or open Command Prompt
and run `python scraper.py` from this folder.

Config:
    --limit N       only scrape N routes (for testing)
    --no-geocode    skip geocoding (useful for testing the scraper alone)
    --output FILE   output path (default: zones.json)
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies.")
    print("Run this command once to install them:")
    print("    pip install requests beautifulsoup4")
    sys.exit(1)


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
INDEX_URL = "https://yolradar.com/radar-noktalari/"
ROUTE_URL_PATTERN = re.compile(r"/guzergah/([a-z0-9-]+-radar-ve-hiz-koridorlari)/?")
USER_AGENT = (
    "SpeedZoneProDataCollector/1.0 "
    "(personal research; respects robots; <=1 req/sec)"
)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY_SEC = 1.1   # Nominatim ToS: max 1 req/sec
YOLRADAR_DELAY_SEC = 0.5    # be polite
REQUEST_TIMEOUT = 30

# Turkey bounding box for geocoding constraints
TR_BBOX = {
    "viewbox": "25.5,42.2,44.9,35.8",  # lon_min, lat_max, lon_max, lat_min
    "bounded": "1",
    "countrycodes": "tr",
}


# -----------------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------------

def http_get(url, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", USER_AGENT)
    headers.setdefault("Accept-Language", "tr-TR,tr;q=0.9,en;q=0.5")
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp.text


# -----------------------------------------------------------------------------
# YolRadar parsing
# -----------------------------------------------------------------------------

def discover_route_urls():
    """Crawl the index page and return the full list of /guzergah/* URLs."""
    print(f"[1/3] Discovering routes from {INDEX_URL}")
    html = http_get(INDEX_URL)
    soup = BeautifulSoup(html, "html.parser")
    urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/guzergah/" not in href:
            continue
        if href.startswith("/"):
            href = "https://yolradar.com" + href
        if not href.endswith("/"):
            href += "/"
        if ROUTE_URL_PATTERN.search(href):
            urls.add(href)
    sorted_urls = sorted(urls)
    print(f"      Found {len(sorted_urls)} unique route URLs")
    return sorted_urls


def parse_route_page(url):
    """Extract speed corridor records from a single /guzergah/ page.
    Returns a list of dicts: {name, length_m, limit_kph}

    Strategy: find the "Güzergahtaki Hız Koridorları" section by text,
    then use regex to extract corridor blocks. Each corridor in YolRadar
    HTML has the shape:

        <h3>Corridor Name</h3>
        <p>Tahmini Uzunluk: 17 km</p>
        <p>130</p>
        <p>km/s Limit</p>

    But the exact tags may vary. We just look for the text pattern:
        NAME ... Tahmini Uzunluk: N km ... NUMBER ... km/s
    """
    try:
        html = http_get(url)
    except Exception as e:
        print(f"      WARN: fetch failed for {url}: {e}")
        return []

    # Slice to just the corridor section (between section heading and next major heading)
    # The page has "## Güzergahtaki Hız Koridorları" then later "## İl Bazında Denetim Dağılımı"
    start_markers = [
        "Güzergahtaki Hız Koridorları",
        "Hız Koridorları",
    ]
    end_markers = [
        "İl Bazında",
        "Denetim Dağılımı",
        "Radar Cezası Hesaplama",
        "Sıkça Sorulan",
    ]

    start_idx = -1
    for marker in start_markers:
        i = html.find(marker)
        if i > 0:
            start_idx = i
            break
    if start_idx < 0:
        return []

    end_idx = len(html)
    for marker in end_markers:
        i = html.find(marker, start_idx + 100)
        if i > 0 and i < end_idx:
            end_idx = i

    section = html[start_idx:end_idx]

    # Strip HTML tags to get plain text
    text = re.sub(r"<[^>]+>", "\n", section)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    # Collapse whitespace
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    corridors = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for "Tahmini Uzunluk" — this is the anchor.
        # Name is 1-3 lines before it; limit is 1-5 lines after it.
        if "Tahmini Uzunluk" in line or "Uzunluk" in line:
            # Extract length
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", line, re.I)
            if not m:
                # length might be on next line
                if i + 1 < len(lines):
                    m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", lines[i + 1], re.I)
            if not m:
                i += 1
                continue
            length_m = int(float(m.group(1).replace(",", ".")) * 1000)

            # Find name: walk backwards until we find a non-empty line that
            # is not "Tahmini Uzunluk", not "km/s", not just a number, and
            # not a section heading
            name = None
            for back in range(1, 6):
                if i - back < 0:
                    break
                candidate = lines[i - back]
                if (len(candidate) > 5
                        and "Uzunluk" not in candidate
                        and "km/s" not in candidate
                        and "Limit" not in candidate
                        and not re.fullmatch(r"\d+", candidate)
                        and "Koridor" not in candidate):
                    name = candidate
                    break
            if not name:
                i += 1
                continue

            # Find limit: walk forward up to 8 lines, find a 2-3 digit number
            limit_kph = None
            for fwd in range(1, 9):
                if i + fwd >= len(lines):
                    break
                m2 = re.search(r"\b(\d{2,3})\b", lines[i + fwd])
                if m2:
                    val = int(m2.group(1))
                    if 30 <= val <= 200:
                        limit_kph = val
                        break

            if name and length_m and limit_kph:
                corridors.append({
                    "name": name,
                    "length_m": length_m,
                    "limit_kph": limit_kph,
                })
            i += 1
        else:
            i += 1

    return corridors


# -----------------------------------------------------------------------------
# Geocoding via Nominatim (OSM)
# -----------------------------------------------------------------------------

def slugify(s):
    """Make a stable, ASCII-only identifier from a corridor name."""
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:60]


def split_endpoints(name):
    """Split a corridor name like 'Foo Kavşağı - Bar Çıkışı' into two strings."""
    for sep in [" - ", " – ", " — ", " / ", "/"]:
        if sep in name:
            parts = name.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return name, name  # no separator, use whole name for both


def nominatim_geocode(query, cache):
    """Geocode a text string to (lat, lon) using Nominatim. Cached on disk."""
    if query in cache:
        return cache[query]

    params = {"q": query, "format": "json", "limit": 1, **TR_BBOX}
    try:
        time.sleep(NOMINATIM_DELAY_SEC)
        resp = requests.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"      WARN: geocode failed for {query!r}: {e}")
        cache[query] = None
        return None

    if not data:
        cache[query] = None
        return None

    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    cache[query] = (lat, lon)
    return cache[query]


# -----------------------------------------------------------------------------
# Main pipeline
# -----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only scrape N routes")
    ap.add_argument("--no-geocode", action="store_true")
    ap.add_argument("--output", default="zones.json")
    ap.add_argument("--debug-url", help="parse a single URL and dump corridors, no geocoding/output")
    args = ap.parse_args()

    if args.debug_url:
        print(f"[DEBUG] Parsing single URL: {args.debug_url}")
        corridors = parse_route_page(args.debug_url)
        print(f"[DEBUG] Found {len(corridors)} corridors:")
        for c in corridors:
            print(f"  - {c['name']}  ({c['length_m']}m, {c['limit_kph']}km/s)")
        return

    script_dir = Path(__file__).parent.resolve()
    output_path = script_dir / args.output
    geocode_cache_path = script_dir / "geocode-cache.json"

    # Load existing geocode cache
    geocode_cache = {}
    if geocode_cache_path.exists():
        try:
            raw = json.loads(geocode_cache_path.read_text(encoding="utf-8"))
            for k, v in raw.items():
                geocode_cache[k] = tuple(v) if v else None
            print(f"      Loaded {len(geocode_cache)} cached geocode entries")
        except Exception as e:
            print(f"      WARN: geocode cache unreadable: {e}")

    # Step 1: discover
    route_urls = discover_route_urls()
    if args.limit:
        route_urls = route_urls[:args.limit]
        print(f"      LIMIT: only scraping first {len(route_urls)} routes")

    # Step 2: parse each route page, collect unique corridors by name
    print(f"[2/3] Scraping {len(route_urls)} route pages")
    corridor_by_name = {}
    for i, url in enumerate(route_urls):
        print(f"      [{i+1}/{len(route_urls)}] {url.split('/')[-2]}")
        corridors = parse_route_page(url)
        for c in corridors:
            if c["name"] not in corridor_by_name:
                corridor_by_name[c["name"]] = c
        time.sleep(YOLRADAR_DELAY_SEC)
    print(f"      Extracted {len(corridor_by_name)} unique corridors")

    # Step 3: geocode each corridor (endpoint names)
    zones = []
    if args.no_geocode:
        print("[3/3] Skipping geocoding (--no-geocode)")
        for name, c in corridor_by_name.items():
            zones.append({
                "id": "yr-" + slugify(name),
                "name": name,
                "lengthMeters": c["length_m"],
                "speedLimitKph": float(c["limit_kph"]),
            })
    else:
        print(f"[3/3] Geocoding {len(corridor_by_name)} corridors via Nominatim")
        for i, (name, c) in enumerate(corridor_by_name.items()):
            entry_name, exit_name = split_endpoints(name)
            entry_query = f"{entry_name}, Türkiye"
            exit_query = f"{exit_name}, Türkiye"

            entry = nominatim_geocode(entry_query, geocode_cache)
            exit_ = nominatim_geocode(exit_query, geocode_cache)

            status = "OK"
            if not entry or not exit_:
                status = "SKIP"
            elif entry == exit_:
                # Same place both ends — fake endpoints using length offset
                status = "FUZZY"

            print(f"      [{i+1}/{len(corridor_by_name)}] {status}  {name[:50]}")

            if not entry or not exit_:
                continue

            zones.append({
                "id": "yr-" + slugify(name),
                "name": name,
                "entryLat": entry[0],
                "entryLon": entry[1],
                "exitLat": exit_[0],
                "exitLon": exit_[1],
                "lengthMeters": c["length_m"],
                "speedLimitKph": float(c["limit_kph"]),
            })

            # Flush cache every 20 entries so interrupts don't lose work
            if (i + 1) % 20 == 0:
                geocode_cache_path.write_text(
                    json.dumps({k: list(v) if v else None for k, v in geocode_cache.items()},
                              ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )

    # Save geocode cache
    geocode_cache_path.write_text(
        json.dumps({k: list(v) if v else None for k, v in geocode_cache.items()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Write final zones.json
    payload = {
        "version": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "yolradar.com + Nominatim (OSM) geocoding",
        "count": len(zones),
        "zones": zones,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\nDone. Wrote {len(zones)} zones to {output_path}")


if __name__ == "__main__":
    main()
