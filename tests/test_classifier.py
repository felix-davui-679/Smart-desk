"""Unit tests for the keyword-heuristic fallback in classifier.classify_text.

These run without an OPENAI_API_KEY so the OpenAI path is skipped and the
deterministic heuristics are exercised.
"""
import pytest

from classifier import classify_text, CATEGORIES, PRIORITY_LEVELS


@pytest.fixture(autouse=True)
def no_openai(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)


def test_empty_text_returns_other_low():
    result = classify_text('')
    assert result == {'category': 'other', 'priority': 'Low', 'confidence': 0.0}


@pytest.mark.parametrize('text,expected_category,expected_priority', [
    ('I forgot my password and cannot login', 'microsoft 365', 'High'),
    ('The office printer is jammed', 'hardware', 'Medium'),
    ('VPN keeps dropping my internet connection', 'networking', 'High'),
    ('I think I clicked a phishing link with malware', 'security', 'Critical'),
    ('The app crashes when I export a report', 'software', 'Medium'),
])
def test_heuristic_classification(text, expected_category, expected_priority):
    result = classify_text(text)
    assert result['category'] == expected_category
    assert result['priority'] == expected_priority
    assert result['category'] in CATEGORIES
    assert result['priority'] in PRIORITY_LEVELS
    assert 0.0 <= result['confidence'] <= 1.0
