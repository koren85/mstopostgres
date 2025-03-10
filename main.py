import os
import logging
from app import app
from db_setup import setup_database

if __name__ == '__main__':
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Проверяем и обновляем структуру БД перед запуском приложения
    logging.info("Запуск проверки структуры базы данных...")
    setup_database()
    logging.info("Проверка структуры базы данных завершена")

    # Запускаем приложение
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)