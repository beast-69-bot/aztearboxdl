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

def test_extract():
    surl = "6j9ZbdrBAAL6qvL70yPO2A"
    session = curl_requests.Session(impersonate="chrome110")
    
    # Load cookie header
    cookie_header = ""
    paths = ["terabox_cookie_header.txt", "../terabox_cookie_header.txt"]
    for path in paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cookie_header = f.read().strip()
                break
                
    if cookie_header:
        print(f"Loaded cookie header from txt file. Length: {len(cookie_header)}")
    else:
        cookie_header = f"ndus={NDUS_COOKIE}"
        print("Falling back to ndus environment variable")
        
    if STATIC_PROXY:
        session.proxies = format_curl_proxy(STATIC_PROXY)
        print(f"Using proxy: {STATIC_PROXY}")
    else:
        print("Using direct connection")
        
    url = f"https://dm.1024tera.com/sharing/link?surl={surl}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cookie": cookie_header
    }
    
    print(f"GET: {url}")
    resp = session.get(url, headers=headers, allow_redirects=False)
    print(f"Status: {resp.status_code}")
    print("Headers:")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
    
    print("\nResponse Text (first 2000 chars):")
    print(resp.text[:2000])

if __name__ == "__main__":
    test_extract()
