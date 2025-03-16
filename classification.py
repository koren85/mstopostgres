import uuid
from datetime import datetime
import pandas as pd
from sqlalchemy import func, text
from database import db
from models import MigrationClass, Discrepancy, TransferRule
import logging

def create_batch_id():
    """Generate a unique batch ID for grouping uploaded records"""
    return str(uuid.uuid4())

def classify_record(record):
    """
    Classify a record based on historical data and rules
    Returns: dict with classification and confidence score
    """
    try:
        # Если у записи уже есть priznak, просто возвращаем его
        if record.priznak is not None:
            logging.info(f"[КЛАССИФИКАЦИЯ] Пропускаем классификацию, использую существующий priznak='{record.priznak}'")
            return {
                'priznak': record.priznak,
                'confidence': 1.0,  # Полная уверенность для существующих значений
                'method': 'manual'  # Считаем, что существующие значения были заданы вручную
            }
            
        logging.info(f"[КЛАССИФИКАЦИЯ] Начинаем классификацию: class_name='{record.mssql_sxclass_name}', description='{record.mssql_sxclass_description}'")

        # Поиск точных совпадений в предыдущих загрузках
        logging.info(f"[КЛАССИФИКАЦИЯ] Поиск исторических совпадений...")
        matches = MigrationClass.query.filter(
            (MigrationClass.mssql_sxclass_name == record.mssql_sxclass_name) &
            (MigrationClass.mssql_sxclass_description == record.mssql_sxclass_description) &
            (MigrationClass.batch_id != record.batch_id)  # Исключаем текущую загрузку
        ).with_entities(
            MigrationClass.priznak,
            func.count(MigrationClass.id).label('count')
        ).group_by(MigrationClass.priznak).all()

        logging.info(f"[КЛАССИФИКАЦИЯ] Найдено {len(matches)} исторических совпадений")

        if matches:
            total = sum(m.count for m in matches)
            best_match = max(matches, key=lambda m: m.count)
            confidence = best_match.count / total

            logging.info(f"[КЛАССИФИКАЦИЯ] Лучшее совпадение: priznak='{best_match.priznak}', confidence={confidence}")

            return {
                'priznak': best_match.priznak,
                'confidence': confidence,
                'method': 'historical',
                'has_conflicts': len(matches) > 1
            }

        # Поиск по правилам классификации
        try:
            logging.info(f"[КЛАССИФИКАЦИЯ] Поиск по правилам классификации...")

            # Получаем правила, безопасно извлекая только гарантированно существующие данные
            rules_query = text("""
                SELECT id, condition_value, condition_field, priznak_value, priority, confidence_threshold
                FROM transfer_rules 
                WHERE priznak_value IS NOT NULL
                ORDER BY priority DESC
            """)

            rule_results = db.session.execute(rules_query).fetchall()
            logging.info(f"[КЛАССИФИКАЦИЯ] Найдено {len(rule_results)} правил классификации")

            # Обрабатываем правила
            for rule in rule_results:
                # Извлечем данные из результата запроса
                rule_id = rule[0]
                pattern = rule[1]
                field = rule[2]
                priznak_value = rule[3]
                confidence = rule[5] if rule[5] is not None else 0.8  # Используем confidence_threshold если есть, иначе 0.8

                if field == 'name' and record.mssql_sxclass_name and pattern in record.mssql_sxclass_name:
                    logging.info(f"[КЛАССИФИКАЦИЯ] Найдено правило для имени: pattern='{pattern}', priznak='{priznak_value}'")
                    return {
                        'priznak': priznak_value,
                        'confidence': confidence,
                        'method': 'rule',
                        'rule_id': rule_id
                    }
                elif field == 'description' and record.mssql_sxclass_description and pattern in record.mssql_sxclass_description:
                    logging.info(f"[КЛАССИФИКАЦИЯ] Найдено правило для описания: pattern='{pattern}', priznak='{priznak_value}'")
                    return {
                        'priznak': priznak_value,
                        'confidence': confidence,
                        'method': 'rule',
                        'rule_id': rule_id
                    }

        except Exception as e:
            logging.warning(f"[КЛАССИФИКАЦИЯ] Ошибка при поиске правил: {str(e)}", exc_info=True)
            # Продолжаем с классификацией по умолчанию в случае ошибки

        # Если не найдено правил или произошла ошибка при их поиске
        logging.info(f"[КЛАССИФИКАЦИЯ] Не найдено подходящих правил или исторических данных. Используем пустую классификацию.")
        return {
            'priznak': None,
            'confidence': 0,
            'method': None
        }
    except Exception as e:
        logging.error(f"[КЛАССИФИКАЦИЯ] Критическая ошибка в classify_record: {str(e)}", exc_info=True)
        return {
            'priznak': None,
            'confidence': 0,
            'method': None
        }

def export_batch_results(records, batch_id):
    """Export classification results for a batch to Excel"""
    try:
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
    except Exception as e:
        logging.error(f"[ЭКСПОРТ] Ошибка при экспорте результатов: {str(e)}", exc_info=True)
        raise

def analyze_batch_discrepancies(batch_id):
    """Analyze discrepancies within a batch and with historical data"""
    try:
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
    except Exception as e:
        db.session.rollback()
        logging.error(f"[АНАЛИЗ] Ошибка при анализе несоответствий: {str(e)}", exc_info=True)
        raise

def apply_transfer_rules(record):
    """
    Применяет правила переноса к записи и определяет признак
    
    Args:
        record: объект AnalysisData или MigrationClass
        
    Returns:
        dict с результатами применения правил:
        {
            'priznak': определенный признак,
            'rule_id': ID правила, которое сработало,
            'category': категория правила,
            'transfer_action': действие по переносу,
            'confidence': уверенность (всегда 1.0 для правил)
        }
    """
    logging.info(f"[ПРАВИЛА ПЕРЕНОСА] Начинаем применение правил для: {record.mssql_sxclass_name}")
    
    # Получаем все правила, отсортированные по приоритету
    rules = TransferRule.query.order_by(TransferRule.priority).all()
    logging.info(f"[ПРАВИЛА ПЕРЕНОСА] Загружено {len(rules)} правил")
    
    for rule in rules:
        logging.info(f"[ПРАВИЛА ПЕРЕНОСА] Проверяем правило #{rule.id}: {rule.category_name} - {rule.condition_type} - {rule.condition_field}")
        # Проверяем соответствие правилу
        match = False
        
        # Получаем значение поля для проверки
        field_value = None
        if rule.condition_field == 'MSSQL_SXCLASS_NAME':
            field_value = record.mssql_sxclass_name
        elif rule.condition_field == 'MSSQL_SXCLASS_DESCRIPTION':
            field_value = record.mssql_sxclass_description
        elif rule.condition_field == 'MSSQL_SXCLASS_MAP':
            field_value = record.mssql_sxclass_map
        elif rule.condition_field == 'Родительский класс':
            field_value = record.parent_class
        elif rule.condition_field == 'Создал':
            field_value = record.created_by
        
        logging.info(f"[ПРАВИЛА ПЕРЕНОСА] Значение поля {rule.condition_field}: {field_value}, тип: {type(field_value)}")
        
        # Проверяем условие
        if rule.condition_type == 'IS_EMPTY':
            # Проверяем, что поле пустое
            is_none = field_value is None
            is_empty_string = isinstance(field_value, str) and field_value.strip() == ''
            match = is_none or is_empty_string
            logging.info(f"[ПРАВИЛА ПЕРЕНОСА] IS_EMPTY: поле={field_value}, is_none={is_none}, is_empty_string={is_empty_string}, match={match}")
            
        # Если поле пустое и условие не IS_EMPTY, пропускаем правило
        elif not field_value and rule.condition_type != 'ALWAYS_TRUE':
            logging.info(f"[ПРАВИЛА ПЕРЕНОСА] Пропускаем правило #{rule.id}, т.к. значение поля пустое")
            continue
            
        # Проверяем другие типы условий
        elif rule.condition_type == 'EXACT_EQUALS':
            # Проверяем на точное совпадение с любым из значений, разделенных точкой с запятой
            values = rule.condition_value.split(';')
            match = any(value.strip() == field_value for value in values)
            logging.info(f"[ПРАВИЛА ПЕРЕНОСА] EXACT_EQUALS: {values} == {field_value} -> {match}")
            
        elif rule.condition_type == 'STARTS_WITH':
            # Проверяем, начинается ли поле с любого из значений, разделенных точкой с запятой
            values = rule.condition_value.split(';')
            match = any(field_value.startswith(value.strip()) for value in values)
            logging.info(f"[ПРАВИЛА ПЕРЕНОСА] STARTS_WITH: {field_value} начинается с {values} -> {match}")
            
        elif rule.condition_type == 'CONTAINS':
            # Проверяем, содержит ли поле любое из значений, разделенных точкой с запятой
            values = rule.condition_value.split(';')
            match = any(value.strip() in field_value for value in values)
            logging.info(f"[ПРАВИЛА ПЕРЕНОСА] CONTAINS: {field_value} содержит {values} -> {match}")
            
        elif rule.condition_type == 'ALWAYS_TRUE':
            # Правило-заглушка, которое всегда срабатывает
            match = True
            logging.info(f"[ПРАВИЛА ПЕРЕНОСА] ALWAYS_TRUE -> {match}")
        
        # Если правило сработало, возвращаем результат
        if match:
            logging.info(f"[ПРАВИЛА ПЕРЕНОСА] Сработало правило #{rule.id}: {rule.category_name} - {rule.transfer_action}")
            
            # Определяем признак на основе действия по переносу
            priznak = None
            if rule.transfer_action == 'Переносим':
                priznak = 'Переносим'
            elif rule.transfer_action == 'Переносим пакетом':
                priznak = 'Переносим пакетом'
            elif rule.transfer_action == 'Не переносим':
                priznak = 'Не переносим'
            
            logging.info(f"[ПРАВИЛА ПЕРЕНОСА] Установлен признак: {priznak}")
            
            return {
                'priznak': priznak,
                'rule_id': rule.id,
                'category': rule.category_name,
                'transfer_action': rule.transfer_action,
                'confidence': 1.0,  # Для правил уверенность всегда 100%
                'method': 'transfer_rule'
            }
    
    # Если ни одно правило не сработало, возвращаем None
    logging.info(f"[ПРАВИЛА ПЕРЕНОСА] Не найдено подходящих правил для: {record.mssql_sxclass_name}")
    return {
        'priznak': None,
        'rule_id': None,
        'category': None,
        'transfer_action': None,
        'confidence': 0,
        'method': None
    }