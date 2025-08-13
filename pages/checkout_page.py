# pages/login_page.py
import pytest
from pages.Smart_Base_Page import BasePage




@pytest.mark.login
class CheckoutPage:
    def __init__(self, page):
        self.page = page
        self.base_page_instance = BasePage(self.page)

    EMAIL_TEXT_INPUT = "//input[@placeholder='Email']"
    PASSWORD_TEXT_INPUT = "//input[@type='password']"
    LOGIN_BUTTON = "//button[@type='submit']"
    SUPER_ADMIN_LINK = "//div[@class='mat-tab-label-content' and text()='Super Admins']"
    HOSPITAL_USER_LINK = "//div[@class='mat-tab-label-content' and text()='Hospital User']"
    TOAST_MESSAGE = "//div[@aria-label='Invalid Email or Password']"
    USERNAME_LABEL = "//span[@class='user-name']"



    def login_with_super_admin(self, username, password):
        self.base_page_instance.smart_click("Super Admin", self.SUPER_ADMIN_LINK)
        self.base_page_instance.smart_fill("Email", self.EMAIL_TEXT_INPUT, username)
        self.base_page_instance.smart_fill("Password", self.PASSWORD_TEXT_INPUT, password)
        self.base_page_instance.smart_click("Login", self.LOGIN_BUTTON)

    def login_with_hospital_user(self, username, password):
        self.base_page_instance.smart_click("Hospital User", self.HOSPITAL_USER_LINK)
        self.base_page_instance.smart_fill("Email", self.EMAIL_TEXT_INPUT, username)
        self.base_page_instance.smart_fill("Password", self.PASSWORD_TEXT_INPUT, password)
        self.base_page_instance.smart_click("Login", self.LOGIN_BUTTON)


    def click_super_admin_link(self):
        """Legacy method - kept for backward compatibility"""
        self.base_page_instance.smart_click("Super Admin", self.SUPER_ADMIN_LINK)

    def click_hospital_user_link(self):
        """Legacy method - kept for backward compatibility"""
        self.base_page_instance.smart_click("Hospital User", self.HOSPITAL_USER_LINK)

    def validate_url(self, expected_url):
        actual_url = self.page.url
        print(f"👉 Expected: {expected_url}")
        print(f"👉 Actual:   {actual_url}")
        return actual_url == expected_url

    def validate_dashboard_page(self):
        self.wait_for_locator(self.USERNAME_LABEL)


    def assert_toast_contains(self, expected_text: str):
        """Waits for toast and asserts it contains expected text."""
        self.wait_for_locator(self.TOAST_MESSAGE)
        self.wait_for_locator(self.TOAST_MESSAGE)
        actual = self.page.locator(self.TOAST_MESSAGE)
        actual_text = actual.inner_text()
        assert expected_text in actual_text, f"❌ Toast did not match. Expected: '{expected_text}' | Actual: '{actual_text}'"

    def wait_for_locator(self, selector: str, timeout: int = 10000):
        """Waits for the given locator to be visible within the timeout."""
        try:
            self.page.wait_for_selector(selector, timeout=timeout, state='visible')
            return True
        except Exception as e:
            print(f"⚠️ Locator '{selector}' not visible within {timeout}ms. Error: {e}")
            return False