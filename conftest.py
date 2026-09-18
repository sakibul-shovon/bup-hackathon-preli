"""Registers the `live` marker and keeps live (real-Groq) tests out of the
default `pytest` run -- they only execute when explicitly selected with
`pytest -m live` (and need a real GROQ_API_KEYS/GROQ_API_KEY to pass
meaningfully; plan Section 12.1: "Run live tests manually with the key set,
never in the default suite").
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: requires a real GROQ_API_KEYS/GROQ_API_KEY; run explicitly with `pytest -m live`"
    )


def pytest_collection_modifyitems(config, items):
    markexpr = config.getoption("markexpr", default="") or ""
    if "live" in markexpr:
        return  # user explicitly selected live tests via -m; let pytest's own filtering run them
    skip_live = pytest.mark.skip(reason="live test: run explicitly with `pytest -m live` (needs a real GROQ key)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
