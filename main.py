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
import json
import models, schemas
import re
from sqlalchemy import extract, desc
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
ai_model = genai.GenerativeModel('gemini-2.5-pro')

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

def extract_json_from_string(text: str) -> str | None:
    """使用正则表达式从字符串中提取第一个JSON对象。"""
    # 查找从'{'开始，到'}'结束，并且内容尽可能匹配最短的模式
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return None

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


@app.post("/api/analysis/daily/{diary_id}", response_model=schemas.AnalysisResponse)
def analyze_daily_diary(diary_id: int, db: Session = Depends(get_db)):
    print(f"--- 收到对日记 {diary_id} 的【带上下文】分析请求 ---")
    
    # 1. 获取当前需要分析的日记
    current_diary = db.query(models.Diary).filter(models.Diary.id == diary_id).first()
    if current_diary is None:
        raise HTTPException(status_code=404, detail="Diary not found")

    # 2. 获取最近的3篇历史日记作为上下文 (不包括当前这篇)
    # 注意：我们假设date字段是字符串 'YYYY-MM-DayX'，所以按ID降序排列来获取最新的
    recent_diaries = db.query(models.Diary).filter(
        models.Diary.id < diary_id
    ).order_by(desc(models.Diary.id)).limit(3).all()
    
    # 3. 构建“历史背景”文本
    history_context = ""
    if recent_diaries:
        history_context += "--- 这是我最近的一些日记作为参考 ---\n\n"
        # 为了让顺序更自然，我们把获取到的日记反转一下，变成从旧到新
        for diary in reversed(recent_diaries):
            history_context += f"日期: {diary.date}\n内容:\n{diary.content}\n\n---\n\n"

    # 4. 构建最终的、带有上下文的Prompt
    prompt = f"""
    你是一位富有同情心且深刻的个人成长教练，你拥有我过去所有日记的记忆。
    你的任务是，在理解我历史背景的基础上，对我今天的日记进行评估。请特别关注我是否在重复过去的模式，或者是否取得了新的突破。

    {history_context}
    
    --- 这是我今天的日记 ---
    日期: {current_diary.date}
    内容:
    {current_diary.content}
    
    --- 你的任务 ---
    请严格按照以下JSON格式返回结果，不要有任何额外说明：
    {{
      "score": <评分整数, 1-10分>,
      "analysis": "<一段有深度、有洞察力、并结合了历史背景的分析>"
    }}
    """
    
    try:
        # (接下来的AI调用、JSON提取等逻辑，和之前完全一样)
        print("▶️ 准备调用带有上下文的Gemini API...")
        analysis_text = get_ai_analysis(prompt)
        # ...
        # (此处省略，请确保你后续的JSON提取和返回逻辑是完整的)
        # ...
        print("✅ 解析成功，直接返回结果给前端。")
        # 假设json_string, score, analysis已经被正确解析
        json_string = extract_json_from_string(analysis_text)
        analysis_json = json.loads(json_string)
        score = analysis_json.get("score")
        analysis = analysis_json.get("analysis")
        return schemas.AnalysisResponse(score=score, analysis=analysis)

    except Exception as e:
        print(f"❌ 分析过程中出错: {e}")
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {e}")
