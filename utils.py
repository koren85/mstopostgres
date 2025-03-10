import pandas as pd
from models import MigrationClass, Discrepancy, db
from sqlalchemy import func
import logging
from classification import create_batch_id, classify_record, analyze_batch_discrepancies

def process_excel_file(file, source_system):
    """Process uploaded Excel file and convert to database records"""
    # Создаем уникальный ID для этой загрузки
    batch_id = create_batch_id()

    # Сначала попробуем прочитать с обычными заголовками
    df = pd.read_excel(file)

    required_columns = [
        'A_OUID', 'MSSQL_SXCLASS_DESCRIPTION', 'MSSQL_SXCLASS_NAME',
        'MSSQL_SXCLASS_MAP', 'priznak'
    ]

    # Если не найдены требуемые столбцы, попробуем использовать вторую строку как заголовки
    if not all(col in df.columns for col in required_columns):
        logging.info("Trying to read Excel with header in the second row")
        df = pd.read_excel(file, header=1)

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

    records = []
    for _, row in df.iterrows():
        # Проверяем и преобразуем a_ouid в числовой тип
        try:
            a_ouid = int(row['A_OUID']) if pd.notna(row['A_OUID']) else None
        except (ValueError, TypeError):
            logging.warning(f"Invalid A_OUID value: {row['A_OUID']}, setting to None")
            a_ouid = None

        # Получаем классификацию для записи
        classification = classify_record(
            class_name=str(row['MSSQL_SXCLASS_NAME']) if pd.notna(row['MSSQL_SXCLASS_NAME']) else None,
            description=str(row['MSSQL_SXCLASS_DESCRIPTION']) if pd.notna(row['MSSQL_SXCLASS_DESCRIPTION']) else None,
            batch_id=batch_id
        )

        # Если в Excel есть признак, используем его (ручная классификация)
        if pd.notna(row['priznak']):
            priznak = str(row['priznak'])
            classified_by = 'manual'
            confidence_score = 1.0
        else:
            # Иначе используем автоматическую классификацию
            priznak = classification['priznak']
            classified_by = classification['method']
            confidence_score = classification['confidence']

        record = {
            'batch_id': batch_id,
            'file_name': file.filename,
            'a_ouid': a_ouid,
            'mssql_sxclass_description': str(row['MSSQL_SXCLASS_DESCRIPTION']) if pd.notna(row['MSSQL_SXCLASS_DESCRIPTION']) else None,
            'mssql_sxclass_name': str(row['MSSQL_SXCLASS_NAME']) if pd.notna(row['MSSQL_SXCLASS_NAME']) else None,
            'mssql_sxclass_map': str(row['MSSQL_SXCLASS_MAP']) if pd.notna(row['MSSQL_SXCLASS_MAP']) else None,
            'priznak': priznak,
            'source_system': source_system,
            'confidence_score': confidence_score,
            'classified_by': classified_by
        }
        records.append(record)

    return batch_id, records

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