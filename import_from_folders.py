# import_from_folders.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import date
import re
import models

# --- 配置 ---
load_dotenv()
DIARY_FOLDER_PATH = os.getenv("DIARY_FOLDER_PATH") # 请确保.env文件里有这个路径
DATABASE_URL = "sqlite:///./mindgarden.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def sync_diaries_from_folders():
    if not DIARY_FOLDER_PATH or not os.path.isdir(DIARY_FOLDER_PATH):
        print("错误：日记文件夹路径未设置或无效，请检查 .env 文件。")
        return

    db = SessionLocal()
    print(f"正在从 {DIARY_FOLDER_PATH} 同步日记...")

    # 遍历年月文件夹，例如 "2025.8"
    for month_folder in os.listdir(DIARY_FOLDER_PATH):
        month_folder_path = os.path.join(DIARY_FOLDER_PATH, month_folder)
        if os.path.isdir(month_folder_path):
            try:
                year, month = map(int, month_folder.split('.'))
            except ValueError:
                print(f"跳过格式不正确的文件夹: {month_folder}")
                continue

            # 遍历日记文件，例如 "Day26.md"
            for day_file in os.listdir(month_folder_path):
                if day_file.lower().startswith("day") and day_file.endswith(".md"):
                    # 从 "Day26.md" 中提取数字 26
                    day_match = re.search(r'\d+', day_file)
                    if not day_match:
                        continue
                    
                    day = int(day_match.group(0))

                    try:
                        diary_date = date(year, month, day)
                    except ValueError:
                        print(f"跳过无效日期文件: {month_folder}/{day_file}")
                        continue
                    
                    # 检查数据库中是否已存在
                    existing_diary = db.query(models.Diary).filter(models.Diary.date == diary_date).first()
                    if existing_diary:
                        continue # 如果已存在，则跳过

                    # 读取文件内容并添加
                    file_path = os.path.join(month_folder_path, day_file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    new_diary = models.Diary(date=diary_date, content=content)
                    db.add(new_diary)
                    print(f"添加新日记：{diary_date}")

    db.commit()
    db.close()
    print("同步完成！")

if __name__ == "__main__":
    # 确保数据库和表已创建
    models.Base.metadata.create_all(bind=engine)
    sync_diaries_from_folders()