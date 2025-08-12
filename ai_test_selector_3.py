import os
import re
import subprocess
import logging
from pathlib import Path
from git import Repo
from datetime import datetime

# === Logging ===
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

# === Step 1: Get changed lines ===
def get_changed_lines():
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

# === Step 2: Extract changed files & methods ===
changed_files = re.findall(r"\+\+\+ b/(.+)", diff_content)
changed_methods = set()
changed_test_files = []

for f in changed_files:
    if f.startswith("tests/") and f.endswith(".py"):
        changed_test_files.append(f)

changed_methods.update(re.findall(r"^\+\s*def\s+(\w+)", diff_content, re.MULTILINE))

logging.info(f"Changed files: {changed_files}")
logging.info(f"Changed methods: {changed_methods}")
logging.info(f"Changed test files: {changed_test_files}")

# === Step 3: Get all test files ===
all_test_files = []
for root, _, files in os.walk("tests"):
    for file in files:
        if file.startswith("test") and file.endswith(".py"):
            all_test_files.append(os.path.join(root, file))

if not all_test_files:
    logging.warning("No test files found.")
    print("No test files found.")
    exit()

# === Step 4: Scenario Selection ===
test_files_to_run = []

# 1️⃣ If a test file itself changed, run it directly
if changed_test_files:
    logging.info("Detected direct changes in test files.")
    test_files_to_run.extend(changed_test_files)

# 2️⃣ If a page method changed, find impacted tests only
elif changed_methods:
    for test_file in all_test_files:
        with open(test_file, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
            for method in changed_methods:
                if re.search(rf"\b{method}\s*\(", code):
                    logging.info(f"Impacted test: {test_file} (uses {method}())")
                    test_files_to_run.append(test_file)

# 3️⃣ AI fallback if nothing matched
if not test_files_to_run:
    logging.info("No direct matches found, falling back to AI mapping.")
    prompt = (
        "You are an AI that maps Python code changes to pytest test files.\n"
        f"Changed files: {changed_files}\n"
        f"Changed methods: {', '.join(changed_methods) if changed_methods else 'None'}\n"
        "Return ONLY the pytest test file paths (starting with tests/) "
        "that are most likely to be affected. One per line."
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

        for line in ai_output.splitlines():
            line = line.strip()
            if line.endswith(".py"):
                path = (project_root / line).resolve()
                if path.exists():
                    test_files_to_run.append(str(path.relative_to(project_root)))
    except subprocess.TimeoutExpired:
        logging.error("Ollama request timed out. Skipping AI step.")

# === Step 5: Run matched tests ===
test_files_to_run = list(set(test_files_to_run))
if not test_files_to_run:
    logging.warning("No relevant test files found.")
    print("No relevant test files found.")
    exit()

logging.info(f"Selected tests to run: {test_files_to_run}")
print("Selected tests to run:\n", "\n".join(test_files_to_run))
os.system(f"pytest {' '.join(test_files_to_run)}")
