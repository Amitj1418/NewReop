# pages/login_page.py
import pytest
from core.self_healing import heal_locator

@pytest.mark.login
class LoginPage:


    EMAIL_TEXT_INPUT = "//input[@placeholder='Emails']"
    PASSWORD_TEXT_INPUT = "//input[@type='password']"
    LOGIN_BUTTON = "//button[@type='submit']"
    SUPER_ADMIN_LINK="//div[@class='mat-tab-label-content'and text()='Super Admins']"
    HOSPITAL_USER_LINK="//div[@class='mat-tab-label-content'and text()='Supers Admin']"
    TOAST_MESSAGE="//div[@id='toast-container']"
    USERNAME_LABEL="//span[@class='user-name']"

    def __init__(self, page):
        self.page = page

    def login_with_super_admin(self, username, password):
        self.click_super_admin_link()
        self.page.fill(self.EMAIL_TEXT_INPUT, username)
        self.page.fill(self.PASSWORD_TEXT_INPUT, password)
        self.page.wait_for_selector(self.LOGIN_BUTTON)
        self.page.click(self.LOGIN_BUTTON)


    def login_with_hospital_user(self, username, password):
        self.click_hospital_user_link()
        self.page.fill(self.EMAIL_TEXT_INPUT, username)
        self.page.fill(self.PASSWORD_TEXT_INPUT, password)
        self.page.wait_for_selector(self.LOGIN_BUTTON)
        self.page.click(self.LOGIN_BUTTON)

    def click_super_admin_link(self):
        try:
            self.page.click(self.SUPER_ADMIN_LINK)
        except Exception:
            print("⚠️ SUPER_ADMIN_LINK locator failed, trying healing...")
            html = self.page.content()
            healed_selector = heal_locator(html, "Super Admin")
            print(f"🧠 Healed SUPER_ADMIN_LINK Selector: {healed_selector}")
            self.page.click(healed_selector)
            if healed_selector:
                self.page.click(healed_selector)
            else:
                raise Exception("❌ Healing failed: No valid selector was returned.")

    def click_hospital_user_link(self):
        self.page.click(self.HOSPITAL_USER_LINK)

    def validate_url(self, expected_url):
        actual_url = self.page.url
        print(f"👉 Expected: {expected_url}")
        print(f"👉 Actual:   {actual_url}")
        return actual_url == expected_url

    def validate_dashboard_page(self,timeout: int = 5000):
        self.wait_for_locator(self.USERNAME_LABEL,timeout=timeout)

    def assert_toast_contains(self, expected_text: str, timeout: int = 5000):
        """Waits for toast and asserts it contains expected text."""
        self.page.wait_for_selector(self.TOAST_MESSAGE, timeout=timeout)
        actual = self.page.locator(self.TOAST_MESSAGE)
        actual_text = actual.inner_text()
        assert expected_text in actual_text, f"❌ Toast did not match. Expected: '{expected_text}' | Actual: '{actual_text}'"

    def wait_for_locator(self, selector: str, timeout: int = 5000):
        """Waits for the given locator to be visible within the timeout."""
        try:
            self.page.wait_for_selector(selector, timeout=timeout, state='visible')
            return True
        except Exception as e:
            print(f"⚠️ Locator '{selector}' not visible within {timeout}ms. Error: {e}")
            return False