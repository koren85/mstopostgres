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
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'analysis_data'
                ORDER BY ordinal_position;
            """))

            for col in columns:
                logging.info(f"  {col.column_name}: {col.data_type}")

            # Получаем количество записей
            count_result = connection.execute(text("SELECT COUNT(*) FROM analysis_data"))
            total_count = count_result.scalar()
            logging.info(f"Всего записей в таблице: {total_count}")

            # Проверяем пустые значения в a_ouid
            null_count = connection.execute(text("SELECT COUNT(*) FROM analysis_data WHERE a_ouid IS NULL"))
            null_a_ouid = null_count.scalar()
            logging.info(f"Записей с NULL в поле a_ouid: {null_a_ouid} ({null_a_ouid/total_count*100:.2f}%)")

            # Выводим примеры первых 3 записей
            logging.info("Примеры записей:")
            sample_records = connection.execute(text("""
                SELECT id, batch_id, file_name, a_ouid, mssql_sxclass_name, upload_date 
                FROM analysis_data 
                LIMIT 3
            """))

            for record in sample_records:
                logging.info(f"  ID: {record.id}, Batch: {record.batch_id}, File: {record.file_name}")
                logging.info(f"  A_OUID: {record.a_ouid}, Class: {record.mssql_sxclass_name}")

            # Проверяем исходные данные в Excel (проверяем, есть ли соответствующие записи)
            logging.info("Анализ оригинальных данных из Excel по значению mssql_sxclass_name:")
            class_names = connection.execute(text("""
                SELECT mssql_sxclass_name, COUNT(*) as count
                FROM analysis_data
                GROUP BY mssql_sxclass_name
                ORDER BY count DESC
                LIMIT 5
            """))

            for name_record in class_names:
                logging.info(f"  {name_record.mssql_sxclass_name}: {name_record.count} записей")

            # Проверяем batch_id записей
            logging.info("Информация по batch_id:")
            batches = connection.execute(text("""
                SELECT batch_id, file_name, COUNT(*) as record_count
                FROM analysis_data
                GROUP BY batch_id, file_name
            """))

            for batch in batches:
                logging.info(f"  Batch: {batch.batch_id}, File: {batch.file_name}, Records: {batch.record_count}")

            # Получаем несколько записей для анализа (from original code)
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

            # Проверяем наличие заполненных полей mssql_sxclass_name (from original code, slightly modified)
            names_query = text("""
                SELECT mssql_sxclass_name, COUNT(*) 
                FROM analysis_data 
                WHERE mssql_sxclass_name IS NOT NULL
                GROUP BY mssql_sxclass_name
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """)

            names = connection.execute(names_query).fetchall()

            logging.info(f"\nПримеры заполненных полей mssql_sxclass_name (всего {len(names)}):")
            for name, count in names:
                logging.info(f"  '{name}': {count} записей")

    except Exception as e:
        logging.error(f"Ошибка при проверке таблицы analysis_data: {str(e)}", exc_info=True)

if __name__ == "__main__":
    check_analysis_data()