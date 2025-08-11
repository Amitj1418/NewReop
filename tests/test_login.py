# tests/test_login.py

import pytest
from pages.Login_Page import LoginPage

@pytest.mark.login
@pytest.mark.usefixtures("page")
class TestLoginScenarios:

    @pytest.fixture(autouse=True)
    def _setup(self, page):  # ✅ underscore avoids fixture-name conflicts
        self.page = page
        self.login_page = LoginPage(self.page)

    def test_valid_login_super_admin(self):
        self.login_page.login_with_super_admin("ayyajj@futurismtechnologies.com", "Ayyaj@123")
        self.login_page.validate_dashboard_page()
        assert self.login_page.validate_url("https://synergymedqa.futurismdemo.com/#/admin/home")

    # def test_login_super_admin(self):
    #     self.login_page.login_with_super_admin("ayyajj@futurismtechnologies.com", "Ayyaj@1234")
    #     self.login_page.assert_toast_contains("Invalid Email or Password")
