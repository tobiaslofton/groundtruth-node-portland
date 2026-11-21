"""Trust & Safety Intent Classifier for GroundTruth Protocol.

Evaluates incoming real-world task dispatches against safety policies:
1. Surveillance / Stalking (tracking individuals, license plates, private residences)
2. Hazardous Environments (active construction/PPE, high-voltage, rail tracks, freeway traffic)
3. Restricted / Sensitive Locations (schools, childcare, secure government/defense/jails)
"""
import logging
import os
import re
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger("ground_truth.safety")

# ==============================================================================
# DETERMINISTIC ADVERSARIAL PATTERN DEFINITIONS
# ==============================================================================

SURVEILLANCE_PATTERNS = [
    (
        r"\b(license\s*plates?|tag\s*numbers?|plate\s*#|vehicle\s*tags?|car\s*plates?)\b",
        "Vehicle license plate inspection or recording",
    ),
    (
        r"\b(run\s+(the\s+)?plate|check\s+(the\s+)?plate|record\s+(the\s+)?plate|photograph\s+(the\s+)?(license\s*)?plate)\b",
        "Targeted vehicle plate recording",
    ),
    (
        r"\bvin\s*(number|#)?\b",
        "Vehicle Identification Number (VIN) tracking",
    ),
    (
        r"\b(track|tracking|follow|following|stalk|stalking|tail|tailing|shadow|shadowing)\s+(an?\s+)?(person|individual|man|woman|someone|ex|target|vehicle|car|subject|resident|him|her|them)\b",
        "Targeted tracking or stalking of an individual",
    ),
    (
        r"\b(find\s+out\s+where\s+(she|he|they)\s+(live|go|work)|where\s+does\s+(he|she|they)\s+live|where\s+(she|he|they)\s+lives?)\b",
        "Personal whereabouts / residence discovery",
    ),
    (
        r"\b(who\s+is\s+living\s+at|who\s+lives\s+here|who\s+lives\s+at|identify\s+the\s+(resident|occupant|owner|person|homeowner|tenant))\b",
        "Occupant / resident personal identification",
    ),
    (
        r"\b(watch|monitor|stakeout|spy\s+on)\s+(the\s+)?(resident|person|someone|house|front\s*door|entry\s*and\s*exit|ex|target|individual)\b",
        "Physical stakeout or covert surveillance",
    ),
    (
        r"\b(facial\s+recognition|photograph\s+(the\s+)?faces?|identify\s+(the\s+)?faces?|capture\s+(the\s+)?faces?)\b",
        "Facial identification or biometric harvesting",
    ),
    (
        r"\b(look\s+through\s+(the\s+)?(bedroom|living\s*room|bathroom)?\s*window|into\s+(a\s+)?window|peer\s+inside\s+(the\s+)?(window|house|home|apartment))\b",
        "Private residential window intrusion / voyeurism",
    ),
    (
        r"\b(private\s+residence|residential\s+home\s+backyard|private\s+backyard|climb\s+over\s+fence|backyard\s+of\s+(the\s+)?house)\b",
        "Private residential intrusion / trespassing",
    ),
    (
        r"\b(inside\s+(the\s+)?private\s+residence|inside\s+(the\s+)?home|apartment\s+interior|into\s+(someone's|their)\s+home)\b",
        "Unauthorized entry into private residence",
    ),
]

HAZARDOUS_PATTERNS = [
    (
        r"\b(active\s+construction(\s+site)?|demolition\s+zone|hard\s*hat\s+(area|required|zone))\b",
        "Active construction or demolition site requiring industrial PPE",
    ),
    (
        r"\b(climb(ing)?\s+(the\s+)?(scaffolding|crane|tower|cell\s+tower)|enter\s+trench|open\s+excavation|work\s+at\s+heights?)\b",
        "Fall hazard or unauthorized scaling of industrial structure",
    ),
    (
        r"\b(high-?voltage|electrical\s+substation|power\s+transformer|live\s+wire|substation\s+yard|utility\s+vault)\b",
        "High-voltage electrical danger or electrical substation intrusion",
    ),
    (
        r"\b(chemical\s+(storage|plant|facility)|hazmat|toxic\s+waste|confined\s+space\s+entry|asbestos)\b",
        "Chemical, toxic material, or confined space biohazard",
    ),
    (
        r"\b(train\s+tracks?|railroad\s+tracks?|active\s+rail(way)?|subway\s+tracks?|train\s+trestle|rail\s+yard)\b",
        "Active railway tracks or train transit right-of-way",
    ),
    (
        r"\b(freeway\s+median|highway\s+median|middle\s+of\s+(the\s+)?(freeway|highway|interstate)|walk\s+on\s+(the\s+)?freeway|active\s+traffic\s+lanes?)\b",
        "Highway traffic corridor or high-speed motor vehicle hazard",
    ),
]

RESTRICTED_PATTERNS = [
    (
        r"\b(elementary\s+school|middle\s+school|high\s+school|k-12\s+school|kindergarten|preschool|daycare|childcare|playground\s+with\s+children|nursery\s+school)\b",
        "School, childcare facility, or minor-occupied playground",
    ),
    (
        r"\b(children\s+playing|photograph\s+children|watch\s+kids|observe\s+students)\b",
        "Surveillance or photographing of minors",
    ),
    (
        r"\b(military\s+base|air\s+force\s+base|naval\s+station|national\s+guard\s+armory|secure\s+government\s+facility|pentagon|fbi\s+field\s+office|cia\s+facility|federal\s+courthouse\s+security)\b",
        "Military installation or secure federal government facility",
    ),
    (
        r"\b(prison|jail|correctional\s+(facility|institution)|detention\s+center|police\s+holding\s+cell|inmate\s+area)\b",
        "Correctional institution, jail, or secure police holding facility",
    ),
    (
        r"\b(defense\s+contractor(\s+facility)?|munitions\s+(depot|plant)|weapons\s+storage|classified\s+research\s+facility)\b",
        "Defense contractor, arms depot, or classified facility",
    ),
]


def classify_task_safety(
    location: str,
    specific_questions: List[str],
    stated_purpose: str = ""
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Classify whether a proposed physical task dispatch is safe and compliant.
    
    Checks against:
    - Surveillance & Stalking (tracking people, license plates, private residences)
    - Hazardous Environments (active construction, electrical substations, railway tracks)
    - Restricted / Sensitive Locations (schools, daycares, secure government/defense/jails)

    Returns:
        (is_safe, refusal_reason, safety_metadata)
    """
    questions_joined = " ".join(specific_questions) if specific_questions else ""
    aggregate_text = f"{location} {questions_joined} {stated_purpose}".strip().lower()

    # 1. Evaluate Surveillance & Stalking
    for pattern, description in SURVEILLANCE_PATTERNS:
        if re.search(pattern, aggregate_text, re.IGNORECASE):
            reason = f"Safety policy violation: Surveillance / Stalking prohibited ({description})."
            metadata = {
                "violation_category": "surveillance_stalking",
                "matched_pattern": pattern,
                "description": description,
                "risk_score": 1.0,
                "evaluation_method": "deterministic_heuristic"
            }
            logger.warning("Task rejected by safety filter: %s", reason)
            return False, reason, metadata

    # 2. Evaluate Hazardous Environments
    for pattern, description in HAZARDOUS_PATTERNS:
        if re.search(pattern, aggregate_text, re.IGNORECASE):
            reason = f"Safety policy violation: Hazardous environment prohibited ({description})."
            metadata = {
                "violation_category": "hazardous_environment",
                "matched_pattern": pattern,
                "description": description,
                "risk_score": 0.95,
                "evaluation_method": "deterministic_heuristic"
            }
            logger.warning("Task rejected by safety filter: %s", reason)
            return False, reason, metadata

    # 3. Evaluate Restricted / Sensitive Locations
    for pattern, description in RESTRICTED_PATTERNS:
        if re.search(pattern, aggregate_text, re.IGNORECASE):
            reason = f"Safety policy violation: Restricted / Sensitive location prohibited ({description})."
            metadata = {
                "violation_category": "restricted_sensitive_location",
                "matched_pattern": pattern,
                "description": description,
                "risk_score": 0.95,
                "evaluation_method": "deterministic_heuristic"
            }
            logger.warning("Task rejected by safety filter: %s", reason)
            return False, reason, metadata

    # Optional LLM evaluation when configured and enabled
    if os.getenv("ENABLE_LLM_SAFETY_CLASSIFIER", "false").lower() in ("true", "1", "yes"):
        llm_safe, llm_reason, llm_meta = _evaluate_with_llm(location, specific_questions, stated_purpose)
        if not llm_safe:
            return False, llm_reason, llm_meta

    # Passed all checks
    metadata = {
        "violation_category": None,
        "matched_pattern": None,
        "risk_score": 0.0,
        "evaluation_method": "deterministic_heuristic"
    }
    return True, "", metadata


def validate_task_safety(
    location: str = "",
    stated_purpose: str = "",
    proposed_action: str = "",
    questions: Optional[List[str]] = None
) -> Tuple[bool, Optional[str]]:
    """Backward-compatible helper returning (is_safe, error_or_None)."""
    qs = list(questions) if questions else []
    if proposed_action:
        qs.append(proposed_action)
    is_safe, refusal_reason, _ = classify_task_safety(location, qs, stated_purpose)
    return is_safe, (refusal_reason if not is_safe else None)


def _evaluate_with_llm(
    location: str,
    specific_questions: List[str],
    stated_purpose: str
) -> Tuple[bool, str, Dict[str, Any]]:
    """Optional LLM evaluation fallback using Gemini if configured."""
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return True, "", {"evaluation_method": "llm_skipped_no_key"}
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Analyze if the following real-world dispatch request is SAFE or UNSAFE for a human operator:\n"
            f"Location: {location}\n"
            f"Questions: {specific_questions}\n"
            f"Stated Purpose: {stated_purpose}\n\n"
            f"Policies to enforce:\n"
            f"1. No surveillance, stalking, tracking people, or photographing license plates or private homes.\n"
            f"2. No hazardous zones (construction requiring PPE, electrical substations, railway tracks, highways).\n"
            f"3. No schools, daycares, secure military/defense/correctional facilities.\n\n"
            f"Respond with JSON: {{\"safe\": true/false, \"reason\": \"string\", \"category\": \"string\"}}"
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        import json
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        if not data.get("safe", True):
            return False, data.get("reason", "Rejected by safety policy."), {
                "violation_category": data.get("category", "llm_flagged"),
                "risk_score": 0.9,
                "evaluation_method": "llm_evaluated"
            }
        return True, "", {"evaluation_method": "llm_evaluated", "risk_score": 0.0}
    except Exception as e:
        logger.warning("LLM safety evaluation skipped/failed: %s", e)
        return True, "", {"evaluation_method": "llm_failed_fallback_pass"}

def validate_task_safety(
    location: str,
    questions: Optional[List[str]] = None,
    stated_purpose: Optional[str] = "",
    proposed_action: Optional[str] = ""
) -> Tuple[bool, Optional[str]]:
    """Convenience alias for classify_task_safety."""
    qs = list(questions or [])
    if proposed_action:
        qs.append(proposed_action)
    is_safe, reason, _ = classify_task_safety(location, qs, stated_purpose or "")
    return is_safe, reason if not is_safe else None

