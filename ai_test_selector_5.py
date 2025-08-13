import os
import re
import subprocess
import logging
import requests
import json
from difflib import get_close_matches
from logging.handlers import RotatingFileHandler

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

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"

# -----------------------------
# Git helpers
# -----------------------------
def run_git_cmd(cmd):
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


def get_changed_files():
    result = run_git_cmd(["git", "diff", "--name-only", "HEAD~1"])
    changed_files = [f.strip() for f in result.split("\n") if f.strip()]
    logging.info(f"Changed files: {changed_files}")
    return changed_files


def get_changed_methods(changed_files):
    changed_methods = set()
    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue

        diff_output = run_git_cmd(["git", "diff", "HEAD~1", "--", file_path])
        if not diff_output:
            continue

        current_method = None
        for line in diff_output.splitlines():
            def_match = re.match(r'^[\+\s-]*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', line)
            if def_match:
                current_method = def_match.group(1)
                continue

            if line.startswith(('+', '-')) and not line.startswith(('+++', '---')) and current_method:
                changed_methods.add(current_method)

            if line and not line.startswith((' ', '+', '-')):
                current_method = None

    logging.info(f"Changed methods detected: {changed_methods}")
    return changed_methods

# -----------------------------
# Locator helpers
# -----------------------------
def get_changed_locators(changed_files):
    changed_locators = set()
    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue

        diff_output = run_git_cmd(["git", "diff", "HEAD~1", "--", file_path])
        if not diff_output:
            continue

        for line in diff_output.splitlines():
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

# -----------------------------
# Test file helpers
# -----------------------------
def get_all_test_files():
    all_tests = []
    for root, _, files in os.walk("tests"):
        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                all_tests.append(os.path.join(root, file).replace("\\", "/"))
    return all_tests


def find_tests_using_methods(test_files, changed_methods):
    matched_tests = []
    patterns = [
        re.compile(rf'\b{method}\s*\(') for method in changed_methods
    ] + [
        re.compile(rf'\.\s*{method}\s*\(') for method in changed_methods
    ]
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
def ask_ollama_for_tests(changed_files, changed_methods, repo_tests):
    prompt = f"""
You are an AI test file selector.
You must ONLY choose from the provided list of real test files in the repo.

Changed files:
{json.dumps(changed_files)}

Changed methods:
{json.dumps(list(changed_methods))}

Available test files in the repo:
{json.dumps(repo_tests)}

Return ONLY the paths from the list of available test files that are most likely impacted.
Return one file per line, nothing else.
"""
    response = requests.post(OLLAMA_URL, json={"model": MODEL, "prompt": prompt, "stream": False})
    try:
        output = response.json().get("response", "")
        return [line.strip() for line in output.splitlines() if line.strip()]
    except Exception as e:
        logging.error(f"Error parsing Ollama output: {e}")
        return []


def map_ai_files_to_repo(ai_files, repo_tests):
    mapped_files = []
    for ai_file in ai_files:
        if ai_file in repo_tests:
            mapped_files.append(ai_file)
        else:
            matches = get_close_matches(ai_file, repo_tests, n=1, cutoff=0.5)
            if matches:
                mapped_files.append(matches[0])
    return list(set(mapped_files))

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    logging.info("=== AI Test Selector Started ===")
    changed_files = get_changed_files()
    changed_methods = get_changed_methods(changed_files)

    # Detect locator changes and map to methods
    changed_locators = get_changed_locators(changed_files)
    for file_path in changed_files:
        if changed_locators and file_path.endswith(".py"):
            locator_methods = map_locators_to_methods(file_path, changed_locators)
            changed_methods.update(locator_methods)

    repo_tests = get_all_test_files()

    # Step 1 — Direct match by changed test file
    changed_test_files = [f for f in changed_files if f in repo_tests]
    if changed_test_files:
        logging.info(f"Running directly changed test files: {changed_test_files}")
        os.system(f"pytest {' '.join(changed_test_files)}")
        exit(0)

    # Step 2 — Match tests by method usage
    method_matched_tests = find_tests_using_methods(repo_tests, changed_methods)
    if method_matched_tests:
        logging.info(f"Running tests that reference changed methods: {method_matched_tests}")
        os.system(f"pytest {' '.join(method_matched_tests)}")
        exit(0)

    # Step 3 — Fallback to AI
    ai_suggested = ask_ollama_for_tests(changed_files, changed_methods, repo_tests)
    mapped_tests = map_ai_files_to_repo(ai_suggested, repo_tests)

    if mapped_tests:
        logging.info(f"Running AI-selected test files: {mapped_tests}")
        os.system(f"pytest {' '.join(mapped_tests)}")
    else:
        logging.warning("No relevant test files found.")
