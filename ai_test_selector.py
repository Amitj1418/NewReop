import os
import re
import subprocess
from git import Repo

# --- Step 1: Detect changed files ---
repo = Repo(".")
if repo.head.is_detached:
    print("Detached HEAD state. Cannot find last commit changes.")
    exit()

last_commit = repo.head.commit
if not last_commit.parents:
    print("No parent commit found — this is the first commit.")
    changed_files = [item.a_path for item in last_commit.diff(None)]
else:
    changed_files = [item.a_path for item in last_commit.diff(last_commit.parents[0])]

if not changed_files:
    print("No changed files in the last commit.")
    exit()

print(f"Changed files: {changed_files}")

# --- Step 2: Extract functions/classes ---
def extract_summary(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
        functions = re.findall(r"def\s+(\w+)\s*\(", code)
        classes = re.findall(r"class\s+(\w+)\s*\(", code)
        return {
            "functions": functions,
            "classes": classes
        }
    except FileNotFoundError:
        return {"functions": [], "classes": []}

changed_summary = {file: extract_summary(file) for file in changed_files}

# --- Step 3: Get all test files ---
all_test_files = []
for root, _, files in os.walk("tests"):
    for f in files:
        if f.startswith("test") and f.endswith(".py"):
            all_test_files.append(os.path.join(root, f))

if not all_test_files:
    print("No test files found in 'tests' directory.")
    exit()

# --- Step 4: Prepare Ollama prompt ---
prompt = "You are an AI that maps Python code changes to pytest test files.\n"
prompt += f"Existing test files:\n{all_test_files}\n\n"
prompt += "Changed files and their elements:\n"

for file, summary in changed_summary.items():
    prompt += f"- {file}\n"
    prompt += f"  Functions: {', '.join(summary['functions']) or 'None'}\n"
    prompt += f"  Classes: {', '.join(summary['classes']) or 'None'}\n"

prompt += (
    "\nSelect only from the above test file list. "
    "Output only file paths exactly as in the list or filenames if unsure."
)

print("\nQuerying Ollama for test suggestions...\n")

try:
    result = subprocess.run(
        ["ollama", "run", "mistral"],
        input=prompt.encode("utf-8"),
        capture_output=True,
        timeout=60
    )
    output = result.stdout.decode().strip()
except subprocess.TimeoutExpired:
    print("Ollama request timed out. Using local fallback.\n")
    output = ""

# --- Step 5: Normalize Ollama output ---
def normalize_ai_output(output, all_files):
    if not output:
        return []
    selected = []
    ai_lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in ai_lines:
        for test_path in all_files:
            if line.lower() in test_path.lower() or os.path.basename(test_path).lower() == line.lower():
                selected.append(test_path)
    return list(set(selected))

test_files = normalize_ai_output(output, all_test_files)

# --- Step 6: Local fallback if AI fails ---
if not test_files:
    print("Using fallback matching...\n")
    changed_names = set()
    for summary in changed_summary.values():
        changed_names.update(summary["functions"])
        changed_names.update(summary["classes"])

    # Convert CamelCase to snake_case
    def camel_to_snake(name):
        return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

    changed_names_snake = {camel_to_snake(name) for name in changed_names}
    base_names = {os.path.splitext(os.path.basename(f))[0].lower() for f in changed_files}

    for test_file in all_test_files:
        try:
            with open(test_file, "r", encoding="utf-8", errors="ignore") as f:
                test_code = f.read().lower()

            # Match by function/class name
            name_match = any(name.lower() in test_code for name in changed_names.union(changed_names_snake))

            # Match by file name similarity
            file_match = any(
                base in os.path.basename(test_file).lower()
                for base in base_names.union(changed_names_snake)
            )

            if name_match or file_match:
                test_files.append(test_file)

        except FileNotFoundError:
            continue

# --- Step 7: Remove duplicates ---
test_files = list(set(test_files))

if not test_files:
    print("No relevant test files found.")
    exit()

print("Selected tests:\n", "\n".join(test_files))

# --- Step 8: Run selected tests ---
print("\nRunning suggested tests...\n")
os.system(f"pytest {' '.join(test_files)}")
