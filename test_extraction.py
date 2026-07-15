"""
TeraBox Extraction Test - Phase 5: Deep HTML scan + all endpoint variants
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


def deep_scan_html(html: str):
    """Print ALL occurrences of important keywords in the HTML."""
    print("\n=== DEEP HTML SCAN ===")
    keywords = ["FDTAER", "sign", "timestamp", "SIGN", "TIMESTAMP",
                "yunData", "__NEXT_DATA__", "initialState", "shareid",
                "share_id", "shareId", "logid", "bdstoken"]
    for kw in keywords:
        positions = [m.start() for m in re.finditer(re.escape(kw), html, re.IGNORECASE)]
        if positions:
            print(f"\n['{kw}'] found at {len(positions)} positions:")
            for pos in positions[:3]:  # show first 3
                snippet = html[max(0, pos-20):pos+100]
                print(f"  pos={pos}: ...{repr(snippet)}...")
        else:
            print(f"\n['{kw}'] NOT FOUND")


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
    print("STEP 1: Fetching HTML...")
    r = make_session().get(
        f"{domain}/sharing/link?surl={surl}",
        headers={"Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"},
        timeout=15, allow_redirects=True
    )
    html = r.text
    print(f"Status: {r.status_code} | HTML: {len(html)} chars")

    # Save full HTML for inspection
    with open("/tmp/terabox_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Full HTML saved to /tmp/terabox_page.html")

    # Deep scan
    deep_scan_html(html)

    # jsToken
    js_token = ""
    m = re.search(r'fn%28%22(.*?)%22%29', html)
    if m:
        js_token = m.group(1)

    # ─── STEP 2: Anonymous /share/list ───────────────────────────────────
    print("\n\nSTEP 2: Anonymous /share/list...")
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
    server_time = str(d2.get("server_time", ""))
    items = d2.get("list", [])
    item = items[0] if items else {}
    fs_id = item.get("fs_id", "")
    md5 = item.get("md5", "")
    size = item.get("size", "0")
    thumbs = item.get("thumbs", {})
    thumb_url = thumbs.get("url1", "")

    # Extract sign+time from thumb URL
    sign = ""
    timestamp = ""
    if thumb_url:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(thumb_url).query)
        sign = qs.get("sign", [""])[0]
        timestamp = qs.get("time", [""])[0]

    print(f"uk={uk} | share_id={share_id} | fs_id={fs_id}")
    print(f"server_time={server_time} | sign={sign[:30]}... | timestamp={timestamp}")

    # ─── STEP 3: /share/list WITH web=1 + sign + timestamp (anon) ────────
    print("\nSTEP 3: /share/list with web=1 + sign + timestamp (anonymous)...")
    r3 = make_session().get(
        f"{domain}/share/list",
        params={
            "app_id": "250528", "jsToken": js_token, "shorturl": surl,
            "root": "1", "web": "1", "channel": "chunlei",
            "sign": sign, "timestamp": timestamp,
            "uk": uk, "shareid": share_id,
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
        },
        timeout=12
    )
    d3 = r3.json()
    items3 = d3.get("list", [{}])
    dlink3 = items3[0].get("dlink", "") if items3 else ""
    print(f"errno: {d3.get('errno')} | dlink: {'✅ '+dlink3[:60] if dlink3 else '❌ NOT FOUND'}")

    # ─── STEP 4: /share/list WITH web=1 + cookie ─────────────────────────
    print("\nSTEP 4: /share/list with web=1 + COOKIE...")
    r4 = make_session().get(
        f"{domain}/share/list",
        params={
            "app_id": "250528", "jsToken": js_token, "shorturl": surl,
            "root": "1", "web": "1", "channel": "chunlei",
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
            "Cookie": cookie_header,
        },
        timeout=12
    )
    d4 = r4.json()
    items4 = d4.get("list", [{}])
    dlink4 = items4[0].get("dlink", "") if items4 else ""
    print(f"errno: {d4.get('errno')} | dlink: {'✅ '+dlink4[:60] if dlink4 else '❌ NOT FOUND'}")

    # ─── STEP 5: POST /api/sharedownload ─────────────────────────────────
    print("\nSTEP 5: POST /api/sharedownload...")
    r5 = make_session().post(
        f"{domain}/api/sharedownload",
        params={"app_id": "250528", "jsToken": js_token},
        data={
            "uk": uk,
            "shareid": share_id,
            "fs_ids": json.dumps([int(fs_id)]),
            "sign": sign,
            "timestamp": timestamp,
            "type": "dlink",
            "product": "share",
            "nozip": "0",
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
            "Cookie": cookie_header,
        },
        timeout=12
    )
    print(f"Status: {r5.status_code}")
    print(f"Response: {r5.text[:500]}")

    # ─── STEP 6: Try constructing dlink from thumb sign ───────────────────
    print("\nSTEP 6: Construct dlink URL from thumb sign and test HEAD...")
    if md5 and sign and timestamp:
        constructed = (
            f"https://d.1024tera.com/file/{md5}"
            f"?fid={uk}-250528-{fs_id}"
            f"&time={timestamp}"
            f"&rt=sh"
            f"&sign={urllib.parse.quote(sign)}"
            f"&expires=8h"
            f"&chkv=0&chkbd=0&chkpc="
            f"&size={size}"
            f"&vuk={uk}"
        )
        print(f"Constructed URL:\n{constructed}")
        try:
            hr = make_session().head(constructed, headers={
                "Cookie": cookie_header,
                "Referer": f"{domain}/sharing/link?surl={surl}",
            }, timeout=10, allow_redirects=True)
            print(f"HEAD Status: {hr.status_code}")
            print(f"Content-Length: {hr.headers.get('Content-Length', 'N/A')}")
            print(f"Content-Type: {hr.headers.get('Content-Type', 'N/A')}")
            print(f"Accept-Ranges: {hr.headers.get('Accept-Ranges', 'N/A')}")
        except Exception as e:
            print(f"HEAD failed: {e}")
    else:
        print("Missing md5/sign/timestamp for construction")


if __name__ == "__main__":
    test_full_flow()
