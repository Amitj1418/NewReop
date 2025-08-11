import os
import subprocess
from git import Repo

# --- Step 1: Detect changed files ---
repo = Repo(".")
changed_files = [item.a_path for item in repo.index.diff("HEAD")]

if not changed_files:
    print("No changed files detected since last commit.")
    exit()

print(f"Changed files: {changed_files}")

# --- Step 2: Read code from changed files ---
def get_file_content(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except FileNotFoundError:
        return ""

changed_code = {}
for file in changed_files:
    changed_code[file] = get_file_content(file)

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
