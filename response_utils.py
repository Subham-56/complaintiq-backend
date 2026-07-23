from fastapi import HTTPException, status

def success_response(data: dict | list | None = None, message: str | None = None):
    payload: dict = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return payload

def pagination_payload(
    items: list,
    *,
    limit: int,
    offset: int,
    total: int,
):
    return {
        "items": items,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "count": len(items),
            "total": total,
            "has_more": offset + len(items) < total,
        },
    }

def error_response(
    message: str,
    *,
    status_code: int = status.HTTP_400_BAD_REQUEST,
):
    raise HTTPException(
        status_code=status_code,
        detail=message,
    )