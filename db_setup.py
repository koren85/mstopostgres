
import os
import logging
from sqlalchemy import create_engine, text
import sys

def setup_database():
    """Проверяет структуру базы данных и добавляет необходимые колонки"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logging.info("Начинаем проверку структуры базы данных...")
    
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logging.error("Не установлена переменная DATABASE_URL")
        return
    
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as connection:
            # Проверяем существует ли таблица classification_rules
            result = connection.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'classification_rules'
                );
            """))
            if not result.scalar():
                logging.info("Таблица classification_rules не существует, будет создана автоматически.")
                return
            
            # Проверяем наличие колонки confidence_threshold
            result = connection.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'classification_rules' AND column_name = 'confidence_threshold'
                );
            """))
            if not result.scalar():
                logging.info("Добавляем колонку confidence_threshold в таблицу classification_rules")
                try:
                    connection.execute(text("""
                        ALTER TABLE classification_rules 
                        ADD COLUMN IF NOT EXISTS confidence_threshold FLOAT DEFAULT 0.8;
                    """))
                    connection.commit()  # Явное подтверждение изменений
                    logging.info("Колонка confidence_threshold успешно добавлена")
                except Exception as e:
                    connection.rollback()  # Откат при ошибке
                    logging.error(f"Ошибка при добавлении колонки confidence_threshold: {str(e)}")
            
            # Проверяем наличие колонки source_batch_id
            result = connection.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'classification_rules' AND column_name = 'source_batch_id'
                );
            """))
            if not result.scalar():
                logging.info("Добавляем колонку source_batch_id в таблицу classification_rules")
                try:
                    connection.execute(text("""
                        ALTER TABLE classification_rules 
                        ADD COLUMN IF NOT EXISTS source_batch_id VARCHAR(36);
                    """))
                    connection.commit()  # Явное подтверждение изменений
                    logging.info("Колонка source_batch_id успешно добавлена")
                except Exception as e:
                    connection.rollback()  # Откат при ошибке
                    logging.error(f"Ошибка при добавлении колонки source_batch_id: {str(e)}")
            
            # Проверка таблицы migration_classes
            result = connection.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'migration_classes'
                );
            """))
            if not result.scalar():
                logging.info("Таблица migration_classes не существует, будет создана автоматически.")
                return
            
            # Проверяем необходимые колонки в migration_classes
            required_columns = [
                ('batch_id', 'VARCHAR(36)'),
                ('file_name', 'VARCHAR(255)'),
                ('confidence_score', 'FLOAT'),
                ('classified_by', 'VARCHAR(50)')
            ]
            
            for col_name, col_type in required_columns:
                result = connection.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'migration_classes' AND column_name = '{col_name}'
                    );
                """))
                if not result.scalar():
                    logging.info(f"Добавляем колонку {col_name} в таблицу migration_classes")
                    connection.execute(text(f"""
                        ALTER TABLE migration_classes 
                        ADD COLUMN {col_name} {col_type};
                    """))
                    logging.info(f"Колонка {col_name} успешно добавлена")
                    
            # Проверка таблицы discrepancies
            result = connection.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'discrepancies'
                );
            """))
            if not result.scalar():
                logging.info("Таблица discrepancies не существует, будет создана автоматически.")
                return
                
            # Проверяем необходимые колонки в discrepancies
            discrepancy_columns = [
                ('resolved', 'BOOLEAN DEFAULT FALSE'),
                ('resolution_note', 'TEXT')
            ]
            
            for col_name, col_type in discrepancy_columns:
                result = connection.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'discrepancies' AND column_name = '{col_name}'
                    );
                """))
                if not result.scalar():
                    logging.info(f"Добавляем колонку {col_name} в таблицу discrepancies")
                    connection.execute(text(f"""
                        ALTER TABLE discrepancies 
                        ADD COLUMN {col_name} {col_type};
                    """))
                    logging.info(f"Колонка {col_name} успешно добавлена")
                    
            logging.info("Проверка структуры базы данных успешно завершена")
                
    except Exception as e:
        logging.error(f"Ошибка при проверке/обновлении базы данных: {str(e)}", exc_info=True)

if __name__ == "__main__":
    setup_database()
