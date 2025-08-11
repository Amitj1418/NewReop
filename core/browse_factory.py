from playwright.sync_api import sync_playwright



def launch_browser(headless=True):
    
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context()
    page = context.new_page()
    return playwright, browser, context, page