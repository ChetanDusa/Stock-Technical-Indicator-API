"""Database dependency for FastAPI."""

from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from database import SessionLocal


def get_db() -> Iterator[Session]:
    """Yield a request-scoped session and always release its pooled connection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
