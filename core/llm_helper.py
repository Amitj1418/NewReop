# core/llm_helper.py
import requests

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
