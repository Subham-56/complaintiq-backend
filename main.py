import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
from models import Complaint, Upvote, User
from response_utils import success_response
from routers import admin_routes, auth_routes, complaint_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(title="ComplaintIQ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(auth_routes.router)
app.include_router(complaint_routes.router)
app.include_router(admin_routes.router)


@app.get("/")
def root():
    return success_response(data={"message": "ComplaintIQ API is running"})