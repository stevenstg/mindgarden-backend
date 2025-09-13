# models.py
from sqlalchemy import Column, Integer, String, Text, Date
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Diary(Base):
    __tablename__ = "diaries"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    content = Column(Text, nullable=False)
    ai_score = Column(Integer, nullable=True)
    ai_analysis = Column(Text, nullable=True)