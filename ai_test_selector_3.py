import os
import subprocess
import logging
import json
import requests
import ast
from difflib import get_close_matches

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"  # installed Ollama model

def run_git_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()

def get_changed_files():
    """Get changed files from the last commit."""
    output = run_git_cmd(["git", "diff", "--name-only", "HEAD~1"])
    changed_files = [f for f in output.split("\n") if f.strip()]
    logging.info(f"Changed files: {changed_files}")
    return changed_files

def get_changed_methods(changed_files):
    """Extract method names from changed code."""
    changed_methods = set()
    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue
        diff_output = run_git_cmd(["git", "diff", "HEAD~1", "--", file_path])
        for line in diff_output.splitlines():
            if line.startswith("+") and "def " in line:
                try:
                    tree = ast.parse(line[1:])
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            changed_methods.add(node.name)
                except Exception:
                    pass
    logging.info(f"Changed methods: {changed_methods}")
    return changed_methods

def get_all_test_files():
    """List all test files."""
    return [
        os.path.join(root, f).replace("\\", "/")
        for root, _, files in os.walk("tests")
        for f in files if f.startswith("test_") and f.endswith(".py")
    ]

def find_tests_using_methods(methods, test_files):
    """Find test files that use changed methods."""
    matched = []
    for tf in test_files:
        try:
            with open(tf, encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if any(m in content for m in methods):
                    matched.append(tf)
        except Exception as e:
            logging.error(f"Error reading {tf}: {e}")
    return matched

def ask_ollama_for_tests(changed_files, changed_methods, repo_tests):
    prompt = f"""
You are an AI test file selector.
You MUST choose ONLY from the provided repo test files.

Changed files:
{json.dumps(changed_files)}

Changed methods:
{json.dumps(list(changed_methods))}

Available test files:
{json.dumps(repo_tests)}

Return ONLY exact paths from the list above that are most likely impacted.
One per line, nothing else.
"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False}
        )
        output = response.json().get("response", "")
        return [line.strip() for line in output.splitlines() if line.strip()]
    except Exception as e:
        logging.error(f"Error talking to Ollama: {e}")
        return []

def map_ai_files_to_repo(ai_files, repo_tests):
    mapped = []
    for ai_file in ai_files:
        if ai_file in repo_tests:
            mapped.append(ai_file)
        else:
            match = get_close_matches(ai_file, repo_tests, n=1, cutoff=0.5)
            if match:
                mapped.append(match[0])
    return list(set(mapped))

if __name__ == "__main__":
    logging.info("=== AI Test Selector Started ===")
    changed_files = get_changed_files()
    changed_methods = get_changed_methods(changed_files)
    repo_tests = get_all_test_files()

    # First: deterministic direct match
    matched_tests = find_tests_using_methods(changed_methods, repo_tests)

    if matched_tests:
        logging.info(f"Running direct method-matched tests: {matched_tests}")
        os.system(f"pytest {' '.join(matched_tests)}")
    else:
        logging.info("No direct matches found, using AI fallback.")
        ai_suggested = ask_ollama_for_tests(changed_files, changed_methods, repo_tests)
        mapped_tests = map_ai_files_to_repo(ai_suggested, repo_tests)

        if mapped_tests:
            logging.info(f"Running AI-selected tests: {mapped_tests}")
            os.system(f"pytest {' '.join(mapped_tests)}")
        else:
            logging.warning("No relevant test files found.")
