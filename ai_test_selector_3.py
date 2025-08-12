import os
import subprocess
import ast
import logging
from pathlib import Path
import ollama
import re

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ------------------------
# Git Utils
# ------------------------
def get_changed_files():
    """Return list of changed files in the last commit."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True, text=True
    )
    files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    return files

def get_changed_methods(file_path):
    """Extract changed method names from a Python file diff."""
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD", "--", file_path],
        capture_output=True, text=True
    )
    diff_text = result.stdout
    method_pattern = re.compile(r"^\+?\s*def\s+([a-zA-Z_]\w*)\s*\(", re.MULTILINE)
    return set(method_pattern.findall(diff_text))

# ------------------------
# AST Utils
# ------------------------
def get_called_methods_in_test(test_file):
    """Return set of method names directly called in the test file."""
    called_methods = set()
    try:
        with open(test_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=test_file)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called_methods.add(node.func.attr)
    except Exception as e:
        logging.warning(f"Could not parse {test_file}: {e}")
    return called_methods

# ------------------------
# AI Mapping (Fallback)
# ------------------------
def ai_map_files_to_tests(changed_files):
    """Ask Ollama which test files are relevant."""
    prompt = f"""
You are given changed source files:
{changed_files}

Return a Python list of test file paths that are most likely to be affected.
Only include test files that exist in the repo.
    """
    response = ollama.chat(model="mistral", messages=[
        {"role": "system", "content": "You are an AI that maps changed code to relevant tests."},
        {"role": "user", "content": prompt}
    ])
    text = response["message"]["content"]
    return re.findall(r"tests[^\s'\"]+\.py", text)

# ------------------------
# Main Selector
# ------------------------
def main():
    logging.info("=== AI Test Selector Started ===")
    changed_files = get_changed_files()
    logging.info(f"Changed files: {changed_files}")

    # Step 1: Method-level matching
    changed_methods = set()
    for f in changed_files:
        if f.endswith(".py") and Path(f).exists():
            changed_methods |= get_changed_methods(f)
    logging.info(f"Changed methods: {changed_methods}")

    # Step 2: Direct test matching
    matched_tests = []
    if changed_methods:
        for test_file in Path("tests").rglob("test_*.py"):
            calls = get_called_methods_in_test(test_file)
            if changed_methods & calls:
                matched_tests.append(str(test_file))

    matched_tests = list(set(matched_tests))
    logging.info(f"Method-level matched tests: {matched_tests}")

    # Step 3: AI Fallback if no matches
    if not matched_tests:
        logging.info("No direct matches found, falling back to AI mapping...")
        ai_tests = ai_map_files_to_tests(changed_files)
        matched_tests = [t for t in ai_tests if Path(t).exists()]

    # Final output
    if matched_tests:
        logging.info(f"Selected test files: {matched_tests}")
        subprocess.run(["pytest", "-v"] + matched_tests)
    else:
        logging.warning("No relevant test files found.")

if __name__ == "__main__":
    main()
