import os
import re
import subprocess
from git import Repo
from datetime import datetime

repo = Repo(".")

LOG_DIR = "ai_test_logs"
os.makedirs(LOG_DIR, exist_ok=True)

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

changed_files = re.findall(r"\+\+\+ b/(.+)", diff_content)
changed_names = set()

changed_names.update(re.findall(r"^\+\s*def\s+(\w+)", diff_content, re.MULTILINE))
changed_names.update(re.findall(r"^\+\s*class\s+(\w+)", diff_content, re.MULTILINE))
changed_names.update(re.findall(r"^\+\s*self\.(\w+)", diff_content, re.MULTILINE))

print(f"Changed files: {changed_files}")
print(f"Changed elements: {changed_names}")

# Collect all test files
all_test_files = []
for root, _, files in os.walk("tests"):
    for f in files:
        if f.startswith("test") and f.endswith(".py"):
            all_test_files.append(os.path.join(root, f))

if not all_test_files:
    print("No test files found.")
    exit()

# Track reasons
test_files_to_run = {}
for test_file in all_test_files:
    with open(test_file, "r", encoding="utf-8", errors="ignore") as f:
        test_code = f.read()
        for name in changed_names:
            if re.search(rf"\b{name}\b", test_code):
                test_files_to_run[test_file] = f"Matched keyword: {name}"
                break

# AI fallback if no matches
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
        ai_tests = [
            line.strip()
            for line in ai_output.splitlines()
            if line.strip().endswith(".py") and os.path.exists(line.strip())
        ]
        for t in ai_tests:
            test_files_to_run[t] = "AI suggested"
    except subprocess.TimeoutExpired:
        print("Ollama request timed out. Skipping AI step.")

if not test_files_to_run:
    print("No relevant test files found.")
    exit()

# Show reason log in console
print("\n📋 Test Selection Summary:")
for test_file, reason in test_files_to_run.items():
    print(f" - {test_file} → {reason}")

# Save to log file
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_path = os.path.join(LOG_DIR, f"test_selection_{timestamp}.log")

with open(log_path, "w", encoding="utf-8") as log_file:
    log_file.write(f"=== Test Selection Log ===\n")
    log_file.write(f"Run Time: {datetime.now()}\n\n")
    log_file.write(f"Changed Files:\n")
    for f in changed_files:
        log_file.write(f" - {f}\n")
    log_file.write(f"\nChanged Elements:\n")
    for e in changed_names:
        log_file.write(f" - {e}\n")
    log_file.write("\nSelected Tests:\n")
    for test_file, reason in test_files_to_run.items():
        log_file.write(f" - {test_file} → {reason}\n")

print(f"\n📝 Log saved to: {log_path}")

# Run tests
os.system(f"pytest {' '.join(test_files_to_run.keys())}")
