import os
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
    changed_files = [item.a_path for item in last_commit.diff(None)]  # first commit case
else:
    changed_files = [item.a_path for item in last_commit.diff(last_commit.parents[0])]

if not changed_files:
    print("No changed files in the last commit.")
    exit()

print(f"Changed files: {changed_files}")

# --- Step 2: Read code from changed files ---
def get_file_content(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except FileNotFoundError:
        return ""

changed_code = {file: get_file_content(file) for file in changed_files}

# --- Step 3: Ask Ollama which tests to run ---
prompt = (
    "You are an AI that analyzes Python code changes and suggests which pytest test files "
    "should be executed. Here is the changed code:\n\n"
)

for file, code in changed_code.items():
    prompt += f"File: {file}\nCode:\n{code[:1000]}...\n\n"  # limit to 1000 chars per file

prompt += (
    "Based on the changed files, list only the pytest test file names (with paths) "
    "that are most relevant to test these changes. "
    "Only output file paths, one per line, no extra text."
)

print("\nQuerying Ollama for test suggestions...\n")

result = subprocess.run(
    ["ollama", "run", "mistral"],
    input=prompt.encode("utf-8"),
    capture_output=True,
    timeout=60
)

output = result.stdout.decode().strip()
if not output:
    print("Ollama returned no suggestions.")
    exit()

print("AI Suggested Tests:\n", output)

# --- Step 4: Run only the suggested tests ---
test_files = [t.strip() for t in output.splitlines() if t.strip() and t.strip().endswith(".py")]

if not test_files:
    print("No valid test files found in AI output.")
    exit()

print("\nRunning suggested tests...\n")
os.system(f"pytest {' '.join(test_files)}")
