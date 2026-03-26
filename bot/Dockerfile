FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ .

CMD ["python", "bot.py"]
