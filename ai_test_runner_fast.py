# ai_test_runner_fast_complete.py
import os
import re
import json
import subprocess
import logging
from pathlib import Path
import requests
import hashlib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [INFO] %(message)s")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3"
CACHE_FILE = Path(".cache/ai_test_map.json")
CACHE_FILE.parent.mkdir(exist_ok=True)

# -------------------- Git Utilities -------------------- #
def get_changed_files():
    result = subprocess.run(["git", "diff", "--name-only", "HEAD~1"], capture_output=True, text=True)
    return [f.strip() for f in result.stdout.splitlines() if f.strip().endswith(".py")]

def get_git_diff(file_path):
    result = subprocess.run(["git", "diff", "HEAD~1", "--", file_path], capture_output=True, text=True)
    return result.stdout

def find_all_tests():
    return [str(p.as_posix()) for p in Path("tests").rglob("test_*.py")]

# -------------------- Diff Parsing -------------------- #
def extract_methods_and_locators(diff_text):
    methods = set()
    locators = set()

    # Method definitions
    methods.update(re.findall(r"def\s+(\w+)\s*\(", diff_text))
    # Method calls
    methods.update(re.findall(r"(\w+)\s*\(", diff_text))

    # Direct XPath/CSS selectors
    locators.update(re.findall(r"(//[^\s'\"]+|[.#][A-Za-z0-9_-]+)", diff_text))
    # Locator variables (e.g., LOGIN_BUTTON = "//input[@name='username']")
    locators.update(re.findall(r"([A-Z_]+)\s*=", diff_text))

    return methods, locators

# -------------------- Local Fallback -------------------- #
def local_match_tests(methods, locators, repo_tests):
    matched = set()
    for test_file in repo_tests:
        try:
            content = Path(test_file).read_text()
        except:
            continue
        if any(m in content for m in methods) or any(l in content for l in locators):
            matched.add(Path(test_file).as_posix())
    return matched

# -------------------- AI Selector -------------------- #
def ai_select_tests(methods, locators, repo_tests):
    prompt = f"""
    You are a Python test selector. 
    Changed methods: {list(methods)}
    Changed locators: {list(locators)}
    Available test files: {repo_tests}

    Select ALL test files from the list that could be impacted.
    Output one test file path per line, no explanations, no extra text.
    """
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=30
        )
        output = response.json().get("response", "")
        valid_tests = set(map(lambda p: Path(p).as_posix().strip(), repo_tests))
        selected = set(Path(line.strip()).as_posix() for line in output.splitlines() if Path(line.strip()).as_posix() in valid_tests)
        return selected
    except Exception as e:
        logging.error(f"AI request failed: {e}")
        return set()

# -------------------- Cache -------------------- #
def load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}

def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

# -------------------- Main Runner -------------------- #
def main():
    logging.info("=== Fast + Complete AI Test Runner Started ===")

    commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    cache = load_cache()

    if commit_hash in cache:
        logging.info(f"Using cached test selection for commit {commit_hash}")
        tests_to_run = cache[commit_hash]
    else:
        changed_files = get_changed_files()
        repo_tests = find_all_tests()
        all_methods = set()
        all_locators = set()

        for file in changed_files:
            diff_text = get_git_diff(file)
            methods, locators = extract_methods_and_locators(diff_text)
            all_methods.update(methods)
            all_locators.update(locators)

        ai_tests = ai_select_tests(all_methods, all_locators, repo_tests)
        local_tests = local_match_tests(all_methods, all_locators, repo_tests)

        tests_to_run = sorted(ai_tests.union(local_tests))
        cache[commit_hash] = tests_to_run
        save_cache(cache)

    if not tests_to_run:
        logging.info("No impacted tests found. Exiting.")
        return

    logging.info(f"Running selected tests: {tests_to_run}")
    os.system(f"pytest {' '.join(tests_to_run)}")

if __name__ == "__main__":
    main()
