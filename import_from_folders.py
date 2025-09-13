# import_from_folders.py
import os
import re
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models

# --- 配置 ---
load_dotenv()
DIARY_FOLDER_PATH = os.getenv("DIARY_FOLDER_PATH")
DATABASE_URL = "sqlite:///./mindgarden.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# vvvv 定义一个辅助函数，用于从文件名中提取数字 vvvv
def extract_day_number(filename):
    """从'Day26.md'这样的文件名中提取数字26，如果失败则返回一个大数以便排序。"""
    match = re.search(r'\d+', filename)
    if match:
        return int(match.group(0))
    return float('inf') # 如果没有数字，把它排到最后
# ^^^^ 定义辅助函数结束 ^^^^

def sync_diaries_from_folders():
    if not DIARY_FOLDER_PATH or not os.path.isdir(DIARY_FOLDER_PATH):
        print("错误：日记文件夹路径未设置或无效，请检查 .env 文件。")
        return

    db = SessionLocal()
    print(f"正在从 {DIARY_FOLDER_PATH} 同步日记...")

    # vvvv 先对文件夹进行排序 vvvv
    month_folders = sorted(os.listdir(DIARY_FOLDER_PATH))
    # ^^^^ 文件夹排序结束 ^^^^

    for month_folder in month_folders:
        month_folder_path = os.path.join(DIARY_FOLDER_PATH, month_folder)
        if os.path.isdir(month_folder_path):
            try:
                year, month = map(int, month_folder.split('.'))
            except ValueError:
                print(f"跳过格式不正确的文件夹: {month_folder}")
                continue

            # vvvv 对日记文件进行数字排序 vvvv
            day_files = sorted(
                [f for f in os.listdir(month_folder_path) if f.lower().startswith("day") and f.endswith(".md")],
                key=extract_day_number
            )
            # ^^^^ 日记文件排序结束 ^^^^

            for day_file in day_files:
                day_match = re.search(r'\d+', day_file)
                if not day_match:
                    continue
                
                day_number = int(day_match.group(0))
                diary_date_str = f"{year}-{month:02d}-Day{day_number}"
                
                existing_diary = db.query(models.Diary).filter(models.Diary.date == diary_date_str).first()
                if existing_diary:
                    continue

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