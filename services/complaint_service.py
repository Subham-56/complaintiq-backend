import os
import json
import logging
import cloudinary
import cloudinary.uploader
from google import genai
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


def upload_image_to_cloudinary(file_bytes: bytes, filename: str) -> str:
    result = cloudinary.uploader.upload(
        file_bytes,
        folder="complaintiq",
        public_id=filename,
        overwrite=True,
    )
    return result["secure_url"]

def analyze_complaint_with_ai(description: str, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    prompt = """
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
    - category: a specific category for this complaint (e.g. "Pothole", "Broken Streetlight", 
      "Sewage Overflow", "Garbage Overflow", "Water Shortage", "Illegal Parking", 
      "Noise Pollution", "Tree Fall"). Only fill this if is_valid is true.
    - urgency: "high", "medium", or "low" based on how urgently this needs to be fixed. 
      Only fill this if is_valid is true.
    - department: which government department should handle this. Only fill this if is_valid is true.
    
    Return only a valid JSON object. No extra text. No markdown. No backticks.
    
    Citizen's description: {description}
    """.format(description=description)

    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash",
            contents=[
                {"text": prompt},
                {
    "inline_data": {
        "mime_type": mime_type,
        "data": image_b64
    }
}
            ],
        )
        result = json.loads(response.text)

        return {
            "is_valid": result.get("is_valid", True),
            "rejection_reason": result.get("rejection_reason"),
            "ai_category": result.get("category"),
            "ai_urgency": result.get("urgency"),
            "ai_department": result.get("department"),
        }
    except Exception:
        # Fail closed: if AI verification couldn't run (bad key, rate limit,
        # network issue, malformed response), don't silently treat the
        # complaint as verified. Flag it for manual admin review instead.
        logger.exception("Gemini analysis failed, flagging complaint for manual review")
        return {
            "is_valid": False,
            "rejection_reason": "AI verification unavailable — flagged for manual review",
            "ai_category": None,
            "ai_urgency": None,
            "ai_department": None,
        }


def serialize_complaint(complaint, upvote_count: int = 0, user_has_upvoted: bool = False) -> dict:
    return {
        "id": complaint.id,
        "description": complaint.description,
        "latitude": complaint.latitude,
        "longitude": complaint.longitude,
        "issue_type": complaint.issue_type,
        "ai_category": complaint.ai_category,
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