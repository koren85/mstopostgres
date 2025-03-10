import os
import logging
import multiprocessing
from app import app
from db_setup import setup_database

if __name__ == "__main__":
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Проверяем и настраиваем структуру БД перед запуском
    logging.info("Проверка структуры базы данных перед запуском...")
    setup_database()

    # Запуск приложения
    # В development режиме используем встроенный сервер Flask
    if os.environ.get("FLASK_ENV") == "development":
        app.run(host="0.0.0.0", port=5000, debug=True)
    else:
        # В production режиме используем Gunicorn с нашей конфигурацией
        from gunicorn.app.base import BaseApplication

        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                config = {
                    key: value for key, value in self.options.items()
                    if key in self.cfg.settings and value is not None
                }
                for key, value in config.items():
                    self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        options = {
            'bind': '0.0.0.0:5000',
            'workers': multiprocessing.cpu_count(),
            'worker_class': 'sync',
            'worker_connections': 1000,
            'timeout': 120,
            'keepalive': 2,
            'accesslog': '-',
            'errorlog': '-',
            'loglevel': 'info',
            'reload': True
        }

        StandaloneApplication(app, options).run()