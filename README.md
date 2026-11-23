# Lowongan IT Surabaya & Sidoarjo

Papan lowongan pekerjaan bidang **IT** untuk area **Surabaya, Sidoarjo, Gresik, Mojokerto, dan sekitarnya**, diambil dari berbagai sumber di internet (JobStreet, Indeed, Glints, Dealls, Jooble, SmartRecruiters, situs karier perusahaan, dll).

🌐 **Web:** https://yoga777.github.io/lowongan-it-surabaya-sidoarjo/

## Dinamis, bukan statis

- Halaman (`index.html`) membaca data dari `data/jobs.json` saat dibuka (tanpa cache).
- Data diperbarui **otomatis setiap hari pukul 06:00 WIB** oleh GitHub Actions
  (`.github/workflows/update-jobs.yml`) yang menjalankan `scripts/update_jobs.py`,
  lalu meng-commit `data/jobs.json` baru. Commit itu memicu deploy ulang GitHub Pages.
- Pembaruan juga bisa dijalankan manual: tab **Actions → Update lowongan (harian) → Run workflow**.
- Kalau satu run gagal mengambil cukup data baru (< 5 lowongan), data lama dipertahankan — situs tidak pernah kosong.

## Fitur

- Pencarian kata kunci (posisi / perusahaan / skill)
- Filter lokasi (chip), kategori, dan sumber
- Kartu lowongan modern dengan tombol **Lamar di Sumber Asli**
- Mode gelap/terang mengikuti sistem

## Struktur

```
index.html                      # halaman web (vanilla HTML/CSS/JS, tanpa build)
data/jobs.json                  # data lowongan (diperbarui otomatis)
scripts/update_jobs.py          # pengambil data dari RSS pencarian web
.github/workflows/
  update-jobs.yml               # cron harian pembaruan data
  deploy-pages.yml              # deploy ke GitHub Pages
```

## Jalankan lokal

Cukup buka `index.html` lewat server statis apa pun, mis. `python3 -m http.server`.

## Catatan

Lowongan adalah milik portal/perusahaan sumbernya; tombol Lamar selalu mengarah ke halaman asli. Rekrutmen resmi tidak memungut biaya — waspada penipuan.
