from app.sanitize import sanitize_note, sanitize_explanation

def test_sanitize_note_normal():
    assert sanitize_note("Normal readable note") == "Normal readable note"

def test_sanitize_note_control_chars():
    text = "Hello\u200B World\u202E!"
    assert sanitize_note(text) == "Hello World!"

def test_sanitize_note_truncate():
    text = "a" * 2000
    assert sanitize_note(text) == "a" * 1000

def test_sanitize_note_whitespace():
    text = "  spaces\t\ttabs\n\nnewlines  "
    assert sanitize_note(text) == "spaces tabs newlines"

def test_sanitize_explanation_empty():
    assert sanitize_explanation(None, "fallback") == "fallback"
    assert sanitize_explanation("", "fallback") == "fallback"
    assert sanitize_explanation("   ", "fallback") == "fallback"

def test_sanitize_explanation_truncate():
    text = "b" * 500
    assert sanitize_explanation(text, "fallback") == "b" * 200

def test_sanitize_explanation_all_control_becomes_empty():
    text = "\u200B\u202E \t"
    assert sanitize_explanation(text, "fallback") == "fallback"
