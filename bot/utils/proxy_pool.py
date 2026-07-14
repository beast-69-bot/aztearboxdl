import re
from curl_cffi import requests as curl_requests

# A simple list of fallback free proxy providers to try when IP is throttled
FREE_PROXY_LISTS = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt"
]

def fetch_fresh_proxies() -> list:
    """Fetches a list of fresh proxies to bypass IP blocks."""
    proxies = []
    session = curl_requests.Session(impersonate="chrome110")
    for url in FREE_PROXY_LISTS:
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                # Extract ip:port format
                found = re.findall(r"(\d+\.\d+\.\d+\.\d+:\d+)", resp.text)
                proxies.extend(found)
        except Exception:
            continue
    # Keep unique list
    return list(set(proxies))

def get_proxy_dict(proxy_str: str) -> dict:
    """Format proxy string to curl_cffi proxy dict structure."""
    if not proxy_str:
        return {}
    
    # Try SOCKS5 first, then fallback to HTTP
    if "socks5" in proxy_str.lower():
        clean_proxy = proxy_str.lower()
    elif "http" in proxy_str.lower():
        clean_proxy = proxy_str.lower()
    else:
        clean_proxy = f"http://{proxy_str}"
        
    return {
        "http": clean_proxy,
        "https": clean_proxy
    }
