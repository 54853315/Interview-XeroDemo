FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

# SQLite 数据目录
RUN mkdir -p /app/db

EXPOSE 5000

# 容器内必须绑定 0.0.0.0 才能从外部访问
CMD ["xerodemo", "web", "--host", "0.0.0.0", "--port", "5000"]
