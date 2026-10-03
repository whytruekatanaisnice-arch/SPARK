"""Simple offset-based pagination helper."""
from sqlalchemy import Select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings


async def paginate(db: AsyncSession, stmt: Select, page: int = 1, page_size: int | None = None):
    page = max(page, 1)
    page_size = min(page_size or settings.DEFAULT_PAGE_SIZE, settings.MAX_PAGE_SIZE)

    count_stmt = stmt.with_only_columns(func.count()).order_by(None)
    total = (await db.execute(count_stmt)).scalar_one()

    result_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(result_stmt)).scalars().all()

    return {"total": total, "page": page, "page_size": page_size, "items": items}
