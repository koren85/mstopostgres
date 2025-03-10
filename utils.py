import pandas as pd
from models import MigrationClass, Discrepancy, db
from sqlalchemy import func
import logging

def process_excel_file(file, source_system):
    """Process uploaded Excel file and convert to database records"""
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
        
        # Проверяем и преобразуем другие поля в строковый тип или None
        record = {
            'a_ouid': a_ouid,
            'mssql_sxclass_description': str(row['MSSQL_SXCLASS_DESCRIPTION']) if pd.notna(row['MSSQL_SXCLASS_DESCRIPTION']) else None,
            'mssql_sxclass_name': str(row['MSSQL_SXCLASS_NAME']) if pd.notna(row['MSSQL_SXCLASS_NAME']) else None,
            'mssql_sxclass_map': str(row['MSSQL_SXCLASS_MAP']) if pd.notna(row['MSSQL_SXCLASS_MAP']) else None,
            'priznak': str(row['priznak']) if pd.notna(row['priznak']) else None,
            'source_system': source_system
        }
        records.append(record)
    
    return records

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

def suggest_classification(class_name, description):
    """Suggest classification based on historical data"""
    # Check exact matches first
    matches = MigrationClass.query.filter_by(
        mssql_sxclass_name=class_name,
        mssql_sxclass_description=description
    ).with_entities(
        MigrationClass.priznak,
        func.count(MigrationClass.id).label('count')
    ).group_by(MigrationClass.priznak).order_by(
        func.count(MigrationClass.id).desc()
    ).all()
    
    if matches:
        suggestions = [
            {'priznak': m.priznak, 'confidence': m.count} 
            for m in matches
        ]
        return {
            'suggestions': suggestions,
            'has_discrepancies': len(suggestions) > 1
        }
    
    # If no exact matches, look for similar patterns
    similar = MigrationClass.query.filter(
        MigrationClass.mssql_sxclass_name.like(f"%{class_name}%")
    ).with_entities(
        MigrationClass.priznak,
        func.count(MigrationClass.id).label('count')
    ).group_by(MigrationClass.priznak).order_by(
        func.count(MigrationClass.id).desc()
    ).limit(3).all()
    
    return {
        'suggestions': [
            {'priznak': s.priznak, 'confidence': s.count} 
            for s in similar
        ],
        'has_discrepancies': False
    }
