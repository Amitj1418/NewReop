import os
import re
import sys
import logging
import subprocess
from pathlib import Path
import requests
from datetime import datetime

# === Logging setup ===
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"ai_test_selector_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)]
)

logging.info("=== AI Test Selector Started ===")
logging.debug(f"sys.platform='{sys.platform}', git_executable='git'")

# === Git diff retrieval ===
def get_changed_lines():
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "--cached", "--unified=0", "HEAD"],
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

diff_content = get_changed_lines()

# === Step 1: Filter changed files (ignore logs) ===
changed_files = [
    f for f in re.findall(r"\+\+\+ b/(.+)", diff_content)
    if not f.startswith("logs/") and f.endswith(".py")
]
logging.info(f"Changed files: {changed_files}")

# === Step 2: Identify changed test files & methods ===
changed_test_files = []
changed_methods = set()
project_root = Path(__file__).parent

for f in changed_files:
    if f.startswith("tests/"):
        changed_test_files.append(f)
    elif f.startswith("pages/"):
        try:
            file_path = project_root / f
            with open(file_path, "r", encoding="utf-8", errors="ignore") as src:
                content = src.read()
                methods = re.findall(r"^\s*def\s+(\w+)", content, re.MULTILINE)
                changed_methods.update(methods)
        except FileNotFoundError:
            logging.warning(f"File not found for method scan: {f}")

logging.info(f"Changed methods: {changed_methods}")
logging.info(f"Changed test files: {changed_test_files}")

# === Step 3: Map changed methods to tests ===
selected_tests = set(changed_test_files)

if changed_methods:
    tests_dir = project_root / "tests"
    for test_file in tests_dir.glob("test_*.py"):
        try:
            content = test_file.read_text(encoding="utf-8", errors="ignore")
            for method in changed_methods:
                if re.search(rf"\b{method}\b", content):
                    logging.info(f"Matched method '{method}' in test file: {test_file}")
                    selected_tests.add(str(test_file))
        except Exception as e:
            logging.error(f"Error reading test file {test_file}: {e}")

# === Step 4: Fallback to AI (Ollama) if nothing found ===
if not selected_tests and changed_files:
    logging.info("No direct matches found, falling back to AI mapping.")
    try:
        prompt = (
            "Given the changed files:\n" + "\n".join(changed_files) +
            "\nSuggest relevant pytest test files from 'tests/' directory to run."
        )
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral", "prompt": prompt, "stream": False},
            timeout=25
        )
        if resp.status_code == 200:
            ai_output = resp.json().get("response", "")
            logging.debug(f"Ollama AI output: {ai_output}")
            for match in re.findall(r"tests[\\/][\w_]+\.py", ai_output):
                if os.path.exists(match):
                    selected_tests.add(match)
        else:
            logging.error(f"Ollama request failed: {resp.status_code}")
    except requests.exceptions.Timeout:
        logging.error("Ollama request timed out. Skipping AI step.")
    except Exception as e:
        logging.error(f"Ollama request failed: {e}")

# === Step 5: Run pytest or exit ===
if selected_tests:
    logging.info(f"Selected tests to run: {list(selected_tests)}")
    test_args = ["pytest"] + list(selected_tests)
    subprocess.run(test_args)
else:
    logging.warning("No relevant test files found.")
