# OSINT v3 Package

git clone https://github.com/spyschools/osint-indonesiav3.git
cd osint-indonesiav3
pip3 install requests beautifulsoup4
python3 osint_v3.py 3275124308050003 +6281234567890

Files:
- osint_v3.py         (main scanner with multi-threaded Google dorking)
- kode_wilayah.json   (provinsi/kabupaten/kecamatan full)
- README.md

Usage:
1. Pastikan Python 3 dan dependensi:
   pip3 install requests beautifulsoup4

2. Jalankan scanner:
   python3 osint_v3.py 3275124308050003 +6281234567890

Output:
- report_TIMESTAMP.html (buka di browser)

Notes:
- Google scraping dapat rate-limit; gunakan bijak.
- Jika API wilayah.id berubah, generator bisa gagal; kamu bisa isi kode_wilayah.json manual.
