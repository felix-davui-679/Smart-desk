import os
import json
import openai

from typing import Dict

openai.api_key = os.environ.get('OPENAI_API_KEY')

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

def classify_text(text: str) -> Dict:
    """Call OpenAI to classify the text and return a dict with category, priority, confidence.

    Falls back to simple heuristics if the API call or parsing fails.
    """
    if not text:
        return {'category': 'other', 'priority': 'Low', 'confidence': 0.0}

    prompt = _build_prompt(text)

    try:
        resp = openai.ChatCompletion.create(
            model=os.environ.get('OPENAI_MODEL', 'gpt-3.5-turbo'),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=200,
            temperature=0.0,
        )
        content = resp['choices'][0]['message']['content']
        data = json.loads(content)
        category = data.get('category', '').lower()
        if category not in CATEGORIES:
            category = 'other'
        priority = data.get('priority', 'Medium')
        if priority not in PRIORITY_LEVELS:
            priority = 'Medium'
        confidence = float(data.get('confidence', 0.0))
        return {'category': category, 'priority': priority, 'confidence': confidence}
    except Exception:
        text_l = text.lower()
        if 'password' in text_l or 'login' in text_l or 'mfa' in text_l:
            category = 'microsoft 365'
            priority = 'High'
            confidence = 0.5
        elif 'printer' in text_l or 'hard drive' in text_l or 'keyboard' in text_l or 'mouse' in text_l:
            category = 'hardware'
            priority = 'Medium'
            confidence = 0.35
        elif 'vpn' in text_l or 'network' in text_l or 'internet' in text_l:
            category = 'networking'
            priority = 'High'
            confidence = 0.5
        elif 'phish' in text_l or 'malware' in text_l or 'ransom' in text_l:
            category = 'security'
            priority = 'Critical'
            confidence = 0.6
        else:
            category = 'software'
            priority = 'Medium'
            confidence = 0.25
        return {'category': category, 'priority': priority, 'confidence': confidence}
