"""Shared club endpoints readable by any authenticated role, plus admin CRUD."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.club import Club, ClubSchedule, Venue
from app.schemas.club import (
    AssignVenueRequest, ClubCreate, ClubOut, ClubUpdate, VenueCreate, VenueOut,
)
from app.schemas.common import Message
from app.security import CurrentUser, require_admin

router = APIRouter(tags=["clubs"])


@router.get("/api/clubs", response_model=list[ClubOut])
async def list_clubs(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Any authenticated user can browse the club catalog."""
    result = await db.execute(select(Club).where(Club.is_active == True))  # noqa: E712
    return result.scalars().all()


@router.get("/api/clubs/{club_id}", response_model=ClubOut)
async def get_club(club_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


# ---------------- Admin-only club management ----------------

admin_router = APIRouter(prefix="/api/admin", tags=["admin:clubs"], dependencies=[Depends(require_admin)])


@admin_router.post("/clubs", response_model=ClubOut, status_code=status.HTTP_201_CREATED)
async def create_club(payload: ClubCreate, db: AsyncSession = Depends(get_db)):
    club = Club(
        name=payload.name,
        category=payload.category,
        description=payload.description,
        coach_id=payload.coach_id,
        venue_id=payload.venue_id,
    )
    db.add(club)
    await db.flush()

    for slot in payload.schedules:
        db.add(ClubSchedule(club_id=club.id, day_of_week=slot.day_of_week, start_time=slot.start_time, end_time=slot.end_time))

    await db.commit()
    await db.refresh(club)
    return club


@admin_router.patch("/clubs/{club_id}", response_model=ClubOut)
async def update_club(club_id: uuid.UUID, payload: ClubUpdate, db: AsyncSession = Depends(get_db)):
    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(club, field, value)

    await db.commit()
    await db.refresh(club)
    return club


@admin_router.delete("/clubs/{club_id}", response_model=Message)
async def delete_club(club_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    club.is_active = False  # soft delete to preserve history
    await db.commit()
    return Message(detail="Club deactivated")


@admin_router.post("/clubs/{club_id}/assign-venue", response_model=ClubOut)
async def assign_venue(club_id: uuid.UUID, payload: AssignVenueRequest, db: AsyncSession = Depends(get_db)):
    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    venue = await db.get(Venue, payload.venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    club.venue_id = venue.id
    await db.commit()
    await db.refresh(club)
    return club


@admin_router.get("/venues", response_model=list[VenueOut])
async def list_venues(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Venue))
    return result.scalars().all()


@admin_router.post("/venues", response_model=VenueOut, status_code=status.HTTP_201_CREATED)
async def create_venue(payload: VenueCreate, db: AsyncSession = Depends(get_db)):
    venue = Venue(**payload.model_dump())
    db.add(venue)
    await db.commit()
    await db.refresh(venue)
    return venue


@admin_router.patch("/venues/{venue_id}", response_model=VenueOut)
async def update_venue(venue_id: uuid.UUID, payload: VenueCreate, db: AsyncSession = Depends(get_db)):
    venue = await db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(venue, field, value)
    await db.commit()
    await db.refresh(venue)
    return venue


@admin_router.delete("/venues/{venue_id}", response_model=Message)
async def delete_venue(venue_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    venue = await db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    await db.delete(venue)
    await db.commit()
    return Message(detail="Venue deleted")
