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


# 找到这个函数并用下面的新版本替换它
@app.post("/api/analysis/daily/{diary_id}", response_model=schemas.Diary)
def analyze_daily_diary(diary_id: int, db: Session = Depends(get_db)):
    print(f"--- 收到对日记 {diary_id} 的分析请求 ---")
    
    loaded_key = os.getenv("GEMINI_API_KEY")
    if not loaded_key:
        print("❌ 错误：GEMINI_API_KEY 未能加载！")
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured on server")
    print("✅ GEMINI_API_KEY 已成功加载！")

    db_diary = db.query(models.Diary).filter(models.Diary.id == diary_id).first()
    if db_diary is None:
        raise HTTPException(status_code=404, detail="Diary not found")

    if db_diary.ai_score is not None:
        return db_diary

    prompt = f"""
    你是一位富有同情心且深刻的个人成长教练。请评估以下日记，基于自我觉察、积极行动和情绪管理的程度，给出一个1-10分的评分。
    请严格按照以下JSON格式返回结果，不要有任何额外说明和代码块标记：
    {{
      "score": <评分整数>,
      "analysis": "<一段简洁但有洞察力的分析>"
    }}

    日记内容：
    {db_diary.content}
    """
    
    try:
        print("▶️ 准备调用Gemini API...")
        analysis_text = get_ai_analysis(prompt)
        print(f"✅ Gemini API 调用成功！返回原始内容: {analysis_text}")

        # 使用新的辅助函数来提取纯净的JSON部分
        json_string = extract_json_from_string(analysis_text)
        if not json_string:
            raise ValueError("在AI返回的文本中找不到有效的JSON对象")
        
        print(f"🔧 成功提取JSON部分: {json_string}")
        analysis_json = json.loads(json_string)
        
        score = analysis_json.get("score")
        analysis = analysis_json.get("analysis")

        if score is None or analysis is None:
            raise ValueError("AI返回的JSON格式不正确（缺少'score'或'analysis'字段）")

        db_diary.ai_score = score
        db_diary.ai_analysis = analysis
        db.commit()
        db.refresh(db_diary)
        
        return db_diary

    except (json.JSONDecodeError, ValueError) as e:
        print(f"❌ 解析AI响应时出错: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {e}")
    except Exception as e:
        print(f"❌ 发生未知错误: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")