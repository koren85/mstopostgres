import uuid
from datetime import datetime
import pandas as pd
from sqlalchemy import func
from models import db, MigrationClass, ClassificationRule, Discrepancy

def create_batch_id():
    """Generate a unique batch ID for grouping uploaded records"""
    return str(uuid.uuid4())

def classify_record(class_name, description, batch_id=None):
    """
    Classify a record based on historical data and rules
    Returns: dict with classification and confidence score
    """
    # Поиск точных совпадений в предыдущих загрузках
    matches = MigrationClass.query.filter(
        (MigrationClass.mssql_sxclass_name == class_name) &
        (MigrationClass.mssql_sxclass_description == description) &
        (MigrationClass.batch_id != batch_id)  # Исключаем текущую загрузку
    ).with_entities(
        MigrationClass.priznak,
        func.count(MigrationClass.id).label('count')
    ).group_by(MigrationClass.priznak).all()
    
    if matches:
        total = sum(m.count for m in matches)
        best_match = max(matches, key=lambda m: m.count)
        confidence = best_match.count / total
        
        return {
            'priznak': best_match.priznak,
            'confidence': confidence,
            'method': 'historical',
            'has_conflicts': len(matches) > 1
        }
    
    # Поиск по правилам классификации
    rules = ClassificationRule.query.order_by(ClassificationRule.priority.desc()).all()
    for rule in rules:
        if rule.field == 'name' and rule.pattern in class_name:
            return {
                'priznak': rule.priznak_value,
                'confidence': rule.confidence_threshold,
                'method': 'rule',
                'rule_id': rule.id
            }
        elif rule.field == 'description' and rule.pattern in description:
            return {
                'priznak': rule.priznak_value,
                'confidence': rule.confidence_threshold,
                'method': 'rule',
                'rule_id': rule.id
            }
    
    # TODO: Добавить классификацию через нейросеть
    return {
        'priznak': None,
        'confidence': 0,
        'method': None
    }

def export_batch_results(batch_id):
    """Export classification results for a batch to Excel"""
    records = MigrationClass.query.filter_by(batch_id=batch_id).all()
    
    data = []
    for record in records:
        data.append({
            'A_OUID': record.a_ouid,
            'MSSQL_SXCLASS_NAME': record.mssql_sxclass_name,
            'MSSQL_SXCLASS_DESCRIPTION': record.mssql_sxclass_description,
            'priznak': record.priznak,
            'confidence_score': record.confidence_score,
            'classified_by': record.classified_by,
            'upload_date': record.upload_date
        })
    
    df = pd.DataFrame(data)
    output_file = f'classification_results_{batch_id[:8]}.xlsx'
    df.to_excel(output_file, index=False)
    return output_file

def analyze_batch_discrepancies(batch_id):
    """Analyze discrepancies within a batch and with historical data"""
    # Находим случаи, когда для одинаковых записей были разные признаки
    current_batch = MigrationClass.query.filter_by(batch_id=batch_id).all()
    
    for record in current_batch:
        historical = MigrationClass.query.filter(
            MigrationClass.batch_id != batch_id,
            MigrationClass.mssql_sxclass_name == record.mssql_sxclass_name,
            MigrationClass.mssql_sxclass_description == record.mssql_sxclass_description,
            MigrationClass.priznak != record.priznak
        ).all()
        
        if historical:
            different_priznaks = list(set([h.priznak for h in historical] + [record.priznak]))
            source_systems = list(set([h.source_system for h in historical] + [record.source_system]))
            
            discrepancy = Discrepancy(
                class_name=record.mssql_sxclass_name,
                description=record.mssql_sxclass_description,
                different_priznaks=different_priznaks,
                source_systems=source_systems
            )
            db.session.add(discrepancy)
    
    db.session.commit()
