import os
import json
import logging
import time
import cloudinary
import cloudinary.uploader
import requests
from google import genai
from google.genai import errors as genai_errors
import base64

from config import (
    CLOUDINARY_CLOUD_NAME,
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET,
    GEMINI_API_KEY,
)

logger = logging.getLogger(__name__)

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
)

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

GEMINI_MODEL = "gemini-3.6-flash"
_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 2

# Fixed department list. Without this, Gemini can return any free-text
# string it wants — which silently breaks admin filtering/grouping, since
# that relies on exact string matches. Constraining the prompt to this list,
# and normalizing the result against it, keeps departments consistent.
# Category classification was dropped entirely — department is the only
# classification that matters operationally (who actually handles this).
ALLOWED_DEPARTMENTS = [
    "Public Works Department",      # potholes, damaged roads, general infra
    "Water Supply Department",      # water shortage, leakage, pipe issues
    "Electricity Department",       # broken streetlights, power issues
    "Sanitation Department",        # garbage, sewage overflow, illegal dumping
    "Traffic Police",               # illegal parking, traffic issues
    "Parks and Horticulture Department",  # tree fall, park damage
    "Pollution Control Board",      # noise pollution, air/water pollution
    "General Municipal Department", # fallback for anything else
]


def upload_image_to_cloudinary(file_bytes: bytes, filename: str) -> str:
    result = cloudinary.uploader.upload(
        file_bytes,
        folder="complaintiq",
        public_id=filename,
        overwrite=True,
    )
    return result["secure_url"]


def _build_prompt(description: str) -> str:
    departments = ", ".join(f'"{d}"' for d in ALLOWED_DEPARTMENTS)
    return f"""
    You are an AI assistant for a civic complaint management system.
    You will be given a photo and a description submitted by a citizen.

    First, verify if the image genuinely shows a real civic infrastructure issue
    (like potholes, garbage, broken streetlights, water leakage, damaged roads,
    sewage problems, illegal dumping, etc).

    If the image does NOT show a genuine civic issue (e.g. it's an unrelated photo,
    a selfie, a screenshot, random object, or clearly fake/unrelated to the description),
    mark it as invalid.

    Return a JSON object with exactly these fields:
    - is_valid: true or false
    - rejection_reason: if is_valid is false, a short reason why. Otherwise null.
    - urgency: "high", "medium", or "low" based on how urgently this needs to be fixed.
      Only fill this if is_valid is true.
    - department: MUST be exactly one of these strings: {departments}.
      Choose whichever department would realistically handle this issue.
      Only fill this if is_valid is true.

    Return only a valid JSON object. No extra text. No markdown. No backticks.

    Citizen's description: {description}
    """


def _normalize_department(value: str | None) -> str | None:
    if value is None:
        return None
    for candidate in ALLOWED_DEPARTMENTS:
        if candidate.lower() == value.strip().lower():
            return candidate
    logger.warning(
        "Gemini returned an unrecognized department: %r — using 'General Municipal Department'",
        value,
    )
    return "General Municipal Department"


def analyze_complaint_with_ai(description: str, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    prompt = _build_prompt(description)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    last_error = None
    for attempt in range(1, _MAX_RETRIES + 2):  # e.g. 3 total attempts
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_b64,
                        }
                    },
                ],
            )
            result = json.loads(response.text)

            # Log the raw AI result so you can see exactly what Gemini
            # returned for any given complaint, straight from your Render
            # or local logs.
            logger.info("Gemini analysis result: %s", result)

            return {
                "is_valid": result.get("is_valid", True),
                "rejection_reason": result.get("rejection_reason"),
                "ai_urgency": result.get("urgency"),
                "ai_department": _normalize_department(result.get("department")),
            }
        except genai_errors.ServerError as e:
            # Transient overload (503) or similar server-side issue.
            # Worth a short retry before giving up.
            last_error = e
            logger.warning(
                "Gemini server error on attempt %s/%s: %s",
                attempt,
                _MAX_RETRIES + 1,
                e,
            )
            if attempt <= _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
        except Exception as e:
            # Non-retryable error (bad request, auth issue, malformed
            # response, etc). Don't waste time retrying these.
            last_error = e
            break

    # Fail closed: if AI verification couldn't run after retries (bad key,
    # persistent overload, network issue, malformed response), don't
    # silently treat the complaint as verified. Flag it for manual review.
    logger.exception(
        "Gemini analysis failed after retries, flagging complaint for manual review: %s",
        last_error,
    )
    return {
        "is_valid": False,
        "rejection_reason": "AI verification unavailable — flagged for manual review",
        "ai_urgency": None,
        "ai_department": None,
    }


def reanalyze_complaint(complaint) -> dict:
    """
    Re-runs AI analysis for a complaint that's stuck as unclassified/under
    review (e.g. because Gemini was overloaded on first submission).
    Downloads the already-uploaded image from Cloudinary and re-analyzes it —
    no need to re-upload, since the image is already stored.
    """
    if not complaint.image_url:
        raise ValueError("This complaint has no image to re-analyze")

    response = requests.get(complaint.image_url, timeout=15)
    response.raise_for_status()
    image_bytes = response.content

    content_type = response.headers.get("Content-Type", "image/jpeg")
    return analyze_complaint_with_ai(complaint.description, image_bytes, content_type)


def serialize_complaint(complaint, upvote_count: int = 0, user_has_upvoted: bool = False) -> dict:
    return {
        "id": complaint.id,
        "description": complaint.description,
        "latitude": complaint.latitude,
        "longitude": complaint.longitude,
        "issue_type": complaint.issue_type,
        "ai_urgency": complaint.ai_urgency,
        "ai_department": complaint.ai_department,
        "status": complaint.status,
        "image_url": complaint.image_url,
        "upvote_count": upvote_count,
        "user_has_upvoted": user_has_upvoted,
        "created_at": complaint.created_at.isoformat() if complaint.created_at else None,
        "updated_at": complaint.updated_at.isoformat() if complaint.updated_at else None,
    }


def serialize_admin_complaint(complaint, user, upvote_count: int = 0) -> dict:
    base = serialize_complaint(complaint, upvote_count)
    base["user_id"] = user.id
    base["username"] = user.username
    base["email"] = user.email
    return base