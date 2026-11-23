#!/usr/bin/env python3
"""
Update data/jobs.json untuk Lowongan IT Surabaya & Sidoarjo.

Sumber: RSS pencarian Bing untuk beberapa kueri lowongan IT di area
Surabaya / Sidoarjo / Gresik / Mojokerto. Hasil difilter ke domain/portal
lowongan yang dikenal, didedup berdasarkan URL, dan dikategorikan sederhana.

Kalau hasil baru < 5 (mis. jaringan diblokir), file lama TIDAK ditimpa —
jadi situs tidak pernah kosong gara-gara satu run gagal.

Jalankan:  python3 scripts/update_jobs.py
Dipakai oleh: .github/workflows/update-jobs.yml (harian)
"""
import json, re, sys, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "jobs.json"

QUERIES = [
    "lowongan kerja IT programmer Surabaya Jobstreet Indeed Glints",
    "lowongan kerja IT developer Sidoarjo",
    "lowongan kerja IT support Surabaya Sidoarjo",
    "lowongan QA data engineer Surabaya",
    "lowongan full stack developer Surabaya",
    "lowongan IT Gresik Mojokerto programmer",
]
LOCATIONS = ["Sidoarjo", "Gresik", "Mojokerto", "Surabaya"]
CATEGORY_RULES = [
    ("QA", ["qa", "quality assurance", "tester", "sdet"]),
    ("Data", ["data engineer", "data analyst", "database", "data quality"]),
    ("Mobile", ["mobile", "android", "ios", "flutter"]),
    ("Frontend", ["front end", "front-end", "frontend", "ui/ux", "ui ux"]),
    ("IT Support", ["it support", "helpdesk", "help desk", "it officer", "technical support"]),
    ("DevOps & Network", ["devops", "network", "infrastructure", "sysadmin", "system administrator"]),
    ("Backend", ["backend", "back end", "php", "odoo", ".net", "mainframe", "java developer"]),
    ("Fullstack", ["full stack", "full-stack", "fullstack", "web developer", "software engineer", "programmer", "developer", "software development"]),
]

def fetch_rss(query: str):
    url = "https://www.bing.com/search?format=rss&q=" + urllib.request.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LowonganIT-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return ET.fromstring(r.read())

def categorize(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    for cat, keys in CATEGORY_RULES:
        if any(k in text for k in keys):
            return cat
    return "Lainnya"

def location_of(text: str) -> str:
    for loc in LOCATIONS:
        if loc.lower() in text.lower():
            return loc
    return "Surabaya"

def main() -> int:
    seen, jobs = set(), []
    for q in QUERIES:
        try:
            root = fetch_rss(q)
        except Exception as e:
            print(f"WARN: query gagal: {q}: {e}", file=sys.stderr)
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = re.sub("<[^>]+>", "", item.findtext("description") or "").strip()
            if not title or not link or link in seen:
                continue
            if "surabaya" not in (title + desc).lower() and "sidoarjo" not in (title + desc).lower() \
               and "gresik" not in (title + desc).lower() and "mojokerto" not in (title + desc).lower():
                continue
            seen.add(link)
            host = re.sub(r"^www\.", "", urllib.request.urlparse(link).netloc)
            source_name = host.split(".")[0].capitalize()
            jobs.append({
                "title": title[:140],
                "company": None,
                "location": location_of(title + " " + desc),
                "category": categorize(title, desc),
                # Skema kanonis yang dibaca index.html (url + source_name),
                # plus alias lama agar kompatibel dengan data/konsumen lama.
                "url": link,
                "sourceUrl": link,
                "source_name": source_name,
                "sourceName": source_name,
                "summary": desc[:280],
            })
    if len(jobs) < 5:
        print(f"Hasil baru cuma {len(jobs)} (<5) — file lama dipertahankan.")
        return 0
    data = {"fetchedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "jobs": jobs}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(jobs)} lowongan ditulis ke {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
