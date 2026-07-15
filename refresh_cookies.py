import os
import re
import sys
import json
import asyncio
import argparse
from dotenv import load_dotenv
import httpx
from playwright.async_api import async_playwright

# Reconfigure stdout to use UTF-8 on Windows to prevent encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Parse command line arguments
parser = argparse.ArgumentParser(description="TeraBox Cookie Refresher")
parser.add_argument("--headless", action="store_true", help="Run the browser in headless mode")
args = parser.parse_args()

# Configuration Paths
WORKSPACE_DIR = r"c:\Users\anshu\OneDrive\Documents\diskwala new latest"
PARENT_DIR = r"c:\Users\anshu\OneDrive\Documents"

# Load credentials from root .env
load_dotenv(os.path.join(WORKSPACE_DIR, ".env"))
USER_EMAIL = os.getenv("TERABOX_EMAIL")
USER_PASS = os.getenv("TERABOX_PASSWORD")

# Destination Paths to Update
TARGET_PATHS = {
    "az_dotenv": os.path.join(WORKSPACE_DIR, "aztearboxdl", ".env"),
    "tera_dotenv": os.path.join(WORKSPACE_DIR, "TeraBox-Dl", ".env"),
    "tera_py": os.path.join(WORKSPACE_DIR, "TeraBox-Dl", "terabox.py"),
    "fap1_dotenv": os.path.join(PARENT_DIR, "AZ NETWORK TG BOTS", "faphouse_bots", "faphouse1", ".env"),
    "fap2_dotenv": os.path.join(PARENT_DIR, "AZ NETWORK TG BOTS", "faphouse_bots", "faphouse2", ".env"),
    "fap3_dotenv": os.path.join(PARENT_DIR, "AZ NETWORK TG BOTS", "faphouse_bots", "faphouse3", ".env"),
    "faphouse_cookies_txt": os.path.join(PARENT_DIR, "AZ NETWORK TG BOTS", "faphouse_cookies.txt"),
}

async def verify_ndus(ndus):
    """Verify if the ndus cookie is currently valid."""
    if not ndus:
        return False
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Cookie": f"ndus={ndus}"
    }
    
    # Try multiple domains to accommodate regional redirects
    test_urls = [
        "https://dm.1024terabox.com/api/list?dir=%2F&num=10&page=1",
        "https://www.terabox.app/api/list?dir=%2F&num=10&page=1",
        "https://www.1024terabox.com/api/list?dir=%2F&num=10&page=1"
    ]
    
    try:
        async with httpx.AsyncClient() as client:
            for url in test_urls:
                try:
                    response = await client.get(url, headers=headers, timeout=10.0)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("errno") == 0:
                            return True
                except Exception:
                    pass
    except Exception:
        pass
        
    return False

def update_env_variable(env_path, key, value):
    """Update a specific key-value pair in a .env file."""
    if not os.path.exists(env_path):
        return False
    
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    new_lines = []
    updated = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)
            
    if not updated:
        new_lines.append(f"{key}={value}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return True

def update_files(new_ndus):
    """Propagate the new ndus cookie to all required target configurations."""
    print("[INFO] Propagating new cookie to all bots...")
    
    # 1. Update aztearboxdl/.env
    if update_env_variable(TARGET_PATHS["az_dotenv"], "NDUS_COOKIE", new_ndus):
        print("[SUCCESS] Updated aztearboxdl/.env")
        
    # 2. Update TeraBox-Dl/.env
    if update_env_variable(TARGET_PATHS["tera_dotenv"], "COOKIE_JSON", f'{{"ndus": "{new_ndus}"}}'):
        print("[SUCCESS] Updated TeraBox-Dl/.env")
        
    # 3. Update TeraBox-Dl/terabox.py (hardcoded cookie)
    py_path = TARGET_PATHS["tera_py"]
    if os.path.exists(py_path):
        with open(py_path, "r", encoding="utf-8") as f:
            py_content = f.read()
        pattern = r'("ndus":\s*")[a-zA-Z0-9_-]+(")'
        new_content = re.sub(pattern, rf'\1{new_ndus}\2', py_content)
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("[SUCCESS] Updated TeraBox-Dl/terabox.py")
        
    # 4. Update faphouse bots .env files
    for key in ["fap1_dotenv", "fap2_dotenv", "fap3_dotenv"]:
        if update_env_variable(TARGET_PATHS[key], "NDUS_COOKIE", new_ndus):
            print(f"[SUCCESS] Updated {os.path.basename(os.path.dirname(TARGET_PATHS[key]))}/.env")
            
    # 5. Update faphouse_cookies.txt
    txt_path = TARGET_PATHS["faphouse_cookies_txt"]
    if os.path.exists(txt_path) or os.path.exists(os.path.dirname(txt_path)):
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"{new_ndus}\n")
        print("[SUCCESS] Updated faphouse_cookies.txt")

async def perform_autologin():
    """Launch Playwright browser, type credentials, detect captcha and wait for manual solution."""
    async with async_playwright() as p:
        user_data_dir = os.path.join(WORKSPACE_DIR, ".terabox_session")
        print(f"[INFO] Launching Chromium (headless={args.headless}) using profile {user_data_dir}...")
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=args.headless,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        # 1. Check if the saved context session is already logged in
        try:
            cookies = await context.cookies()
            ndus_val = next((c["value"] for c in cookies if c["name"] == "ndus"), None)
            if ndus_val and await verify_ndus(ndus_val):
                print("[SUCCESS] Saved browser session is already active and valid!")
                await context.close()
                return ndus_val
        except Exception:
            pass
            
        # 2. Perform Login Flow
        print("[INFO] Navigating to TeraBox...")
        await page.goto("https://www.terabox.com/", wait_until="domcontentloaded")
        
        try:
            login_btn = page.locator(".login-btn").first
            await login_btn.wait_for(state="visible", timeout=10000)
            await login_btn.click()
            await page.wait_for_timeout(2000)
        except Exception:
            pass
            
        print("[INFO] Opening Email login dialog...")
        try:
            email_logo = page.locator(".other-item .logo").nth(1)
            await email_logo.wait_for(state="visible", timeout=5000)
            await email_logo.click()
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[ERROR] Could not click email tab logo: {e}")
            screenshot_path = os.path.join(WORKSPACE_DIR, "debug_screenshot.png")
            await page.screenshot(path=screenshot_path)
            print(f"[DEBUG] Saved debug screenshot to {screenshot_path}")
            await context.close()
            return None
            
        print("[INFO] Filling email and password...")
        try:
            await page.locator("input[placeholder*='email']").first.fill(USER_EMAIL)
            await page.locator("input[type='password']").first.fill(USER_PASS)
            await page.wait_for_timeout(500)
            
            await page.locator(".btn-class-login").first.click()
            print("[INFO] Credentials submitted. Waiting for authentication...")
            await page.wait_for_timeout(4000)
        except Exception as e:
            print(f"[ERROR] Failed to input login credentials: {e}")
            screenshot_path = os.path.join(WORKSPACE_DIR, "debug_screenshot.png")
            await page.screenshot(path=screenshot_path)
            print(f"[DEBUG] Saved debug screenshot to {screenshot_path}")
            await context.close()
            return None
            
        # 3. Handle CAPTCHA / verification puzzle
        captcha_input = page.locator("input[placeholder*='verification code']")
        if await captcha_input.count() > 0 or "verification" in page.url.lower():
            print("\n[WARNING] CAPTCHA / Puzzle challenge detected!")
            
            if args.headless:
                print("[ERROR] Headless mode is active. Cannot display browser window to solve CAPTCHA.")
                print("[INFO] Please run the script in HEADFUL mode (without --headless) to solve it once.")
                await context.close()
                return None
                
            print("[ACTION REQUIRED] Please solve the puzzle/captcha in the open browser window.")
            print("[INFO] Waiting up to 60 seconds for you to solve the CAPTCHA...")
            
            # Poll cookies for up to 60 seconds
            found_cookie = None
            for attempt in range(60):
                try:
                    cookies = await context.cookies()
                    ndus_val = next((c["value"] for c in cookies if c["name"] == "ndus"), None)
                    if ndus_val and await verify_ndus(ndus_val):
                        found_cookie = ndus_val
                        break
                except Exception:
                    print("[INFO] Browser window closed by user.")
                    break
                await asyncio.sleep(1)
                
            if not found_cookie:
                screenshot_path = os.path.join(WORKSPACE_DIR, "debug_screenshot.png")
                await page.screenshot(path=screenshot_path)
                print(f"[DEBUG] Saved debug screenshot to {screenshot_path}")
            await context.close()
            return found_cookie
            
        # 4. Success verification (if no captcha was triggered)
        cookies = await context.cookies()
        ndus_val = next((c["value"] for c in cookies if c["name"] == "ndus"), None)
        if ndus_val and await verify_ndus(ndus_val):
            await context.close()
            return ndus_val
            
        screenshot_path = os.path.join(WORKSPACE_DIR, "debug_screenshot.png")
        await page.screenshot(path=screenshot_path)
        print(f"[DEBUG] Saved debug screenshot to {screenshot_path}")
        await context.close()
        return None

async def main():
    print("--- TeraBox Auto-Login & Cookie Refresh Utility ---")
    if not USER_EMAIL or not USER_PASS:
        print("[ERROR] Credentials not found in .env. Please set TERABOX_EMAIL and TERABOX_PASSWORD.")
        sys.exit(1)
        
    # Check if current cookie is still valid
    # Try reading from aztearboxdl/.env first
    current_ndus = None
    if os.path.exists(TARGET_PATHS["az_dotenv"]):
        with open(TARGET_PATHS["az_dotenv"], "r") as f:
            content = f.read()
        match = re.search(r"NDUS_COOKIE=(.*)", content)
        if match:
            current_ndus = match.group(1).strip()
            
    print("[INFO] Verifying current session cookie...")
    if await verify_ndus(current_ndus):
        print("[SUCCESS] Current cookie is already valid! Synchronizing configs just in case...")
        update_files(current_ndus)
        return
        
    print("[INFO] Cookie is invalid or expired. Initializing automated login...")
    new_ndus = await perform_autologin()
    
    if new_ndus:
        print("[SUCCESS] Successfully logged in and retrieved valid ndus cookie!")
        update_files(new_ndus)
    else:
        print("[ERROR] Failed to login or retrieve valid ndus cookie.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
