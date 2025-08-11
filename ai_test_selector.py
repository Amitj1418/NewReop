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

# --- Step 2: Read code & extract only relevant parts ---
def extract_summary(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
        # Only keep function and class definitions
        functions = re.findall(r"def\s+(\w+)\s*\(", code)
        classes = re.findall(r"class\s+(\w+)\s*\(", code)
        return {
            "functions": functions,
            "classes": classes
        }
    except FileNotFoundError:
        return {"functions": [], "classes": []}

changed_summary = {file: extract_summary(file) for file in changed_files}

# --- Step 3: Build prompt for Ollama ---
prompt = "You are an AI that maps Python code changes to pytest test files.\n"
prompt += "Here are the changed files and their modified elements:\n\n"

for file, summary in changed_summary.items():
    prompt += f"File: {file}\n"
    prompt += f"Functions: {', '.join(summary['functions']) or 'None'}\n"
    prompt += f"Classes: {', '.join(summary['classes']) or 'None'}\n\n"

prompt += (
    "Based on these changes, return ONLY the pytest test file paths that should be run. "
    "One per line, no extra explanation."
)

print("\nQuerying Ollama for test suggestions...\n")

try:
    result = subprocess.run(
        ["ollama", "run", "mistral"],
        input=prompt.encode("utf-8"),
        capture_output=True,
        timeout=30  # Reduced timeout
    )
    output = result.stdout.decode().strip()
except subprocess.TimeoutExpired:
    print("Ollama request timed out. Using local keyword matching instead.\n")
    output = ""

# --- Step 4: AI failed? Use fallback ---
if not output:
    test_files = []
    for file in changed_files:
        base_name = os.path.splitext(os.path.basename(file))[0]
        for root, _, files in os.walk("tests"):
            for f in files:
                if f.startswith("test") and base_name in f:
                    test_files.append(os.path.join(root, f))
else:
    test_files = [t.strip() for t in output.splitlines() if t.strip().endswith(".py")]

if not test_files:
    print("No relevant test files found.")
    exit()

print("Selected tests:\n", "\n".join(test_files))

# --- Step 5: Run only the suggested tests ---
print("\nRunning suggested tests...\n")
os.system(f"pytest {' '.join(test_files)}")
