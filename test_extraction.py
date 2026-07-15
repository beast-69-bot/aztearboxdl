"""
TeraBox Extraction Test - Phase 4: sharedownload with sign+timestamp
"""
import os
import re
import json
import urllib.parse
from dotenv import load_dotenv
import curl_cffi.requests as curl_requests

load_dotenv()

NDUS_COOKIE = os.getenv("NDUS_COOKIE")
STATIC_PROXY = os.getenv("STATIC_PROXY")


def format_curl_proxy(proxy_str: str) -> dict:
    if not proxy_str:
        return {}
    parts = proxy_str.strip().split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return {"http": f"http://{user}:{pwd}@{ip}:{port}",
                "https": f"http://{user}:{pwd}@{ip}:{port}"}
    p = proxy_str if proxy_str.startswith("http") else f"http://{proxy_str}"
    return {"http": p, "https": p}


def make_session():
    s = curl_requests.Session(impersonate="chrome110")
    if STATIC_PROXY:
        s.proxies = format_curl_proxy(STATIC_PROXY)
    return s


def test_full_flow():
    surl = "6j9ZbdrBAAL6qvL70yPO2A"
    domain = "https://dm.1024tera.com"

    # Load cookie
    cookie_header = ""
    for path in ["terabox_cookie_header.txt", "../terabox_cookie_header.txt"]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cookie_header = f.read().strip()
            break
    if not cookie_header and NDUS_COOKIE:
        cookie_header = f"ndus={NDUS_COOKIE}"

    # ─── STEP 1: Anonymous HTML ───────────────────────────────────────────
    print("STEP 1: Fetching HTML anonymously...")
    r = make_session().get(
        f"{domain}/sharing/link?surl={surl}",
        headers={"Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"},
        timeout=15, allow_redirects=True
    )
    html = r.text
    print(f"Status: {r.status_code} | HTML: {len(html)} chars")

    # Extract jsToken
    js_token = ""
    m = re.search(r'fn%28%22(.*?)%22%29', html)
    if m:
        js_token = m.group(1)
        print(f"jsToken: ✅ {js_token[:40]}...")

    # Extract sign from HTML (multiple patterns)
    sign = ""
    for pat in [
        r'"sign"\s*:\s*"(FDTAER[^"]+)"',
        r"'sign'\s*:\s*'(FDTAER[^']+)'",
        r'sign\s*=\s*"(FDTAER[^"]+)"',
        r'sign\s*=\s*\'(FDTAER[^\']+)\'',
        r'SIGN\s*=\s*"(FDTAER[^"]+)"',
        r'yunData\.SIGN\s*=\s*"(FDTAER[^"]+)"',
    ]:
        m = re.search(pat, html)
        if m:
            sign = m.group(1)
            print(f"sign (HTML): ✅ {sign[:50]}...")
            break
    if not sign:
        print("sign: ❌ NOT FOUND in HTML (will try thumbnail URL)")

    # Extract timestamp from HTML
    timestamp = ""
    for pat in [
        r'"timestamp"\s*:\s*"(\d+)"',
        r"'timestamp'\s*:\s*'(\d+)'",
        r'timestamp\s*=\s*"(\d+)"',
        r'TIMESTAMP\s*=\s*"(\d+)"',
        r'yunData\.TIMESTAMP\s*=\s*"(\d+)"',
    ]:
        m = re.search(pat, html)
        if m:
            timestamp = m.group(1)
            print(f"timestamp (HTML): ✅ {timestamp}")
            break
    if not timestamp:
        print("timestamp: ❌ NOT FOUND in HTML")

    if not js_token:
        print("ERROR: No jsToken. Aborting.")
        return

    # ─── STEP 2: Anonymous /share/list ───────────────────────────────────
    print("\nSTEP 2: Anonymous /share/list...")
    r2 = make_session().get(
        f"{domain}/share/list",
        params={"app_id": "250528", "jsToken": js_token, "shorturl": surl, "root": "1"},
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
        },
        timeout=12
    )
    d2 = r2.json()
    uk = str(d2.get("uk", ""))
    share_id = str(d2.get("share_id", ""))
    items = d2.get("list", [])
    item = items[0] if items else {}
    fs_id = item.get("fs_id", "")
    thumb_url = ""
    thumbs = item.get("thumbs", {})
    if thumbs:
        thumb_url = thumbs.get("url1", thumbs.get("url2", ""))

    print(f"uk: {uk} | share_id: {share_id} | fs_id: {fs_id}")
    print(f"thumb url: {thumb_url[:80]}...")

    # Extract sign+timestamp from thumbnail URL if not found in HTML
    if thumb_url and (not sign or not timestamp):
        parsed = urllib.parse.urlparse(thumb_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if not sign and "sign" in qs:
            sign = qs["sign"][0]
            print(f"sign (thumb URL): ✅ {sign[:50]}...")
        if not timestamp and "time" in qs:
            timestamp = qs["time"][0]
            print(f"timestamp (thumb URL): ✅ {timestamp}")

    print(f"\nAll params for sharedownload:")
    print(f"  uk:        {uk}")
    print(f"  share_id:  {share_id}")
    print(f"  fs_id:     {fs_id}")
    print(f"  sign:      {sign[:40] if sign else '❌ MISSING'}...")
    print(f"  timestamp: {timestamp if timestamp else '❌ MISSING'}")
    print(f"  jsToken:   {js_token[:40]}...")

    # ─── STEP 3: /api/sharedownload with all params + cookie ─────────────
    print("\nSTEP 3: /api/sharedownload (cookie + sign + timestamp)...")
    r3 = make_session().get(
        f"{domain}/api/sharedownload",
        params={
            "app_id": "250528",
            "jsToken": js_token,
            "uk": uk,
            "shareid": share_id,
            "fs_ids": f"[{fs_id}]",
            "sign": sign,
            "timestamp": timestamp,
            "type": "dlink",
            "product": "share",
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
            "Cookie": cookie_header,
        },
        timeout=12
    )
    print(f"Status: {r3.status_code}")
    print(f"Response: {r3.text[:600]}")

    # ─── STEP 4: /api/sharedownload WITHOUT cookie ────────────────────────
    print("\nSTEP 4: /api/sharedownload WITHOUT cookie (compare)...")
    r4 = make_session().get(
        f"{domain}/api/sharedownload",
        params={
            "app_id": "250528",
            "jsToken": js_token,
            "uk": uk,
            "shareid": share_id,
            "fs_ids": f"[{fs_id}]",
            "sign": sign,
            "timestamp": timestamp,
            "type": "dlink",
            "product": "share",
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
        },
        timeout=12
    )
    print(f"Status: {r4.status_code}")
    print(f"Response: {r4.text[:600]}")


if __name__ == "__main__":
    test_full_flow()
