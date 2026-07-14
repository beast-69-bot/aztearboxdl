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

first_url = "https://www.1024tera.com/sharing/link?surl=nB0iE2tirouodSxPwQCH2g"
response = session.get(first_url, headers=HEADERS, timeout=12)

print("Status Code:", response.status_code)
print("Final URL:", response.url)

# Print if target strings are in response
print("'need verify' in text:", "need verify" in response.text.lower())
print("'errno' in text:", "errno" in response.text.lower())

# Look for fn() jsToken pattern
match = re.search(r'fn%28%22(.*?)%22%29', response.text)
if match:
    print("Found jsToken:", match.group(1))
else:
    print("jsToken fn() pattern not found.")

# Look for errno pattern
err_match = re.findall(r'"errno":\s*\d+', response.text)
print("Found errno occurrences:", err_match)

# Print a snippet of response text around where 'need verify' might be, if present
if "need verify" in response.text.lower():
    idx = response.text.lower().index("need verify")
    print("Snippet around 'need verify':", response.text[max(0, idx-100):min(len(response.text), idx+100)])
