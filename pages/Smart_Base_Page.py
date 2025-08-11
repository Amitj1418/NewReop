from playwright.sync_api import Page

from core.self_healing import heal_locator

class BasePage:
    def __init__(self, page: Page):
        # self.keyboard = None
        self.page = page

    def smart_click(self, element_name, primary_selector, timeout=5000):
        """Generic method to click elements with automatic healing"""
        try:
            self.page.wait_for_selector(primary_selector, timeout=timeout)
            self.page.click(primary_selector)
            print(f"✅ Clicked {element_name} using primary selector")
        except Exception as e:
            print(f"⚠️ Primary selector failed for {element_name}: {e}")
            print(f"🔧 Attempting to heal selector for '{element_name}'...")

            # Get page content for healing
            html_content = self.page.content()

            # Try multiple healing strategies
            healed_selectors = self._generate_healing_selectors(element_name, html_content)

            for i, selector in enumerate(healed_selectors):
                try:
                    print(f"🧠 Trying healing strategy {i + 1}: {selector}")
                    self.page.wait_for_selector(selector, timeout=2000)
                    self.page.click(selector)
                    print(f"✅ Successfully clicked {element_name} using healed selector: {selector}")
                    return
                except Exception as heal_error:
                    print(f"❌ Healing strategy {i + 1} failed: {heal_error}")
                    continue

            # If all healing fails, use external heal_locator as last resort
            try:
                final_selector = heal_locator(html_content, element_name)
                if final_selector:
                    self.page.click(final_selector)
                    print(f"✅ External healing successful for {element_name}: {final_selector}")
                else:
                    raise Exception(f"❌ All healing strategies failed for {element_name}")
            except Exception as final_error:
                raise Exception(f"❌ Complete healing failure for {element_name}: {final_error}")

    def smart_fill(self, field_name, primary_selector, value, timeout=5000):
        """Generic method to fill input fields with automatic healing"""
        try:
            self.page.wait_for_selector(primary_selector, timeout=timeout)
            self.page.fill(primary_selector, value)
            print(f"✅ Filled {field_name} using primary selector")
        except Exception as e:
            print(f"⚠️ Primary selector failed for {field_name}: {e}")
            print(f"🔧 Attempting to heal selector for '{field_name}'...")

            html_content = self.page.content()
            healed_selectors = self._generate_input_healing_selectors(field_name, html_content)

            for i, selector in enumerate(healed_selectors):
                try:
                    print(f"🧠 Trying input healing strategy {i + 1}: {selector}")
                    self.page.wait_for_selector(selector, timeout=2000)
                    self.page.fill(selector, value)
                    print(f"✅ Successfully filled {field_name} using healed selector: {selector}")
                    return
                except Exception as heal_error:
                    print(f"❌ Input healing strategy {i + 1} failed: {heal_error}")
                    continue

            raise Exception(f"❌ All input healing strategies failed for {field_name}")

    def _generate_healing_selectors(self, element_name, html_content):
        """Generate multiple healing selector strategies for clickable elements"""
        selectors = []

        # Strategy 1: Exact text match variations
        selectors.extend([
            f"//button[text()='{element_name}']",
            f"//div[text()='{element_name}']",
            f"//span[text()='{element_name}']",
            f"//a[text()='{element_name}']",
            f"//*[text()='{element_name}']"
        ])

        # Strategy 2: Contains text variations
        selectors.extend([
            f"//button[contains(text(), '{element_name}')]",
            f"//div[contains(text(), '{element_name}')]",
            f"//span[contains(text(), '{element_name}')]",
            f"//a[contains(text(), '{element_name}')]",
            f"//*[contains(text(), '{element_name}')]"
        ])

        # Strategy 3: Case insensitive matching
        element_lower = element_name.lower()
        selectors.extend([
            f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{element_lower}')]",
            f"//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{element_lower}')]"
        ])

        # Strategy 4: Material Design specific patterns
        if 'mat-' in html_content:
            selectors.extend([
                f"//div[@class='mat-tab-label-content' and contains(text(), '{element_name}')]",
                f"//div[contains(@class, 'mat-tab') and contains(text(), '{element_name}')]",
                f"//button[contains(@class, 'mat-') and contains(text(), '{element_name}')]"
            ])

        # Strategy 5: Bootstrap patterns
        if 'nav-link' in html_content or 'btn' in html_content:
            selectors.extend([
                f"//a[@class='nav-link' and contains(text(), '{element_name}')]",
                f"//button[contains(@class, 'btn') and contains(text(), '{element_name}')]"
            ])

        # Strategy 6: Partial word matching
        words = element_name.split()
        if len(words) > 1:
            for word in words:
                selectors.extend([
                    f"//*[contains(text(), '{word}')]",
                    f"//button[contains(text(), '{word}')]"
                ])

        return selectors

    def _generate_input_healing_selectors(self, field_name, html_content):
        """Generate healing selectors specifically for input fields"""
        selectors = []
        field_lower = field_name.lower()

        # Strategy 1: Placeholder matching
        selectors.extend([
            f"//input[@placeholder='{field_name}']",
            f"//input[contains(@placeholder, '{field_name}')]",
            f"//input[contains(@placeholder, '{field_lower}')]"
        ])

        # Strategy 2: Type-based matching
        if 'email' in field_lower:
            selectors.extend([
                "//input[@type='email']",
                "//input[contains(@placeholder, 'email')]",
                "//input[contains(@name, 'email')]"
            ])
        elif 'password' in field_lower:
            selectors.extend([
                "//input[@type='password']",
                "//input[contains(@placeholder, 'password')]",
                "//input[contains(@name, 'password')]"
            ])

        # Strategy 3: Name and ID attributes
        selectors.extend([
            f"//input[@name='{field_lower}']",
            f"//input[@id='{field_lower}']",
            f"//input[contains(@name, '{field_lower}')]",
            f"//input[contains(@id, '{field_lower}')]"
        ])

        # Strategy 4: Label association
        selectors.extend([
            f"//input[following-sibling::label[contains(text(), '{field_name}')]]",
            f"//input[preceding-sibling::label[contains(text(), '{field_name}')]]"
        ])

        return selectors
