import os
import re
import subprocess
from git import Repo

# --- Step 1: Detect changed files in the latest commit ---
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

# --- Step 2: Extract functions/classes from changed files ---
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

# --- Step 4: Build Ollama prompt ---
prompt = "You are an AI that maps Python code changes to existing pytest test files.\n"
prompt += f"Existing test files:\n{all_test_files}\n\n"
prompt += "Changed files and their elements:\n"

for file, summary in changed_summary.items():
    prompt += f"- {file}\n"
    prompt += f"  Functions: {', '.join(summary['functions']) or 'None'}\n"
    prompt += f"  Classes: {', '.join(summary['classes']) or 'None'}\n"

prompt += (
    "\nSelect only from the above test file list. "
    "Output only file paths exactly as in the list."
)

print("\nQuerying Ollama for test suggestions...\n")

try:
    result = subprocess.run(
        ["ollama", "run", "mistral"],
        input=prompt.encode("utf-8"),
        capture_output=True,
        timeout=60  # Increased to 60s
    )
    output = result.stdout.decode().strip()
except subprocess.TimeoutExpired:
    print("Ollama request timed out. Using smart local fallback instead.\n")
    output = ""

# --- Step 5: Filter output ---
if output:
    test_files = [t.strip() for t in output.splitlines() if t.strip() in all_test_files]
else:
    test_files = []
    changed_names = set()
    for summary in changed_summary.values():
        changed_names.update(summary["functions"])
        changed_names.update(summary["classes"])

    for test_file in all_test_files:
        try:
            with open(test_file, "r", encoding="utf-8", errors="ignore") as f:
                test_code = f.read()

            # Match whole words only
            name_match = any(
                re.search(rf"\b{name}\b", test_code)
                for name in changed_names if name
            )

            # Match exact file name (without extension)
            base_names = [os.path.splitext(os.path.basename(f))[0] for f in changed_files]
            file_match = os.path.splitext(os.path.basename(test_file))[0] in base_names

            if name_match or file_match:
                test_files.append(test_file)

        except FileNotFoundError:
            continue

# --- Step 6: Remove duplicates ---
test_files = list(set(test_files))

if not test_files:
    print("No relevant test files found.")
    exit()

print("Selected tests:\n", "\n".join(test_files))

# --- Step 7: Run tests ---
print("\nRunning suggested tests...\n")
os.system(f"pytest {' '.join(test_files)}")
