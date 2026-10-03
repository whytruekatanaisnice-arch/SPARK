"""Simple inbox-style messaging, backing admin/conversation.html."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.message import Conversation, ConversationParticipant, Message as MessageModel
from app.security import CurrentUser

router = APIRouter(prefix="/api/messaging", tags=["messaging"])


@router.get("/conversations")
async def list_conversations(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.id)
        .where(ConversationParticipant.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
    )
    return result.scalars().all()


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(participant_ids: list[UUID], subject: str | None, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    conversation = Conversation(subject=subject)
    db.add(conversation)
    await db.flush()

    all_participants = set(participant_ids) | {current_user.id}
    for uid in all_participants:
        db.add(ConversationParticipant(conversation_id=conversation.id, user_id=uid))

    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: UUID, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    participant_check = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    if not participant_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a participant of this conversation")

    result = await db.execute(
        select(MessageModel).where(MessageModel.conversation_id == conversation_id).order_by(MessageModel.sent_at)
    )
    return result.scalars().all()


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(conversation_id: UUID, body: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    participant_check = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    if not participant_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a participant of this conversation")

    message = MessageModel(conversation_id=conversation_id, sender_id=current_user.id, body=body)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message
