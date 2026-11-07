"""Role-restricted inbox-style messaging."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.message import Conversation, ConversationParticipant, Message as MessageModel
from app.models.user import User, UserRole
from app.security import CurrentUser

router = APIRouter(prefix="/api/messaging", tags=["messaging"])


class ConversationCreate(BaseModel):
    participant_ids: list[UUID] = Field(min_length=1, max_length=1)
    subject: str | None = None


def allowed_recipient_roles(role: UserRole) -> set[UserRole]:
    if role == UserRole.ADMIN:
        return {UserRole.COACH}
    if role == UserRole.COACH:
        return {UserRole.ADMIN, UserRole.PARENT}
    if role == UserRole.PARENT:
        return {UserRole.COACH}
    return set()


async def ensure_participant(conversation_id: UUID, current_user: User, db: AsyncSession) -> None:
    result = await db.execute(select(ConversationParticipant).where(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id,
    ))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a participant of this conversation")


@router.get("/contacts")
async def list_contacts(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    allowed = allowed_recipient_roles(current_user.role)
    if not allowed:
        return []
    result = await db.execute(select(User).where(User.role.in_(allowed), User.is_active == True).order_by(User.full_name))
    return [{"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role.value} for user in result.scalars().all()]


@router.get("/conversations")
async def list_conversations(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.id)
        .where(ConversationParticipant.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
    )
    conversations = result.scalars().all()
    output = []
    for conversation in conversations:
        participants_result = await db.execute(
            select(User, ConversationParticipant.last_read_at)
            .join(ConversationParticipant, ConversationParticipant.user_id == User.id)
            .where(ConversationParticipant.conversation_id == conversation.id)
        )
        participant_rows = participants_result.all()
        participants = [row[0] for row in participant_rows]
        own_read_at = next((row[1] for row in participant_rows if row[0].id == current_user.id), None)

        latest_result = await db.execute(
            select(MessageModel).where(MessageModel.conversation_id == conversation.id)
            .order_by(MessageModel.sent_at.desc()).limit(1)
        )
        latest = latest_result.scalar_one_or_none()

        unread_result = await db.execute(
            select(MessageModel).where(
                MessageModel.conversation_id == conversation.id,
                MessageModel.sender_id != current_user.id,
            ).order_by(MessageModel.sent_at.desc())
        )
        unread_messages = unread_result.scalars().all()
        unread_count = sum(1 for message in unread_messages if own_read_at is None or message.sent_at > own_read_at)

        output.append({
            "id": conversation.id,
            "subject": conversation.subject,
            "created_at": conversation.created_at,
            "last_message": latest.body if latest else None,
            "last_message_at": latest.sent_at if latest else conversation.created_at,
            "last_sender_id": latest.sender_id if latest else None,
            "unread_count": unread_count,
            "participants": [{"id": user.id, "full_name": user.full_name, "role": user.role.value} for user in participants],
        })
    return output


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(payload: ConversationCreate, current_user: CurrentUser = None, db: AsyncSession = Depends(get_db)):
    allowed = allowed_recipient_roles(current_user.role)
    recipient_id = payload.participant_ids[0]

    recipient_result = await db.execute(select(User).where(User.id == recipient_id, User.is_active == True))
    recipient = recipient_result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    if recipient.role not in allowed:
        raise HTTPException(status_code=403, detail="This recipient is not allowed by your role")

    existing_result = await db.execute(
        select(Conversation)
        .join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.id)
        .where(ConversationParticipant.user_id == current_user.id)
    )
    for existing in existing_result.scalars().unique().all():
        pair_result = await db.execute(
            select(ConversationParticipant.user_id).where(ConversationParticipant.conversation_id == existing.id)
        )
        participant_ids_in_conversation = set(pair_result.scalars().all())
        if participant_ids_in_conversation == {current_user.id, recipient.id}:
            return await get_conversation(existing.id, current_user, db)

    conversation = Conversation(subject=payload.subject or f"{current_user.full_name} & {recipient.full_name}")
    db.add(conversation)
    await db.flush()
    db.add(ConversationParticipant(conversation_id=conversation.id, user_id=current_user.id))
    db.add(ConversationParticipant(conversation_id=conversation.id, user_id=recipient.id))
    await db.commit()
    return await get_conversation(conversation.id, current_user, db)


async def get_conversation(conversation_id: UUID, current_user: User, db: AsyncSession):
    await ensure_participant(conversation_id, current_user, db)
    conversation = await db.get(Conversation, conversation_id)
    result = await db.execute(
        select(User).join(ConversationParticipant, ConversationParticipant.user_id == User.id)
        .where(ConversationParticipant.conversation_id == conversation_id)
    )
    participants = result.scalars().all()
    return {
        "id": conversation.id,
        "subject": conversation.subject,
        "created_at": conversation.created_at,
        "participants": [{"id": user.id, "full_name": user.full_name, "role": user.role.value} for user in participants],
    }


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await ensure_participant(conversation_id, current_user, db)
    participant_result = await db.execute(select(ConversationParticipant).where(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id,
    ))
    participant = participant_result.scalar_one()
    participant.last_read_at = datetime.now(timezone.utc)
    result = await db.execute(select(MessageModel).where(MessageModel.conversation_id == conversation_id).order_by(MessageModel.sent_at))
    messages = result.scalars().all()
    await db.commit()
    return messages


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(conversation_id: UUID, body: str = Query(min_length=1, max_length=5000), current_user: CurrentUser = None, db: AsyncSession = Depends(get_db)):
    await ensure_participant(conversation_id, current_user, db)
    message = MessageModel(conversation_id=conversation_id, sender_id=current_user.id, body=body.strip())
    if not message.body:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message
