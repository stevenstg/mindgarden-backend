# main.py
import os
import json
import re
import logging
from typing import List, Optional
from datetime import date

import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, desc, text
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

import models, schemas

# -----------------------------
# 环境 & 基础配置
# -----------------------------
load_dotenv()  # 读取 .env（本地开发用；在 HF Space 用 Secrets）

# -----------------------------
# 数据库配置（Neon/SQLite）
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # 本地开发回退到 SQLite
    print("警告：未找到云数据库地址，将使用本地SQLite文件。")
    DATABASE_URL = "sqlite:///./mindgarden.db"

# Neon 建议开启 TLS；如果 URL 中缺少 sslmode，则补上
if DATABASE_URL.startswith("postgresql://") and "sslmode=" not in DATABASE_URL:
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{sep}sslmode=require"

# 部分环境/旧驱动不支持 channel_binding=require，会导致 SSL 被断开
if "channel_binding=require" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "").replace("?channel_binding=require", "?")

# 创建 Engine：开启探活 & 连接回收，适配 serverless 空闲挂起
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # 取连接前 ping，失效则重连
    pool_recycle=1800,    # 连接最大生存 30 分钟，避免被服务端断开
    pool_size=5,
    max_overflow=0,
)

# Session 工厂 & 依赖（每请求创建/关闭）
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """FastAPI 依赖：确保每个请求用完即关闭会话，避免长连失效。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 根据模型建表（简单场景可用；复杂迁移建议 Alembic）
models.Base.metadata.create_all(bind=engine)

# -----------------------------
# Gemini API 配置
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("警告：未设置 GEMINI_API_KEY，AI 分析接口将报错。")
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel("gemini-2.5-pro")  # 你的原配置

# -----------------------------
# FastAPI 应用 & 中间件
# -----------------------------
app = FastAPI()

# CORS：生产环境建议把域名放到 ORIGINS 环境变量（逗号分隔），否则默认 *
origins_env = os.getenv("ORIGINS", "").strip()
if origins_env:
    origins = [o.strip() for o in origins_env.split(",") if o.strip()]
else:
    origins = ["*"]  # 开发期放开；上线可改为你的 Vercel 域名

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# 全局异常处理：保证前端总能拿到 JSON
# -----------------------------
logger = logging.getLogger("uvicorn.error")

@app.exception_handler(Exception)
async def all_exception_handler(request, exc: Exception):
    logger.exception(exc)
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "server_error", "detail": str(exc)[:200]},
    )

# -----------------------------
# 工具函数
# -----------------------------
def extract_json_from_string(text: str) -> Optional[str]:
    """从任意文本中提取第一个 JSON 对象（尽量宽松）。"""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else None

def get_ai_analysis(prompt: str) -> str:
    """封装 Gemini 调用，统一异常转为 500。"""
    try:
        resp = ai_model.generate_content(prompt)
        return resp.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI API Error: {e}")

# -----------------------------
# 健康检查（用于唤醒 & 自测数据库连通）
# -----------------------------
@app.get("/health")
def health():
    with engine.begin() as conn:
        conn.exec_driver_sql("SELECT 1")
    return {"ok": True}

# -----------------------------
# API 端点
# -----------------------------
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

    # 1) 获取当前日记
    current_diary = db.query(models.Diary).filter(models.Diary.id == diary_id).first()
    if current_diary is None:
        raise HTTPException(status_code=404, detail="Diary not found")

    # 2) 最近 3 篇历史（日记 ID 倒序，排除当前）
    recent_diaries = (
        db.query(models.Diary)
        .filter(models.Diary.id < diary_id)
        .order_by(desc(models.Diary.id))
        .limit(3)
        .all()
    )

    # 3) 组装历史上下文
    history_context = ""
    if recent_diaries:
        history_context += "--- 这是我最近的一些日记作为参考 ---\n\n"
        for diary in reversed(recent_diaries):
            history_context += f"日期: {diary.date}\n内容:\n{diary.content}\n\n---\n\n"

    # 4) Prompt（带上下文）
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
""".strip()

    try:
        print("▶️ 调用 Gemini 进行分析 ...")
        analysis_text = get_ai_analysis(prompt)

        json_string = extract_json_from_string(analysis_text or "")
        if not json_string:
            raise ValueError("LLM 未返回可解析的 JSON")

        analysis_json = json.loads(json_string)
        score = analysis_json.get("score")
        analysis = analysis_json.get("analysis")
        if score is None or analysis is None:
            raise ValueError("JSON 中缺少 score 或 analysis 字段")

        print("✅ 解析成功，返回结果。")
        return schemas.AnalysisResponse(score=score, analysis=analysis)

    except Exception as e:
        print(f"❌ 分析过程中出错: {e}")
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {e}")
