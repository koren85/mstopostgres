
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
            # Проверка таблицы classification_rules
            check_and_fix_table(connection, 'classification_rules', [
                ('pattern', 'VARCHAR(255) NOT NULL'),
                ('field', 'VARCHAR(50) NOT NULL'),
                ('priznak_value', 'VARCHAR(50) NOT NULL'),
                ('priority', 'INTEGER DEFAULT 0'),
                ('created_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('confidence_threshold', 'FLOAT DEFAULT 0.8'),
                ('source_batch_id', 'VARCHAR(36)')
            ])
            
            # Проверка таблицы migration_classes
            check_and_fix_table(connection, 'migration_classes', [
                ('batch_id', 'VARCHAR(36)'),
                ('file_name', 'VARCHAR(255)'),
                ('a_ouid', 'BIGINT'),
                ('mssql_sxclass_description', 'TEXT'),
                ('mssql_sxclass_name', 'TEXT'),
                ('mssql_sxclass_map', 'TEXT'),
                ('priznak', 'TEXT'),
                ('system_class', 'BOOLEAN'),
                ('is_link_table', 'BOOLEAN'),
                ('parent_class', 'TEXT'),
                ('child_classes', 'TEXT'),
                ('child_count', 'INTEGER'),
                ('created_date', 'TIMESTAMP'),
                ('created_by', 'TEXT'),
                ('modified_date', 'TIMESTAMP'),
                ('modified_by', 'TEXT'),
                ('folder_paths', 'TEXT'),
                ('object_count', 'INTEGER'),
                ('last_object_created', 'TIMESTAMP'),
                ('last_object_modified', 'TIMESTAMP'),
                ('attribute_count', 'INTEGER'),
                ('category', 'TEXT'),
                ('migration_flag', 'TEXT'),
                ('rule_info', 'TEXT'),
                ('source_system', 'TEXT'),
                ('upload_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('confidence_score', 'FLOAT'),
                ('classified_by', 'VARCHAR(50)')
            ])
            
            # Проверка таблицы discrepancies
            check_and_fix_table(connection, 'discrepancies', [
                ('class_name', 'TEXT'),
                ('description', 'TEXT'),
                ('different_priznaks', 'JSON'),
                ('source_systems', 'JSON'),
                ('detected_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('resolved', 'BOOLEAN DEFAULT FALSE'),
                ('resolution_note', 'TEXT')
            ])
            
            # Проверка таблицы analysis_data
            check_and_fix_table(connection, 'analysis_data', [
                ('batch_id', 'VARCHAR(36) NOT NULL'),
                ('file_name', 'VARCHAR(255)'),
                ('a_ouid', 'BIGINT'),
                ('mssql_sxclass_description', 'TEXT'),
                ('mssql_sxclass_name', 'TEXT'),
                ('mssql_sxclass_map', 'TEXT'),
                ('priznak', 'TEXT'),
                ('system_class', 'BOOLEAN'),
                ('is_link_table', 'BOOLEAN'),
                ('parent_class', 'TEXT'),
                ('child_classes', 'TEXT'),
                ('child_count', 'INTEGER'),
                ('created_date', 'TIMESTAMP'),
                ('created_by', 'TEXT'),
                ('modified_date', 'TIMESTAMP'),
                ('modified_by', 'TEXT'),
                ('folder_paths', 'TEXT'),
                ('object_count', 'INTEGER'),
                ('last_object_created', 'TIMESTAMP'),
                ('last_object_modified', 'TIMESTAMP'),
                ('attribute_count', 'INTEGER'),
                ('category', 'TEXT'),
                ('migration_flag', 'TEXT'),
                ('rule_info', 'TEXT'),
                ('source_system', 'TEXT'),
                ('upload_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('confidence_score', 'FLOAT'),
                ('classified_by', 'VARCHAR(50)'),
                ('analysis_state', 'VARCHAR(50) DEFAULT \'pending\''),
                ('matched_historical_data', 'JSON'),
                ('analysis_date', 'TIMESTAMP')
            ])
            
            logging.info("Проверка структуры базы данных успешно завершена")
                
    except Exception as e:
        logging.error(f"Ошибка при проверке/обновлении базы данных: {str(e)}", exc_info=True)

def check_and_fix_table(connection, table_name, required_columns):
    """Проверяет существование таблицы и наличие всех необходимых колонок"""
    logging.info(f"Проверка таблицы {table_name}...")
    
    # Проверяем существование таблицы
    result = connection.execute(text(f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = '{table_name}'
        );
    """))
    
    if not result.scalar():
        logging.info(f"Таблица {table_name} не существует. Будет создана автоматически.")
        create_table(connection, table_name, required_columns)
        return
    
    # Проверяем наличие всех необходимых колонок
    existing_columns = get_table_columns(connection, table_name)
    
    for col_name, col_type in required_columns:
        if col_name.lower() not in (col.lower() for col in existing_columns):
            logging.info(f"Добавляем отсутствующую колонку {col_name} в таблицу {table_name}")
            try:
                connection.execute(text(f"""
                    ALTER TABLE {table_name} 
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type};
                """))
                logging.info(f"Успешно добавлена колонка {col_name}")
            except Exception as e:
                logging.error(f"Ошибка при добавлении колонки {col_name}: {str(e)}")

def create_table(connection, table_name, columns):
    """Создает новую таблицу с указанными колонками"""
    try:
        # Формируем SQL для создания таблицы
        columns_sql = ", ".join([f"{name} {type_}" for name, type_ in columns])
        
        # Добавляем id колонку если она не указана
        if not any(col[0].lower() == 'id' for col in columns):
            columns_sql = f"id SERIAL PRIMARY KEY, {columns_sql}"
        
        sql = f"CREATE TABLE {table_name} ({columns_sql});"
        
        connection.execute(text(sql))
        connection.commit()
        logging.info(f"Таблица {table_name} успешно создана")
    except Exception as e:
        connection.rollback()
        logging.error(f"Ошибка при создании таблицы {table_name}: {str(e)}")

def get_table_columns(connection, table_name):
    """Возвращает список колонок таблицы"""
    result = connection.execute(text(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}'
    """))
    return [row[0] for row in result]

if __name__ == "__main__":
    setup_database()
