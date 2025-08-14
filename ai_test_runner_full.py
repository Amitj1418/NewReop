# ai_test_runner_full_v2.py
import os
import re
import logging
import requests
import subprocess
from logging.handlers import RotatingFileHandler

# -----------------------------
# Logging setup
# -----------------------------
LOG_DIR = "logs"
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

# -----------------------------
# Git helpers
# -----------------------------
def run_git_cmd(cmd):
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Git command failed: {e.stderr}")
        return ""

def get_changed_files():
    result = run_git_cmd(["git", "diff", "--name-only", "HEAD~1"])
    return [f.strip() for f in result.splitlines() if f.strip()]

def get_file_diff(file_path):
    return run_git_cmd(["git", "diff", "HEAD~1", "--", file_path])

# -----------------------------
# Test file helpers
# -----------------------------
def get_all_test_files(test_dir="tests"):
    all_tests = []
    for root, _, files in os.walk(test_dir):
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                all_tests.append(os.path.join(root, f).replace("\\", "/"))
    return all_tests

# -----------------------------
# Detect changed methods and locators
# -----------------------------
def get_changed_methods(changed_files):
    changed_methods = set()
    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue
        diff = get_file_diff(file_path)
        current_method = None
        for line in diff.splitlines():
            def_match = re.match(r'^[\+\s-]*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', line)
            if def_match:
                current_method = def_match.group(1)
                continue
            if line.startswith(('+', '-')) and current_method:
                changed_methods.add(current_method)
            if line and not line.startswith((' ', '+', '-')):
                current_method = None
    logging.info(f"Changed methods detected: {changed_methods}")
    return changed_methods

def get_changed_locators(changed_files):
    changed_locators = set()
    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue
        diff = get_file_diff(file_path)
        for line in diff.splitlines():
            locator_match = re.match(r'^[\+\-]\s*([A-Z_0-9]+_LOCATOR)\s*=', line)
            if locator_match:
                changed_locators.add(locator_match.group(1))
    logging.info(f"Changed locators detected: {changed_locators}")
    return changed_locators

def map_locators_to_methods(file_path, changed_locators):
    impacted_methods = set()
    current_method = None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                method_match = re.match(r'^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', line)
                if method_match:
                    current_method = method_match.group(1)
                    continue
                if current_method and any(locator in line for locator in changed_locators):
                    impacted_methods.add(current_method)
    except Exception as e:
        logging.error(f"Error reading {file_path}: {e}")
    return impacted_methods

def find_tests_using_methods(test_files, changed_methods):
    matched_tests = []
    patterns = [re.compile(rf'\b{method}\s*\(') for method in changed_methods]
    for test_file in test_files:
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
            if any(p.search(content) for p in patterns):
                matched_tests.append(test_file)
        except Exception as e:
            logging.error(f"Error reading {test_file}: {e}")
    return matched_tests

# -----------------------------
# AI fallback
# -----------------------------
def ask_ai_for_tests(changed_files, file_diffs, repo_tests):
    prompt = (
        "You are an AI Python test selector.\n"
        "Given the changed files and their diffs, return ALL test files impacted.\n"
        "Do not skip any test. Return one file per line, nothing else.\n\n"
    )
    for f in changed_files:
        diff = file_diffs.get(f, "")
        prompt += f"\nFile: {f}\nDiff:\n{diff}\n"
    prompt += "\nAvailable test files:\n" + "\n".join(repo_tests)
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        logging.error(f"AI request failed: {e}")
        return ""

def parse_ai_selected_tests(output, repo_tests):
    selected = []
    for line in output.splitlines():
        line = line.strip().strip("`")
        if line in repo_tests:
            selected.append(line)
    return selected

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    logging.info("=== Fully AI-Driven Test Runner v2 Started ===")

    changed_files = get_changed_files()
    if not changed_files:
        logging.info("No changed files detected. Exiting.")
        exit(0)

    repo_tests = get_all_test_files()
    if not repo_tests:
        logging.warning("No test files found. Exiting.")
        exit(0)

    # Detect changed methods and locators
    changed_methods = get_changed_methods(changed_files)
    changed_locators = get_changed_locators(changed_files)

    # Map locators to methods
    for file_path in changed_files:
        if changed_locators and file_path.endswith(".py"):
            locator_methods = map_locators_to_methods(file_path, changed_locators)
            changed_methods.update(locator_methods)

    # Find test files impacted by method/locator changes
    method_matched_tests = find_tests_using_methods(repo_tests, changed_methods)

    # Get AI suggestions
    file_diffs = {f: get_file_diff(f) for f in changed_files}
    raw_ai_output = ask_ai_for_tests(changed_files, file_diffs, repo_tests)
    ai_selected_tests = parse_ai_selected_tests(raw_ai_output, repo_tests)

    # Combine all tests and run
    all_tests_to_run = list(set(method_matched_tests + ai_selected_tests))

    if all_tests_to_run:
        logging.info(f"Running all impacted tests: {all_tests_to_run}")
        os.system(f"pytest {' '.join(all_tests_to_run)}")
    else:
        logging.warning("No impacted test files found. Exiting.")
