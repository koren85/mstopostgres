
import os
import logging
from sqlalchemy import create_engine, text
from datetime import datetime
import json

def check_analysis_data():
    """Проверяет содержимое таблицы analysis_data"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logging.info("Начинаем проверку данных в таблице analysis_data...")

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

            # Проверяем структуру таблицы
            logging.info("Структура таблицы analysis_data:")
            columns = connection.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'analysis_data'
                ORDER BY ordinal_position;
            """))

            for col in columns:
                logging.info(f"  {col.column_name}: {col.data_type} (nullable: {col.is_nullable})")

            # Получаем количество записей
            count_result = connection.execute(text("SELECT COUNT(*) FROM analysis_data"))
            total_count = count_result.scalar()
            logging.info(f"Всего записей в таблице: {total_count}")

            # Проверяем количество записей по batch_id
            batches = connection.execute(text("""
                SELECT batch_id, COUNT(*) as record_count, file_name
                FROM analysis_data
                GROUP BY batch_id, file_name
                ORDER BY MAX(upload_date) DESC
            """))
            
            logging.info("Информация по батчам:")
            for batch in batches:
                logging.info(f"  Batch: {batch.batch_id}, File: {batch.file_name}, Records: {batch.record_count}")

            # Проверяем пустые значения в важных полях
            null_fields = ['a_ouid', 'mssql_sxclass_name', 'mssql_sxclass_description', 'priznak']
            for field in null_fields:
                null_count = connection.execute(text(f"SELECT COUNT(*) FROM analysis_data WHERE {field} IS NULL"))
                null_field_count = null_count.scalar()
                percentage = (null_field_count / total_count * 100) if total_count > 0 else 0
                logging.info(f"Записей с NULL в поле {field}: {null_field_count} ({percentage:.2f}%)")

            # Выводим примеры первых 5 записей с подробной информацией
            logging.info("Примеры записей:")
            sample_records = connection.execute(text("""
                SELECT *
                FROM analysis_data 
                ORDER BY upload_date DESC
                LIMIT 5
            """))

            for i, record in enumerate(sample_records):
                logging.info(f"\nЗапись #{i+1}:")
                record_dict = dict(record._mapping)
                
                # Отображаем основные поля
                logging.info(f"  ID: {record_dict.get('id')}")
                logging.info(f"  Batch: {record_dict.get('batch_id')}")
                logging.info(f"  File: {record_dict.get('file_name')}")
                logging.info(f"  A_OUID: {record_dict.get('a_ouid')}")
                logging.info(f"  Class Name: {record_dict.get('mssql_sxclass_name')}")
                logging.info(f"  Description: {record_dict.get('mssql_sxclass_description')}")
                logging.info(f"  Priznak: {record_dict.get('priznak')}")
                logging.info(f"  Analysis State: {record_dict.get('analysis_state')}")
                
                # Проверяем matched_historical_data
                matched_data = record_dict.get('matched_historical_data')
                if matched_data:
                    if isinstance(matched_data, str):
                        try:
                            parsed_data = json.loads(matched_data)
                            logging.info(f"  Matched Historical Data: {len(parsed_data)} элементов")
                            for j, match in enumerate(parsed_data[:3]):  # Показываем первые 3 совпадения
                                logging.info(f"    Match #{j+1}: {match}")
                        except json.JSONDecodeError:
                            logging.warning(f"  Matched Historical Data: невалидный JSON: {matched_data[:100]}...")
                    elif isinstance(matched_data, list):
                        logging.info(f"  Matched Historical Data: {len(matched_data)} элементов")
                        for j, match in enumerate(matched_data[:3]):  # Показываем первые 3 совпадения
                            logging.info(f"    Match #{j+1}: {match}")
                    else:
                        logging.info(f"  Matched Historical Data: {type(matched_data).__name__} - {matched_data}")
                else:
                    logging.info("  Matched Historical Data: NULL")

            # Проверяем статусы анализа
            logging.info("\nСтатусы анализа:")
            states = connection.execute(text("""
                SELECT analysis_state, COUNT(*) 
                FROM analysis_data 
                GROUP BY analysis_state
            """))

            for state in states:
                logging.info(f"  {state.analysis_state}: {state[1]} записей")

            # Проверяем заполненность priznak
            priznak_info = connection.execute(text("""
                SELECT 
                    CASE WHEN priznak IS NULL THEN 'NULL' ELSE priznak END as priznak_value,
                    COUNT(*) 
                FROM analysis_data 
                GROUP BY 
                    CASE WHEN priznak IS NULL THEN 'NULL' ELSE priznak END
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """))

            logging.info("\nРаспределение значений priznak:")
            for priznak in priznak_info:
                logging.info(f"  '{priznak[0]}': {priznak[1]} записей")

    except Exception as e:
        logging.error(f"Ошибка при проверке таблицы analysis_data: {str(e)}", exc_info=True)

if __name__ == "__main__":
    check_analysis_data()
