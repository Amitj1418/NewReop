import pytest
from pages.checkout_page import CheckoutPage


@pytest.mark.login
@pytest.mark.usefixtures("page")
class TestValidateUser:

    @pytest.fixture(autouse=True)
    def _setup(self, page):  # ✅ underscore avoids fixture-name conflicts
        self.page = page
        self.login_page = CheckoutPage(self.page)

    def test_valid_login_hospital_user(self):
       self.login_page.login_with_hospital_user("ayyajj@futurismtechnologies.com")
       self.login_page.assert_toast_contains("Please enter email registered with the hospital")
       self.login_page.assert_toast_contains("Please enter email registered with the hospital")