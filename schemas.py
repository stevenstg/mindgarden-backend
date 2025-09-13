# schemas.py
from pydantic import BaseModel
from datetime import date

class DiaryBase(BaseModel):
    date: date
    content: str

class DiaryCreate(DiaryBase):
    pass

class Diary(DiaryBase):
    id: int
    ai_score: int | None = None
    ai_analysis: str | None = None

    class Config:
        orm_mode = True