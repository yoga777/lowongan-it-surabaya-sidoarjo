#!/usr/bin/env python3
"""
Update data/jobs.json untuk Lowongan IT seluruh Indonesia.

Sumber: hasil pencarian web untuk beberapa kueri lowongan IT di kota-kota
besar Indonesia (Jakarta, Bandung, Surabaya, Semarang, Medan, Denpasar,
Makassar, dll) — utama lewat DuckDuckGo HTML, cadangan Bing HTML.
(RSS pencarian Bing berhenti mengembalikan hasil pada Nov 2026, jadi
lapisan ambil data diganti ke halaman hasil pencarian HTML.)
Hasil disaring (harus menyebut kota target + kata kunci lowongan/bidang
IT, host berita/sosial dibuang), didedup berdasarkan URL, dan
dikategorikan sederhana.

Kalau hasil baru < 5 (mis. jaringan diblokir), file lama TIDAK ditimpa —
jadi situs tidak pernah kosong gara-gara satu run gagal.

Jalankan:  python3 scripts/update_jobs.py
Dipakai oleh: .github/workflows/update-jobs.yml (tiap jam)
"""
import html as htmlmod
import json, re, sys, time, urllib.parse, urllib.request
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
    "lowongan kerja IT programmer developer Jakarta Jobstreet Glints",
    "lowongan kerja IT developer Tangerang Bekasi Bogor Depok",
    "lowongan kerja IT programmer Bandung Cimahi Jobstreet Glints",
    "lowongan kerja IT developer Semarang Yogyakarta Solo",
    "lowongan kerja IT programmer Malang Kediri",
    "lowongan kerja IT developer Medan Palembang Batam Pekanbaru",
    "lowongan kerja IT programmer Denpasar Bali Jobstreet",
    "lowongan kerja IT developer Makassar Balikpapan Samarinda Pontianak Manado Banjarmasin",
]
# Urutkan dari nama terpanjang/spesifik dulu agar "Tangerang Selatan"
# tidak tertangkap sebagai "Tangerang" dan "Kota" generik tidak menimpa.
LOCATIONS = [
    "Tangerang Selatan", "Jakarta Selatan", "Jakarta Barat", "Jakarta Timur",
    "Jakarta Utara", "Jakarta Pusat", "Sidoarjo", "Gresik", "Mojokerto",
    "Surabaya", "Jakarta", "Tangerang", "Bekasi", "Bogor", "Depok",
    "Bandung", "Cimahi", "Semarang", "Yogyakarta", "Solo", "Malang",
    "Kediri", "Medan", "Palembang", "Batam", "Pekanbaru", "Denpasar",
    "Makassar", "Balikpapan", "Samarinda", "Pontianak", "Banjarmasin",
    "Manado",
]
# Host sampah/non-lowongan yang tidak boleh masuk data: contoh, media
# sosial (dinding login), dan situs berita (artikel, bukan lowongan).
DENY_HOSTS = {
    "example.com", "example.org", "example.net",
    "linkedin.com", "facebook.com", "instagram.com", "youtube.com",
    "twitter.com", "x.com", "wikipedia.org",
    "detik.com", "kompas.com", "tribunnews.com", "liputan6.com",
    "cnnindonesia.com", "tempo.co", "antaranews.com", "merdeka.com",
    "suara.com", "okezone.com", "grid.id", "pikiran-rakyat.com",
}
# Judul hasil harus mengandung salah satu kata ini agar lolos saring.
TITLE_KEYS = [
    "lowongan", "loker", "vacancy", "vacancies", "jobs", "job fair",
    "karir", "career", "developer", "programmer", "engineer", "qa",
    "data", "it support", "helpdesk", "devops", "frontend", "front-end",
    "backend", "back-end", "fullstack", "full stack", "software",
    "sistem informasi", "teknologi informasi", "database", "network",
    "programer", "web", "mobile", "android", "flutter",
]
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

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")

def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", htmlmod.unescape(fragment or ""))).strip()

def fetch_ddg(query: str):
    """Hasil pencarian DuckDuckGo (halaman HTML) -> [{title, link, desc}]."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    page = _get(url)
    titles = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page, re.S)
    out = []
    for i, (link, title) in enumerate(titles):
        link = htmlmod.unescape(link)
        if "uddg=" in link:
            link = urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])
        out.append({"title": _clean(title), "link": link,
                    "desc": _clean(snips[i]) if i < len(snips) else ""})
    return out

def fetch_bing(query: str):
    """Cadangan: hasil pencarian Bing (halaman HTML) -> [{title, link, desc}]."""
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&count=20"
    page = _get(url)
    out = []
    for m in re.finditer(r'<li class="b_algo".*?<h2>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a></h2>(.*?)</li>', page, re.S):
        pm = re.search(r"<p[^>]*>(.*?)</p>", m.group(3), re.S)
        out.append({"title": _clean(m.group(2)), "link": htmlmod.unescape(m.group(1)),
                    "desc": _clean(pm.group(1)) if pm else ""})
    return out

def fetch_search(query: str):
    """Gabung hasil DDG + Bing HTML (keduanya kadang bolong secara acak),
    dedup per URL, buang tautan pembungkus redirect mesin pencari."""
    out, seen = [], set()
    for fn in (fetch_ddg, fetch_bing):
        try:
            res = fn(query)
        except Exception as e:
            print(f"WARN: {fn.__name__} gagal: {query}: {e}", file=sys.stderr)
            continue
        for r in res:
            host = re.sub(r"^www\.", "", urllib.parse.urlparse(r["link"]).netloc).lower()
            if host.endswith("bing.com") or host.endswith("duckduckgo.com"):
                continue  # tautan ck/a / l/?uddg yang gagal terurai
            if r["link"] in seen:
                continue
            seen.add(r["link"])
            out.append(r)
    return out

def denied(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in DENY_HOSTS)

def categorize(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    for cat, keys in CATEGORY_RULES:
        if any(k in text for k in keys):
            return cat
    return "Lainnya"

def work_type_of(title: str, summary: str):
    """Tipe pekerjaan dari teks sumber; None bila tidak disebutkan."""
    text = (title + " " + summary).lower()
    if re.search(r"\bremote\b|work from home|\bwfh\b|dari rumah", text):
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    if re.search(r"onsite|on-site|di kantor|work from office|\bwfo\b", text):
        return "onsite"
    return None

def location_of(text: str) -> str:
    """Lokasi = nama kota yang MUNCUL PALING AWAL di teks (bukan urutan
    daftar), agar judul menyebut kota utamanya dengan benar."""
    low = text.lower()
    best = None
    for loc in LOCATIONS:
        i = low.find(loc.lower())
        if i >= 0 and (best is None or i < best[0] or (i == best[0] and len(loc) > len(best[1]))):
            best = (i, loc)
    if best is None:
        return "Jakarta"
    loc = best[1]
    # Normalisasi: "Jakarta Selatan" dsb. digabung ke "Jakarta",
    # "Tangerang Selatan" digabung ke "Tangerang".
    if loc.startswith("Jakarta"):
        return "Jakarta"
    if loc.startswith("Tangerang"):
        return "Tangerang"
    return loc

PORTAL_NAMES = {"jobstreet", "indeed", "glints", "jooble", "loker", "dealls",
                "pintarnya", "joblum", "kitalulus", "urbanhire", "kalibrr",
                "karirhub", "linkedin", "crossover", "siduta", "jakartakerja"}

def source_name_of(host: str) -> str:
    parts = host.split(".")
    for p in parts:
        if p in PORTAL_NAMES:
            return p.capitalize()
    return (parts[1] if parts[0] in ("id", "www", "m") and len(parts) > 2 else parts[0]).capitalize()

def main() -> int:
    seen, jobs = set(), []
    for qi, q in enumerate(QUERIES):
        if qi:
            time.sleep(1.2)  # jeda sopan antar-kueri agar tidak kena batas laju
        try:
            items = fetch_search(q)
        except Exception as e:
            print(f"WARN: query gagal: {q}: {e}", file=sys.stderr)
            continue
        for item in items:
            title = item["title"].strip()
            link = item["link"].strip()
            desc = item["desc"].strip()
            if not title or not link or link in seen:
                continue
            if not any(k in title.lower() for k in TITLE_KEYS):
                continue
            if not any(loc.lower() in (title + desc).lower() for loc in LOCATIONS):
                continue
            host = re.sub(r"^www\.", "", urllib.parse.urlparse(link).netloc).lower()
            if denied(host):
                continue
            if "(closed)" in title.lower() or "(ditutup)" in title.lower():
                continue
            seen.add(link)
            source_name = source_name_of(host)
            job = {
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
            }
            wt = work_type_of(title, desc)
            if wt:
                job["work_type"] = wt
            jobs.append(job)
    if len(jobs) < 5:
        print(f"Hasil baru cuma {len(jobs)} (<5) — file lama dipertahankan.")
        return 0
    data = {"fetchedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "jobs": jobs}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(jobs)} lowongan ditulis ke {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
