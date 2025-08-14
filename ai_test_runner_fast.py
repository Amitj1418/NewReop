import os
import re
import json
import subprocess
import logging
from pathlib import Path

# Config
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3"
CACHE_FILE = Path(".cache/ai_test_map.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# --- Utility functions ---
def run_git_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def get_changed_files():
    return run_git_cmd(["git", "diff", "--name-only", "HEAD~1"]).splitlines()

def get_git_diff(file_path):
    return run_git_cmd(["git", "diff", "HEAD~1", "--", file_path])

def extract_methods_and_locators(diff_text):
    methods = set(re.findall(r"def\s+(\w+)\s*\(", diff_text))
    locators = set(re.findall(r"(//[^\s'\"]+|[.#][A-Za-z0-9_-]+)", diff_text))
    return list(methods), list(locators)

def find_all_tests():
    return [str(p) for p in Path("tests").rglob("test_*.py")]

def ai_select_tests(methods, locators, repo_tests):
    prompt = f"""
    You are an AI test selector for Python.

    CHANGED METHODS:
    {json.dumps(methods, indent=2)}

    CHANGED LOCATORS:
    {json.dumps(locators, indent=2)}

    AVAILABLE TEST FILES:
    {json.dumps(repo_tests, indent=2)}

    Rules:
    - Return ALL test files that reference any of the changed methods or locators.
    - Return only file paths from the AVAILABLE TEST FILES list, one per line.
    - Do not add explanations or formatting.
    """
    import requests
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False}
    )
    output = response.json().get("response", "")
    return [line.strip() for line in output.splitlines() if line.strip() in repo_tests]

def load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}

def save_cache(cache):
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


# --- Main runner ---
def main():
    logging.info("=== Fast AI-Driven Test Runner Started ===")
    commit_hash = run_git_cmd(["git", "rev-parse", "HEAD"])

    # Cache check
    cache = load_cache()
    if commit_hash in cache:
        logging.info("Loaded tests from cache.")
        tests_to_run = cache[commit_hash]
    else:
        changed_files = get_changed_files()
        all_methods, all_locators = set(), set()

        for file in changed_files:
            diff_text = get_git_diff(file)
            methods, locators = extract_methods_and_locators(diff_text)
            all_methods.update(methods)
            all_locators.update(locators)

        repo_tests = find_all_tests()
        tests_to_run = ai_select_tests(list(all_methods), list(all_locators), repo_tests)

        # Save to cache
        cache[commit_hash] = tests_to_run
        save_cache(cache)

    if not tests_to_run:
        logging.warning("No impacted tests found.")
        return

    logging.info(f"Running tests: {tests_to_run}")
    os.system(f"pytest {' '.join(tests_to_run)}")


if __name__ == "__main__":
    main()
