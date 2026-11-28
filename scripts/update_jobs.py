#!/usr/bin/env python3
"""
Update data/jobs.json untuk Lowongan IT seluruh Indonesia.

Sumber UTAMA: API pencarian publik Jobstreet (SEEK) dengan klasifikasi
Teknologi Informasi (6281) per kota — menghasilkan lowongan INDIVIDUAL
asli lengkap dengan perusahaan, lokasi, tanggal posting, dan tipe
kerja (Kantor/Hibrid/Jarak jauh) dari sumbernya.
Sumber KEDUA: API publik Dealls (api.sejutacita.id/v1/explore-job/job,
pencarian per kata kunci peran IT). Sumber KETIGA: Glints — data
terstruktur (__NEXT_DATA__) di halaman find-jobs per kota/kata kunci
(API resminya terkunci login, tapi halaman publiknya membawa data job
lengkap: perusahaan, lokasi, gaji, tipe kerja).
Sumber PELENGKAP: hasil pencarian web (DuckDuckGo HTML + Bing HTML)
untuk portal lain; dari sini HANYA URL lowongan individual (pola URL
detail) yang diambil — halaman daftar portal dibuang, agar tombol Lamar
selalu membuka detail pekerjaan. Semua hasil juga melewati gerbang
relevansi peran IT (judul/frasa teknis) karena klasifikasi portal saja
terbukti membawa posting non-IT (F&B, sales, akunting).
(RSS pencarian Bing berhenti mengembalikan hasil pada Nov 2026.)
Hasil disaring (host berita/sosial dibuang, lowongan "(Closed)" dibuang),
didedup berdasarkan URL, dan dikategorikan sederhana.

Kalau hasil baru < 5 (mis. jaringan diblokir), file lama TIDAK ditimpa —
jadi situs tidak pernah kosong gara-gara satu run gagal.
Pengaman sumber utama: kalau hasil baru TIDAK berisi Jobstreet sama
sekali padahal file lama berisi Jobstreet, file lama juga TIDAK ditimpa
dan run GAGAL dengan kode keluar 1 — kegagalan satu sumber tidak boleh
menimpa dataset bagus secara diam-diam (kejadian 28 Nov 2026: dataset
140 tertimpa 107 tanpa Jobstreet dan run-nya tetap "sukses").

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

# ===== Gerbang relevansi peran IT =====
# Klasifikasi portal saja tidak cukup: sebagian posting salah kategori
# (F&B, staf dapur, sales, akunting ikut terbawa). Gerbang dua lapis:
# judul mengandung kata peran IT, ATAU ringkasan mengandung frasa teknis
# kuat (untuk konsultan ERP, analis sistem, dsb. yang judulnya umum).
ROLE_KEYS = [
    "developer", "programmer", "programer", "software", "engineer", "data",
    "qa", "quality assurance", "tester", "testing", "devops", "network",
    "system", "sistem", "database", "web", "mobile", "android", "ios",
    "flutter", "frontend", "front-end", "backend", "back-end", "fullstack",
    "full-stack", "full stack", "security", "cyber", "cloud", "helpdesk",
    "support", "analyst", "analis", "administrator", "teknisi", "noc",
    "erp", "sap", "automation", "machine learning", "infrastruktur",
    "infrastructure", "teknologi", "technology", "informasi", "digital",
    "scrum", "technical", "php", "java", "python", "javascript", "laravel",
    "react", "node", "golang", "sql", "linux", "server", "hardware",
    "telekomunikasi", "it", "ai", "ui", "ux",
]
STRONG_KEYS = [
    "software", "erp", "sap", "sistem informasi", "database", "server",
    "aplikasi", "programming", "pemrograman", "teknologi informasi",
    "jaringan", "it support", "information technology", "data center",
    "cloud", "cyber", "keamanan siber",
]

def it_role_gate(title: str, teaser: str = "") -> bool:
    t = title.lower()
    for k in ROLE_KEYS:
        if len(k) >= 4:
            if k in t:
                return True
        elif re.search(r"\b" + re.escape(k) + r"\b", t):
            return True
    s = (teaser or "").lower()
    return any(k in s for k in STRONG_KEYS)

# ===== Sumber utama: API Jobstreet (SEEK), klasifikasi IT 6281 =====
SEEK_CITIES = [
    "Surabaya", "Sidoarjo", "Gresik", "Mojokerto", "Jakarta", "Tangerang",
    "Bekasi", "Bogor", "Depok", "Bandung", "Cimahi", "Semarang",
    "Yogyakarta", "Solo", "Malang", "Kediri", "Medan", "Palembang",
    "Batam", "Pekanbaru", "Denpasar", "Makassar", "Balikpapan",
    "Samarinda", "Pontianak", "Banjarmasin", "Manado",
]

def parse_salary(label: str):
    """'Rp 5.500.000 – Rp 7.000.000 per month' -> (label bersih, min per bulan).
    Mengembalikan (None, 0) bila tidak ada angka Rp yang bisa dibaca."""
    if not label:
        return None, 0
    text = re.sub(r"\s+", " ", str(label)).strip()
    nums = []
    for raw in re.findall(r"Rp\s*([\d][\d.,]*)", text):
        try:
            nums.append(int(re.sub(r"[.,]", "", raw)))
        except ValueError:
            pass
    if not nums:
        return None, 0
    low = text.lower()
    if "year" in low or "annum" in low or "tahun" in low:
        factor = 1 / 12
    elif "day" in low or "hari" in low:
        factor = 22
    elif "hour" in low or "jam" in low:
        factor = 160
    elif "week" in low or "minggu" in low:
        factor = 4.33
    else:
        factor = 1
    return text, int(min(nums) * factor)

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
        if not it_role_gate(title, j.get("teaser") or ""):
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
        sal_label, sal_min = parse_salary(j.get("salaryLabel") or "")
        if sal_label:
            job["salary"] = sal_label
            job["salary_min"] = sal_min
        job["_date"] = j.get("listingDate") or ""
        out.append(job)
    return out

def rel_id(iso: str) -> str:
    """ISO datetime -> label relatif ala Jobstreet ('3 jam yang lalu')."""
    try:
        dt = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return ""
    secs = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    if secs < 3600:
        return f"{max(1, secs // 60)} menit yang lalu"
    if secs < 86400:
        return f"{secs // 3600} jam yang lalu"
    if secs < 30 * 86400:
        return f"{secs // 86400} hari yang lalu"
    return f"{secs // (30 * 86400)} bulan yang lalu"

def rp(n) -> str:
    return "Rp " + f"{int(n):,}".replace(",", ".")

# ===== Sumber kedua: Dealls (API publik api.sejutacita.id) =====
DEALLS_SEARCHES = ["developer", "software", "engineer", "data", "qa",
                   "IT support", "programmer", "IT", "devops", "frontend"]

def fetch_dealls(keyword: str):
    qs = urllib.parse.urlencode({"search": keyword, "page": 1, "limit": 30})
    url = "https://api.sejutacita.id/v1/explore-job/job?" + qs
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    out = []
    for j in data.get("data", {}).get("docs", []):
        if j.get("status") != "active":
            continue
        title = (j.get("role") or "").strip()
        if not title or "(closed)" in title.lower():
            continue
        city = (j.get("city") or {}).get("name", "")
        loc_text = city or title
        if not any(l.lower() in loc_text.lower() for l in LOCATIONS):
            continue
        if not it_role_gate(title, ""):
            continue
        comp = j.get("company") or {}
        url_job = f"https://dealls.com/loker/{j.get('slug')}~{comp.get('slug') or ''}".rstrip("~")
        wp = (j.get("workplaceType") or "").lower()
        job = {
            "title": title[:140],
            "company": comp.get("name") or None,
            "location": location_of(loc_text),
            "category": categorize(title, ""),
            "url": url_job,
            "sourceUrl": url_job,
            "source_name": "Dealls",
            "sourceName": "Dealls",
            "summary": "",
            "posted": rel_id(j.get("publishedAt") or ""),
            "_date": j.get("publishedAt") or "",
        }
        if "remote" in wp:
            job["work_type"] = "remote"
        elif "hybrid" in wp or "hibrid" in wp:
            job["work_type"] = "hybrid"
        elif wp:
            job["work_type"] = "onsite"
        out.append(job)
    return out

# ===== Sumber ketiga: Glints (data terstruktur di halaman find-jobs) =====
GLINTS_CITIES = ["surabaya", "jakarta", "bandung", "semarang", "yogyakarta",
                 "tangerang", "denpasar", "medan", "malang"]
GLINTS_KEYWORDS = ["programmer", "developer"]

def _slugify(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")

def fetch_glints(city_slug: str, keyword: str):
    url = f"https://glints.com/id/find-jobs/loker-{keyword}-{city_slug}"
    page = _get(url)
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    jobs = data.get("props", {}).get("pageProps", {}).get("initialJobs", {}).get("jobsInPage", [])
    out = []
    for j in jobs:
        if j.get("status") != "OPEN":
            continue
        title = (j.get("title") or "").strip()
        if not title or "(closed)" in title.lower():
            continue
        loc = j.get("location") or {}
        names = [p.get("name", "") for p in loc.get("parents", [])] + [loc.get("name", "")]
        loc_text = " ".join(n for n in names if n)
        if not any(l.lower() in loc_text.lower() for l in LOCATIONS):
            continue
        cat_name = (j.get("hierarchicalJobCategory") or {}).get("name", "")
        if not it_role_gate(title, cat_name):
            continue
        comp = (j.get("company") or {}).get("name")
        url_job = f"https://glints.com/id/opportunities/jobs/{_slugify(title)}/{j.get('id')}"
        job = {
            "title": title[:140],
            "company": comp or None,
            "location": location_of(loc_text),
            "category": categorize(title, cat_name),
            "url": url_job,
            "sourceUrl": url_job,
            "source_name": "Glints",
            "sourceName": "Glints",
            "summary": "",
            "posted": rel_id(j.get("createdAt") or ""),
            "_date": j.get("updatedAt") or j.get("createdAt") or "",
        }
        wa = (j.get("workArrangementOption") or "").upper()
        if wa in ("REMOTE", "HYBRID", "ONSITE"):
            job["work_type"] = wa.lower()
        sals = j.get("salaries") or []
        if sals and j.get("shouldShowSalary") in (True, "True"):
            s0 = sals[0]
            mn, mx = s0.get("minAmount"), s0.get("maxAmount")
            if mn:
                job["salary"] = f"{rp(mn)} – {rp(mx)} per month" if mx and mx != mn else f"{rp(mn)} per month"
                job["salary_min"] = int(mn)
        out.append(job)
    return out

# ===== Deskripsi lengkap (untuk modal Detail di situs) =====
def html_to_text(h: str, cap: int = 2000) -> str:
    if not h:
        return ""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S)
    t = re.sub(r"<li[^>]*>", "\n• ", t)
    t = re.sub(r"</(p|li|ul|ol|div|h\d)>", "\n", t)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t).strip()
    return t[:cap].rstrip()

def desc_jobstreet(url: str) -> str:
    page = _get(url)
    i = page.find('data-automation="jobAdDetails"')
    if i < 0:
        return ""
    start = page.find(">", i) + 1
    seg = page[start:start + 20000]
    txt = html_to_text(seg)
    if txt.lower().startswith("job description"):
        txt = txt[len("Job Description"):].lstrip(" :\n")
    return txt

def desc_dealls(url: str) -> str:
    m = re.search(r"dealls\.com/loker/([^~/?]+)", url)
    if not m:
        return ""
    api = "https://api.sejutacita.id/v1/job-portal/job/slug/" + m.group(1)
    req = urllib.request.Request(api, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r).get("data", {}).get("result", {})
    parts = []
    if res.get("description"):
        parts.append(html_to_text(res["description"], 1200))
    if res.get("responsibilities"):
        parts.append("Tanggung Jawab:\n" + html_to_text(res["responsibilities"], 1200))
    if res.get("requirements"):
        parts.append("Kualifikasi:\n" + html_to_text(res["requirements"], 1200))
    if res.get("perks"):
        parts.append("Benefit:\n" + html_to_text(res["perks"], 600))
    return "\n\n".join(p for p in parts if p)[:2400]

def desc_glints(url: str) -> str:
    page = _get(url)
    m = re.search(r'"description":"((?:\\.|[^"\\])*)"', page)
    if not m:
        return ""
    try:
        raw = json.loads('"' + m.group(1) + '"')
    except ValueError:
        return ""
    return html_to_text(raw)

def enrich_descriptions(final: list):
    """Isi field 'description' untuk lowongan final terpilih."""
    for job in final:
        try:
            src = job.get("source_name")
            if src == "Jobstreet":
                job["description"] = desc_jobstreet(job["url"])
            elif src == "Dealls":
                job["description"] = desc_dealls(job["url"])
            elif src == "Glints":
                job["description"] = desc_glints(job["url"])
        except Exception as e:
            print(f"WARN: deskripsi gagal {job.get('source_name')}: {e}", file=sys.stderr)
            job["description"] = ""
        time.sleep(0.15)

# Pola URL lowongan INDIVIDUAL (detail) untuk sumber pelengkap pencarian.
POSTING_RES = [
    r"glints\.com/id/opportunities/jobs/",
    r"jobstreet\.com/id/job/\d+",
    r"indeed\.com/viewjob",
    r"jobs\.smartrecruiters\.com/",
    r"kalibrr\.com/c/[^/]+/jobs/",
    r"dealls\.com/(peluang-kerja|loker)/",
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
    seen_tcl = set()
    for ci, city in enumerate(SEEK_CITIES):
        if ci:
            time.sleep(0.4)
        try:
            for job in fetch_jobstreet(city):
                if job["url"] in seen:
                    continue
                tcl = (job["title"].lower(), (job.get("company") or "").lower(), job["location"])
                if tcl in seen_tcl:
                    continue  # posting ulang: judul+perusahaan+kota sama
                seen_tcl.add(tcl)
                seen.add(job["url"])
                jobs.append(job)
        except Exception as e:
            print(f"WARN: Jobstreet gagal: {city}: {e}", file=sys.stderr)

    # 1b) Sumber kedua & ketiga: Dealls (API) dan Glints (halaman
    #     find-jobs). Digabung satu kolam, dedup URL + judul/perusahaan/kota.
    extra = []
    for kw in DEALLS_SEARCHES:
        try:
            for job in fetch_dealls(kw):
                if job["url"] in seen:
                    continue
                tcl = (job["title"].lower(), (job.get("company") or "").lower(), job["location"])
                if tcl in seen_tcl:
                    continue
                seen_tcl.add(tcl)
                seen.add(job["url"])
                extra.append(job)
        except Exception as e:
            print(f"WARN: Dealls gagal: {kw}: {e}", file=sys.stderr)
        time.sleep(0.3)
    for city_slug in GLINTS_CITIES:
        for kw in GLINTS_KEYWORDS:
            try:
                for job in fetch_glints(city_slug, kw):
                    if job["url"] in seen:
                        continue
                    tcl = (job["title"].lower(), (job.get("company") or "").lower(), job["location"])
                    if tcl in seen_tcl:
                        continue
                    seen_tcl.add(tcl)
                    seen.add(job["url"])
                    extra.append(job)
            except Exception as e:
                print(f"WARN: Glints gagal: {city_slug}/{kw}: {e}", file=sys.stderr)
            time.sleep(0.3)
    extra.sort(key=lambda j: j.get("_date", ""), reverse=True)

    # 2) Pelengkap pencarian web: HANYA lowongan individual (URL detail).
    #    Halaman daftar portal dibuang — tombol Lamar harus membuka detail
    #    pekerjaan, bukan daftar.
    postings = []
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
            if not is_posting(link):
                continue  # halaman daftar/search portal — dibuang
            if not it_role_gate(title, desc):
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
            sal_label, sal_min = parse_salary(desc)
            if sal_label:
                job["salary"] = sal_label
                job["salary_min"] = sal_min
            postings.append(job)
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

    take(jobs, 20, 100)       # utama: individual Jobstreet
    take(extra, 25, 140)      # kedua/ketiga: Dealls + Glints
    take(postings, 25, 150)   # pelengkap: individual dari pencarian web
    if len(final) < 5:
        print(f"Hasil baru cuma {len(final)} (<5) — file lama dipertahankan.")
        return 0
    # Pengaman sumber utama: Jobstreet 0 di hasil baru padahal file lama
    # berisi Jobstreet = sumber utama gagal total (diblokir/berubah).
    # Jangan timpa dataset bagus dengan hasil menyusut; gagal secara
    # terlihat (kode keluar 1) supaya kelihatan di tab Actions.
    def _n_jobstreet(pool):
        return sum(1 for j in pool
                   if (j.get("source_name") or j.get("sourceName")) == "Jobstreet")
    if _n_jobstreet(final) == 0 and OUT.exists():
        try:
            old_jobs = json.loads(OUT.read_text(encoding="utf-8")).get("jobs", [])
        except Exception:
            old_jobs = []
        old_js = _n_jobstreet(old_jobs)
        if old_js > 0:
            print(f"ERROR: Jobstreet 0 di hasil baru, file lama berisi "
                  f"{old_js} Jobstreet — file lama TIDAK ditimpa, run gagal.",
                  file=sys.stderr)
            return 1
    enrich_descriptions(final)
    data = {"fetchedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "jobs": final}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(final)} lowongan ditulis ke {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
