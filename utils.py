import re
import json

def clean_json_string(text: str) -> str:
    """
    Robustly extract JSON from a string.
    Finds the largest substring wrapped in {...} or [...]
    """
    text = text.strip()
    
    # Try to find the first '{' and the last '}'
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return text[start_idx:end_idx+1]
        
    # If no object found, try array
    start_idx = text.find('[')
    end_idx = text.rfind(']')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return text[start_idx:end_idx+1]

    # Fallback: simple cleanup
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text.strip()
