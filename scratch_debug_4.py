import re
from curl_cffi import requests as curl_requests

NDUS_COOKIE = "Yzdw9XNpeHuiBzA-tBVQH3_0RU0qwhsyioPsG2x6"

# Real standard chrome UA
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def test_with_impersonate(impersonation):
    session = curl_requests.Session(impersonate=impersonation)
    session.cookies.update({"ndus": NDUS_COOKIE})
    url = "https://www.1024tera.com/sharing/link?surl=nB0iE2tirouodSxPwQCH2g"
    print(f"\nTesting with impersonate={impersonation}")
    try:
        resp = session.get(url, headers=HEADERS, timeout=12)
        match = re.search(r'fn%28%22(.*?)%22%29', resp.text)
        need_verify_matches = re.findall(r'var\s+needVerify\s*=\s*(true|false)', resp.text)
        print("Final URL:", resp.url)
        print("jsToken:", match.group(1) if match else "Not found")
        print("needVerify:", need_verify_matches)
    except Exception as e:
        print("Error:", str(e))

test_with_impersonate("chrome110")
test_with_impersonate("chrome120")
test_with_impersonate("safari15_5")
