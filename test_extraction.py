"""
TeraBox Extraction Test - Phase 3: Extract uk+shareid, get dlink
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


def extract_from_html(html: str) -> dict:
    """Extract jsToken, uk, shareid, shorturl from the HTML page."""
    result = {}

    # jsToken
    m = re.search(r'fn%28%22(.*?)%22%29', html)
    if m:
        result["js_token"] = m.group(1)

    # uk (owner user key) - various patterns
    for pat in [
        r'"uk"\s*:\s*(\d+)',
        r'uk\s*=\s*(\d+)',
        r"'uk'\s*:\s*(\d+)",
        r'&uk=(\d+)',
    ]:
        m = re.search(pat, html)
        if m and m.group(1) != "0":
            result["uk"] = m.group(1)
            break

    # shareid
    for pat in [
        r'"shareid"\s*:\s*(\d+)',
        r'share_id\s*=\s*(\d+)',
        r"shareid\s*=\s*(\d+)",
        r'&shareid=(\d+)',
    ]:
        m = re.search(pat, html)
        if m:
            result["shareid"] = m.group(1)
            break

    # shorturl / surl
    for pat in [
        r'"shorturl"\s*:\s*"([^"]+)"',
        r'surl\s*=\s*"([^"]+)"',
        r"shorturl\s*=\s*'([^']+)'",
    ]:
        m = re.search(pat, html)
        if m:
            result["shorturl"] = m.group(1)
            break

    return result


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

    print(f"Cookie length: {len(cookie_header)} | Proxy: {STATIC_PROXY[:20] if STATIC_PROXY else 'None'}...")

    # ─── STEP 1: Anonymous HTML → extract ALL params ──────────────────────
    print("\n" + "="*55)
    print("STEP 1: Anonymous HTML → extract jsToken, uk, shareid")
    print("="*55)

    r = make_session().get(
        f"{domain}/sharing/link?surl={surl}",
        headers={"Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"},
        timeout=15, allow_redirects=True
    )
    print(f"Status: {r.status_code} | HTML: {len(r.text)} chars")

    params = extract_from_html(r.text)
    js_token = params.get("js_token", "")
    uk = params.get("uk", "")
    shareid = params.get("shareid", "")
    shorturl = params.get("shorturl", surl)

    print(f"jsToken:  {'✅ ' + js_token[:40] + '...' if js_token else '❌ NOT FOUND'}")
    print(f"uk:       {'✅ ' + uk if uk else '❌ NOT FOUND'}")
    print(f"shareid:  {'✅ ' + shareid if shareid else '❌ NOT FOUND'}")
    print(f"shorturl: {shorturl}")

    # Print raw HTML sections with these keywords for debugging
    if not uk:
        print("\n  Searching HTML for 'uk':")
        for kw in ['"uk"', "'uk'", 'uk=',' uk:']:
            idx = r.text.find(kw)
            if idx >= 0:
                print(f"    Found '{kw}' at {idx}: ...{r.text[idx:idx+80]}...")
                break

    if not shareid:
        print("\n  Searching HTML for 'shareid':")
        for kw in ['"shareid"', 'shareid=', 'share_id']:
            idx = r.text.find(kw)
            if idx >= 0:
                print(f"    Found '{kw}' at {idx}: ...{r.text[idx:idx+80]}...")
                break

    if not js_token:
        print("ERROR: jsToken not found. Cannot continue.")
        return

    # ─── STEP 2: /share/list WITH uk+shareid (anonymous) ─────────────────
    print("\n" + "="*55)
    print("STEP 2: /share/list + uk + shareid (anonymous, no cookie)")
    print("="*55)

    list_params = {
        "app_id": "250528",
        "jsToken": js_token,
        "shorturl": shorturl,
        "root": "1",
    }
    if uk:
        list_params["uk"] = uk
    if shareid:
        list_params["shareid"] = shareid

    print(f"Params: {list(list_params.keys())}")

    r2 = make_session().get(
        f"{domain}/share/list",
        params=list_params,
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
        },
        timeout=12
    )

    try:
        d2 = r2.json()
        errno = d2.get("errno")
        print(f"errno: {errno}")
        print(f"top-level keys: {list(d2.keys())}")
        # Show uk/shareid from response top level
        print(f"uk in resp:      {d2.get('uk', 'NOT FOUND')}")
        print(f"shareid in resp: {d2.get('shareid', 'NOT FOUND')}")

        items = d2.get("list", [])
        if items:
            item = items[0]
            dlink = item.get("dlink", "")
            print(f"\nFile: {item.get('server_filename')}")
            print(f"Size: {int(item.get('size',0))/1024/1024:.1f} MB")
            print(f"dlink: {'✅ ' + dlink[:70] if dlink else '❌ NOT in response'}")
            print(f"\nAll keys in item: {list(item.keys())}")
    except Exception as e:
        print(f"Parse error: {e}")
        print(r2.text[:300])

    # ─── STEP 3: Try /api/sharedownload endpoint ──────────────────────────
    print("\n" + "="*55)
    print("STEP 3: /api/sharedownload with cookie + uk + shareid")
    print("="*55)

    dl_params = {
        "app_id": "250528",
        "jsToken": js_token,
        "shorturl": shorturl,
        "uk": uk or "",
        "shareid": shareid or "",
        "sign": "",
        "timestamp": "",
        "product": "share",
        "nozip": "0",
    }

    r3 = make_session().get(
        f"{domain}/api/sharedownload",
        params=dl_params,
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{domain}/sharing/link?surl={surl}",
            "Cookie": cookie_header,
        },
        timeout=12
    )
    print(f"Status: {r3.status_code}")
    print(f"Response: {r3.text[:500]}")

    # ─── STEP 4: Try /share/list response top-level for shareid/uk ────────
    print("\n" + "="*55)
    print("STEP 4: Raw first 1000 chars of /share/list response")
    print("="*55)
    print(r2.text[:1000])


if __name__ == "__main__":
    test_full_flow()
