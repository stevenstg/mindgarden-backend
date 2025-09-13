# main.py
import os
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import date
from typing import List
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware # 引入CORS

import models, schemas

# --- 配置 ---
load_dotenv() # 加载.env文件

# 数据库配置
DATABASE_URL = "sqlite:///./mindgarden.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
models.Base.metadata.create_all(bind=engine)

# Gemini API 配置
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-pro-latest')

app = FastAPI()

# --- CORS 配置 ---
# 允许所有来源的跨域请求（在开发阶段）
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 依赖 ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- AI 辅助函数 ---
def get_ai_analysis(prompt: str):
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI API Error: {e}")

# --- API 端点 ---
@app.post("/api/diaries/", response_model=schemas.Diary)
def create_diary(diary: schemas.DiaryCreate, db: Session = Depends(get_db)):
    db_diary = models.Diary(date=diary.date, content=diary.content)
    db.add(db_diary)
    db.commit()
    db.refresh(db_diary)
    return db_diary

@app.get("/api/diaries/", response_model=List[schemas.Diary])
def read_diaries(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    diaries = db.query(models.Diary).offset(skip).limit(limit).all()
    return diaries

@app.post("/api/analysis/daily/{diary_id}")
def analyze_daily_diary(diary_id: int, db: Session = Depends(get_db)):
    db_diary = db.query(models.Diary).filter(models.Diary.id == diary_id).first()
    if db_diary is None:
        raise HTTPException(status_code=404, detail="Diary not found")

    prompt = f"""
    你是一位富有同情心且深刻的个人成长教练。请评估以下日记，基于自我觉察、积极行动和情绪管理的程度，给出一个1-10分的评分。
    请按以下JSON格式返回结果，不要有任何额外说明：
    {{
      "score": <评分整数>,
      "analysis": "<一段简洁但有洞察力的分析>"
    }}

    日记内容：
    {db_diary.content}
    """
    analysis_text = get_ai_analysis(prompt)
    # 此处应添加代码来解析返回的JSON，并更新数据库
    # 为保持教程简洁，我们先直接返回文本
    return {"analysis_text": analysis_text}

# (月度复盘的端点可以类似地添加)