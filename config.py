import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_CODE = os.getenv("ADMIN_CODE")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

_required = {
    "SECRET_KEY": SECRET_KEY,
    "ADMIN_CODE": ADMIN_CODE,
    "DATABASE_URL": DATABASE_URL,
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "CLOUDINARY_CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
    "CLOUDINARY_API_KEY": CLOUDINARY_API_KEY,
    "CLOUDINARY_API_SECRET": CLOUDINARY_API_SECRET,
}

_missing = [name for name, value in _required.items() if not value]

if _missing:
    raise ValueError(
        f"Missing required environment variable(s): {', '.join(_missing)}. "
        "Set them in your .env file (locally) or in your deployment platform's "
        "environment settings (e.g. Render dashboard)."
    )