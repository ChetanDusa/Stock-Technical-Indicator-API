"""Account lookups through a request-scoped SQLAlchemy session."""

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DependencyUnavailableException
from app.core.security import hash_api_key
from models import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_api_key(self, api_key: str) -> User | None:
        try:
            return self.db.scalar(select(User).where(User.api_key_hash == hash_api_key(api_key)))
        except SQLAlchemyError as exc:
            raise DependencyUnavailableException("Account service unavailable") from exc
