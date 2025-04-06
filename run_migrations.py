#!/usr/bin/env python3
"""
Скрипт для ручного запуска миграций на продакшн-сервере.
Выполняет только миграции, не запуская веб-приложение.
"""
import os
import logging
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def main():
    print("Запуск миграций базы данных...")
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Инициализируем Flask и SQLAlchemy
    from app import create_app
    app = create_app()
    
    # Запускаем миграции в контексте приложения
    with app.app_context():
        print("Инициализация приложения выполнена")
        from migrations import run_migrations
        
        try:
            # Запускаем миграции
            run_migrations()
            print("Миграции успешно выполнены!")
        except Exception as e:
            print(f"Ошибка при выполнении миграций: {str(e)}")
            raise

if __name__ == "__main__":
    main() 