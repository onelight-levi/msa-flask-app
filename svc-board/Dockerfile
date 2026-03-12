FROM python:3.9-slim
WORKDIR /app
# 먼저 의존성 파일을 복사하여 캐시 효율을 높입니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 나머지 소스 코드를 복사합니다.
COPY . .
CMD ["python", "app.py"]