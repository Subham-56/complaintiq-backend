import logging
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_admin
from models import Complaint, Upvote, User
from response_utils import error_response, pagination_payload, success_response
from schemas import StatusUpdateRequest
from services.complaint_service import reanalyze_complaint, serialize_admin_complaint

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = logging.getLogger(__name__)


@router.get("/complaints")
def get_all_complaints(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None),
    department_filter: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    query = db.query(Complaint, User).join(User, Complaint.user_id == User.id)

    if status_filter:
        query = query.filter(Complaint.status == status_filter)

    if department_filter:
        query = query.filter(Complaint.ai_department == department_filter)

    query = query.order_by(Complaint.created_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    result = []
    for complaint, user in rows:
        upvote_count = db.query(Upvote).filter(
            Upvote.complaint_id == complaint.id
        ).count()
        result.append(serialize_admin_complaint(complaint, user, upvote_count))

    logger.info("Admin fetched complaints count=%s", len(result))

    return success_response(
        pagination_payload(result, limit=limit, offset=offset, total=total)
    )


@router.put("/complaints/{complaint_id}")
def update_status(
    complaint_id: int,
    payload: StatusUpdateRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()

    if not complaint:
        error_response("Complaint not found", status_code=status.HTTP_404_NOT_FOUND)

    complaint.status = payload.status

    try:
        db.commit()
        db.refresh(complaint)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to update status complaint_id=%s", complaint_id)
        error_response("Failed to update status", status_code=500)

    user = db.query(User).filter(User.id == complaint.user_id).first()
    upvote_count = db.query(Upvote).filter(
        Upvote.complaint_id == complaint_id
    ).count()

    logger.info(
        "Status updated complaint_id=%s status=%s",
        complaint_id,
        payload.status,
    )

    return success_response(
        data={
            "message": "Status updated successfully",
            "complaint": serialize_admin_complaint(complaint, user, upvote_count),
        }
    )


@router.post("/complaints/{complaint_id}/reanalyze")
def reanalyze_complaint_route(
    complaint_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """
    Re-runs AI analysis for a complaint that's stuck unclassified/under
    review — typically because Gemini was overloaded or failed on the
    original submission. Re-downloads the already-uploaded image and
    re-analyzes it without requiring the citizen to resubmit anything.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()

    if not complaint:
        error_response("Complaint not found", status_code=status.HTTP_404_NOT_FOUND)

    try:
        ai_result = reanalyze_complaint(complaint)
    except Exception:
        logger.exception("Re-analysis failed complaint_id=%s", complaint_id)
        error_response(
            "Re-analysis failed. Please try again shortly.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    complaint.ai_urgency = ai_result["ai_urgency"]
    complaint.ai_department = ai_result["ai_department"]
    complaint.issue_type = ai_result["ai_department"] or complaint.issue_type

    if ai_result["is_valid"] and complaint.status == "Under Review":
        complaint.status = "Pending"

    try:
        db.commit()
        db.refresh(complaint)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to save re-analysis complaint_id=%s", complaint_id)
        error_response("Failed to save re-analysis result", status_code=500)

    user = db.query(User).filter(User.id == complaint.user_id).first()
    upvote_count = db.query(Upvote).filter(
        Upvote.complaint_id == complaint_id
    ).count()

    logger.info(
        "Re-analyzed complaint_id=%s valid=%s department=%s",
        complaint_id,
        ai_result["is_valid"],
        ai_result["ai_department"],
    )

    return success_response(
        data={
            "message": (
                "Re-analysis complete"
                if ai_result["is_valid"]
                else f"Still flagged: {ai_result['rejection_reason']}"
            ),
            "complaint": serialize_admin_complaint(complaint, user, upvote_count),
        }
    )


@router.get("/analytics")
def get_analytics(
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    total_complaints = db.query(Complaint).count()

    status_counts = {}
    for s in ["Pending", "Under Review", "In Progress", "Resolved", "Rejected"]:
        status_counts[s] = db.query(Complaint).filter(
            Complaint.status == s
        ).count()

    department_counts = {}
    departments = db.query(Complaint.ai_department).distinct().all()
    for (department,) in departments:
        if department:
            department_counts[department] = db.query(Complaint).filter(
                Complaint.ai_department == department
            ).count()

    resolved = status_counts.get("Resolved", 0)
    resolution_rate = round((resolved / total_complaints * 100), 1) if total_complaints > 0 else 0

    top_upvoted = db.query(Complaint, User).join(
        User, Complaint.user_id == User.id
    ).order_by(Complaint.id.desc()).limit(5).all()

    top_upvoted_list = []
    for complaint, user in top_upvoted:
        upvote_count = db.query(Upvote).filter(
            Upvote.complaint_id == complaint.id
        ).count()
        top_upvoted_list.append({
            "id": complaint.id,
            "description": complaint.description,
            "ai_department": complaint.ai_department,
            "status": complaint.status,
            "upvote_count": upvote_count,
        })

    top_upvoted_list.sort(key=lambda x: x["upvote_count"], reverse=True)

    total_users = db.query(User).filter(User.role == "user").count()

    logger.info("Admin fetched analytics")

    return success_response(
        data={
            "total_complaints": total_complaints,
            "total_users": total_users,
            "resolution_rate": resolution_rate,
            "status_counts": status_counts,
            "department_counts": department_counts,
            "top_upvoted": top_upvoted_list,
        }
    )


@router.get("/users")
def get_all_users(
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    users = db.query(User).filter(User.role == "user").all()

    return success_response(
        data={
            "users": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "complaint_count": db.query(Complaint).filter(
                        Complaint.user_id == u.id
                    ).count(),
                }
                for u in users
            ]
        }
    )