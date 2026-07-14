import re
from curl_cffi import requests as curl_requests

NDUS_COOKIE = "Yzdw9XNpeHuiBzA-tBVQH3_0RU0qwhsyioPsG2x6"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

session = curl_requests.Session(impersonate="chrome110")
session.cookies.update({"ndus": NDUS_COOKIE})

# Link 1: The one that works (check link)
url_working = "https://www.1024tera.com/sharing/link?surl=tKDPsB5RNnjdWLwoLcCFyg"
# Link 2: The one that triggers verify wall
url_failing = "https://www.1024tera.com/sharing/link?surl=nB0iE2tirouodSxPwQCH2g"

def test_link(url, name):
    print(f"\n--- Testing {name} ---")
    try:
        resp = session.get(url, headers=HEADERS, timeout=12)
        print("Status Code:", resp.status_code)
        print("Final URL:", resp.url)
        
        # Check jsToken fn() pattern
        match = re.search(r'fn%28%22(.*?)%22%29', resp.text)
        if match:
            print("Found jsToken:", match.group(1))
        else:
            print("jsToken fn() pattern not found.")
            
        # Find 'needVerify' variable in JS
        need_verify_matches = re.findall(r'var\s+needVerify\s*=\s*(true|false)', resp.text)
        print("needVerify value in JS:", need_verify_matches)
        
    except Exception as e:
        print("Error:", type(e).__name__, str(e))

test_link(url_working, "Working Link")
test_link(url_failing, "Failing Link")
