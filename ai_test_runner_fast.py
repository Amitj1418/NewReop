import subprocess
import os
import logging
import requests

# === CONFIG ===
MODEL = "mistral"   # Ollama model name
OLLAMA_URL = "http://localhost:11434/api/generate"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


def run_git_cmd(args):
    """Run a git command and return its output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return result.stdout.decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError as e:
        logging.error(f"Git command failed: {e}")
        return ""


def get_changed_files():
    """Get changed files from the last commit."""
    output = run_git_cmd(["diff", "--name-only", "HEAD~1", "HEAD"])
    files = [line.strip() for line in output.splitlines() if line.strip()]
    logging.info(f"Changed files: {files}")
    return files


def get_diffs_for_changed_files(changed_files):
    """Get full diffs for changed files."""
    diffs = {}
    for file_path in changed_files:
        diff_output = run_git_cmd(["diff", "HEAD~1", "HEAD", "--", file_path])
        if diff_output:
            diffs[file_path] = diff_output
    logging.info(f"Collected diffs for {len(diffs)} changed files.")
    return diffs


def get_all_test_files():
    """Find all test files in repo."""
    test_files = []
    for root, _, files in os.walk("."):
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                test_files.append(os.path.join(root, f))
    logging.info(f"Total test files found: {len(test_files)}")
    return test_files


def ai_select_tests(changed_files, diffs, repo_tests, model=MODEL):
    """
    Fully AI-driven test selection using file diffs and repo test list.
    """
    prompt = f"""
You are an AI test selector for a Python project.

### Rules:
1. You must ONLY pick test files from the AVAILABLE TEST FILES list.
2. A test file should be selected if:
   - It is directly changed.
   - It uses a method or locator that was modified.
   - A method it depends on had any code change inside.
3. Consider changed methods, locators, and function names from the DIFFS.
4. Output one matching test file path per line. No explanations.

### CHANGED FILES:
{changed_files}

### DIFFS:
{diffs}

### AVAILABLE TEST FILES:
{repo_tests}
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        output = response.json().get("response", "")
        selected = [line.strip() for line in output.splitlines() if line.strip()]
        logging.info(f"AI selected tests: {selected}")
        return selected
    except Exception as e:
        logging.error(f"AI test selection failed: {e}")
        return []


def main():
    logging.info("=== Fully AI-Driven Test Runner Started ===")

    changed_files = get_changed_files()
    if not changed_files:
        logging.warning("No changed files detected.")
        return

    diffs = get_diffs_for_changed_files(changed_files)
    repo_tests = get_all_test_files()

    selected_tests = ai_select_tests(changed_files, diffs, repo_tests)

    if selected_tests:
        logging.info(f"Running selected tests: {selected_tests}")
        os.system(f"pytest {' '.join(selected_tests)}")
    else:
        logging.warning("No tests selected by AI.")


if __name__ == "__main__":
    main()
