import logging
from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth import create_access_token, hash_password, verify_password
from config import ADMIN_CODE
from database import get_db
from models import User
from response_utils import error_response, success_response
from schemas import LoginRequest, RegisterRequest

router = APIRouter(tags=["Auth"])
logger = logging.getLogger(__name__)


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        error_response("Email already registered")

    admin_code = payload.admin_code.strip() if payload.admin_code else None
    if admin_code and admin_code != ADMIN_CODE:
        error_response("Invalid admin code")

    role = "admin" if admin_code == ADMIN_CODE else "user"

    user = User(
        email=payload.email,
        username=payload.username,
        password=hash_password(payload.password),
        role=role,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to register user email=%s", payload.email)
        error_response("Registration failed", status_code=500)

    logger.info("User registered id=%s role=%s", user.id, user.role)

    return success_response(
        data={
            "message": "Account created successfully",
            "username": user.username,
            "role": user.role,
        }
    )


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password):
        error_response("Invalid email or password", status_code=401)

    token = create_access_token({
        "user_id": user.id,
        "role": user.role,
        "username": user.username,
    })

    logger.info("User logged in id=%s role=%s", user.id, user.role)

    return success_response(
        data={
            "access_token": token,
            "token_type": "bearer",
            "username": user.username,
            "role": user.role,
            "user_id": user.id,
        }
    )