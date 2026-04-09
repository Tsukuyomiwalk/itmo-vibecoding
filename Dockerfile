FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости отдельным слоем для кэширования
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py database.py api_client.py scheduler.py deepseek_client.py ./

RUN mkdir -p /app/data

CMD ["python", "bot.py"]
