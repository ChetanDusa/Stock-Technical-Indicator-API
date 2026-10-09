"""Account metadata. Daily usage is stored exclusively in Redis."""

from sqlalchemy import CheckConstraint, Column, Integer, String

from database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("subscription IN ('free', 'pro', 'premium')", name="ck_users_subscription"),
    )

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    api_key_hash = Column(String(64), unique=True, nullable=False)
    subscription = Column(String(16), nullable=False)
