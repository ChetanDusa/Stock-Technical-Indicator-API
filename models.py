# models.py
from sqlalchemy import Column, Integer, String, Date
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    api_key = Column(String, unique=True, index=True)
    subscription = Column(String)  # 'free', 'pro', 'premium'
    request_count = Column(Integer, default=0)
    last_request_date = Column(Date)
