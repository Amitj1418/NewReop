import os
import re
import sys
import subprocess
import logging
from datetime import datetime

# === LOGGING SETUP ===
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"ai_test_selector_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(console_handler)

logging.info("=== AI Test Selector Started ===")
logging.debug(f"sys.platform='{sys.platform}', git_executable='git'")


def get_changed_lines():
    """Get raw git diff for staged changes, or last commit if nothing staged."""
    try:
        # First check for staged changes
        diff_output = subprocess.check_output(
            ["git", "diff", "--cached", "--unified=0", "HEAD"],
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )

        # If nothing staged, fallback to last commit
        if not diff_output.strip():
            logging.info("No staged changes found, checking last commit...")
            diff_output = subprocess.check_output(
                ["git", "diff", "HEAD~1", "HEAD", "--unified=0"],
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )

        logging.info("Fetched git diff successfully.")
        return diff_output

    except subprocess.CalledProcessError as e:
        logging.error(f"Error running git diff: {e.output}")
        return ""


def extract_changed_files_and_methods(diff_text):
    changed_files = set()
    changed_methods = set()
    current_file = None

    method_pattern = re.compile(r"^\+.*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            changed_files.add(current_file)
        elif line.startswith("+") and current_file and current_file.endswith(".py"):
            method_match = method_pattern.match(line)
            if method_match:
                changed_methods.add(method_match.group(1))

    return changed_files, changed_methods


def find_impacted_tests(changed_files, changed_methods):
    """Find relevant tests based on changes."""
    impacted_tests = set()

    # Scenario 1: Direct test file changes
    for f in changed_files:
        if f.startswith("tests/") and f.endswith(".py"):
            impacted_tests.add(f)

    # Scenario 2 & 3: Page class method changes
    if changed_methods:
        for root, _, files in os.walk("tests"):
            for file in files:
                if file.endswith(".py"):
                    test_path = os.path.join(root, file)
                    try:
                        with open(test_path, encoding="utf-8", errors="ignore") as tf:
                            content = tf.read()
                            for method in changed_methods:
                                if re.search(rf"\b{method}\b", content):
                                    impacted_tests.add(test_path)
                    except Exception as e:
                        logging.error(f"Error reading file {test_path}: {e}")

    return list(impacted_tests)


if __name__ == "__main__":
    diff_content = get_changed_lines()
    changed_files, changed_methods = extract_changed_files_and_methods(diff_content)

    logging.info(f"Changed files: {list(changed_files)}")
    logging.info(f"Changed methods: {changed_methods}")

    impacted_tests = find_impacted_tests(changed_files, changed_methods)

    if impacted_tests:
        logging.info(f"Selected tests to run: {impacted_tests}")
        for test in impacted_tests:
            print(test)
    else:
        logging.warning("No relevant test files found.")
