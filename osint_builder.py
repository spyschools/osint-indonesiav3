#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
osint_builder.py
All-in-one builder:
- Download wilayah (prov/kab/kec) from wilayah.id API
- Generate osint_v3.py (with multi-threaded Google dorking, NIK/HP parsing, HTML report)
- Create README.md
- Package into osint_v3.zip
"""
import requests, json, time, zipfile, os, sys, datetime
from pathlib import Path

BASE_URL = "https://wilayah.id/api"
OUTPUT_JSON = "kode_wilayah.json"
ZIP_NAME = "osint_v3.zip"

# ---------------------------
# STEP 1: download wilayah
# ---------------------------
def get_data(endpoint, params=None):
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[!] Gagal ambil {endpoint}: {e}")
        return {"data": []}

def generate_wilayah():
    print("[*] Mengambil data provinsi dari API wilayah.id...")
    prov = get_data("provinsi")
    wilayah = {}
    for p in prov.get("data", []):
        kode_prov = p.get("kode")  # biasanya 2 digits or longer
        nama_prov = p.get("nama")
        if not kode_prov:
            continue
        print(f"  - Provinsi: {nama_prov} ({kode_prov})")
        wilayah[kode_prov] = {"nama": nama_prov, "kabupaten": {}}

        # kabupaten
        kab = get_data("kabupaten", {"provinsi_id": kode_prov})
        time.sleep(0.2)
        for k in kab.get("data", []):
            kode_kab_full = k.get("kode")  # full code like prov(2)+kab(2)+...
            nama_kab = k.get("nama")
            if not kode_kab_full:
                continue
            # kab id two-digit (pos 2:4) may vary by API; store full code key to be safe
            kab_key = kode_kab_full
            print(f"    - Kabupaten/Kota: {nama_kab} ({kab_key})")
            wilayah[kode_prov]["kabupaten"][kab_key] = {"nama": nama_kab, "kecamatan": {}}

            # kecamatan
            kec = get_data("kecamatan", {"kabupaten_id": kode_kab_full})
            time.sleep(0.15)
            for kc in kec.get("data", []):
                kode_kec_full = kc.get("kode")
                nama_kec = kc.get("nama")
                if not kode_kec_full:
                    continue
                wilayah[kode_prov]["kabupaten"][kab_key]["kecamatan"][kode_kec_full] = nama_kec
    # simpan
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(wilayah, f, indent=2, ensure_ascii=False)
    print(f"[✓] Simpan data wilayah ke `{OUTPUT_JSON}` (entries: provinsi={len(wilayah)})")

# ---------------------------
# STEP 2: generate osint_v3.py (with multithread dorking)
# ---------------------------
def create_osint_script():
    code = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
osint_v3.py
- Parse NIK & Phone
- Multi-threaded Google Dorking (scrape search results)
- Generate HTML report
Usage:
  python3 osint_v3.py 3275124308050003 +6281234567890
Dependencies:
  pip3 install requests beautifulsoup4
"""
import sys, re, json, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import html

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64)"
TIMEOUT = 12
MAX_THREADS = 8

# Sites to dork (tweakable)
DORK_SITES = [
    "site:go.id",
    "site:ac.id",
    "site:facebook.com",
    "site:instagram.com",
    "site:olx.co.id",
    "site:shopee.co.id",
    "site:tokopedia.com",
    ""  # global
]
GOOGLE_SEARCH = "https://www.google.com/search?q={query}&num=10"

# load wilayah if present
WILAYAH_FILE = "kode_wilayah.json"
try:
    with open(WILAYAH_FILE, "r", encoding="utf-8") as wf:
        WIL = json.load(wf)
except Exception:
    WIL = {}

PROVIDER_PREFIX = {
  "0811":"Telkomsel","0812":"Telkomsel","0813":"Telkomsel","0821":"Telkomsel",
  "0814":"Indosat","0815":"Indosat","0816":"Indosat","0855":"Indosat",
  "0817":"XL","0818":"XL","0819":"XL","0895":"Tri","0896":"Tri","0881":"Smartfren"
}

def is_nik(s): return re.fullmatch(r"\d{16}", s) is not None
def is_phone(s): return re.fullmatch(r"(\+62\d{8,13}|08\d{8,13})", s) is not None

def parse_nik(nik):
    res = {"nik": nik, "provinsi": "Tidak diketahui", "kabupaten": "Tidak diketahui", "kecamatan": "Tidak diketahui"}
    if len(nik) != 16:
        return res
    kode_prov = nik[:2]
    # Attempt to find by startswith in WIL (key may be '32' or longer). try multiple matches.
    if WIL:
        # Find prov key exactly or starting with kode_prov
        prov_key = None
        for k in WIL.keys():
            if k.startswith(kode_prov):
                prov_key = k; break
        if prov_key:
            res["provinsi"] = WIL.get(prov_key, {}).get("nama", "Tidak diketahui")
            # find matching kab where kab key startswith prov_key
            kab_key_found = None
            for kabk, kabv in WIL[prov_key].get("kabupaten", {}).items():
                # kabk might be full code; check if nik startswith kabk[:len(kabk)]
                if nik.startswith(kabk[:len(kabk)]):
                    kab_key_found = kabk
                    break
            if kab_key_found:
                res["kabupaten"] = WIL[prov_key]["kabupaten"][kab_key_found].get("nama","Tidak diketahui")
                # kecamatan: try exact match by kode substring
                for kec_k, kec_n in WIL[prov_key]["kabupaten"][kab_key_found].get("kecamatan", {}).items():
                    if nik.startswith(kec_k[:len(kec_k)]):
                        res["kecamatan"] = kec_n
                        break
    # date & gender
    try:
        dd = int(nik[6:8])
        mm = int(nik[8:10])
        yy = int(nik[10:12])
        gender = "Laki-laki"
        if dd > 40:
            dd -= 40; gender = "Perempuan"
        # heuristic for full year
        cur = datetime.datetime.now().year % 100
        year_full = 2000 + yy if yy <= cur else 1900 + yy
        res["tanggal_lahir"] = f"{dd:02d}-{mm:02d}-{year_full}"
        res["jenis_kelamin"] = gender
    except Exception:
        pass
    return res

def parse_phone(phone):
    norm = phone
    if norm.startswith("+62"):
        norm = "0" + norm[3:]
    prefix = norm[:4]
    provider = PROVIDER_PREFIX.get(prefix, "Tidak diketahui")
    return {"input": phone, "normalized": norm, "prefix": prefix, "provider": provider}

def google_search_raw(query):
    url = GOOGLE_SEARCH.format(query=requests.utils.requote_uri(query))
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        # parse /url?q= links
        for a in soup.select("a"):
            href = a.get("href","")
            if href.startswith("/url?q="):
                u = href.split("/url?q=")[1].split("&")[0]
                if u.startswith("http"):
                    links.append(u)
        # fallback: href containing http
        if not links:
            for a in soup.select("a"):
                href = a.get("href","")
                if href and "http" in href and "google" not in href:
                    links.append(href)
        # dedup preserve order
        seen = set(); uniq = []
        for u in links:
            if u not in seen:
                seen.add(u); uniq.append(u)
        return uniq[:25]
    except Exception:
        return []

def dork_target_multisite(target, sites=DORK_SITES, max_workers=6):
    queries = []
    for s in sites:
        q = f'{s} "{target}"' if s else f'"{target}"'
        queries.append(q)
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(queries), max_workers)) as ex:
        futures = { ex.submit(google_search_raw, q): q for q in queries }
        for fut in as_completed(futures):
            q = futures[fut]
            try:
                res = fut.result()
            except Exception:
                res = []
            results[q] = res
    return results

def generate_html_report(entries, filename=None):
    parts = []
    for e in entries:
        parts.append(f"<h2>{html.escape(e.get('title','Target'))}</h2>")
        parts.append("<table border='1' cellpadding='6' style='border-collapse:collapse'>")
        for k,v in e.get("summary",{}).items():
            parts.append(f"<tr><th style='text-align:left'>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>")
        parts.append("</table>")
        parts.append("<h3>Dorking</h3>")
        for q,urls in e.get("dork",{}).items():
            parts.append(f"<b>{html.escape(q)}</b><ul>")
            for u in urls[:30]:
                parts.append(f"<li><a href='{html.escape(u)}' target='_blank'>{html.escape(u)}</a></li>")
            parts.append("</ul>")
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = "".join(parts)
    doc = f"<!doctype html><html><head><meta charset='utf-8'><title>OSINT v3 Report</title></head><body><h1>OSINT v3 Report</h1><p>Generated: {ts}</p>{body}</body></html>"
    if not filename:
        filename = f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(doc)
    return filename

def process_target(t):
    if is_nik(t):
        parsed = parse_nik(t)
        dork = dork_target_multisite(t, max_workers=6)
        return {"title": f"NIK {t}", "summary": parsed, "dork": dork}
    elif is_phone(t):
        parsed = parse_phone(t)
        dork = dork_target_multisite(parsed["normalized"], max_workers=6)
        return {"title": f"Phone {t}", "summary": parsed, "dork": dork}
    else:
        dork = dork_target_multisite(t, max_workers=6)
        return {"title": f"Unknown {t}", "summary": {"note":"format not recognized"}, "dork": dork}

def main(argv):
    if len(argv) < 2:
        print("Usage: python3 osint_v3.py <NIK/Phone> [NIK/Phone ...]")
        return
    targets = argv[1:]
    entries = []
    with ThreadPoolExecutor(max_workers=min(len(targets), MAX_THREADS)) as ex:
        futures = { ex.submit(process_target, t): t for t in targets }
        for fut in as_completed(futures):
            res = fut.result()
            entries.append(res)
            print(f"[+] Done: {res.get('title')}")
    out = generate_html_report(entries)
    print(f"[+] Report saved: {out}")

if __name__ == "__main__":
    import sys
    main(sys.argv)
'''
    with open("osint_v3.py", "w", encoding="utf-8") as f:
        f.write(code)
    os.chmod("osint_v3.py", 0o755)
    print("[✓] osint_v3.py dibuat (dengan multi-threaded dorking)")

# ---------------------------
# STEP 3: create README
# ---------------------------
def create_readme():
    readme = """# OSINT v3 Package

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
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)
    print("[✓] README.md dibuat")

# ---------------------------
# STEP 4: zip everything
# ---------------------------
def make_zip():
    files = ["osint_v3.py", "README.md", OUTPUT_JSON]
    with zipfile.ZipFile(ZIP_NAME, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for fname in files:
            if os.path.exists(fname):
                z.write(fname)
    print(f"[✓] Paket {ZIP_NAME} berhasil dibuat")

# ---------------------------
# MAIN
# ---------------------------
def main():
    try:
        generate_wilayah()
        create_osint_script()
        create_readme()
        make_zip()
        print("[ALL DONE] Selesai. Ekstrak osint_v3.zip dan jalankan osint_v3.py")
    except KeyboardInterrupt:
        print("\n[!] Dibatalkan pengguna")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    # kebutuhan: requests, beautifulsoup4 pada runtime script yang dibuat
    main()
