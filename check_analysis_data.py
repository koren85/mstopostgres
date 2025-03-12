
import os
import logging
from sqlalchemy import create_engine, text
import json

def check_analysis_data_table():
    """Проверяет содержимое таблицы analysis_data"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logging.info("Начинаем проверку содержимого таблицы analysis_data...")

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
                logging.info("Таблица analysis_data не существует.")
                return
                
            # Получаем список колонок таблицы
            columns_query = text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'analysis_data'
                ORDER BY ordinal_position;
            """)
            
            columns = connection.execute(columns_query).fetchall()
            
            logging.info(f"Структура таблицы analysis_data ({len(columns)} колонок):")
            for col in columns:
                logging.info(f"  {col[0]}: {col[1]}, nullable: {col[2]}")
                
            # Проверяем количество записей
            count_query = text("SELECT COUNT(*) FROM analysis_data")
            count = connection.execute(count_query).scalar()
            
            logging.info(f"Количество записей в таблице: {count}")
            
            if count == 0:
                logging.info("Таблица пуста, нет данных для проверки")
                return
                
            # Получаем несколько записей для анализа
            records_query = text("""
                SELECT * FROM analysis_data 
                ORDER BY upload_date DESC
                LIMIT 3
            """)
            
            records = connection.execute(records_query).fetchall()
            column_names = connection.execute(records_query).keys()
            
            for i, record in enumerate(records):
                logging.info(f"\nЗапись #{i+1}:")
                record_dict = {}
                
                for j, col_name in enumerate(column_names):
                    value = record[j]
                    if value is not None:
                        try:
                            if col_name == 'matched_historical_data' and value:
                                # Пытаемся распарсить JSON
                                if isinstance(value, str):
                                    try:
                                        parsed = json.loads(value)
                                        value = f"JSON: {parsed}"
                                    except:
                                        value = f"Невалидный JSON: {value}"
                            record_dict[col_name] = f"{value} (тип: {type(value).__name__})"
                        except Exception as e:
                            record_dict[col_name] = f"[Ошибка отображения: {str(e)}]"
                    else:
                        record_dict[col_name] = "NULL"
                
                # Выводим все поля записи
                for key, value in record_dict.items():
                    logging.info(f"  {key}: {value}")
            
            # Проверяем наличие заполненных полей mssql_sxclass_name
            names_query = text("""
                SELECT mssql_sxclass_name, COUNT(*) 
                FROM analysis_data 
                WHERE mssql_sxclass_name IS NOT NULL
                GROUP BY mssql_sxclass_name
                LIMIT 10
            """)
            
            names = connection.execute(names_query).fetchall()
            
            logging.info(f"\nПримеры заполненных полей mssql_sxclass_name (всего {len(names)}):")
            for name, count in names:
                logging.info(f"  '{name}': {count} записей")
                
    except Exception as e:
        logging.error(f"Ошибка при проверке таблицы analysis_data: {str(e)}", exc_info=True)

if __name__ == "__main__":
    check_analysis_data_table()
