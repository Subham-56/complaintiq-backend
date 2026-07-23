import logging
import uuid
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import Complaint, Upvote
from response_utils import error_response, pagination_payload, success_response
from services.complaint_service import (
    analyze_complaint_with_ai,
    serialize_complaint,
    upload_image_to_cloudinary,
)

router = APIRouter(tags=["Complaints"])
logger = logging.getLogger(__name__)

@router.post("/complaints")
async def create_complaint(
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        error_response("Only image files are supported", status_code=status.HTTP_400_BAD_REQUEST)

    if not description or len(description.strip()) < 5:
        error_response("Please provide a more detailed description", status_code=status.HTTP_400_BAD_REQUEST)

    file_bytes = await file.read()
    filename = f"{uuid.uuid4()}"

    try:
        image_url = upload_image_to_cloudinary(file_bytes, filename)
    except Exception:
        logger.exception("Cloudinary upload failed user_id=%s", current_user.id)
        error_response(
            "Image upload failed. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    ai_result = analyze_complaint_with_ai(description, file_bytes, file.content_type or "image/jpeg")

    complaint_status = "Pending" if ai_result["is_valid"] else "Under Review"

    complaint = Complaint(
        description=description,
        latitude=latitude,
        longitude=longitude,
        issue_type=ai_result["ai_category"] or "Unclassified",
        ai_category=ai_result["ai_category"],
        ai_urgency=ai_result["ai_urgency"],
        ai_department=ai_result["ai_department"],
        image_url=image_url,
        status=complaint_status,
        user_id=current_user.id,
    )

    try:
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to save complaint user_id=%s", current_user.id)
        error_response(
            "Failed to save complaint.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.info(
        "Complaint created id=%s user_id=%s valid=%s",
        complaint.id,
        current_user.id,
        ai_result["is_valid"],
    )

    return success_response(
        data={
            "message": (
                "Complaint submitted successfully"
                if ai_result["is_valid"]
                else f"Complaint flagged for manual review: {ai_result['rejection_reason']}"
            ),
            "is_valid": ai_result["is_valid"],
            "complaint": serialize_complaint(complaint),
        }
    )

@router.get("/complaints/feed")
def get_community_feed(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Complaint).order_by(Complaint.created_at.desc())
    total = query.count()
    complaints = query.offset(offset).limit(limit).all()

    result = []
    for complaint in complaints:
        upvote_count = db.query(Upvote).filter(
            Upvote.complaint_id == complaint.id
        ).count()
        user_has_upvoted = db.query(Upvote).filter(
            Upvote.complaint_id == complaint.id,
            Upvote.user_id == current_user.id
        ).first() is not None

        result.append(serialize_complaint(complaint, upvote_count, user_has_upvoted))

    return success_response(
        pagination_payload(result, limit=limit, offset=offset, total=total)
    )

@router.get("/complaints")
def get_my_complaints(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Complaint).filter(
        Complaint.user_id == current_user.id
    ).order_by(Complaint.created_at.desc())

    total = query.count()
    complaints = query.offset(offset).limit(limit).all()

    # Get upvote counts and user upvote status for each complaint
    result = []
    for complaint in complaints:
        upvote_count = db.query(Upvote).filter(
            Upvote.complaint_id == complaint.id
        ).count()

        user_has_upvoted = db.query(Upvote).filter(
            Upvote.complaint_id == complaint.id,
            Upvote.user_id == current_user.id
        ).first() is not None

        result.append(serialize_complaint(complaint, upvote_count, user_has_upvoted))

    logger.info(
        "Fetched complaints user_id=%s count=%s",
        current_user.id,
        len(result),
    )

    return success_response(
        pagination_payload(result, limit=limit, offset=offset, total=total)
    )


@router.get("/complaints/all")
def get_all_complaints_map(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    complaints = db.query(Complaint).order_by(Complaint.created_at.desc()).all()

    result = []
    for complaint in complaints:
        upvote_count = db.query(Upvote).filter(
            Upvote.complaint_id == complaint.id
        ).count()

        user_has_upvoted = db.query(Upvote).filter(
            Upvote.complaint_id == complaint.id,
            Upvote.user_id == current_user.id
        ).first() is not None

        result.append(serialize_complaint(complaint, upvote_count, user_has_upvoted))

    return success_response(data={"complaints": result})


@router.post("/complaints/{complaint_id}/upvote")
def toggle_upvote(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        error_response("Complaint not found", status_code=status.HTTP_404_NOT_FOUND)

    existing_upvote = db.query(Upvote).filter(
        Upvote.complaint_id == complaint_id,
        Upvote.user_id == current_user.id,
    ).first()

    try:
        if existing_upvote:
            db.delete(existing_upvote)
            db.commit()
            action = "removed"
        else:
            upvote = Upvote(
                complaint_id=complaint_id,
                user_id=current_user.id,
            )
            db.add(upvote)
            db.commit()
            action = "added"
    except SQLAlchemyError:
        db.rollback()
        error_response("Failed to update upvote", status_code=500)

    upvote_count = db.query(Upvote).filter(
        Upvote.complaint_id == complaint_id
    ).count()

    logger.info(
        "Upvote %s complaint_id=%s user_id=%s",
        action,
        complaint_id,
        current_user.id,
    )

    return success_response(
        data={
            "action": action,
            "upvote_count": upvote_count,
            "user_has_upvoted": action == "added",
        }
    )