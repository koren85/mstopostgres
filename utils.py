import os
import logging
import uuid
import pandas as pd
from datetime import datetime
from app import db
from models import MigrationClass, ClassificationRule
from sqlalchemy import func

def process_excel_file(file, source_system):
    """Обработка загруженного Excel файла"""
    logging.info(f"Начинаем обработку Excel файла: {file.filename}")

    # Генерируем уникальный идентификатор для группировки записей из одного файла
    batch_id = str(uuid.uuid4())
    logging.info(f"Создан batch_id: {batch_id} для файла {file.filename}")

    # Читаем Excel
    try:
        df = pd.read_excel(file)
        logging.info(f"Успешно прочитан Excel файл, строк: {len(df)}")

        # Проверяем, есть ли в Excel колонка priznak
        has_priznak_column = 'PRIZNAK' in df.columns
        if has_priznak_column:
            logging.info("В Excel файле обнаружена колонка PRIZNAK, будем сохранять её значения")

        # Преобразуем DataFrame в список словарей для добавления в БД
        records = []

        for index, row in df.iterrows():
            record = {
                'batch_id': batch_id,
                'file_name': file.filename,
                'a_ouid': row.get('A_OUID'),
                'mssql_sxclass_description': row.get('MSSQL_SXCLASS_DESCRIPTION'),
                'mssql_sxclass_name': row.get('MSSQL_SXCLASS_NAME'),
                'mssql_sxclass_map': row.get('MSSQL_SXCLASS_MAP'),
                'priznak': row.get('PRIZNAK') if has_priznak_column else None,  # Сохраняем значение, если есть
                'system_class': row.get('SYSTEM_CLASS'),
                'is_link_table': row.get('IS_LINK_TABLE'),
                'parent_class': row.get('PARENT_CLASS'),
                'child_classes': row.get('CHILD_CLASSES'),
                'child_count': row.get('CHILD_COUNT'),
                'created_date': row.get('CREATED_DATE'),
                'created_by': row.get('CREATED_BY'),
                'modified_date': row.get('MODIFIED_DATE'),
                'modified_by': row.get('MODIFIED_BY'),
                'folder_paths': row.get('FOLDER_PATHS'),
                'object_count': row.get('OBJECT_COUNT'),
                'last_object_created': row.get('LAST_OBJECT_CREATED'),
                'last_object_modified': row.get('LAST_OBJECT_MODIFIED'),
                'attribute_count': row.get('ATTRIBUTE_COUNT'),
                'category': row.get('CATEGORY'),
                'migration_flag': row.get('MIGRATION_FLAG'),
                'rule_info': row.get('RULE_INFO'),
                'source_system': source_system,
                'upload_date': datetime.utcnow(),
                'confidence_score': 0,  # Изначально уверенность 0
                'classified_by': 'manual' if has_priznak_column and pd.notna(row.get('PRIZNAK')) else None  # Отмечаем записи с уже заполненным priznak как классифицированные вручную
            }
            records.append(record)

            if index % 100 == 0:
                logging.info(f"Обработано {index} записей из файла")

        logging.info(f"Успешно обработано {len(records)} записей из Excel файла")
        return batch_id, records
    except Exception as e:
        logging.error(f"Ошибка при обработке Excel файла: {str(e)}", exc_info=True)
        raise ValueError(f"Ошибка при обработке Excel файла: {str(e)}")

def analyze_discrepancies():
    """Анализ и выявление несоответствий в данных"""
    from models import Discrepancy

    logging.info("Начинаем анализ несоответствий")
    try:
        # Поиск классов с одинаковыми именами, но разными признаками
        discrepancies = db.session.query(
            MigrationClass.mssql_sxclass_name,
            MigrationClass.mssql_sxclass_description,
            func.array_agg(func.distinct(MigrationClass.priznak)).label('different_priznaks'),
            func.array_agg(func.distinct(MigrationClass.source_system)).label('source_systems')
        ).group_by(
            MigrationClass.mssql_sxclass_name,
            MigrationClass.mssql_sxclass_description
        ).having(
            func.count(func.distinct(MigrationClass.priznak)) > 1
        ).all()

        logging.info(f"Найдено {len(discrepancies)} несоответствий")

        # Очищаем предыдущие результаты
        db.session.query(Discrepancy).delete()

        # Сохраняем новые несоответствия
        for d in discrepancies:
            discrepancy = Discrepancy(
                class_name=d.mssql_sxclass_name,
                description=d.mssql_sxclass_description,
                different_priznaks=d.different_priznaks,
                source_systems=d.source_systems
            )
            db.session.add(discrepancy)

        db.session.commit()
        logging.info("Анализ несоответствий завершен успешно")

    except Exception as e:
        db.session.rollback()
        logging.error(f"Ошибка при анализе несоответствий: {str(e)}", exc_info=True)
        raise

def get_batch_statistics(batch_id):
    """Получение статистики по конкретной загрузке"""
    try:
        # Общее количество записей в загрузке
        total_records = db.session.query(func.count(MigrationClass.id)).filter(
            MigrationClass.batch_id == batch_id
        ).scalar()

        # Уникальные источники
        source_systems = db.session.query(func.count(func.distinct(MigrationClass.source_system))).filter(
            MigrationClass.batch_id == batch_id
        ).scalar()

        # Статистика по методам классификации
        manual_count = db.session.query(func.count(MigrationClass.id)).filter(
            MigrationClass.batch_id == batch_id,
            MigrationClass.classified_by == 'manual'
        ).scalar() or 0

        historical_count = db.session.query(func.count(MigrationClass.id)).filter(
            MigrationClass.batch_id == batch_id,
            MigrationClass.classified_by == 'historical'
        ).scalar() or 0

        rule_based_count = db.session.query(func.count(MigrationClass.id)).filter(
            MigrationClass.batch_id == batch_id,
            MigrationClass.classified_by == 'rule'
        ).scalar() or 0

        # Средняя уверенность
        avg_confidence = db.session.query(func.avg(MigrationClass.confidence_score)).filter(
            MigrationClass.batch_id == batch_id,
            MigrationClass.confidence_score.isnot(None)
        ).scalar() or 0

        return {
            'total_records': total_records,
            'source_systems': source_systems,
            'classifications': {
                'manual': manual_count,
                'historical': historical_count,
                'rule_based': rule_based_count
            },
            'avg_confidence': avg_confidence
        }
    except Exception as e:
        logging.error(f"Ошибка при получении статистики по загрузке {batch_id}: {str(e)}", exc_info=True)
        return {
            'total_records': 0,
            'source_systems': 0,
            'classifications': {
                'manual': 0,
                'historical': 0,
                'rule_based': 0
            },
            'avg_confidence': 0
        }