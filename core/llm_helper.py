# core/llm_helper.py
import logging

import requests

MODEL = "llama3"
OLLAMA_URL = "http://localhost:11434/api/generate"

def get_ai_locator_suggestion(failure_reason: str, html_snippet: str, model="llama3"):
    prompt = f"""
    A test failed due to a missing locator. 
    Failure reason: {failure_reason}
    HTML snippet: {html_snippet}
    Suggest the best alternate selector in XPath or CSS.
    """
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False
        }
    )
    suggestion = response.json()["response"]
    return suggestion.strip()

def summarize_diffs(diffs):
    """
    Extract a minimal summary of changes from git diff output.
    Only method/function names and locator-related changes are included.
    """
    summary = []
    for file, diff in diffs.items():
        added_methods = re.findall(r"^\+\s*def\s+(\w+)", diff, re.MULTILINE)
        removed_methods = re.findall(r"^-\s*def\s+(\w+)", diff, re.MULTILINE)
        locator_changes = re.findall(r"[+-].*(locator|xpath|css).*=", diff, re.IGNORECASE)

        if added_methods or removed_methods or locator_changes:
            summary.append({
                "file": file,
                "added_methods": added_methods,
                "removed_methods": removed_methods,
                "locator_changes": locator_changes
            })
    return summary


def ai_select_tests(changed_files, diffs, repo_tests, model=MODEL):
    """
    Fully AI-driven test selection with strict filtering.
    """
    diff_summary = summarize_diffs(diffs)

    prompt = f"""
You are an AI that selects the MINIMAL set of impacted test files.

### STRICT RULES:
- Only pick tests if there is a DIRECT and OBVIOUS link between changed code and a test file.
- A test is impacted if:
    1. It directly imports the changed file.
    2. It calls a changed method/function.
    3. It uses a changed locator.
- If no match is found, output NOTHING.
- DO NOT guess or include unrelated tests.
- Output EXACT file paths from the AVAILABLE TEST FILES list, one per line.

### CHANGED FILES:
{changed_files}

### DIFF SUMMARY:
{diff_summary}

### AVAILABLE TEST FILES:
{repo_tests}
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        output = response.json().get("response", "")
        selected = [line.strip() for line in output.splitlines() if line.strip()]
        logging.info(f"AI selected tests: {selected}")
        return selected
    except Exception as e:
        logging.error(f"AI test selection failed: {e}")
        return []
