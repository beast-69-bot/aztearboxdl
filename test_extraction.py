import os
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


def make_session():
    session = curl_requests.Session(impersonate="chrome110")
    if STATIC_PROXY:
        session.proxies = format_curl_proxy(STATIC_PROXY)
    return session


def do_get(label, session, url, headers):
    print(f"\n  [{label}]")
    print(f"  URL: {url}")
    try:
        resp = session.get(url, headers=headers, timeout=12, allow_redirects=True)
        print(f"  Status: {resp.status_code}")
        print(f"  Response: {resp.text[:400]}")
        return resp
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def test_extract():
    surl = "6j9ZbdrBAAL6qvL70yPO2A"

    # Load full cookie header
    cookie_header = ""
    paths = ["terabox_cookie_header.txt", "../terabox_cookie_header.txt"]
    for path in paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cookie_header = f.read().strip()
            break

    if cookie_header:
        print(f"[OK] Loaded full cookie header. Length: {len(cookie_header)}")
    else:
        cookie_header = f"ndus={NDUS_COOKIE}" if NDUS_COOKIE else ""
        print("[WARN] Falling back to ndus only cookie")

    if STATIC_PROXY:
        print(f"[OK] Using proxy: {STATIC_PROXY[:30]}...")
    else:
        print("[WARN] No proxy configured")

    # ─── BASE HEADERS (no cookie) ───────────────────────────────────────────
    base_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
    }
    auth_headers = {**base_headers, "Cookie": cookie_header}

    domains = [
        "https://dm.1024tera.com",
        "https://dm.terabox.com",
    ]

    for domain in domains:
        print("\n" + "="*60)
        print(f"DOMAIN: {domain}")
        print("="*60)

        # ── TEST 1: Anonymous (no cookie) /sharing/link ──────────────────
        print("\n--- TEST 1: Anonymous access /sharing/link ---")
        do_get("no-cookie", make_session(),
               f"{domain}/sharing/link?surl={surl}", base_headers)

        # ── TEST 2: With cookie /sharing/link ────────────────────────────
        print("\n--- TEST 2: Authenticated /sharing/link ---")
        do_get("with-cookie", make_session(),
               f"{domain}/sharing/link?surl={surl}", auth_headers)

        # ── TEST 3: With cookie + Referer /sharing/link ──────────────────
        print("\n--- TEST 3: Authenticated + Referer ---")
        headers_with_ref = {
            **auth_headers,
            "Referer": f"https://www.terabox.com/sharing/link?surl={surl}",
        }
        do_get("with-referer", make_session(),
               f"{domain}/sharing/link?surl={surl}", headers_with_ref)

        # ── TEST 4: /share/list API directly ─────────────────────────────
        print("\n--- TEST 4: /share/list API (direct JSON endpoint) ---")
        api_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
            "Cookie": cookie_header,
        }
        share_list_url = (
            f"{domain}/share/list"
            f"?app_id=250528"
            f"&shorturl={surl}"
            f"&root=1"
        )
        do_get("share/list no-jsToken", make_session(), share_list_url, api_headers)

    # ── TEST 5: NO PROXY - direct request ────────────────────────────────
    print("\n" + "="*60)
    print("TEST 5: NO PROXY (direct connection to dm.1024tera.com)")
    print("="*60)
    session_no_proxy = curl_requests.Session(impersonate="chrome110")
    # Do NOT set proxy
    do_get("no-proxy", session_no_proxy,
           f"https://dm.1024tera.com/sharing/link?surl={surl}", auth_headers)


if __name__ == "__main__":
    test_extract()
