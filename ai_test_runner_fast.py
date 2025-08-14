# ai_test_runner_fast_complete_ai_only.py
import os
import json
import subprocess
import logging
from pathlib import Path
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [INFO] %(message)s")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3"
CACHE_FILE = Path(".cache/ai_test_map.json")
CACHE_FILE.parent.mkdir(exist_ok=True)


# -------------------- Git Utilities -------------------- #
def get_changed_files():
    """Get all changed Python files in the last commit."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1"],
        capture_output=True,
        text=True
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip().endswith(".py")]


def get_git_diff(file_path):
    """Get the git diff for a given file."""
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "--", file_path],
        capture_output=True,
        text=True
    )
    return result.stdout


def find_all_tests():
    """Find all available test files in the repo."""
    return [str(p.as_posix()) for p in Path("tests").rglob("test_*.py")]


# -------------------- AI Selector -------------------- #
def ai_select_tests(diff_texts, repo_tests):
    prompt = f"""
You are an AI Python test impact analyzer.

Recent CHANGES (from git diff):
{diff_texts}

AVAILABLE TEST FILES:
{repo_tests}

Selection Rules:
1. If a method is added, removed, renamed, or its body changes → run all tests that use it.
2. If any locator (XPath, CSS selector, variable holding locator) changes → run all tests that use it.
3. If any method's code logic changes (even without name change) → run all tests linked to that method.
4. Return ONLY the impacted test file paths, EXACTLY as they appear in the AVAILABLE TEST FILES list.
5. Output ONE file path per line, no explanations, no extra text.
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=60
        )
        output = response.json().get("response", "")
        valid_tests = set(Path(p).as_posix() for p in repo_tests)

        # Only keep valid test files in final set
        selected = {
            Path(line.strip()).as_posix()
            for line in output.splitlines()
            if Path(line.strip()).as_posix() in valid_tests
        }
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
    logging.info("=== Fully AI-Driven Test Runner Started ===")

    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True
    ).stdout.strip()

    cache = load_cache()

    if commit_hash in cache:
        logging.info(f"Using cached test selection for commit {commit_hash}")
        tests_to_run = cache[commit_hash]
    else:
        changed_files = get_changed_files()
        if not changed_files:
            logging.info("No changed Python files detected.")
            return

        repo_tests = find_all_tests()
        diff_texts = "\n\n".join(get_git_diff(f) for f in changed_files)

        ai_tests = ai_select_tests(diff_texts, repo_tests)

        if not ai_tests:
            logging.warning("AI did not select any tests — no tests will be run.")
            return

        tests_to_run = sorted(ai_tests)
        cache[commit_hash] = tests_to_run
        save_cache(cache)

    logging.info(f"Running selected tests: {tests_to_run}")
    os.system(f"pytest {' '.join(tests_to_run)}")


if __name__ == "__main__":
    main()
