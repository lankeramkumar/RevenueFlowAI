"""CSV template downloads — intent.md: "Provide template downloads and a
machine-readable schema manifest." Templates are header-only CSVs matching
ingestion/manifest.py's columns exactly, so a filled-in template always
passes the schema check.
"""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from revenueflowai.auth.deps import get_current_app_user
from revenueflowai.ingestion.manifest import REQUIRED_COLUMNS
from revenueflowai.models.tenancy import AppUser

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


@router.get("/{filename}")
async def download_template(
    filename: str, _app_user: AppUser = Depends(get_current_app_user)
) -> StreamingResponse:
    if filename not in REQUIRED_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "unknown_template", "message": f"No template for '{filename}'."},
        )

    buffer = io.StringIO()
    csv.DictWriter(buffer, fieldnames=REQUIRED_COLUMNS[filename]).writeheader()
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("")
async def list_templates(_app_user: AppUser = Depends(get_current_app_user)) -> list[str]:
    return sorted(REQUIRED_COLUMNS.keys())
