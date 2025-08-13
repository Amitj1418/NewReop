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

def ai_select_tests(changed_files, diffs, repo_tests, model=MODEL):
    """
    Fully AI-driven test selection.
    """
    # Build JSON-like strings manually instead of using json.dumps
    changed_files_str = str(changed_files)
    diffs_str = str(diffs)
    repo_tests_str = str(repo_tests)

    prompt = (
        "You are an AI test selector for Python projects.\n\n"
        f"CHANGED FILES:\n{changed_files_str}\n\n"
        f"DIFFS:\n{diffs_str}\n\n"
        f"AVAILABLE TEST FILES:\n{repo_tests_str}\n\n"
        "Instructions:\n"
        "- Pick ONLY test files from the AVAILABLE TEST FILES list that are most likely impacted.\n"
        "- Consider changed Python methods, functions, and locators in the diffs.\n"
        "- Output one matching test file path per line, nothing else."
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        output = response.json().get("response", "")
        return [line.strip() for line in output.splitlines() if line.strip()]
    except Exception as e:
        logging.error(f"AI test selection failed: {e}")
        return []
