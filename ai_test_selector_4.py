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
    return [f for f in changed_files if f.strip()]

def get_diff_for_file(file_path):
    return run_git_cmd(["git", "diff", "HEAD~1", "HEAD", "--", file_path])

def get_changed_methods(diff_text):
    method_pattern = re.compile(r"^\+.*def\s+(\w+)\s*\(", re.MULTILINE)
    return set(method_pattern.findall(diff_text))

def get_changed_locators():
    """ Detects changes to locator variable names OR values in POM files. """
    changed_locators = set()
    diff_output = run_git_cmd(["git", "diff", "HEAD~1", "HEAD", "--", "pages/"])

    locator_pattern = re.compile(r"^\+\s*(\w+_LOCATOR)\s*=\s*[\"'](.+)[\"']")
    value_pattern = re.compile(r"[\"'](.+)[\"']")

    current_locator_var = None
    for line in diff_output.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            current_locator_var = None
            continue
        match_var = locator_pattern.search(line)
        if match_var:
            locator_var = match_var.group(1)
            changed_locators.add(locator_var)
            current_locator_var = locator_var
            continue
        if (line.startswith("+") or line.startswith("-")) and current_locator_var:
            match_val = value_pattern.search(line)
            if match_val:
                changed_locators.add(current_locator_var)

    return changed_locators

def map_locators_to_methods(locators):
    """ Finds methods that use any of the changed locators. """
    methods_using_locators = set()
    for file_path in Path("pages").rglob("*.py"):
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        for locator in locators:
            if locator in content:
                # Find methods containing this locator
                method_blocks = re.findall(r"def\s+(\w+)\s*\(.*?\):([\s\S]*?)(?=def\s+\w+\s*\(|$)", content)
                for method_name, method_body in method_blocks:
                    if locator in method_body:
                        methods_using_locators.add(method_name)
    return methods_using_locators

def find_tests_using_methods(methods):
    """ Finds tests that call the given methods. """
    tests = []
    for test_file in Path("tests").rglob("test_*.py"):
        with open(test_file, encoding="utf-8") as f:
            content = f.read()
        if any(m in content for m in methods):
            tests.append(str(test_file))
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
        return eval(data.get("response", "[]"))
    except Exception as e:
        logging.error(f"AI fallback failed: {e}")
        return []

def main():
    logging.info("=== AI Test Selector Started ===")
    changed_files = get_changed_files()
    logging.info(f"Changed files: {changed_files}")

    changed_files = [f for f in changed_files if "ai_test_selector" not in f]

    all_changed_methods = set()
    all_changed_locators = get_changed_locators()
    logging.info(f"Changed locators: {all_changed_locators}")

    # Map locators → methods
    if all_changed_locators:
        all_changed_methods |= map_locators_to_methods(all_changed_locators)
    logging.info(f"Methods impacted by locators: {all_changed_methods}")

    # Find tests using impacted methods
    impacted_tests = set(find_tests_using_methods(all_changed_methods))

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
