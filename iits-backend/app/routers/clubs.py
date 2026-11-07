"""Shared club endpoints readable by any authenticated role, plus admin CRUD."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo_store
from app.database import get_db
from app.models.club import Club, ClubSchedule, Venue
from app.models.user import User, UserRole
from app.schemas.club import (
    AssignVenueRequest, ClubCreate, ClubOut, ClubUpdate, VenueCreate, VenueOut,
)
from app.schemas.common import Message
from app.security import CurrentUser, require_admin

router = APIRouter(tags=["clubs"])


@router.get("/api/clubs", response_model=list[ClubOut])
async def list_clubs(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Any authenticated user can browse the club catalog."""
    if demo_store.is_enabled():
        return [club for club in demo_store.collection("clubs") if club.get("is_active", True)]
    result = await db.execute(select(Club).where(Club.is_active == True))  # noqa: E712
    return result.scalars().all()


@router.get("/api/clubs/{club_id}", response_model=ClubOut)
async def get_club(club_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        club = demo_store.get_record("clubs", str(club_id))
        if not club:
            raise HTTPException(status_code=404, detail="Club not found")
        return club
    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


# ---------------- Admin-only club management ----------------

admin_router = APIRouter(prefix="/api/admin", tags=["admin:clubs"], dependencies=[Depends(require_admin)])


def _category_key(category: str | None) -> str:
    normalized = " ".join((category or "").casefold().split())
    aliases = {
        "club & society": "club & society",
        "club and society": "club & society",
        "sports": "sports & games",
        "sports & games": "sports & games",
        "sports and games": "sports & games",
    }
    return aliases.get(normalized, normalized)


async def _validate_coach_assignment(
    db: AsyncSession,
    coach_id: uuid.UUID | None,
    category: str | None,
    *,
    club_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> None:
    if coach_id is None:
        return

    result = await db.execute(select(User).where(User.id == coach_id).with_for_update())
    coach = result.scalar_one_or_none()
    if coach is None or coach.role != UserRole.COACH:
        raise HTTPException(status_code=422, detail="Assigned user must have the coach role")
    if not is_active:
        return

    result = await db.execute(
        select(Club).where(Club.coach_id == coach_id, Club.is_active.is_(True))
    )
    conflicting_clubs = [
        club for club in result.scalars().all()
        if club.id != club_id and _category_key(club.category) == _category_key(category)
    ]
    if conflicting_clubs:
        raise HTTPException(
            status_code=409,
            detail=f"This coach already manages an active {_category_key(category) or 'club'}",
        )


async def _validate_venue_assignment(
    db: AsyncSession,
    venue_id: uuid.UUID | None,
    category: str | None,
    *,
    club_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> None:
    if venue_id is None:
        return

    result = await db.execute(select(Venue).where(Venue.id == venue_id).with_for_update())
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Venue not found")
    if not is_active:
        return

    result = await db.execute(
        select(Club).where(Club.venue_id == venue_id, Club.is_active.is_(True))
    )
    conflicting_clubs = [
        club for club in result.scalars().all()
        if club.id != club_id and _category_key(club.category) == _category_key(category)
    ]
    if conflicting_clubs:
        raise HTTPException(
            status_code=409,
            detail="This venue is already assigned to another active club of the same category",
        )


@admin_router.post("/clubs", response_model=ClubOut, status_code=status.HTTP_201_CREATED)
async def create_club(payload: ClubCreate, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        club = jsonable_encoder(payload, exclude={"schedules"})
        club["schedules"] = jsonable_encoder(payload.schedules)
        club["is_active"] = True
        return demo_store.create_record("clubs", club)

    await _validate_coach_assignment(db, payload.coach_id, payload.category)
    await _validate_venue_assignment(db, payload.venue_id, payload.category)

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
    if demo_store.is_enabled():
        club = demo_store.update_record(
            "clubs",
            str(club_id),
            jsonable_encoder(payload.model_dump(exclude_unset=True)),
        )
        if club is None:
            raise HTTPException(status_code=404, detail="Club not found")
        return club

    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    updates = payload.model_dump(exclude_unset=True)
    coach_id = updates.get("coach_id", club.coach_id)
    category = updates.get("category", club.category)
    is_active = updates.get("is_active", club.is_active)
    venue_id = updates.get("venue_id", club.venue_id)

    if (
        coach_id != club.coach_id
        or _category_key(category) != _category_key(club.category)
        or is_active != club.is_active
    ):
        await _validate_coach_assignment(
            db, coach_id, category, club_id=club.id, is_active=is_active
        )
    if (
        venue_id != club.venue_id
        or _category_key(category) != _category_key(club.category)
        or is_active != club.is_active
    ):
        await _validate_venue_assignment(
            db, venue_id, category, club_id=club.id, is_active=is_active
        )

    for field, value in updates.items():
        setattr(club, field, value)

    await db.commit()
    await db.refresh(club)
    return club


@admin_router.delete("/clubs/{club_id}", response_model=Message)
async def delete_club(club_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        club = demo_store.update_record("clubs", str(club_id), {"is_active": False})
        if club is None:
            raise HTTPException(status_code=404, detail="Club not found")
        return Message(detail="Club deactivated")

    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    club.is_active = False  # soft delete to preserve history
    await db.commit()
    return Message(detail="Club deactivated")


@admin_router.post("/clubs/{club_id}/assign-venue", response_model=ClubOut)
async def assign_venue(club_id: uuid.UUID, payload: AssignVenueRequest, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        if demo_store.get_record("venues", str(payload.venue_id)) is None:
            raise HTTPException(status_code=404, detail="Venue not found")
        club = demo_store.update_record("clubs", str(club_id), {"venue_id": str(payload.venue_id)})
        if club is None:
            raise HTTPException(status_code=404, detail="Club not found")
        return club

    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    venue = await db.get(Venue, payload.venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    if venue.id != club.venue_id:
        await _validate_venue_assignment(
            db, venue.id, club.category, club_id=club.id, is_active=club.is_active
        )
    club.venue_id = venue.id
    await db.commit()
    await db.refresh(club)
    return club


@admin_router.get("/venues", response_model=list[VenueOut])
async def list_venues(db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        return demo_store.collection("venues")
    result = await db.execute(select(Venue))
    return result.scalars().all()


@admin_router.post("/venues", response_model=VenueOut, status_code=status.HTTP_201_CREATED)
async def create_venue(payload: VenueCreate, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        return demo_store.create_record("venues", jsonable_encoder(payload))
    venue = Venue(**payload.model_dump())
    db.add(venue)
    await db.commit()
    await db.refresh(venue)
    return venue


@admin_router.patch("/venues/{venue_id}", response_model=VenueOut)
async def update_venue(venue_id: uuid.UUID, payload: VenueCreate, db: AsyncSession = Depends(get_db)):
    if demo_store.is_enabled():
        venue = demo_store.update_record("venues", str(venue_id), jsonable_encoder(payload))
        if venue is None:
            raise HTTPException(status_code=404, detail="Venue not found")
        return venue
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
    if demo_store.is_enabled():
        if not demo_store.delete_record("venues", str(venue_id)):
            raise HTTPException(status_code=404, detail="Venue not found")
        return Message(detail="Venue deleted")
    venue = await db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    await db.delete(venue)
    await db.commit()
    return Message(detail="Venue deleted")
