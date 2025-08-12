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

# --- Step 1: Get exact changed lines ---
def get_changed_lines():
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "-U0", "HEAD~1", "HEAD"],
            encoding="utf-8",   # Force UTF-8 decoding
            errors="replace"    # Replace invalid chars
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

# --- Step 2: Extract changed files, methods, classes ---
changed_files = re.findall(r"\+\+\+ b/(.+)", diff_content)
changed_names = set()

changed_names.update(re.findall(r"^\+\s*def\s+(\w+)", diff_content, re.MULTILINE))
changed_names.update(re.findall(r"^\+\s*class\s+(\w+)", diff_content, re.MULTILINE))
changed_names.update(re.findall(r"^\+\s*self\.(\w+)", diff_content, re.MULTILINE))

logging.info(f"Changed files: {changed_files}")
logging.info(f"Changed elements: {changed_names}")

method_pattern = re.compile(r"^\s*def\s+(\w+)\(.*\):", re.MULTILINE)
file_methods_map = {}

for file in changed_files:
    file_path = project_root / file
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            file_methods_map[file] = method_pattern.findall(content)

for file in changed_files:
    if "page" in file.lower() and file in file_methods_map:
        changed_names.update(file_methods_map[file])

# --- Step 3: Get all test files ---
all_test_files = []
for root, _, files in os.walk("tests"):
    for f in files:
        if f.startswith("test") and f.endswith(".py"):
            all_test_files.append(os.path.join(root, f))

if not all_test_files:
    logging.warning("No test files found.")
    print("No test files found.")
    exit()

# --- Step 4: More precise method matching ---
def strip_comments_and_docstrings(code):
    """Remove Python comments and docstrings."""
    # Remove docstrings
    code = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '', code)
    # Remove single-line comments
    code = re.sub(r'#.*', '', code)
    return code

test_files_to_run = []

for test_file in all_test_files:
    # If test file itself was changed, always run it
    if any(test_file.replace("\\", "/") == cf for cf in changed_files):
        test_files_to_run.append(test_file)
        logging.info(f"Directly selected changed test file: {test_file}")
        continue

    with open(test_file, "r", encoding="utf-8", errors="ignore") as f:
        raw_code = f.read()
        test_code = strip_comments_and_docstrings(raw_code)

        for name in changed_names:
            pattern = rf"\b(?:\w+|self)\.{name}\s*\("
            if re.search(pattern, test_code):
                test_files_to_run.append(test_file)
                logging.info(f"Matched method '{name}' in test file: {test_file}")
                break

# --- Step 5: AI fallback ---
if not test_files_to_run:
    logging.info("No keyword matches found, using AI fallback.")
    print("No direct keyword matches found. Asking AI...\n")

    prompt = (
        "You are an AI that maps Python code changes to pytest test files.\n"
        "Here are the changed files and modified elements:\n\n"
    )
    for f in changed_files:
        prompt += f"File: {f}\n"
    prompt += f"Changed elements: " + (", ".join(changed_names) if changed_names else "None") + "\n\n"
    prompt += (
        "Return ONLY the pytest test file paths (starting with tests/) "
        "that are most likely to be affected. One per line. No explanations."
    )

    try:
        ai_result = subprocess.run(
            ["ollama", "run", "mistral"],
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=25
        )
        ai_output = ai_result.stdout.decode(errors="replace").strip()
        logging.info(f"AI Output:\n{ai_output}")

        ai_tests = []
        for line in ai_output.splitlines():
            line = line.strip()
            if line.endswith(".py"):
                test_path = (project_root / line).resolve()
                if test_path.exists():
                    ai_tests.append(str(test_path.relative_to(project_root)))

        test_files_to_run.extend(ai_tests)
    except subprocess.TimeoutExpired:
        logging.error("Ollama request timed out. Skipping AI step.")

# --- Step 6: Run matched tests ---
test_files_to_run = list(set(test_files_to_run))

if not test_files_to_run:
    logging.warning("No relevant test files found.")
    print("No relevant test files found.")
    exit()

logging.info(f"Selected tests to run: {test_files_to_run}")
print("Selected tests to run:\n", "\n".join(test_files_to_run))
os.system(f"pytest {' '.join(test_files_to_run)}")
