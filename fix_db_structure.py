
import os
import logging
from sqlalchemy import create_engine, text

def fix_analysis_data_table():
    """Добавляет отсутствующие колонки в таблицу analysis_data"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logging.info("Начинаем исправление структуры таблицы analysis_data...")
    
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logging.error("Не установлена переменная DATABASE_URL")
        return
    
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as connection:
            # Проверяем существует ли таблица analysis_data
            result = connection.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = :table_name
                );
            """).bindparams(table_name='analysis_data'))
            
            if not result.scalar():
                logging.info("Таблица analysis_data не существует. Создаем новую таблицу...")
                # Если таблицы нет, будем использовать миграцию в app.py
                return
            
            # Проверяем и добавляем необходимые колонки
            required_columns = [
                ('confidence_score', 'FLOAT'),
                ('classified_by', 'VARCHAR(50)'),
                ('analysis_state', 'VARCHAR(50) DEFAULT \'pending\''),
                ('matched_historical_data', 'JSON'),
                ('analysis_date', 'TIMESTAMP')
            ]
            
            for col_name, col_type in required_columns:
                # Проверяем наличие колонки
                result = connection.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = :table_name AND column_name = :column_name
                    );
                """).bindparams(table_name='analysis_data', column_name=col_name))
                
                if not result.scalar():
                    logging.info(f"Добавляем отсутствующую колонку {col_name} в таблицу analysis_data")
                    try:
                        # Need to construct this dynamically as column types can't be parameterized
                        sql = f"ALTER TABLE analysis_data ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
                        connection.execute(text(sql))
                        connection.commit()
                        logging.info(f"Успешно добавлена колонка {col_name}")
                    except Exception as e:
                        connection.rollback()
                        logging.error(f"Ошибка при добавлении колонки {col_name}: {str(e)}")
            
            logging.info("Исправление структуры таблицы analysis_data завершено")
                
    except Exception as e:
        logging.error(f"Ошибка при обновлении базы данных: {str(e)}", exc_info=True)

if __name__ == "__main__":
    fix_analysis_data_table()
