FROM python:3.11-slim as builder

WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt pyproject.toml ./
COPY uv.lock ./

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Финальный этап
FROM python:3.11-slim

WORKDIR /app

# Копируем установленные зависимости из builder
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/

# Копируем код приложения
COPY . .

# Создаем директорию для загрузок
RUN mkdir -p uploads && chmod 777 uploads

# Переменные окружения по умолчанию
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

EXPOSE 5001

# Устанавливаем права на выполнение entrypoint скрипта
RUN chmod +x /app/docker-entrypoint.sh

CMD ["/app/docker-entrypoint.sh"] 