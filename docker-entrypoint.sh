#!/bin/bash
set -e

echo "Инициализация приложения и запуск миграций..."
python -c "from app import create_app; app=create_app(); app.app_context().push()"

echo "Запуск приложения..."
exec python app.py 