import subprocess
import re
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

method_pattern = re.compile(r'^\+.*def\s+(\w+)\s*\(', re.MULTILINE)

def get_changed_methods(file_path):
    try:
        diff_text = subprocess.check_output(
            ["git", "diff", file_path],
            stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="ignore")  # ✅ UTF-8 safe
    except subprocess.CalledProcessError:
        return set()
    except Exception as e:
        logging.error(f"Error getting diff for {file_path}: {e}")
        return set()

    if not diff_text.strip():  # ✅ Prevent None/empty
        return set()

    return set(method_pattern.findall(diff_text))


def get_changed_files():
    try:
        output = subprocess.check_output(
            ["git", "diff", "--name-only"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="ignore")
        files = [f.strip() for f in output.splitlines() if f.strip()]
        return files
    except subprocess.CalledProcessError:
        return []
    except Exception as e:
        logging.error(f"Error getting changed files: {e}")
        return []


def main():
    logging.info("=== AI Test Selector Started ===")

    changed_files = get_changed_files()
    logging.info(f"Changed files: {changed_files}")

    changed_methods = set()

    for f in changed_files:
        changed_methods |= get_changed_methods(f)

    logging.info(f"Changed methods: {changed_methods}")

    # Example logic: scan tests for changed methods
    matched_tests = []
    tests_path = Path("tests")

    if tests_path.exists():
        for test_file in tests_path.rglob("test_*.py"):
            try:
                content = test_file.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                logging.error(f"Error reading {test_file}: {e}")
                continue

            if any(method in content for method in changed_methods):
                matched_tests.append(str(test_file))

    if matched_tests:
        logging.info(f"Running matched tests: {matched_tests}")
        pytest_cmd = ["pytest", "-q"] + matched_tests
        os.system(" ".join(pytest_cmd))
    else:
        logging.warning("No relevant test files found.")


if __name__ == "__main__":
    main()
