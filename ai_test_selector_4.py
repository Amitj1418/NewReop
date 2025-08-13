import os
import re
import subprocess
import logging
from pathlib import Path

logging.basicConfig(
    filename="logs/ai_test_selector.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def run_git_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    result.check_returncode()
    return result.stdout.strip()

def get_changed_files():
    changed_files = run_git_cmd(["git", "diff", "--name-only", "HEAD~1", "HEAD"]).split("\n")
    return [f.strip() for f in changed_files if f.strip()]

def get_diff_for_file(file_path):
    return run_git_cmd(["git", "diff", "HEAD~1", "HEAD", "--", file_path])

def get_changed_methods(diff_text):
    """Finds new or modified method names from diff"""
    method_pattern = re.compile(r"^\+.*def\s+(\w+)\s*\(", re.MULTILINE)
    return set(method_pattern.findall(diff_text))

def get_changed_locators(diff_text):
    """
    Detects changes to locator variable names OR their values in any file.
    Returns set of locator variable names that have been modified.
    """
    changed_locators = set()
    locator_var_pattern = re.compile(r"^\+\s*(\w+_LOCATOR)\s*=\s*[\"'](.+?)[\"']", re.MULTILINE)
    locator_value_pattern = re.compile(r"[\"'](.+?)[\"']")

    current_var = None
    for line in diff_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            current_var = None
            continue

        # Added/modified locator variable
        match_var = locator_var_pattern.search(line)
        if match_var:
            current_var = match_var.group(1)
            changed_locators.add(current_var)
            continue

        # Changed locator value
        if (line.startswith("+") or line.startswith("-")) and current_var:
            if locator_value_pattern.search(line):
                changed_locators.add(current_var)

    return changed_locators

def get_changed_variables(diff_text):
    var_pattern = re.compile(r"^\+.*([a-z_]+)\s*=", re.MULTILINE)
    return set(var_pattern.findall(diff_text))

def find_methods_using_locators(locators):
    """Finds methods where changed locators are used"""
    impacted_methods = set()
    for file_path in Path(".").rglob("*.py"):
        if "pages" in str(file_path):  # Only search in POMs for mapping
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            for locator in locators:
                if locator in content:
                    method_matches = re.findall(r"def\s+(\w+)\s*\(.*\):", content)
                    impacted_methods.update(method_matches)
    return impacted_methods

def find_tests_using_methods(methods):
    tests = []
    for test_file in Path("tests").rglob("test_*.py"):
        with open(test_file, encoding="utf-8") as f:
            content = f.read()
        if any(m in content for m in methods):
            tests.append(str(test_file))
    return tests

def find_tests_using_locators(locators):
    tests = []
    for file_path in Path("tests").rglob("*.py"):
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        if any(locator in content for locator in locators):
            tests.append(str(file_path))
    return tests

def ask_ollama_for_tests(changed_files):
    import requests
    prompt = f"""
    You are analyzing a Python Playwright test framework.
    The following files changed: {changed_files}
    Suggest relevant pytest test files to run from the 'tests/' directory.
    Only return a Python list of file paths.
    """
    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral", "prompt": prompt, "stream": False}
        )
        data = r.json()
        return eval(data["response"]) if "response" in data else []
    except Exception as e:
        logging.error(f"AI fallback failed: {e}")
        return []

def main():
    logging.info("=== AI Test Selector Started ===")
    changed_files = [f for f in get_changed_files() if "ai_test_selector" not in f]
    logging.info(f"Changed files: {changed_files}")

    all_changed_methods = set()
    all_changed_locators = set()

    for f in changed_files:
        diff_text = get_diff_for_file(f)
        all_changed_methods |= get_changed_methods(diff_text)
        all_changed_locators |= get_changed_locators(diff_text)

    # If locator changed, find related methods in POM
    related_methods_from_locators = find_methods_using_locators(all_changed_locators)
    all_changed_methods |= related_methods_from_locators

    impacted_tests = set()
    if all_changed_methods:
        impacted_tests |= set(find_tests_using_methods(all_changed_methods))
    if all_changed_locators:
        impacted_tests |= set(find_tests_using_locators(all_changed_locators))

    if not impacted_tests:
        logging.info("No direct matches found — using AI fallback")
        impacted_tests |= set(ask_ollama_for_tests(changed_files))

    impacted_tests = sorted(impacted_tests)
    logging.info(f"Running impacted tests: {impacted_tests}")

    if impacted_tests:
        os.system(f"pytest {' '.join(impacted_tests)}")
    else:
        logging.info("No impacted tests detected")

if __name__ == "__main__":
    main()
