#!/usr/bin/env python3
"""
Update data/jobs.json untuk Lowongan IT seluruh Indonesia.

Sumber UTAMA: API pencarian publik Jobstreet (SEEK) dengan klasifikasi
Teknologi Informasi (6281) per kota — menghasilkan lowongan INDIVIDUAL
asli lengkap dengan perusahaan, lokasi, tanggal posting, dan tipe
kerja (Kantor/Hibrid/Jarak jauh) dari sumbernya.
Sumber PELENGKAP: hasil pencarian web (DuckDuckGo HTML + Bing HTML)
untuk portal lain; dari sini yang diprioritaskan adalah URL lowongan
individual (pola URL detail), halaman daftar portal dibatasi ketat.
(RSS pencarian Bing berhenti mengembalikan hasil pada Nov 2026.)
Hasil disaring (host berita/sosial dibuang, lowongan "(Closed)" dibuang),
didedup berdasarkan URL, dan dikategorikan sederhana.

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

# ===== Sumber utama: API Jobstreet (SEEK), klasifikasi IT 6281 =====
SEEK_CITIES = [
    "Surabaya", "Sidoarjo", "Gresik", "Mojokerto", "Jakarta", "Tangerang",
    "Bekasi", "Bogor", "Depok", "Bandung", "Cimahi", "Semarang",
    "Yogyakarta", "Solo", "Malang", "Kediri", "Medan", "Palembang",
    "Batam", "Pekanbaru", "Denpasar", "Makassar", "Balikpapan",
    "Samarinda", "Pontianak", "Banjarmasin", "Manado",
]

def _arrangement_wt(labels):
    low = " ".join(labels).lower()
    if "jarak jauh" in low or "remote" in low:
        return "remote"
    if "hibrid" in low or "hybrid" in low:
        return "hybrid"
    if "kantor" in low:
        return "onsite"
    return None

def fetch_jobstreet(city: str):
    """Lowongan individual Jobstreet untuk satu kota (klasifikasi IT)."""
    qs = urllib.parse.urlencode({
        "siteKey": "ID-Main", "where": city, "page": 1, "pageSize": 30,
        "locale": "id-ID", "classification": "6281",
    })
    url = "https://id.jobstreet.com/api/jobsearch/v5/search?" + qs
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    out = []
    for j in data.get("data", []):
        cls_ids = [c.get("classification", {}).get("id") for c in j.get("classifications", [])]
        if "6281" not in cls_ids:
            continue
        title = (j.get("title") or "").strip()
        if not title or "(closed)" in title.lower():
            continue
        locs = j.get("locations") or []
        label = locs[0].get("label", "") if locs else ""
        loc = location_of(label) if any(l.lower() in label.lower() for l in LOCATIONS) else location_of(city)
        subs = " ".join(c.get("subclassification", {}).get("description", "") for c in j.get("classifications", []))
        teaser = (j.get("teaser") or "").strip()
        labels = [x.get("label", {}).get("text", "") for x in j.get("workArrangements", {}).get("data", [])]
        job = {
            "title": title[:140],
            "company": (j.get("companyName") or None),
            "location": loc,
            "category": categorize(title, teaser + " " + subs),
            "url": f"https://id.jobstreet.com/id/job/{j.get('id')}",
            "sourceUrl": f"https://id.jobstreet.com/id/job/{j.get('id')}",
            "source_name": "Jobstreet",
            "sourceName": "Jobstreet",
            "summary": teaser[:280],
            "posted": (j.get("listingDateDisplay") or "").strip(),
        }
        wt = _arrangement_wt(labels) or work_type_of(title, teaser)
        if wt:
            job["work_type"] = wt
        job["_date"] = j.get("listingDate") or ""
        out.append(job)
    return out

# Pola URL lowongan INDIVIDUAL (detail) untuk sumber pelengkap pencarian.
POSTING_RES = [
    r"glints\.com/id/opportunities/jobs/",
    r"jobstreet\.com/id/job/\d+",
    r"indeed\.com/viewjob",
    r"jobs\.smartrecruiters\.com/",
    r"kalibrr\.com/c/[^/]+/jobs/",
    r"dealls\.com/peluang-kerja/",
    r"boards\.greenhouse\.io/[^/]+/jobs/",
    r"jobs\.lever\.co/",
    r"apply\.workable\.com/",
    r"glassdoor\.[^/]+/job-listing/",
]

def is_posting(url: str) -> bool:
    return any(re.search(p, url) for p in POSTING_RES)

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

    # 1) Sumber utama: lowongan individual Jobstreet per kota.
    for ci, city in enumerate(SEEK_CITIES):
        if ci:
            time.sleep(0.4)
        try:
            for job in fetch_jobstreet(city):
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                jobs.append(job)
        except Exception as e:
            print(f"WARN: Jobstreet gagal: {city}: {e}", file=sys.stderr)

    # 2) Pelengkap pencarian web: individual diprioritaskan, halaman
    #    daftar dibatasi maks 1 per (sumber, kota).
    postings, listings, listing_keys = [], [], set()
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
                "_date": "",
            }
            wt = work_type_of(title, desc)
            if wt:
                job["work_type"] = wt
            if is_posting(link):
                postings.append(job)
            else:
                key = (source_name, job["location"])
                if key in listing_keys:
                    continue
                listing_keys.add(key)
                listings.append(job)
    # Urutkan Jobstreet terbaru dulu; beri kuota agar pelengkap dari
    # portal lain tetap dapat tempat. Batas per kota menjaga sebaran.
    jobs.sort(key=lambda j: j.get("_date", ""), reverse=True)
    per_loc, final = {}, []

    def take(pool, loc_cap, total_cap):
        for job in pool:
            if len(final) >= total_cap:
                break
            n = per_loc.get(job["location"], 0)
            if n >= loc_cap:
                continue
            per_loc[job["location"]] = n + 1
            job.pop("_date", None)
            final.append(job)

    take(jobs, 20, 120)       # utama: individual Jobstreet
    take(postings, 25, 140)   # pelengkap: individual portal lain
    take(listings, 25, 150)   # terakhir: halaman daftar (sudah dibatasi)
    if len(final) < 5:
        print(f"Hasil baru cuma {len(final)} (<5) — file lama dipertahankan.")
        return 0
    data = {"fetchedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "jobs": final}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(final)} lowongan ditulis ke {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
