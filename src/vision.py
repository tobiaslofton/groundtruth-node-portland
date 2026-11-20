"""Automated multimodal vision parsing via Gemini Flash for verification photos."""
import base64
import json
import logging
import os
import urllib.request
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ground_truth.vision")

def get_gemini_api_key() -> str:
    """Retrieve Gemini API key from environment."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        # Check Windows user environment fallback
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as reg_key:
                val, _ = winreg.QueryValueEx(reg_key, "GEMINI_API_KEY")
                return val
        except Exception:
            pass
    return key

def _post_gemini_sync(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        res_json = json.loads(resp.read().decode())
        candidate_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
        analysis = json.loads(candidate_text)
        analysis["automated_vision"] = True
        return analysis

async def analyze_field_photo(
    image_bytes: bytes,
    location: str,
    questions: List[str]
) -> Dict[str, Any]:
    """
    Call Gemini Flash multimodal API via async thread to inspect photo against verification questions.
    Returns structured key-value answers.
    """
    import asyncio
    api_key = get_gemini_api_key()
    if not api_key:
        logger.warning("GEMINI_API_KEY not found. Skipping automated vision parsing.")
        return {
            "automated_vision": False,
            "operator_notes": "Photo verified on-site. Automated vision disabled (no API key)."
        }

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    questions_fmt = "\n".join([f"- {q}" for q in questions]) or "- General physical environment and object status"

    prompt = (
        "You are an objective physical inspection auditor for an autonomous AI agent.\n"
        f"Target Location: {location}\n"
        f"Questions / Checklist to verify:\n{questions_fmt}\n\n"
        "Inspect the attached photo taken by the human field operator on-site. "
        "Answer each question factually based ONLY on visible details in the image (objects, conditions, physical surroundings, notices, text, status).\n"
        "Respond strictly with valid JSON conforming to this schema:\n"
        "{\n"
        '  "photo_matches_location": true,\n'
        '  "summary": "1-2 sentence objective finding",\n'
        '  "checklist_results": [\n'
        '     {"question": "...", "answer": "...", "evidence_visible": "..."}\n'
        "  ],\n"
        '  "posted_notices_text": "Exact text of any signs/banners if visible, or null"\n'
        "}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64_image
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }

    try:
        return await asyncio.to_thread(_post_gemini_sync, url, payload)
    except Exception as e:
        logger.error("Gemini vision analysis failed: %s", e)
        return {
            "automated_vision": False,
            "vision_error": str(e),
            "operator_notes": "Photo captured on-site (vision parsing error)."
        }
