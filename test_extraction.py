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
    proxy_str = proxy_str.strip()
    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        formatted = f"http://{user}:{pwd}@{ip}:{port}"
    else:
        if not proxy_str.startswith("http://") and not proxy_str.startswith("https://"):
            formatted = f"http://{proxy_str}"
        else:
            formatted = proxy_str
    return {"http": formatted, "https": formatted}


def make_session(with_proxy=True):
    session = curl_requests.Session(impersonate="chrome110")
    if with_proxy and STATIC_PROXY:
        session.proxies = format_curl_proxy(STATIC_PROXY)
    return session


def test_extract():
    surl = "6j9ZbdrBAAL6qvL70yPO2A"
    domain = "https://dm.1024tera.com"

    print(f"surl: {surl} | domain: {domain}")

    # Load cookie
    cookie_header = ""
    for path in ["terabox_cookie_header.txt", "../terabox_cookie_header.txt"]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cookie_header = f.read().strip()
            break
    if not cookie_header and NDUS_COOKIE:
        cookie_header = f"ndus={NDUS_COOKIE}"

    # ── STEP 1: Anonymous HTML → jsToken ─────────────────────────────────
    print("\n" + "="*60)
    print("STEP 1: Fetch HTML anonymously → extract jsToken")
    print("="*60)

    html_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    resp = make_session().get(
        f"{domain}/sharing/link?surl={surl}",
        headers=html_headers, timeout=15, allow_redirects=True
    )
    html = resp.text
    print(f"HTML Status: {resp.status_code}, Length: {len(html)}")

    js_token = None
    for pat in [r'fn%28%22([^%]+)%22%29', r'jsToken\s*=\s*["\']([^"\']+)["\']', r'"jsToken"\s*:\s*"([^"]+)"']:
        m = re.search(pat, html)
        if m:
            js_token = m.group(1)
            print(f"jsToken: {js_token[:50]}...")
            break

    if not js_token:
        print("ERROR: jsToken not found!")
        return

    # ── STEP 2: Anonymous /share/list → FULL RESPONSE ────────────────────
    print("\n" + "="*60)
    print("STEP 2: Anonymous /share/list → FULL response")
    print("="*60)

    api_headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{domain}/sharing/link?surl={surl}",
    }
    share_url = f"{domain}/share/list?app_id=250528&root=1&shorturl={surl}&jsToken={js_token}"

    resp2 = make_session().get(share_url, headers=api_headers, timeout=12)
    print(f"Status: {resp2.status_code}")

    try:
        data = resp2.json()
        print(f"errno: {data.get('errno')}")
        print(f"title: {data.get('title')}")
        files = data.get("list", [])
        print(f"Files found: {len(files)}")

        for i, f in enumerate(files[:3]):
            print(f"\n  File [{i}]:")
            print(f"    name:   {f.get('server_filename')}")
            print(f"    size:   {int(f.get('size', 0)) / 1024 / 1024:.1f} MB")
            print(f"    fs_id:  {f.get('fs_id')}")
            print(f"    dlink:  {f.get('dlink', 'NOT FOUND')}")
            print(f"    path:   {f.get('path')}")

        # also print any top-level keys we haven't seen
        print(f"\n  Top-level keys: {list(data.keys())}")
        print(f"\n  Full first file entry:\n{json.dumps(files[0], indent=2)}" if files else "")

    except Exception as e:
        print(f"JSON parse error: {e}")
        print(resp2.text[:1000])

    # ── STEP 3: Get dlink via /share/download with cookie ─────────────────
    print("\n" + "="*60)
    print("STEP 3: Try /share/download API with cookie to get premium dlink")
    print("="*60)

    if files and files[0].get("fs_id"):
        fs_id = files[0]["fs_id"]
        # Try the fileinfo/download endpoint with cookie
        dl_headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{domain}/sharing/link?surl={surl}",
            "Cookie": cookie_header,
        }
        dl_url = (
            f"{domain}/api/shorturlinfo"
            f"?app_id=250528"
            f"&shorturl={surl}"
            f"&jsToken={js_token}"
        )
        resp3 = make_session().get(dl_url, headers=dl_headers, timeout=12)
        print(f"shorturlinfo Status: {resp3.status_code}")
        print(f"Response: {resp3.text[:400]}")

        # Also try filemetas endpoint
        print("\n--- Trying /api/filemetas ---")
        meta_url = (
            f"{domain}/api/filemetas"
            f"?app_id=250528"
            f"&target=%5B%22{files[0].get('path', '').replace('/', '%2F')}%22%5D"
            f"&dlink=1"
            f"&jsToken={js_token}"
        )
        resp4 = make_session().get(meta_url, headers=dl_headers, timeout=12)
        print(f"filemetas Status: {resp4.status_code}")
        print(f"Response: {resp4.text[:600]}")
    else:
        print("No fs_id available to test download endpoint.")


if __name__ == "__main__":
    test_extract()
