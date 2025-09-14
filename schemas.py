# schemas.py
from pydantic import BaseModel
from datetime import date

class DiaryBase(BaseModel):
    date: str
    content: str

class DiaryCreate(DiaryBase):
    pass

class Diary(DiaryBase):
    id: int
    ai_score: int | None = None
    ai_analysis: str | None = None

    class Config:
        orm_mode = True

# schemas.py
# ... (在文件末尾添加)
class AnalysisResponse(BaseModel):
    score: int
    analysis: str