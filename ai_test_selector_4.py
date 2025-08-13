import os
import re
import subprocess
import logging

# === Logging setup ===
logging.basicConfig(
    filename="logs/ai_test_selector.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# -----------------------
# Git helper
# -----------------------
def run_git_cmd(cmd):
    """Run a git command safely and always return a string."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Git command failed: {e.stderr}")
        return ""

# -----------------------
# Detect changed methods
# -----------------------
def get_changed_methods(changed_files):
    changed_methods = set()
    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue
        diff_output = run_git_cmd(["git", "diff", "HEAD~1", "--", file_path])
        if not diff_output:
            continue
        for match in re.finditer(r'^\+.*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', diff_output, re.MULTILINE):
            changed_methods.add(match.group(1))
    logging.info(f"Changed methods detected: {changed_methods}")
    return changed_methods

# -----------------------
# Detect changed locators
# -----------------------
def get_changed_locators(changed_files):
    """
    Detect changed locators in Python diffs.
    Captures both locator strings and variable names.
    """
    changed_locators = set()
    changed_vars = set()

    locator_string_pattern = re.compile(r'^[\+|-].*["\'](//.*)["\']')
    locator_var_pattern = re.compile(r'^[\+|-]\s*([A-Z0-9_]+)\s*=')

    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue
        diff_output = run_git_cmd(["git", "diff", "HEAD~1", "--", file_path])
        if not diff_output:
            continue

        for line in diff_output.splitlines():
            str_match = locator_string_pattern.search(line)
            var_match = locator_var_pattern.search(line)

            if str_match:
                changed_locators.add(str_match.group(1))
            if var_match:
                changed_vars.add(var_match.group(1))

    logging.info(f"Changed locator strings detected: {changed_locators}")
    logging.info(f"Changed locator variable names detected: {changed_vars}")
    return changed_locators, changed_vars

# -----------------------
# Find methods using locators
# -----------------------
def find_methods_using_locators(all_files, changed_locators, changed_vars):
    matched_methods = set()
    method_pattern = re.compile(r'^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', re.MULTILINE)

    for file_path in all_files:
        if not file_path.endswith(".py"):
            continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if any(locator in content for locator in changed_locators) or \
               any(var in content for var in changed_vars):
                for match in method_pattern.findall(content):
                    matched_methods.add(match)

        except Exception as e:
            logging.error(f"Error reading {file_path}: {e}")

    logging.info(f"Methods using changed locators: {matched_methods}")
    return matched_methods

# -----------------------
# Find tests using methods
# -----------------------
def find_tests_using_methods(test_files, methods):
    matched_tests = set()
    for test_file in test_files:
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
            if any(method in content for method in methods):
                matched_tests.add(test_file)
        except Exception as e:
            logging.error(f"Error reading {test_file}: {e}")

    logging.info(f"Tests using changed methods: {matched_tests}")
    return matched_tests

# -----------------------
# Main Execution
# -----------------------
if __name__ == "__main__":
    logging.info("=== AI Test Selector Started ===")

    changed_files = run_git_cmd(["git", "diff", "--name-only", "HEAD~1"]).splitlines()
    logging.info(f"Changed files: {changed_files}")

    repo_tests = [os.path.join(root, file)
                  for root, _, files in os.walk(".")
                  for file in files if file.startswith("test_") and file.endswith(".py")]
    all_repo_files = [os.path.join(root, file)
                      for root, _, files in os.walk(".")
                      for file in files if file.endswith(".py")]

    # Step 1 — Changed methods
    changed_methods = get_changed_methods(changed_files)
    if changed_methods:
        method_matched_tests = find_tests_using_methods(repo_tests, changed_methods)
        if method_matched_tests:
            logging.info(f"Running tests that reference changed methods: {method_matched_tests}")
            os.system(f"pytest {' '.join(method_matched_tests)}")
            exit(0)

    # Step 2 — Changed locators
    changed_locators, changed_vars = get_changed_locators(changed_files)
    if changed_locators or changed_vars:
        methods_using_locators = find_methods_using_locators(all_repo_files, changed_locators, changed_vars)
        if methods_using_locators:
            locator_matched_tests = find_tests_using_methods(repo_tests, methods_using_locators)
            if locator_matched_tests:
                logging.info(f"Running tests that reference methods using changed locators: {locator_matched_tests}")
                os.system(f"pytest {' '.join(locator_matched_tests)}")
                exit(0)

    logging.info("No impacted tests found. Nothing to run.")
