import os
import json

from typing import Dict

try:  # openai>=1.0 SDK
    from openai import OpenAI
except ImportError:  # pragma: no cover - import guard
    OpenAI = None

# Category taxonomy and basic priority mapping
CATEGORIES = [
    'networking',
    'hardware',
    'microsoft 365',
    'software',
    'security',
    'other'
]

PRIORITY_LEVELS = ['Low', 'Medium', 'High', 'Critical']


def _build_prompt(text: str) -> str:
    taxonomy = ', '.join(CATEGORIES)
    prompt = (
        f"You are an assistant that classifies IT support tickets. "
        f"Given the following ticket description, return a JSON object with keys: 'category', 'priority', and 'confidence'. "
        f"'category' must be one of: {taxonomy}. 'priority' must be one of: {', '.join(PRIORITY_LEVELS)}. "
        f"'confidence' must be a float between 0 and 1 representing your confidence. "
        f"Respond ONLY with valid JSON and nothing else.\n\n"
        f"Ticket description:\n{text}\n"
    )
    return prompt


def _heuristic(text: str) -> Dict:
    """Keyword-based fallback used when the OpenAI call or parsing fails."""
    text_l = text.lower()
    if 'password' in text_l or 'login' in text_l or 'mfa' in text_l:
        return {'category': 'microsoft 365', 'priority': 'High', 'confidence': 0.5}
    if 'printer' in text_l or 'hard drive' in text_l or 'keyboard' in text_l or 'mouse' in text_l:
        return {'category': 'hardware', 'priority': 'Medium', 'confidence': 0.35}
    if 'vpn' in text_l or 'network' in text_l or 'internet' in text_l:
        return {'category': 'networking', 'priority': 'High', 'confidence': 0.5}
    if 'phish' in text_l or 'malware' in text_l or 'ransom' in text_l:
        return {'category': 'security', 'priority': 'Critical', 'confidence': 0.6}
    return {'category': 'software', 'priority': 'Medium', 'confidence': 0.25}


def classify_text(text: str) -> Dict:
    """Classify a ticket description into category/priority/confidence.

    Uses the OpenAI Chat Completions API (openai>=1.0) with JSON output, and
    falls back to simple keyword heuristics if the API key is missing or the
    call/parsing fails — so ticket submission never hard-fails on classification.
    """
    if not text:
        return {'category': 'other', 'priority': 'Low', 'confidence': 0.0}

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key or OpenAI is None:
        return _heuristic(text)

    prompt = _build_prompt(text)

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=200,
            temperature=0.0,
            response_format={'type': 'json_object'},
        )
        content = resp.choices[0].message.content
        data = json.loads(content)

        category = str(data.get('category', '')).lower()
        if category not in CATEGORIES:
            category = 'other'
        priority = data.get('priority', 'Medium')
        if priority not in PRIORITY_LEVELS:
            priority = 'Medium'
        confidence = float(data.get('confidence', 0.0))
        # Clamp to the documented 0..1 range.
        confidence = max(0.0, min(1.0, confidence))
        return {'category': category, 'priority': priority, 'confidence': confidence}
    except Exception:
        return _heuristic(text)
