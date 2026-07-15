import os
import re
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


def test_extract():
    surl = "6j9ZbdrBAAL6qvL70yPO2A"
    domain = "https://dm.1024tera.com"

    print(f"Testing surl: {surl}")
    print(f"Domain: {domain}")
    if STATIC_PROXY:
        print(f"Proxy: {STATIC_PROXY[:30]}...")

    # ── STEP 1: Anonymous HTML request ────────────────────────────────────
    print("\n" + "="*60)
    print("STEP 1: Fetch HTML page (NO cookie, anonymous)")
    print("="*60)

    html_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
    }

    html = None
    session = make_session()
    url = f"{domain}/sharing/link?surl={surl}"
    try:
        resp = session.get(url, headers=html_headers, timeout=15, allow_redirects=True)
        print(f"Status: {resp.status_code}")
        html = resp.text
        print(f"HTML length: {len(html)} chars")
        print(f"First 300 chars:\n{html[:300]}")
    except Exception as e:
        print(f"ERROR: {e}")
        return

    if not html or len(html) < 100:
        print("ERROR: Got no HTML. Aborting.")
        return

    # ── STEP 2: Extract jsToken from HTML ─────────────────────────────────
    print("\n" + "="*60)
    print("STEP 2: Extract jsToken from HTML")
    print("="*60)

    js_token = None
    patterns = [
        r'jsToken\s*=\s*["\']([^"\']+)["\']',
        r'"jsToken"\s*:\s*"([^"]+)"',
        r'fn%28%22([^%]+)%22%29',
        r'encodeURIComponent\("([^"]+)"\)',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            js_token = m.group(1)
            print(f"Found jsToken via pattern [{pat[:40]}...]:")
            print(f"  jsToken = {js_token[:60]}...")
            break

    if not js_token:
        print("WARNING: jsToken NOT found in HTML!")
        # Print relevant sections for debugging
        for keyword in ["jsToken", "token", "js_token", "__NEXT_DATA__", "initialState"]:
            idx = html.lower().find(keyword.lower())
            if idx >= 0:
                print(f"\n  Found '{keyword}' at pos {idx}:")
                print(f"  ...{html[max(0,idx-30):idx+100]}...")
                break
    else:
        print(f"OK! jsToken extracted.")

    # ── STEP 3: Extract shorturl from HTML ────────────────────────────────
    print("\n" + "="*60)
    print("STEP 3: Extract shorturl from HTML")
    print("="*60)

    shorturl = None
    short_patterns = [
        r'"shorturl"\s*:\s*"([^"]+)"',
        r'shorturl["\s]*[:=]["\s]*["\']([^"\']+)["\']',
        r'share_id["\s]*[:=]["\s]*["\']([^"\']+)["\']',
    ]
    for pat in short_patterns:
        m = re.search(pat, html)
        if m:
            shorturl = m.group(1)
            print(f"Found shorturl: {shorturl}")
            break

    if not shorturl:
        shorturl = surl  # fallback to the original surl
        print(f"WARNING: shorturl not found, using surl as fallback: {shorturl}")

    # ── STEP 4: Try /share/list WITHOUT cookie ────────────────────────────
    print("\n" + "="*60)
    print("STEP 4: /share/list WITHOUT cookie (anonymous)")
    print("="*60)

    api_headers_anon = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{domain}/sharing/link?surl={surl}",
    }

    share_list_url = f"{domain}/share/list?app_id=250528&root=1&shorturl={shorturl}"
    if js_token:
        share_list_url += f"&jsToken={js_token}"

    session2 = make_session()
    try:
        resp2 = session2.get(share_list_url, headers=api_headers_anon, timeout=12)
        print(f"Status: {resp2.status_code}")
        print(f"Response: {resp2.text[:600]}")
    except Exception as e:
        print(f"ERROR: {e}")

    # ── STEP 5: Try /share/list WITH cookie ──────────────────────────────
    print("\n" + "="*60)
    print("STEP 5: /share/list WITH cookie (authenticated)")
    print("="*60)

    cookie_header = ""
    for path in ["terabox_cookie_header.txt", "../terabox_cookie_header.txt"]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cookie_header = f.read().strip()
            break
    if not cookie_header and NDUS_COOKIE:
        cookie_header = f"ndus={NDUS_COOKIE}"

    api_headers_auth = {**api_headers_anon, "Cookie": cookie_header}
    session3 = make_session()
    try:
        resp3 = session3.get(share_list_url, headers=api_headers_auth, timeout=12)
        print(f"Status: {resp3.status_code}")
        print(f"Response: {resp3.text[:600]}")
    except Exception as e:
        print(f"ERROR: {e}")

    # ── STEP 6: Extract dlink directly from HTML ──────────────────────────
    print("\n" + "="*60)
    print("STEP 6: Look for dlink / download URL directly in HTML")
    print("="*60)

    dlink_patterns = [
        r'"dlink"\s*:\s*"([^"]+)"',
        r'"uk"\s*:\s*(\d+)',
        r'"fs_id"\s*:\s*(\d+)',
        r'"server_filename"\s*:\s*"([^"]+)"',
        r'"size"\s*:\s*(\d+)',
    ]
    found_any = False
    for pat in dlink_patterns:
        m = re.search(pat, html)
        if m:
            print(f"  [{pat[:35]}] => {m.group(1)[:80]}")
            found_any = True

    if not found_any:
        print("  No dlink/file metadata found directly in HTML.")
        print("  (File info is likely loaded via XHR after page load)")

        # Print any JSON-like structure we find
        json_blocks = re.findall(r'window\.__[A-Z_]+__\s*=\s*(\{.{0,200})', html)
        for i, block in enumerate(json_blocks[:3]):
            print(f"\n  window.__VAR__[{i}]: {block[:150]}")


if __name__ == "__main__":
    test_extract()
