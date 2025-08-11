import requests
import re
from bs4 import BeautifulSoup


def heal_locator(html_snippet: str, label: str) -> str:
    # First try LLM healing
    llm_selector = _try_llm_healing(html_snippet, label)
    if llm_selector:
        return llm_selector

    # Fallback to rule-based healing
    print("🔧 LLM healing failed, trying rule-based healing...")
    return _try_rule_based_healing(html_snippet, label)


def _try_llm_healing(html_snippet: str, label: str) -> str:
    prompt = f"""
You are an expert automation assistant.
Given the following HTML, generate a unique XPath or CSS selector to locate the element labeled '{label}'.

HTML:
{html_snippet}

Return ONLY the selector inside triple backticks.
""".strip()

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama2",
                "prompt": prompt,
                "stream": False
            },
            timeout=15  # Reduced timeout
        )

        if response.status_code == 200:
            raw = response.json().get("response", "").strip()
            print(f"🧠 LLM Raw Response:\n{raw}")

            # Extract code inside triple backticks
            match = re.search(r"```(?:xpath|css)?\s*(.*?)\s*```", raw, re.DOTALL)
            if match:
                return match.group(1).strip()

            # Fallback: look for XPath or CSS-ish string
            match = re.search(r"(//[\w\[\]\@=\"\'\s\-\.\(\):]+)", raw)
            if match:
                return match.group(1).strip()

    except Exception as e:
        print(f"⚠️ LLM Healing failed: {e}")

    return ""


def _try_rule_based_healing(html_snippet: str, label: str) -> str:
    try:
        soup = BeautifulSoup(html_snippet, 'html.parser')

        # Strategy 1: Find by exact text match
        elements = soup.find_all(text=re.compile(re.escape(label), re.IGNORECASE))
        for element in elements:
            parent = element.parent
            if parent:
                selector = _generate_xpath_for_element(parent, soup)
                if selector:
                    print(f"🎯 Rule-based healing found: {selector}")
                    return selector

        # Strategy 2: Find by partial text match
        elements = soup.find_all(text=re.compile(label.split()[0], re.IGNORECASE))
        for element in elements:
            parent = element.parent
            if parent:
                selector = _generate_xpath_for_element(parent, soup)
                if selector:
                    print(f"🎯 Rule-based healing found (partial): {selector}")
                    return selector

        # Strategy 3: Find by common button/tab patterns
        common_selectors = [
            f"//button[contains(text(), '{label}')]",
            f"//div[contains(text(), '{label}')]",
            f"//span[contains(text(), '{label}')]",
            f"//a[contains(text(), '{label}')]",
            f"//*[contains(@class, 'tab') and contains(text(), '{label}')]",
            f"//*[contains(@class, 'button') and contains(text(), '{label}')]"
        ]

        for selector in common_selectors:
            print(f"🎯 Trying common pattern: {selector}")
            return selector

    except Exception as e:
        print(f"⚠️ Rule-based healing failed: {e}")

    return ""


def _generate_xpath_for_element(element, soup):
    """Generate XPath for a given BeautifulSoup element"""
    try:
        components = []
        child = element if element.name else element.parent

        for parent in child.parents:
            siblings = parent.find_all(child.name, recursive=False) if child.name else []
            if len(siblings) == 1:
                components.append(child.name)
            else:
                index = siblings.index(child) + 1
                components.append(f"{child.name}[{index}]")
            child = parent

        components.reverse()
        return "//" + "/".join(components)
    except:
        return ""