"""PAJSK year-end export (CSV/Excel) and per-student breakdown."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import StudentProfile, User
from app.security import require_admin
from app.utils.pa_jsK import calculate_pa_jsK

router = APIRouter(prefix="/api/admin/reports", tags=["reports"], dependencies=[Depends(require_admin)])


@router.get("/pa_jsK/export")
async def export_pajsk(
    year: int = Query(default_factory=lambda: date.today().year),
    format: str = Query("csv", pattern="^(csv|excel)$"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User, StudentProfile)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .order_by(StudentProfile.class_name, User.full_name)
    )
    rows = result.all()

    headers = [
        "student_number", "full_name", "class_name",
        "role_points", "achievement_points", "attendance_points", "nilam_points", "total_pajsk_points",
    ]
    data_rows = []
    for user, profile in rows:
        breakdown = await calculate_pa_jsK(profile.user_id, year, db)
        data_rows.append([
            profile.student_number, user.full_name, profile.class_name or "",
            breakdown["role_points"], breakdown["achievement_points"],
            breakdown["attendance_points"], breakdown["nilam_points"], breakdown["total"],
        ])

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(data_rows)
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=pajsk_export_{year}.csv"},
        )

    # format == "excel"
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="openpyxl is required for Excel export") from exc

    wb = Workbook()
    ws = wb.active
    ws.title = f"PAJSK {year}"
    ws.append(headers)
    for row in data_rows:
        ws.append(row)

    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)
    return StreamingResponse(
        excel_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=pajsk_export_{year}.xlsx"},
    )
