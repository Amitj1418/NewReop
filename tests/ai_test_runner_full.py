# ai_test_runner_full.py
import os
import logging
import requests
from logging.handlers import RotatingFileHandler
import subprocess

# -----------------------------
# Logging setup
# -----------------------------
LOG_DIR = "../logs"
os.makedirs(LOG_DIR, exist_ok=True)

file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "ai_test_selector.log"),
    maxBytes=1_000_000,
    backupCount=5,
    encoding="utf-8"
)
console_handler = logging.StreamHandler()

log_format = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(log_format)
console_handler.setFormatter(log_format)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

# -----------------------------
# AI + Git setup
# -----------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"

def run_git_cmd(cmd):
    """Run git command and return stdout"""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Git command failed: {e.stderr}")
        return ""

def get_changed_files():
    """Get list of changed files from last commit"""
    result = run_git_cmd(["git", "diff", "--name-only", "HEAD~1"])
    return [f.strip() for f in result.splitlines() if f.strip()]

def get_file_diff(file_path):
    """Get full diff of a single file"""
    return run_git_cmd(["git", "diff", "HEAD~1", "--", file_path])

def get_all_test_files(test_dir="tests"):
    """Get all test files in repo"""
    all_tests = []
    for root, _, files in os.walk(test_dir):
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                all_tests.append(os.path.join(root, f).replace("\\", "/"))
    return all_tests

def ask_ai_for_tests(changed_files, file_diffs, repo_tests):
    """Ask AI to select impacted tests using file diffs"""
    prompt = (
        "You are an AI Python test selector.\n\n"
        "Given the following changed files and their diffs in a Python repo, "
        "select which test files should run.\n\n"
        "Changed files with diffs:\n"
    )

    for f in changed_files:
        diff = file_diffs.get(f, "")
        prompt += f"\nFile: {f}\nDiff:\n{diff}\n"

    prompt += "\nAvailable test files:\n"
    for t in repo_tests:
        prompt += f"{t}\n"

    prompt += (
        "\nReturn ONLY the paths of the test files from the list above "
        "that are most likely impacted, one per line, nothing else."
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        output = response.json().get("response", "")
        selected = [line.strip() for line in output.splitlines() if line.strip()]
        logging.info(f"AI suggested tests: {selected}")
        return selected
    except Exception as e:
        logging.error(f"AI request failed: {e}")
        return []

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    logging.info("=== Fully AI-Driven Test Runner Started ===")

    changed_files = get_changed_files()
    if not changed_files:
        logging.info("No changed files detected. Exiting.")
        exit(0)

    repo_tests = get_all_test_files()
    if not repo_tests:
        logging.warning("No test files found in repo. Exiting.")
        exit(0)

    # Get diffs for changed files
    file_diffs = {f: get_file_diff(f) for f in changed_files}

    # Ask AI which tests to run
    tests_to_run = ask_ai_for_tests(changed_files, file_diffs, repo_tests)

    if tests_to_run:
        logging.info(f"Running selected tests: {tests_to_run}")
        os.system(f"pytest {' '.join(tests_to_run)}")
    else:
        logging.warning("No relevant test files selected by AI. Exiting.")
