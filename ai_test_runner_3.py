import os
import re
import subprocess
import logging
import requests
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import get_close_matches
from logging.handlers import RotatingFileHandler
from typing import List, Dict, Set, Optional, Tuple

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
TEST_HISTORY_FILE = ".test_execution_history.json"
MAX_PARALLEL_TESTS = 4
TEST_TIMEOUT = 300  # 5 minutes per test
RETRY_ATTEMPTS = 2


# -----------------------------
# Git helpers
# -----------------------------
def run_git_cmd(cmd, timeout=30):
    """Enhanced git command runner with timeout and better error handling."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=timeout
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logging.error(f"Git command timed out: {' '.join(cmd)}")
        return ""
    except subprocess.CalledProcessError as e:
        logging.error(f"Git command failed: {e.stderr}")
        return ""
    except Exception as e:
        logging.error(f"Unexpected error in git command: {e}")
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
def ask_ollama_for_tests(changed_files, changed_methods, repo_tests, test_history=None):
    """Enhanced AI test selection with historical context and smart prompting."""
    try:
        # Include historical context for smarter decisions
        history_context = ""
        if test_history:
            recent_failures = [test for test, data in test_history.items()
                               if data.get('recent_failures', 0) > 0]
            if recent_failures:
                history_context = f"\nRecently failed tests (higher priority): {recent_failures[:5]}"

        prompt = f"""
You are an expert AI test selector for a Python test automation framework.
Analyze the code changes and select the most relevant tests with high precision.

Changed files:
{json.dumps(changed_files, indent=2)}

Changed methods/functions:
{json.dumps(list(changed_methods), indent=2)}

Available test files in repository:
{json.dumps(repo_tests, indent=2)}
{history_context}

Analysis criteria:
1. Direct impact: Tests that directly use changed methods
2. Integration impact: Tests that might be affected by changes in dependencies
3. Critical path: Tests for core user workflows
4. Historical patterns: Tests that frequently fail when similar changes occur

Instructions:
- Return ONLY file paths from the available test files list
- Prioritize tests most likely to catch issues from these changes
- Maximum 5 test files unless changes are extensive
- One file path per line, no extra text
"""

        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=30
        )

        if response.status_code != 200:
            logging.error(f"Ollama API error: {response.status_code}")
            return []

        output = response.json().get("response", "")
        suggested_tests = [line.strip() for line in output.splitlines() if line.strip()]

        logging.info(f"AI suggested {len(suggested_tests)} tests: {suggested_tests}")
        return suggested_tests[:5]  # Limit to top 5 suggestions

    except requests.exceptions.Timeout:
        logging.error("Ollama request timed out")
        return []
    except requests.exceptions.ConnectionError:
        logging.warning("Ollama not available, skipping AI analysis")
        return []
    except Exception as e:
        logging.error(f"Error in AI test selection: {e}")
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
# Test execution and history tracking
# -----------------------------
def load_test_history() -> Dict:
    """Load historical test execution data."""
    try:
        if os.path.exists(TEST_HISTORY_FILE):
            with open(TEST_HISTORY_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Error loading test history: {e}")
    return {}


def save_test_history(history: Dict):
    """Save test execution history."""
    try:
        with open(TEST_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logging.error(f"Error saving test history: {e}")


def update_test_metrics(test_file: str, execution_time: float, success: bool, history: Dict):
    """Update test execution metrics."""
    if test_file not in history:
        history[test_file] = {
            'execution_times': [],
            'success_rate': [],
            'recent_failures': 0,
            'total_runs': 0
        }

    test_data = history[test_file]
    test_data['execution_times'].append(execution_time)
    test_data['success_rate'].append(success)
    test_data['total_runs'] += 1

    # Keep only last 20 records
    if len(test_data['execution_times']) > 20:
        test_data['execution_times'] = test_data['execution_times'][-20:]
        test_data['success_rate'] = test_data['success_rate'][-20:]

    # Update recent failures counter
    recent_runs = test_data['success_rate'][-5:]  # Last 5 runs
    test_data['recent_failures'] = sum(1 for result in recent_runs if not result)


def run_test_with_monitoring(test_file: str) -> Tuple[bool, float]:
    """Run a single test with monitoring and retry logic."""
    start_time = time.time()

    for attempt in range(RETRY_ATTEMPTS):
        try:
            logging.info(f"Running test {test_file} (attempt {attempt + 1}/{RETRY_ATTEMPTS})")

            result = subprocess.run(
                ["pytest", test_file, "-v", "--tb=short", "-x"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=TEST_TIMEOUT
            )

            execution_time = time.time() - start_time
            success = result.returncode == 0

            if success or attempt == RETRY_ATTEMPTS - 1:
                if not success:
                    logging.error(f"Test {test_file} failed after {RETRY_ATTEMPTS} attempts")
                    logging.error(f"Error output: {result.stderr}")
                return success, execution_time

        except subprocess.TimeoutExpired:
            logging.error(f"Test {test_file} timed out (attempt {attempt + 1})")
            if attempt == RETRY_ATTEMPTS - 1:
                return False, time.time() - start_time
        except Exception as e:
            logging.error(f"Error running test {test_file}: {e}")
            if attempt == RETRY_ATTEMPTS - 1:
                return False, time.time() - start_time

        time.sleep(2)  # Brief pause before retry

    return False, time.time() - start_time


def run_tests_intelligently(test_files: List[str], history: Dict) -> bool:
    """Run tests with intelligent parallel execution and prioritization."""
    if not test_files:
        return True

    # Prioritize tests based on historical data
    def get_priority_score(test_file):
        if test_file not in history:
            return 50  # Medium priority for unknown tests

        data = history[test_file]
        recent_failures = data.get('recent_failures', 0)
        avg_time = sum(data.get('execution_times', [30])) / len(data.get('execution_times', [1]))

        # Higher score = higher priority
        score = recent_failures * 20  # Prioritize recently failed tests
        score += min(60 / max(avg_time, 1), 30)  # Slightly favor faster tests
        return score

    prioritized_tests = sorted(test_files, key=get_priority_score, reverse=True)
    logging.info(f"Test execution order: {prioritized_tests}")

    # Run critical tests first sequentially, then parallel
    critical_tests = prioritized_tests[:2]  # Top 2 priority tests
    remaining_tests = prioritized_tests[2:]

    all_success = True

    # Run critical tests sequentially for immediate feedback
    for test_file in critical_tests:
        success, exec_time = run_test_with_monitoring(test_file)
        update_test_metrics(test_file, exec_time, success, history)

        if not success:
            all_success = False
            logging.error(f"Critical test {test_file} failed, continuing with remaining tests...")

    # Run remaining tests in parallel
    if remaining_tests:
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_TESTS, len(remaining_tests))) as executor:
            future_to_test = {executor.submit(run_test_with_monitoring, test): test
                              for test in remaining_tests}

            for future in as_completed(future_to_test):
                test_file = future_to_test[future]
                try:
                    success, exec_time = future.result()
                    update_test_metrics(test_file, exec_time, success, history)

                    if not success:
                        all_success = False
                        logging.error(f"Test {test_file} failed")
                    else:
                        logging.info(f"Test {test_file} passed in {exec_time:.2f}s")

                except Exception as e:
                    logging.error(f"Exception in test {test_file}: {e}")
                    all_success = False

    return all_success


# -----------------------------
# Enhanced Main Logic
# -----------------------------
if __name__ == "__main__":
    logging.info("=== Enhanced AI Test Selector Started ===")
    start_time = time.time()

    # Load historical data
    test_history = load_test_history()

    try:
        changed_files = get_changed_files()
        if not changed_files:
            logging.info("No changes detected, running smoke tests...")
            # Run a quick smoke test if no changes
            repo_tests = get_all_test_files()
            if repo_tests:
                smoke_test = repo_tests[0]  # Run first available test
                success = run_tests_intelligently([smoke_test], test_history)
                save_test_history(test_history)
                exit(0 if success else 1)
            else:
                logging.info("No test files found")
                exit(0)

        logging.info(f"Detected {len(changed_files)} changed files: {changed_files}")

        changed_methods = get_changed_methods(changed_files)
        logging.info(f"Detected {len(changed_methods)} changed methods: {list(changed_methods)}")

        # Detect locator changes and map to methods
        changed_locators = get_changed_locators(changed_files)
        for file_path in changed_files:
            if changed_locators and file_path.endswith(".py"):
                locator_methods = map_locators_to_methods(file_path, changed_locators)
                changed_methods.update(locator_methods)

        repo_tests = get_all_test_files()
        logging.info(f"Found {len(repo_tests)} test files in repository")

        tests_to_run = []

        # Step 1 — Direct match by changed test file
        changed_test_files = [f for f in changed_files if f in repo_tests]
        if changed_test_files:
            tests_to_run.extend(changed_test_files)
            logging.info(f"Added directly changed test files: {changed_test_files}")

        # Step 2 — Match tests by method usage
        if changed_methods:
            method_matched_tests = find_tests_using_methods(repo_tests, changed_methods)
            tests_to_run.extend(method_matched_tests)
            logging.info(f"Added method-matched tests: {method_matched_tests}")

        # Step 3 — AI-enhanced selection
        if not tests_to_run or len(tests_to_run) > 10:  # Use AI if no tests found or too many
            ai_suggested = ask_ollama_for_tests(changed_files, changed_methods, repo_tests, test_history)
            if ai_suggested:
                mapped_tests = map_ai_files_to_repo(ai_suggested, repo_tests)
                if len(tests_to_run) > 10:  # Replace with AI selection if too many
                    tests_to_run = mapped_tests
                    logging.info(f"Replaced large test set with AI selection: {mapped_tests}")
                else:  # Add to existing selection
                    tests_to_run.extend(mapped_tests)
                    logging.info(f"Added AI-suggested tests: {mapped_tests}")

        # Remove duplicates and limit
        tests_to_run = list(set(tests_to_run))[:8]  # Max 8 tests for reasonable execution time

        if tests_to_run:
            logging.info(f"Final test selection ({len(tests_to_run)} tests): {tests_to_run}")

            success = run_tests_intelligently(tests_to_run, test_history)

            total_time = time.time() - start_time
            logging.info(f"Test execution completed in {total_time:.2f}s, success: {success}")

            save_test_history(test_history)
            exit(0 if success else 1)
        else:
            logging.warning("No relevant test files identified")
            save_test_history(test_history)
            exit(0)

    except KeyboardInterrupt:
        logging.info("Test execution interrupted by user")
        save_test_history(test_history)
        exit(1)
    except Exception as e:
        logging.error(f"Unexpected error in test selector: {e}", exc_info=True)
        save_test_history(test_history)
        exit(1)