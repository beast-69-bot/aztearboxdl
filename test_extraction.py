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
        
    # Let curl_cffi handle User-Agent matching the TLS fingerprint
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cookie": cookie_header
    }

    domains = [
        "https://dm.1024tera.com",
        "https://dm.terabox.com"
    ]

    for domain in domains:
        print("\n" + "="*50)
        url = f"{domain}/sharing/link?surl={surl}"
        
        # Test 1: Chrome 110 impersonate
        print(f"Testing Chrome 110 Impersonation on: {url}")
        session = curl_requests.Session(impersonate="chrome110")
        if STATIC_PROXY:
            session.proxies = format_curl_proxy(STATIC_PROXY)
        try:
            resp = session.get(url, headers=headers, timeout=8, allow_redirects=True)
            print(f"User-Agent sent: {resp.request.headers.get('User-Agent')}")
            print(f"Status: {resp.status_code}")
            print("Response Text (first 500 chars):")
            print(resp.text[:500])
        except Exception as e:
            print(f"Request failed: {e}")
            
        # Test 2: Chrome 120 impersonate
        print("-"*50)
        print(f"Testing Chrome 120 Impersonation on: {url}")
        session = curl_requests.Session(impersonate="chrome120")
        if STATIC_PROXY:
            session.proxies = format_curl_proxy(STATIC_PROXY)
        try:
            resp = session.get(url, headers=headers, timeout=8, allow_redirects=True)
            print(f"User-Agent sent: {resp.request.headers.get('User-Agent')}")
            print(f"Status: {resp.status_code}")
            print("Response Text (first 500 chars):")
            print(resp.text[:500])
        except Exception as e:
            print(f"Request failed: {e}")
            
        # Test 2: Manually requesting with clearCache=1
        print("-"*50)
        cache_url = f"{domain}/sharing/link?surl={surl}&clearCache=1"
        print(f"Testing manual clearCache: {cache_url}")
        session = curl_requests.Session(impersonate="chrome110")
        if STATIC_PROXY:
            session.proxies = format_curl_proxy(STATIC_PROXY)
        try:
            resp = session.get(cache_url, headers=headers, timeout=8, allow_redirects=True)
            print(f"Final URL: {resp.url}")
            print(f"Status: {resp.status_code}")
            print("Response Text (first 500 chars):")
            print(resp.text[:500])
        except Exception as e:
            print(f"Request failed: {e}")

if __name__ == "__main__":
    test_extract()
