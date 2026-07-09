import json
import time
import pyotp
from playwright.sync_api import sync_playwright

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def run():
    config = load_config()
    # Use the first account for testing
    account = config["accounts"][0]
    email = account["email"]
    password = account["password"]
    totp_secret = account["totp_secret"]

    print(f"Starting login flow for: {email}")

    with sync_playwright() as p:
        # Launch browser. Using headless=False so you can see the process.
        browser = p.firefox.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 1. Open main page to handle cookies first
        print("Navigating to main page for cookie handling...")
        page.goto("https://build.nvidia.com/", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # 2. Reject cookies if the modal shows up
        try:
            cookie_selector = "#onetrust-reject-all-handler"
            print("Checking for cookie consent banner...")
            page.wait_for_selector(cookie_selector, timeout=5000)
            page.wait_for_timeout(1000)
            page.click(cookie_selector)
            print("Rejected cookies.")
            page.wait_for_timeout(3000)  # Wait for reload or dismiss transition
        except Exception:
            print("Cookie banner did not appear or was already dismissed.")

        # 2b. Navigate to the actual sign-in modal page
        print("Navigating to sign-in modal page...")
        page.goto("https://build.nvidia.com/?modal=signin", wait_until="networkidle")
        page.wait_for_timeout(4000)

        # 3. Enter Email
        print("Entering email...")
        email_input_selector = "#email > div > input"
        page.wait_for_selector(email_input_selector, timeout=15000)
        page.fill(email_input_selector, email)
        page.wait_for_timeout(1000)

        # 4. Submit Email
        print("Submitting email...")
        # Since radix IDs are dynamic, we try several reliable selectors:
        selectors_to_try = [
            "div[id^='radix-'] button",  # Any button inside the Radix dialog
            "button:has-text('Continue')",
            "button:has-text('Next')",
            "button:has-text('Sign In')",
            "#radix-_r_c_ > div > div > div.flex.flex-col.gap-sm > div.flex.flex-row.items-end.justify-between.gap-sm > button"
        ]
        
        clicked = False
        for sel in selectors_to_try:
            try:
                print(f"Trying selector: {sel}")
                page.wait_for_selector(sel, timeout=3000)
                page.click(sel)
                clicked = True
                print(f"Successfully clicked using: {sel}")
                break
            except Exception:
                continue
                
        if not clicked:
            print("Failed to click email submit button with standard selectors. Let's dump available buttons in the dialog...")
            try:
                buttons = page.query_selector_all("button")
                print(f"Found {len(buttons)} buttons on the page:")
                for i, btn in enumerate(buttons):
                    print(f"Button {i}: text='{btn.inner_text()}', html='{btn.evaluate('el => el.outerHTML')}'")
            except Exception as e:
                print(f"Could not dump buttons: {e}")
            raise Exception("Could not find or click the Email Submit button.")

        # 5. Enter Password
        print("Waiting for password screen...")
        password_input_selector = "#signinPassword"
        page.wait_for_selector(password_input_selector, timeout=20000)
        page.wait_for_timeout(1500)
        page.fill(password_input_selector, password)
        page.wait_for_timeout(1000)

        # 6. Submit Password
        print("Submitting password...")
        password_submit_selector = "#passwordLoginButton"
        page.wait_for_selector(password_submit_selector, timeout=15000)
        page.click(password_submit_selector)

        # 7. Select 2FA method
        print("Waiting for 2FA selection screen...")
        two_fa_select_selector = "#nfactorPromptChallenge_list_0 > span > span > div > h4"
        page.wait_for_selector(two_fa_select_selector, timeout=20000)
        page.wait_for_timeout(1500)
        page.click(two_fa_select_selector)

        # 8. Generate TOTP code and enter it
        print("Generating TOTP code...")
        totp = pyotp.TOTP(totp_secret.replace(" ", ""))
        code = totp.now()
        print(f"Generated 2FA code: {code}")

        code_input_selector = "#code_input"
        page.wait_for_selector(code_input_selector, timeout=15000)
        page.wait_for_timeout(1500)
        page.fill(code_input_selector, code)
        page.wait_for_timeout(1000)

        # 9. Submit 2FA code
        print("Submitting 2FA code...")
        submit_code_selector = "#submit_code_btn"
        page.wait_for_selector(submit_code_selector, timeout=15000)
        page.click(submit_code_selector)

        print("Login submission complete. Waiting 10 seconds for login redirects to settle...")
        page.wait_for_timeout(10000)

        print("Login successful.")
        print(f"API Key for this account: {account.get('api_key')}")

        # 10. Navigate to community models page
        print("Navigating to community models page...")
        try:
            page.goto("https://build.nvidia.com/models/community", timeout=45000)
        except Exception as e:
            print(f"Navigation warning (non-fatal): {e}")
        page.wait_for_timeout(5000)

        # 11. Enter model name in the search box
        print(f"Searching for model: {config['model']}")
        search_container_sel = "#main-content > div > div > div > div > div.flex.flex-1.justify-center > div > div > div.flex.flex-1.flex-col.gap-0.sm\\:flex-row.sm\\:items-center.sm\\:gap-4 > div.flex-1"
        page.wait_for_selector(search_container_sel, timeout=30000)
        
        # Locate the input field inside the search container
        search_input = page.locator(search_container_sel).locator("input")
        search_input.wait_for(timeout=10000)
        search_input.fill(config["model"])
        page.wait_for_timeout(3000)  # Wait for dropdown list to populate and filter

        # 12. Select the EXACT matching model
        print("Matching the model in the dropdown list...")
        # We query for divs with text-md class inside the search area or dropdown list
        dropdown_selector = "div.text-md"
        page.wait_for_selector(dropdown_selector, timeout=15000)
        elements = page.query_selector_all(dropdown_selector)
        
        matched = False
        found_options = []
        for elem in elements:
            text_content = elem.inner_text().strip()
            found_options.append(text_content)
            # Check if any line in the text matches the model exactly
            lines = [line.strip() for line in text_content.split("\n")]
            if config["model"] in lines or text_content == config["model"]:
                print(f"Found exact match: {text_content}. Clicking...")
                elem.click()
                matched = True
                break
                
        if not matched:
            print(f"Warning: Exact match for '{config['model']}' not found in dropdown.")
            print(f"Available options were: {found_options}")
            # Fallback: click the first matching selector if only one is present, or raise error
            raise Exception("Exact model match not found in dropdown list.")

        # 12b. Click the Launch/Deploy button
        print("Clicking the Launch/Deploy button...")
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
                print(f"Successfully clicked Launch button using: {lsel}")
                break
            except Exception:
                continue
                
        if not launch_clicked:
            print("Failed to click Launch button. Dumping all buttons in the main content container...")
            try:
                main_buttons = page.query_selector_all("#main-content button")
                for idx, btn in enumerate(main_buttons):
                    print(f"Main Content Button {idx}: text='{btn.inner_text()}', html='{btn.evaluate('el => el.outerHTML')}'")
            except Exception as e:
                print(f"Error dumping main content buttons: {e}")
            raise Exception("Could not find or click the Launch button.")

        # 13. Wait for deployment (up to 20 minutes)
        print("Model selected. Waiting for deployment to finish (this can take up to 15-20 minutes)...")
        target_a_selector = "#main-content > div > div > div > div > div.flex.flex-1.justify-center > div > div > div > div.flex.flex-1.flex-col.items-start.gap-4.xs\\:flex-row.xs\\:items-center > div.flex.flex-row.gap-4 > a"
        
        # 20 minutes timeout = 1200000 ms
        page.wait_for_selector(target_a_selector, timeout=1200000)
        print("Deployment completed successfully!")

        # 14. Output active API details
        import datetime
        now = datetime.datetime.now()
        expires = now + datetime.timedelta(hours=1)
        
        print("\n" + "="*50)
        print("API KEY DEPLOYED & ACTIVE")
        print(f"URL: https://nim.api.nvidia.com/v1")
        print(f"MODEL: {config['model']}")
        print(f"API KEY: {account.get('api_key')}")
        print(f"DEPLOYED AT: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"EXPIRES AT: {expires.strftime('%Y-%m-%d %H:%M:%S')} (1 hour)")
        print("="*50 + "\n")

        print("Finished.")
        browser.close()

if __name__ == "__main__":
    import sys
    run()
