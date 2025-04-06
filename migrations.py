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
            
            # Выполняем миграцию для добавления столбца base_url в таблицу analysis_data
            add_base_url_column(conn)
            
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

def add_base_url_column(connection):
    """Миграция для добавления столбца base_url в таблицу analysis_data"""
    try:
        # Проверяем, нужно ли выполнять миграцию
        migration_key = 'add_base_url_column'
        if is_migration_applied(connection, migration_key):
            logging.info(f"Миграция {migration_key} уже применена")
            return
        
        logging.info("Выполняется миграция для добавления столбца base_url в таблицу analysis_data...")
        
        # Проверяем существование столбца
        result = connection.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'analysis_data' AND column_name = 'base_url'
            )
        """))
        
        if not result.scalar():
            # Добавляем столбец base_url, если его нет
            connection.execute(text("ALTER TABLE analysis_data ADD COLUMN base_url VARCHAR(255)"))
            logging.info("Столбец base_url успешно добавлен в таблицу analysis_data")
        else:
            logging.info("Столбец base_url уже существует в таблице analysis_data")
        
        # Отмечаем миграцию как выполненную
        mark_migration_as_applied(connection, migration_key)
        logging.info(f"Миграция {migration_key} успешно применена")
    except Exception as e:
        logging.error(f"Ошибка при добавлении столбца base_url: {str(e)}", exc_info=True)

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