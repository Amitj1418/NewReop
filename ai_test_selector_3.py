import os
import re
import subprocess
import logging
from pathlib import Path
from git import Repo
from datetime import datetime
import json

# === Setup logging ===
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

# === Step 1: Get changed files ===
def get_changed_files():
    try:
        output = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            encoding="utf-8",
            errors="replace"
        ).strip().splitlines()
        return [f for f in output if f and not f.startswith("logs/") and not f.endswith(".log")]
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting changed files: {e}")
        return []

changed_files = get_changed_files()
logging.info(f"Changed files: {changed_files}")

# === Step 2: Detect changed methods ===
def get_changed_methods():
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "-U0", "HEAD~1", "HEAD"],
            encoding="utf-8",
            errors="replace"
        )
        return set(re.findall(r"^\+\s*def\s+(\w+)", diff_output, re.MULTILINE))
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting git diff: {e}")
        return set()

changed_methods = get_changed_methods()
logging.info(f"Changed methods: {changed_methods}")

# === Step 3: Changed test files ===
changed_test_files = [
    f for f in changed_files if f.startswith("tests/") and f.endswith(".py")
]
logging.info(f"Changed test files: {changed_test_files}")

if changed_test_files:
    logging.info("Running directly changed test files.")
    os.system(f"pytest {' '.join(changed_test_files)}")
    exit()

# === Step 4: Match methods to test files ===
test_files_to_run = []

if changed_methods:
    all_test_files = []
    for root, _, files in os.walk("tests"):
        for f in files:
            if f.startswith("test") and f.endswith(".py"):
                all_test_files.append(os.path.join(root, f))

    for test_file in all_test_files:
        try:
            with open(test_file, "r", encoding="utf-8", errors="ignore") as tf:
                test_code = tf.read()
                for method in changed_methods:
                    if re.search(rf"\b{method}\b", test_code):
                        test_files_to_run.append(test_file)
                        logging.info(f"Matched method '{method}' in {test_file}")
                        break
        except Exception as e:
            logging.error(f"Error reading {test_file}: {e}")

# === Step 5: AI fallback with Ollama ===
if not test_files_to_run and changed_files:
    logging.info("No direct matches found, falling back to AI mapping.")

    prompt = (
        "You are an AI that maps Python code changes to pytest test files.\n"
        "Changed files:\n" + "\n".join(changed_files) + "\n"
        "Changed methods:\n" + (", ".join(changed_methods) if changed_methods else "None") + "\n\n"
        "Return ONLY the pytest test file paths (starting with tests/) "
        "that are most likely to be affected. One per line. No explanations."
    )

    try:
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST", "http://localhost:11434/api/generate",
                "-d", json.dumps({
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False
                })
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=30
        )

        ai_response = json.loads(result.stdout)
        ai_output = ai_response.get("response", "").strip()
        logging.info(f"Ollama AI Output:\n{ai_output}")

        # Clean and fuzzy match AI output
        all_tests = []
        for root, _, files in os.walk("tests"):
            for f in files:
                if f.endswith(".py"):
                    all_tests.append(os.path.join(root, f))

        for line in ai_output.splitlines():
            line = line.strip().split()[0]  # Remove extra text
            if not line.endswith(".py"):
                continue
            if os.path.exists(line):
                test_files_to_run.append(line)
            else:
                # Fuzzy match by filename
                fname = os.path.basename(line)
                for real_test in all_tests:
                    if real_test.endswith(fname):
                        test_files_to_run.append(real_test)
                        break

    except subprocess.TimeoutExpired:
        logging.error("Ollama request timed out. Skipping AI step.")
    except Exception as e:
        logging.error(f"Ollama AI request failed: {e}")

# === Step 6: Run selected tests ===
test_files_to_run = list(set(test_files_to_run))
if not test_files_to_run:
    logging.warning("No relevant test files found.")
    print("No relevant test files found.")
    exit()

logging.info(f"Selected tests to run: {test_files_to_run}")
print("Selected tests to run:\n", "\n".join(test_files_to_run))
os.system(f"pytest {' '.join(test_files_to_run)}")
