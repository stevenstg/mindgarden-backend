# 使用官方的Python镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /code

# 复制依赖文件并安装
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 复制所有应用代码
COPY . /code/

# 暴露端口 (Hugging Face Spaces使用7860)
EXPOSE 7860

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]