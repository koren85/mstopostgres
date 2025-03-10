import pandas as pd
from models import MigrationClass, Discrepancy, db
from sqlalchemy import func
import logging
from classification import create_batch_id, classify_record, analyze_batch_discrepancies

def process_excel_file(file, source_system):
    """Process uploaded Excel file and convert to database records"""
    logging.info(f"===== НАЧАЛО ОБРАБОТКИ EXCEL ФАЙЛА =====")
    logging.info(f"Файл: {file.filename}, источник: {source_system}")
    logging.info(f"Тип объекта файла: {type(file)}")

    # Создаем уникальный ID для этой загрузки
    batch_id = create_batch_id()
    logging.info(f"Создан batch_id: {batch_id}")

    try:
        # Сохраняем исходный файл для отладки
        file_path = f"/tmp/{file.filename}"
        logging.info(f"[ЭТАП 1] Попытка сохранения файла по пути: {file_path}")
        file.save(file_path)
        import os
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logging.info(f"[ЭТАП 1] Файл успешно сохранен. Размер: {file_size} байт")
        else:
            logging.error(f"[ЭТАП 1] Файл не был сохранен по пути {file_path}")
            raise FileNotFoundError(f"Не удалось сохранить файл по пути {file_path}")

        logging.info(f"[ЭТАП 2] Начинаем чтение Excel файла...")
        # Сначала попробуем прочитать с обычными заголовками
        try:
            df = pd.read_excel(file_path)
            logging.info(f"[ЭТАП 2] Файл прочитан успешно")
            logging.info(f"[ЭТАП 2] Найдены столбцы: {list(df.columns)}")
            logging.info(f"[ЭТАП 2] Размер DataFrame: {df.shape}")
        except Exception as e:
            logging.error(f"[ЭТАП 2] Ошибка при чтении Excel файла: {str(e)}", exc_info=True)
            raise ValueError(f"Не удалось прочитать Excel файл: {str(e)}")

        required_columns = [
            'A_OUID', 'MSSQL_SXCLASS_DESCRIPTION', 'MSSQL_SXCLASS_NAME',
            'MSSQL_SXCLASS_MAP', 'priznak'
        ]

        # Если не найдены требуемые столбцы, попробуем использовать вторую строку как заголовки
        if not all(col in df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in df.columns]
            logging.info(f"[ЭТАП 2] Не найдены столбцы: {missing}. Пробуем использовать вторую строку как заголовки")
            try:
                df = pd.read_excel(file_path, header=1)
                logging.info(f"[ЭТАП 2] После изменения заголовка найдены столбцы: {list(df.columns)}")
            except Exception as e:
                logging.error(f"[ЭТАП 2] Ошибка при повторном чтении Excel файла с header=1: {str(e)}", exc_info=True)
                raise ValueError(f"Не удалось прочитать Excel файл с другим заголовком: {str(e)}")

        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            error_msg = f"Отсутствуют обязательные столбцы: {', '.join(missing_columns)}"
            logging.error(f"[ЭТАП 2] {error_msg}")
            raise ValueError(error_msg)

        logging.info(f"[ЭТАП 3] Все необходимые столбцы найдены. Обрабатываем {len(df)} записей")

        records = []
        processed_count = 0
        error_count = 0
        
        for index, row in df.iterrows():
            try:
                if index % 100 == 0:
                    logging.info(f"[ЭТАП 3] Обработано {index} записей из {len(df)}")
                
                # Проверяем и преобразуем a_ouid в числовой тип
                try:
                    a_ouid = int(row['A_OUID']) if pd.notna(row['A_OUID']) else None
                except (ValueError, TypeError):
                    logging.warning(f"[ЭТАП 3] Запись {index}: Некорректное значение A_OUID: {row['A_OUID']}, установлено в None")
                    a_ouid = None

                # Логируем данные для отладки при каждой 10-й записи или при ошибке
                if index % 10 == 0:
                    logging.info(f"[ЭТАП 3] Запись {index}: A_OUID={a_ouid}, NAME={row['MSSQL_SXCLASS_NAME'] if pd.notna(row['MSSQL_SXCLASS_NAME']) else 'None'}")

                # Подготовка данных для классификации
                class_name = str(row['MSSQL_SXCLASS_NAME']) if pd.notna(row['MSSQL_SXCLASS_NAME']) else None
                description = str(row['MSSQL_SXCLASS_DESCRIPTION']) if pd.notna(row['MSSQL_SXCLASS_DESCRIPTION']) else None
                
                logging.info(f"[ЭТАП 3] Запись {index}: Начинаем классификацию")
                # Получаем классификацию для записи
                classification = classify_record(
                    class_name=class_name,
                    description=description,
                    batch_id=batch_id
                )

                logging.info(f"[ЭТАП 3] Запись {index}: Результат классификации: {classification}")

                # Если в Excel есть признак, используем его (ручная классификация)
                if pd.notna(row['priznak']):
                    priznak = str(row['priznak'])
                    classified_by = 'manual'
                    confidence_score = 1.0
                    logging.info(f"[ЭТАП 3] Запись {index}: Используется ручная классификация, priznak={priznak}")
                else:
                    # Иначе используем автоматическую классификацию
                    priznak = classification['priznak']
                    classified_by = classification['method']
                    confidence_score = classification['confidence']
                    logging.info(f"[ЭТАП 3] Запись {index}: Автоматическая классификация: method={classified_by}, priznak={priznak}, confidence={confidence_score}")

                record = {
                    'batch_id': batch_id,
                    'file_name': file.filename,
                    'a_ouid': a_ouid,
                    'mssql_sxclass_description': description,
                    'mssql_sxclass_name': class_name,
                    'mssql_sxclass_map': str(row['MSSQL_SXCLASS_MAP']) if pd.notna(row['MSSQL_SXCLASS_MAP']) else None,
                    'priznak': priznak,
                    'source_system': source_system,
                    'confidence_score': confidence_score,
                    'classified_by': classified_by
                }
                records.append(record)
                processed_count += 1
                
            except Exception as e:
                error_count += 1
                logging.error(f"[ЭТАП 3] Ошибка при обработке записи {index}: {str(e)}", exc_info=True)
                # Пропускаем проблемную запись и продолжаем

        logging.info(f"[ЭТАП 4] Завершена обработка {processed_count} записей (успешно: {processed_count}, с ошибками: {error_count})")

        # Открываем файл снова для восстановления исходного положения
        file.stream.seek(0)
        return batch_id, records

    except Exception as e:
        logging.error(f"[КРИТИЧЕСКАЯ ОШИБКА] Ошибка при обработке файла: {str(e)}", exc_info=True)
        # Открываем файл снова для восстановления исходного положения
        file.stream.seek(0)
        raise

def analyze_discrepancies():
    """Analyze and record discrepancies in classifications"""
    # Find classes with different priznaks across sources
    discrepancies = db.session.query(
        MigrationClass.mssql_sxclass_name,
        MigrationClass.mssql_sxclass_description,
        func.array_agg(MigrationClass.priznak.distinct()).label('different_priznaks'),
        func.array_agg(MigrationClass.source_system.distinct()).label('source_systems')
    ).group_by(
        MigrationClass.mssql_sxclass_name,
        MigrationClass.mssql_sxclass_description
    ).having(
        func.count(MigrationClass.priznak.distinct()) > 1
    ).all()

    # Clear existing discrepancies
    Discrepancy.query.delete()

    # Record new discrepancies
    for disc in discrepancies:
        new_disc = Discrepancy(
            class_name=disc.mssql_sxclass_name,
            description=disc.mssql_sxclass_description,
            different_priznaks=disc.different_priznaks,
            source_systems=disc.source_systems
        )
        db.session.add(new_disc)

    db.session.commit()

def get_batch_statistics(batch_id):
    """Get statistics for a specific batch"""
    stats = db.session.query(
        func.count(MigrationClass.id).label('total_records'),
        func.count(func.distinct(MigrationClass.source_system)).label('source_systems'),
        func.sum(
            func.case([(MigrationClass.classified_by == 'manual', 1)], else_=0)
        ).label('manual_classifications'),
        func.sum(
            func.case([(MigrationClass.classified_by == 'historical', 1)], else_=0)
        ).label('historical_classifications'),
        func.sum(
            func.case([(MigrationClass.classified_by == 'rule', 1)], else_=0)
        ).label('rule_based_classifications'),
        func.avg(MigrationClass.confidence_score).label('avg_confidence')
    ).filter(
        MigrationClass.batch_id == batch_id
    ).first()

    return {
        'total_records': stats.total_records,
        'source_systems': stats.source_systems,
        'classifications': {
            'manual': stats.manual_classifications,
            'historical': stats.historical_classifications,
            'rule_based': stats.rule_based_classifications
        },
        'avg_confidence': round(stats.avg_confidence, 2) if stats.avg_confidence else 0
    }