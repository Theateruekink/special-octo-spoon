import json
import sys
import time
import datetime
import pyotp
from playwright.sync_api import sync_playwright

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def deploy_account(account):
    email = account["email"]
    password = account["password"]
    totp_secret = account["totp_secret"]
    config = load_config()
    model = config["model"]

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Starting deployment for: {email}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 1. Open main page to handle cookies
        print("Navigating to base URL for cookies...")
        page.goto("https://build.nvidia.com/", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # 2. Reject cookies
        try:
            cookie_selector = "#onetrust-reject-all-handler"
            page.wait_for_selector(cookie_selector, timeout=5000)
            page.wait_for_timeout(1000)
            page.click(cookie_selector)
            print("Cookies rejected.")
            page.wait_for_timeout(3000)
        except Exception:
            pass

        # 3. Open login modal URL
        print("Navigating to login modal...")
        page.goto("https://build.nvidia.com/?modal=signin", wait_until="networkidle")
        page.wait_for_timeout(4000)

        # 4. Fill email
        print("Entering email...")
        email_input_sel = "#email > div > input"
        page.wait_for_selector(email_input_sel, timeout=15000)
        page.fill(email_input_sel, email)
        page.wait_for_timeout(1000)

        # 5. Submit email
        print("Submitting email...")
        selectors_to_try = [
            "div[id^='radix-'] button",
            "button:has-text('Continue')",
            "button:has-text('Next')",
            "button:has-text('Sign In')",
            "#radix-_r_c_ > div > div > div.flex.flex-col.gap-sm > div.flex.flex-row.items-end.justify-between.gap-sm > button"
        ]
        clicked = False
        for sel in selectors_to_try:
            try:
                page.wait_for_selector(sel, timeout=3000)
                page.click(sel)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            raise Exception("Failed to click email submit button.")

        # 6. Fill password
        print("Entering password...")
        password_input_sel = "#signinPassword"
        page.wait_for_selector(password_input_sel, timeout=20000)
        page.wait_for_timeout(1500)
        page.fill(password_input_sel, password)
        page.wait_for_timeout(1000)

        # 7. Submit password
        print("Submitting password...")
        password_submit_sel = "#passwordLoginButton"
        page.wait_for_selector(password_submit_sel, timeout=15000)
        page.click(password_submit_sel)

        # 8. Select 2FA method
        print("Selecting 2FA...")
        two_fa_select_sel = "#nfactorPromptChallenge_list_0 > span > span > div > h4"
        page.wait_for_selector(two_fa_select_sel, timeout=20000)
        page.wait_for_timeout(1500)
        page.click(two_fa_select_sel)

        # 9. Enter TOTP
        print("Generating TOTP code...")
        totp = pyotp.TOTP(totp_secret.replace(" ", ""))
        code = totp.now()
        print(f"Generated 2FA code: {code}")

        code_input_sel = "#code_input"
        page.wait_for_selector(code_input_sel, timeout=15000)
        page.wait_for_timeout(1500)
        page.fill(code_input_sel, code)
        page.wait_for_timeout(1000)

        # 10. Submit TOTP
        print("Submitting 2FA...")
        submit_code_sel = "#submit_code_btn"
        page.wait_for_selector(submit_code_sel, timeout=15000)
        page.click(submit_code_sel)

        print("Waiting 10 seconds for login redirects to settle...")
        page.wait_for_timeout(10000)

        # 11. Go to models page
        print("Navigating to community models page...")
        try:
            page.goto("https://build.nvidia.com/models/community", timeout=45000)
        except Exception as e:
            print(f"Navigation warning (non-fatal): {e}")
        page.wait_for_timeout(5000)

        # 12. Search for the model
        print(f"Searching for model: {model}")
        search_container_sel = "#main-content > div > div > div > div > div.flex.flex-1.justify-center > div > div > div.flex.flex-1.flex-col.gap-0.sm\\:flex-row.sm\\:items-center.sm\\:gap-4 > div.flex-1"
        page.wait_for_selector(search_container_sel, timeout=30000)
        
        search_input = page.locator(search_container_sel).locator("input")
        search_input.wait_for(timeout=10000)
        search_input.fill(model)
        page.wait_for_timeout(3000)

        # 13. Select matching model in dropdown
        print("Selecting model from dropdown...")
        dropdown_selector = "div.text-md"
        page.wait_for_selector(dropdown_selector, timeout=15000)
        elements = page.query_selector_all(dropdown_selector)
        
        matched = False
        for elem in elements:
            text_content = elem.inner_text().strip()
            lines = [line.strip() for line in text_content.split("\n")]
            if model in lines or text_content == model:
                elem.click()
                matched = True
                break
        if not matched:
            raise Exception("Model exact match not found in dropdown.")

        # 14. Click Launch
        print("Clicking Launch button...")
        page.wait_for_timeout(1000)
        launch_selectors = [
            "#main-content > div > div > div > div > div.flex.flex-1.justify-center > div > div > div.flex.flex-1.flex-col.gap-0.sm\\:flex-row.sm\\:items-center.sm\\:gap-4 > div.mt-4.flex.flex-row.justify-end.gap-4.sm\\:mt-0 > button",
            "button:has-text('Launch')",
            "button:has-text('Deploy')"
        ]
        launch_clicked = False
        for lsel in launch_selectors:
            try:
                page.wait_for_selector(lsel, timeout=5000)
                page.click(lsel)
                launch_clicked = True
                break
            except Exception:
                continue
        if not launch_clicked:
            raise Exception("Failed to click Launch button.")

        # 15. Wait for deployment (up to 20 minutes)
        print("Waiting for deployment (this can take up to 15 minutes)...")
        target_a_selector = "#main-content > div > div > div > div > div.flex.flex-1.justify-center > div > div > div > div.flex.flex-1.flex-col.items-start.gap-4.xs\\:flex-row.xs\\:items-center > div.flex.flex-row.gap-4 > a"
        page.wait_for_selector(target_a_selector, timeout=1200000)

        # 16. Log active credentials
        now = datetime.datetime.now()
        expires = now + datetime.timedelta(hours=1)
        print("\n" + "="*60)
        print("API KEY DEPLOYED & ACTIVE")
        print(f"URL: https://nim.api.nvidia.com/v1")
        print(f"MODEL: {model}")
        print(f"API KEY: {account.get('api_key')}")
        print(f"DEPLOYED AT: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"EXPIRES AT: {expires.strftime('%Y-%m-%d %H:%M:%S')} (1 hour)")
        print("="*60 + "\n")
        
        browser.close()

def main():
    print("NVIDIA NIM Key Rotation Script started.")
    current_idx = 0

    while True:
        try:
            config = load_config()
            accounts = config["accounts"]
            account = accounts[current_idx]
            
            deploy_account(account)
            
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Active key deployed. Initiating 43 minutes sleep before next account rotation...")
            for remaining in range(43, 0, -1):
                sys.stdout.write(f"\rTime remaining until next deployment: {remaining} min(s) ...")
                sys.stdout.flush()
                time.sleep(60)
            print("\nTime's up! Initializing deployment on the next account.")
            
            current_idx = (current_idx + 1) % len(accounts)
            
        except Exception as e:
            print(f"\n[ERROR] Process failed for account {current_idx + 1}: {e}")
            print("Retrying this account in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    import sys
    main()
