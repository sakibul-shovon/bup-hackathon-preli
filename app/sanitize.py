import re
import unicodedata

def sanitize_note(text: str) -> str:
    """Clean one operator note before it is shown to the language model."""
    text = unicodedata.normalize("NFKC", text)
    cleaned_chars = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Cf":
            continue
        if cat == "Cc" and ch not in ("\n", "\t", "\r"):
            continue
        cleaned_chars.append(ch)
    
    text = "".join(cleaned_chars)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:1000]

def sanitize_explanation(text: str | None, fallback: str) -> str:
    """Clean the model's explanation before it goes into our API response."""
    if text is None or not text.strip():
        return fallback
    
    cleaned_chars = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in ("Cf", "Cc"):
            continue
        cleaned_chars.append(ch)
        
    cleaned = "".join(cleaned_chars)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = cleaned[:200]
    
    if not cleaned:
        return fallback
        
    return cleaned
