"""Composition root: the only place that knows which implementation backs each port."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.repository import ConversationRepository, CorpusRepository, FeedbackRepository
from app.domain.ports import BuildStore, ConversationStore, FeedbackStore, KnowledgeStore
from app.knowledge.embedder import get_embedder
from app.knowledge.repository import KnowledgeRepository

Session = Annotated[AsyncSession, Depends(get_session)]


def build_store(session: Session) -> BuildStore:
    return CorpusRepository(session)


def knowledge_store(session: Session) -> KnowledgeStore:
    return KnowledgeRepository(session, get_embedder())


def conversation_store(session: Session) -> ConversationStore:
    return ConversationRepository(session)


def feedback_store(session: Session) -> FeedbackStore:
    return FeedbackRepository(session)


Builds = Annotated[BuildStore, Depends(build_store)]
Knowledge = Annotated[KnowledgeStore, Depends(knowledge_store)]
Conversations = Annotated[ConversationStore, Depends(conversation_store)]
Feedback = Annotated[FeedbackStore, Depends(feedback_store)]
