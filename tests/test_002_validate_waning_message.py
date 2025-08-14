import pytest
from pages.checkout_page import CheckoutPage


@pytest.mark.login
@pytest.mark.usefixtures("page")
class TestValidate:

    @pytest.fixture(autouse=True)
    def _setup(self, page):  # ✅ underscore avoids fixture-name conflicts
        self.page = page
        self.login_page = CheckoutPage(self.page)

    def test_super_admin_warning_message(self):
       self.login_page.login_with_super_admin("ayyajj@futurismtechnologies.com", "Ayyaj@1234")
       self.login_page.assert_toast_contains("Invalid Email or Password")











