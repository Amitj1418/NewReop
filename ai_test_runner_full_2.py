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
# Git helpers (UTF-8 safe)
# -----------------------------
def run_git_cmd(cmd):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return (result.stdout or "").strip()
    except Exception as e:
        logging.error(f"Git command failed: {cmd} -> {e}")
        return ""


def get_changed_files():
    try:
        is_ci = os.getenv("GITHUB_ACTIONS", "").lower() == "true"

        if is_ci:
            base_branch = os.getenv("GITHUB_BASE_REF", "main")
            # Avoid error: --unshallow on full clone
            subprocess.run(["git", "fetch", "--prune", "--depth=50"], check=False)
            subprocess.run(["git", "fetch", "origin", base_branch], check=False)
            cmd = ["git", "diff", "--name-only", f"origin/{base_branch}...HEAD"]
        else:
            # Local run
            upstream_branch = run_git_cmd(["git", "rev-parse", "--abbrev-ref", "@{u}"])
            if upstream_branch:
                cmd = ["git", "diff", "--name-only", "@{u}...HEAD"]
            else:
                logging.warning("No upstream branch set. Falling back to last commit comparison.")
                cmd = ["git", "diff", "--name-only", "HEAD~1"]

        result = run_git_cmd(cmd)
        files = [f.strip() for f in result.splitlines() if f.strip()]
        files = [
            f for f in files
            if not (f.startswith("logs/") or f.endswith(".md") or f.endswith(".txt"))
        ]
        return files

    except Exception as e:
        logging.error(f"Failed to get changed files: {e}")
        return []


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
def get_changed_methods(changed_files, file_diffs):
    changed_methods = set()
    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue
        diff = file_diffs.get(file_path, "")
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


def get_changed_locators(changed_files, file_diffs):
    changed_locators = set()
    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue
        diff = file_diffs.get(file_path, "")
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
# AI fallback with strict filtering
# -----------------------------
def ask_ai_for_tests(changed_files, file_diffs, repo_tests):
    repo_tests_list = "\n".join(repo_tests)
    prompt = (
        "You are an AI that selects only impacted pytest files based on the given code changes.\n"
        "RULES:\n"
        "1. Only output test files that EXACTLY match names from the provided list.\n"
        "2. Do not output paths that are not in the list.\n"
        "3. Each output line must be a valid file path, nothing else.\n"
        "4. Avoid unrelated tests. If unsure, return fewer files.\n"
        "5. Output plain text only, no markdown formatting.\n\n"
        f"Available test files:\n{repo_tests_list}\n\n"
        "Changed files and diffs:\n"
    )

    for f in changed_files:
        diff = file_diffs.get(f, "")
        prompt += f"\nFile: {f}\nDiff:\n{diff}\n"

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        raw_output = response.json().get("response", "")

        repo_set = set(repo_tests)
        selected = []
        for line in raw_output.splitlines():
            clean_line = line.strip().lstrip("./").replace("\\", "/")
            if clean_line in repo_set:
                selected.append(clean_line)

        max_allowed = max(5, len(changed_files) * 3)
        if len(selected) > max_allowed:
            logging.warning(f"AI selected {len(selected)} tests — trimming to {max_allowed}.")
            selected = selected[:max_allowed]

        return selected

    except Exception as e:
        logging.error(f"AI request failed: {e}")
        return []


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    logging.info("=== Fully AI-Driven Test Runner v2 (UTF-8 Safe, Corrected) Started ===")

    changed_files = get_changed_files()
    if not changed_files:
        logging.info("No changed files detected. Exiting.")
        exit(0)

    repo_tests = get_all_test_files()
    if not repo_tests:
        logging.warning("No test files found. Exiting.")
        exit(0)

    file_diffs = {f: get_file_diff(f) for f in changed_files}

    changed_methods = get_changed_methods(changed_files, file_diffs)
    changed_locators = get_changed_locators(changed_files, file_diffs)

    for file_path in changed_files:
        if changed_locators and file_path.endswith(".py"):
            locator_methods = map_locators_to_methods(file_path, changed_locators)
            changed_methods.update(locator_methods)

    method_matched_tests = find_tests_using_methods(repo_tests, changed_methods)
    ai_selected_tests = ask_ai_for_tests(changed_files, file_diffs, repo_tests)

    all_tests_to_run = sorted(set(method_matched_tests) | set(ai_selected_tests))

    if all_tests_to_run:
        logging.info(f"Running impacted tests: {all_tests_to_run}")
        os.system(f"pytest {' '.join(all_tests_to_run)}")
    else:
        logging.warning("No impacted test files found. Exiting.")
