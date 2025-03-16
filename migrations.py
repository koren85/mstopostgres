from database import db
import logging
from sqlalchemy import text
import os

def run_migrations():
    """Выполняет необходимые миграции базы данных"""
    try:
        logging.info("Запуск миграций базы данных...")
        
        # Подключаемся к базе данных
        with db.engine.connect() as conn:
            # Начинаем транзакцию
            trans = conn.begin()
            
            # Выполняем миграцию для изменения типов данных в таблице analysis_data
            migrate_analysis_data_columns(conn)
            
            # Проверяем наличие новых колонок в таблице classification_rules
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
        logging.error(f"Ошибка при выполнении миграций: {str(e)}", exc_info=True)
        raise

def migrate_analysis_data_columns(connection):
    """Миграция для изменения типов данных в таблице analysis_data"""
    try:
        # Проверяем, нужно ли выполнять миграцию
        migration_key = 'analysis_data_text_columns'
        if is_migration_applied(connection, migration_key):
            logging.info(f"Миграция {migration_key} уже применена")
            return
        
        logging.info("Выполняется миграция для изменения типов данных в таблице analysis_data...")
        
        # Список колонок, которые нужно изменить с VARCHAR(255) на TEXT
        columns_to_change = [
            'mssql_sxclass_description',
            'mssql_sxclass_map',
            'parent_class',
            'child_classes',
            'created_by',
            'modified_by',
            'folder_paths',
            'category',
            'migration_flag',
            'rule_info'
        ]
        
        # Изменяем тип данных для каждой колонки
        for column in columns_to_change:
            try:
                logging.info(f"Изменение типа данных для колонки {column} на TEXT...")
                connection.execute(text(f"ALTER TABLE analysis_data ALTER COLUMN {column} TYPE TEXT"))
                logging.info(f"Тип данных для колонки {column} успешно изменен")
            except Exception as column_error:
                logging.error(f"Ошибка при изменении типа данных для колонки {column}: {str(column_error)}")
        
        # Отмечаем миграцию как выполненную
        mark_migration_as_applied(connection, migration_key)
        logging.info(f"Миграция {migration_key} успешно применена")
    except Exception as e:
        logging.error(f"Ошибка при выполнении миграции для изменения типов данных: {str(e)}", exc_info=True)

def is_migration_applied(connection, migration_key):
    """Проверяет, была ли применена миграция с указанным ключом"""
    try:
        # Проверяем, существует ли таблица migrations
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'migrations'
            )
        """))
        
        if not result.scalar():
            # Создаем таблицу migrations, если она не существует
            connection.execute(text("""
                CREATE TABLE migrations (
                    id SERIAL PRIMARY KEY,
                    migration_key VARCHAR(255) UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            return False
        
        # Проверяем, была ли применена миграция
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM migrations 
                WHERE migration_key = :key
            )
        """), {'key': migration_key})
        
        return result.scalar()
    except Exception as e:
        logging.error(f"Ошибка при проверке статуса миграции: {str(e)}", exc_info=True)
        return False

def mark_migration_as_applied(connection, migration_key):
    """Отмечает миграцию как выполненную"""
    try:
        connection.execute(text("""
            INSERT INTO migrations (migration_key)
            VALUES (:key)
        """), {'key': migration_key})
    except Exception as e:
        logging.error(f"Ошибка при отметке миграции как выполненной: {str(e)}", exc_info=True) 