import os
import re
import subprocess
from git import Repo

repo = Repo(".")

# --- Step 1: Get exact changed lines ---
def get_changed_lines():
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "-U0", "HEAD~1", "HEAD"],
            universal_newlines=True
        )
        return diff_output
    except subprocess.CalledProcessError:
        return ""

diff_content = get_changed_lines()

if not diff_content.strip():
    print("No code changes detected.")
    exit()

# --- Step 2: Extract changed files, methods, classes ---
changed_files = re.findall(r"\+\+\+ b/(.+)", diff_content)
changed_names = set()

# Methods & classes
changed_names.update(re.findall(r"^\+\s*def\s+(\w+)", diff_content, re.MULTILINE))
changed_names.update(re.findall(r"^\+\s*class\s+(\w+)", diff_content, re.MULTILINE))

# Locators / variables
changed_names.update(re.findall(r"^\+\s*self\.(\w+)", diff_content, re.MULTILINE))

print(f"Changed files: {changed_files}")
print(f"Changed elements: {changed_names}")

# --- Step 3: Get all test files ---
all_test_files = []
for root, _, files in os.walk("tests"):
    for f in files:
        if f.startswith("test") and f.endswith(".py"):
            all_test_files.append(os.path.join(root, f))

if not all_test_files:
    print("No test files found.")
    exit()

# --- Step 4: Keyword matching ---
test_files_to_run = []
for test_file in all_test_files:
    with open(test_file, "r", encoding="utf-8", errors="ignore") as f:
        test_code = f.read()
        if any(re.search(rf"\b{name}\b", test_code) for name in changed_names):
            test_files_to_run.append(test_file)

# --- Step 5: AI fallback ---
if not test_files_to_run:
    print("No direct keyword matches found. Asking AI...\n")

    prompt = (
        "You are an AI that maps Python code changes to pytest test files.\n"
        "Here are the changed files and modified elements:\n\n"
    )
    for f in changed_files:
        prompt += f"File: {f}\n"
    prompt += f"Changed elements: {', '.join(changed_names) or 'None'}\n\n"
    prompt += (
        "Return ONLY the pytest test file paths (starting with tests/) "
        "that are most likely to be affected. One per line. No explanations."
    )

    try:
        ai_result = subprocess.run(
            ["ollama", "run", "mistral"],
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=25
        )
        ai_output = ai_result.stdout.decode().strip()
        ai_tests = [line.strip() for line in ai_output.splitlines() if line.strip().endswith(".py")]

        test_files_to_run.extend(ai_tests)
    except subprocess.TimeoutExpired:
        print("Ollama request timed out. Skipping AI step.")

# --- Step 6: Run matched tests ---
test_files_to_run = list(set(test_files_to_run))  # Remove duplicates

if not test_files_to_run:
    print("No relevant test files found.")
    exit()

print("Selected tests to run:\n", "\n".join(test_files_to_run))
os.system(f"pytest {' '.join(test_files_to_run)}")
