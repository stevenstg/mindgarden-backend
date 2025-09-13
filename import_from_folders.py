# import_from_folders.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import re
import models

# --- 配置 ---
load_dotenv()
DIARY_FOLDER_PATH = os.getenv("DIARY_FOLDER_PATH")
DATABASE_URL = "sqlite:///./mindgarden.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def sync_diaries_from_folders():
    if not DIARY_FOLDER_PATH or not os.path.isdir(DIARY_FOLDER_PATH):
        print("错误：日记文件夹路径未设置或无效，请检查 .env 文件。")
        return

    db = SessionLocal()
    print(f"正在从 {DIARY_FOLDER_PATH} 同步日记...")

    for month_folder in os.listdir(DIARY_FOLDER_PATH):
        month_folder_path = os.path.join(DIARY_FOLDER_PATH, month_folder)
        if os.path.isdir(month_folder_path):
            try:
                # 从 "2025.8" 中提取年份和月份
                year, month = map(int, month_folder.split('.'))
            except ValueError:
                print(f"跳过格式不正确的文件夹: {month_folder}")
                continue

            for day_file in os.listdir(month_folder_path):
                if day_file.lower().startswith("day") and day_file.endswith(".md"):
                    day_match = re.search(r'\d+', day_file)
                    if not day_match:
                        continue
                    
                    day_number = int(day_match.group(0))

                    # vvvv 新的日期字符串拼接逻辑 vvvv
                    # 使用 f-string 格式化月份为两位数（如08, 09），方便未来排序
                    diary_date_str = f"{year}-{month:02d}-Day{day_number}"
                    # ^^^^ 新的日期字符串拼接逻辑 ^^^^
                    
                    # 检查数据库中是否已存在
                    existing_diary = db.query(models.Diary).filter(models.Diary.date == diary_date_str).first()
                    if existing_diary:
                        continue

                    # 读取文件内容并添加
                    file_path = os.path.join(month_folder_path, day_file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    new_diary = models.Diary(date=diary_date_str, content=content)
                    db.add(new_diary)
                    print(f"添加新日记：{diary_date_str}")

    db.commit()
    db.close()
    print("同步完成！")

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    sync_diaries_from_folders()