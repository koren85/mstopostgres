from database import db
import logging
from sqlalchemy import text

def run_migrations():
    """Выполняет необходимые миграции базы данных"""
    try:
        # Проверяем наличие новых колонок в таблице classification_rules
        with db.engine.connect() as conn:
            # Начинаем транзакцию
            trans = conn.begin()
            
            # Проверяем существование колонки category_name
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='classification_rules' AND column_name='category_name'"))
            if not result.fetchone():
                logging.info("Добавление колонки category_name в таблицу classification_rules")
                conn.execute(text("ALTER TABLE classification_rules ADD COLUMN category_name VARCHAR(255)"))
            
            # Проверяем существование колонки condition_type
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='classification_rules' AND column_name='condition_type'"))
            if not result.fetchone():
                logging.info("Добавление колонки condition_type в таблицу classification_rules")
                conn.execute(text("ALTER TABLE classification_rules ADD COLUMN condition_type VARCHAR(50)"))
            
            # Проверяем существование колонки transfer_action
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='classification_rules' AND column_name='transfer_action'"))
            if not result.fetchone():
                logging.info("Добавление колонки transfer_action в таблицу classification_rules")
                conn.execute(text("ALTER TABLE classification_rules ADD COLUMN transfer_action VARCHAR(255)"))
            
            # Проверяем существование колонки comment
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='classification_rules' AND column_name='comment'"))
            if not result.fetchone():
                logging.info("Добавление колонки comment в таблицу classification_rules")
                conn.execute(text("ALTER TABLE classification_rules ADD COLUMN comment TEXT"))
            
            # Фиксируем транзакцию
            trans.commit()
            
        logging.info("Миграции успешно выполнены")
    except Exception as e:
        logging.error(f"Ошибка при выполнении миграций: {e}")
        raise 