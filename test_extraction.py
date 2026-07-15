"""
TeraBox Extraction Test - Phase 2: Test /api/filemetas for premium dlink
"""
import os
import re
import json
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

    print(f"Cookie length: {len(cookie_header)}")
    print(f"Proxy: {STATIC_PROXY[:30] if STATIC_PROXY else 'None'}...")

    # ─── PHASE 1: Anonymous HTML → jsToken ───────────────────────────────
    print("\n" + "="*55)
    print("PHASE 1: Anonymous HTML → jsToken")
    print("="*55)

    r = make_session().get(
        f"{domain}/sharing/link?surl={surl}",
        headers={"Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"},
        timeout=15, allow_redirects=True
    )
    print(f"Status: {r.status_code} | HTML length: {len(r.text)}")

    js_token = None
    m = re.search(r'fn%28%22(.*?)%22%29', r.text)
    if m:
        js_token = m.group(1)
        print(f"jsToken: {js_token[:50]}...  ✅")
    else:
        print("ERROR: jsToken not found!")
        return

    # ─── PHASE 1b: Anonymous /share/list → file metadata ─────────────────
    print("\n" + "="*55)
    print("PHASE 1b: Anonymous /share/list → file metadata")
    print("="*55)

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

    data = r2.json()
    print(f"errno: {data.get('errno')}")

    if data.get("errno") != 0 or not data.get("list"):
        print(f"FAILED: {r2.text[:200]}")
        return

    item = data["list"][0]
    filename = item.get("server_filename", "unknown")
    size_mb = int(item.get("size", 0)) / 1024 / 1024
    path = item.get("path", "")
    fs_id = item.get("fs_id", "")
    dlink_anon = item.get("dlink", "")

    print(f"filename: {filename}")
    print(f"size:     {size_mb:.1f} MB")
    print(f"path:     {path}")
    print(f"fs_id:    {fs_id}")
    print(f"dlink:    {dlink_anon[:60] if dlink_anon else 'NOT in response'}")

    # ─── PHASE 2: Cookie + /api/filemetas → Premium dlink ────────────────
    print("\n" + "="*55)
    print("PHASE 2: Cookie + /api/filemetas → Premium dlink")
    print("="*55)

    r3 = make_session().get(
        f"{domain}/api/filemetas",
        params={
            "app_id": "250528",
            "jsToken": js_token,
            "target": f'["{path}"]',
            "dlink": "1",
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/disk/home",
            "Cookie": cookie_header,
        },
        timeout=12
    )

    print(f"filemetas Status: {r3.status_code}")
    try:
        d3 = r3.json()
        print(f"errno: {d3.get('errno')}")
        print(f"errmsg: {d3.get('errmsg', 'none')}")
        info = d3.get("info", [])
        if info:
            dlink_premium = info[0].get("dlink", "")
            print(f"dlink: {dlink_premium[:80] if dlink_premium else 'NOT FOUND'}...")
            if dlink_premium:
                print("\n✅ SUCCESS! Premium dlink obtained!")
                print(f"\nFull dlink:\n{dlink_premium}")
            else:
                print(f"\ninfo[0] keys: {list(info[0].keys())}")
        else:
            print(f"Full response: {r3.text[:500]}")
    except Exception as e:
        print(f"JSON parse error: {e}")
        print(f"Raw: {r3.text[:300]}")

    # ─── PHASE 2b: Try /api/filemetas without cookie (compare) ───────────
    print("\n" + "="*55)
    print("PHASE 2b: /api/filemetas WITHOUT cookie (compare)")
    print("="*55)

    r4 = make_session().get(
        f"{domain}/api/filemetas",
        params={
            "app_id": "250528",
            "jsToken": js_token,
            "target": f'["{path}"]',
            "dlink": "1",
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/disk/home",
        },
        timeout=12
    )
    print(f"Status: {r4.status_code}")
    print(f"Response: {r4.text[:300]}")


if __name__ == "__main__":
    test_full_flow()
