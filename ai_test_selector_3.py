import os
import re
import subprocess
import logging
from pathlib import Path
from git import Repo
from datetime import datetime

# --- Setup logging ---
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"ai_test_selector_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

logging.info("=== AI Test Selector Started ===")

project_root = Path(__file__).parent.resolve()
repo = Repo(".")

def get_changed_lines():
    """Fetch git diff between last commit and current commit."""
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "-U0", "HEAD~1", "HEAD"],
            encoding="utf-8",
            errors="replace"
        )
        logging.info("Fetched git diff successfully.")
        return diff_output
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting git diff: {e}")
        return ""

diff_content = get_changed_lines()
if not diff_content.strip():
    logging.warning("No code changes detected.")
    print("No code changes detected.")
    exit()

# --- Step 1: Get changed files ---
changed_files = re.findall(r"\+\+\+ b/(.+)", diff_content)
logging.info(f"Changed files: {changed_files}")

# --- Step 2: Detect changed methods from diff ---
changed_methods = set()
for line in diff_content.splitlines():
    method_match = re.match(r"^\+\s*def\s+(\w+)", line)
    if method_match:
        changed_methods.add(method_match.group(1))

logging.info(f"Changed methods from diff: {changed_methods}")

# --- Step 3: Map methods → classes by parsing files ---
changed_classes = {}
for file_path in changed_files:
    abs_path = Path(file_path)
    if not abs_path.exists() or not file_path.endswith(".py"):
        continue

    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
        code_lines = f.readlines()

    current_class = None
    for line in code_lines:
        class_match = re.match(r"\s*class\s+(\w+)", line)
        if class_match:
            current_class = class_match.group(1)

        method_match = re.match(r"\s*def\s+(\w+)", line)
        if method_match and current_class:
            method_name = method_match.group(1)
            if method_name in changed_methods:
                changed_classes.setdefault(current_class, set()).add(method_name)

logging.info(f"Changed classes & methods: {changed_classes}")

# --- Step 4: Get all test files ---
all_test_files = []
for root, _, files in os.walk("tests"):
    for f in files:
        if f.startswith("test") and f.endswith(".py"):
            all_test_files.append(os.path.join(root, f))

if not all_test_files:
    logging.warning("No test files found.")
    print("No test files found.")
    exit()

# --- Step 5: Class-aware method matching ---
test_files_to_run = []
for test_file in all_test_files:
    with open(test_file, "r", encoding="utf-8", errors="ignore") as f:
        code = f.read()

        for cls, methods in changed_classes.items():
            imports_class = (
                re.search(rf"from\s+[\w\.]+\s+import\s+{cls}", code) or
                re.search(rf"import\s+[\w\.]*{cls}", code) or
                re.search(rf"{cls}\s*\(", code)
            )

            if imports_class:
                for method in methods:
                    method_usage = re.search(rf"\b\w+\s*\.\s*{method}\s*\(", code)
                    if method_usage:
                        logging.info(f"Matched {cls}.{method} in test file: {test_file}")
                        test_files_to_run.append(test_file)
                        break  # Avoid duplicates

# --- Step 6: Run tests ---
test_files_to_run = list(set(test_files_to_run))
if not test_files_to_run:
    logging.warning("No relevant test files found.")
    print("No relevant test files found.")
    exit()

logging.info(f"Selected tests to run: {test_files_to_run}")
print("Selected tests to run:\n", "\n".join(test_files_to_run))
os.system(f"pytest {' '.join(test_files_to_run)}")
