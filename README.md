# ComplaintIQ — Backend

FastAPI backend for ComplaintIQ, an AI-powered smart city complaint platform. Handles auth, complaint submission and storage, AI-based verification/classification via Gemini, community upvoting, and admin moderation/analytics.

**Live API:** https://complaintiq-backend-ciaw.onrender.com
**Frontend repo:** https://github.com/Subham-56/complaintiq-frontend

## Features

- JWT-based authentication with citizen and admin roles (admin registration gated by a shared admin code)
- Complaint submission with image upload (Cloudinary) and GPS coordinates
- AI verification and classification (Google Gemini, multimodal image + text):
  - Confirms the photo genuinely shows a civic issue before accepting it
  - Classifies which municipal department should handle it, from a fixed set of departments
  - Assesses urgency (high / medium / low)
  - Falls back to "flagged for manual review" if AI verification fails or is unavailable, rather than silently accepting unverified complaints
  - Automatic retry with backoff on transient AI service errors
- Community upvoting (one per user per complaint, toggleable) — with the original reporter automatically upvoting their own complaint on submission, non-removable
- Admin endpoints: paginated/filterable complaint management, status updates, manual AI re-analysis for stuck complaints, analytics (resolution rate, status/department breakdowns, most-upvoted open issues), user listing

## Tech Stack

- **FastAPI** — API framework
- **SQLAlchemy** + **Supabase PostgreSQL** — data layer
- **google-genai** (Gemini `gemini-3.6-flash`) — AI verification and classification
- **Cloudinary** — image storage
- **python-jose** + **passlib[bcrypt]** — JWT auth and password hashing
- **Render** — deployment

## Project Structure

```
├── main.py                    # App entrypoint, CORS, router registration
├── config.py                  # Environment variable loading/validation
├── database.py                 # SQLAlchemy engine/session setup
├── models.py                  # User, Complaint, Upvote ORM models
├── schemas.py                  # Pydantic request/response models
├── auth.py                    # Password hashing, JWT creation/decoding
├── dependencies.py            # Auth dependency injection (current user/admin)
├── response_utils.py           # Standardized success/error response helpers
├── routers/
│   ├── auth_routes.py          # /register, /login
│   ├── complaint_routes.py     # complaint CRUD, feed, upvoting
│   └── admin_routes.py         # admin complaint management, analytics, re-analysis
└── services/
    └── complaint_service.py    # Cloudinary upload, Gemini AI analysis logic
```

## Environment Variables

Create a `.env` file with:

```
SECRET_KEY=
ADMIN_CODE=
DATABASE_URL=
GEMINI_API_KEY=
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

The app validates all of these are present on startup and fails fast with a clear error listing any that are missing.

## Running Locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## Utility Scripts

- `clear_data.py` — wipes all rows from the database (users, complaints, upvotes) for a clean testing/demo slate. Prompts for confirmation before running.

## Key Design Decisions

- **Fail-closed AI verification**: if Gemini is unavailable or errors out, the complaint is flagged for manual review rather than silently accepted — ensures no complaint bypasses verification due to an infrastructure hiccup.
- **Fixed department list**: AI classification is constrained to a predefined set of departments (normalized against the list, with a fallback), keeping admin filtering/analytics consistent rather than relying on free-text AI output.
- **Admin registration via shared code**: a lightweight tradeoff for a portfolio project — a production system would use proper superadmin-gated role promotion instead.