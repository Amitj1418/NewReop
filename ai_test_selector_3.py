import os
import subprocess
import logging
from difflib import get_close_matches
import json
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"  # or another installed model

def get_changed_files():
    """Get the list of changed files from Git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        changed_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        logging.info(f"Changed files: {changed_files}")
        return changed_files
    except subprocess.CalledProcessError as e:
        logging.error(f"Error fetching git diff: {e.stderr}")
        return []

def get_changed_methods(changed_files):
    """Stub for changed methods detection."""
    # This should parse AST for actual method changes if needed.
    return set()

def get_all_test_files():
    """Find all test files in the repository."""
    all_tests = []
    for root, dirs, files in os.walk("tests"):
        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                all_tests.append(os.path.join(root, file).replace("\\", "/"))
    return all_tests

def ask_ollama_for_tests(changed_files, changed_methods, repo_tests):
    """Ask Ollama which tests to run, only from existing repo tests."""
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

    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False}
    )
    try:
        output = response.json().get("response", "")
        test_files = [line.strip() for line in output.splitlines() if line.strip()]
        return test_files
    except Exception as e:
        logging.error(f"Error parsing Ollama output: {e}")
        return []

def map_ai_files_to_repo(ai_files, repo_tests):
    """Map AI-suggested files to actual repo test files using fuzzy matching."""
    mapped_files = []
    for ai_file in ai_files:
        if ai_file in repo_tests:
            mapped_files.append(ai_file)
        else:
            matches = get_close_matches(ai_file, repo_tests, n=1, cutoff=0.5)
            if matches:
                mapped_files.append(matches[0])
    return list(set(mapped_files))  # deduplicate

if __name__ == "__main__":
    logging.info("=== AI Test Selector Started ===")
    changed_files = get_changed_files()
    changed_methods = get_changed_methods(changed_files)
    repo_tests = get_all_test_files()

    # Direct match: run changed test files
    changed_test_files = [f for f in changed_files if f in repo_tests]
    if changed_test_files:
        logging.info(f"Running directly changed test files: {changed_test_files}")
        os.system(f"pytest {' '.join(changed_test_files)}")
    else:
        logging.info("No direct matches found, falling back to AI mapping.")
        ai_suggested = ask_ollama_for_tests(changed_files, changed_methods, repo_tests)
        mapped_tests = map_ai_files_to_repo(ai_suggested, repo_tests)

        if mapped_tests:
            logging.info(f"Running AI-selected test files: {mapped_tests}")
            os.system(f"pytest {' '.join(mapped_tests)}")
        else:
            logging.warning("No relevant test files found.")
