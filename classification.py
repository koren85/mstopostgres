import uuid
from datetime import datetime
import pandas as pd
from sqlalchemy import func
from models import db, MigrationClass, ClassificationRule, Discrepancy
import logging

def create_batch_id():
    """Generate a unique batch ID for grouping uploaded records"""
    return str(uuid.uuid4())

def classify_record(class_name, description, batch_id=None):
    """
    Classify a record based on historical data and rules
    Returns: dict with classification and confidence score
    """
    logging.info(f"[КЛАССИФИКАЦИЯ] Начинаем классификацию: class_name='{class_name}', description='{description}'")

    try:
        # Поиск точных совпадений в предыдущих загрузках
        logging.info(f"[КЛАССИФИКАЦИЯ] Поиск исторических совпадений...")
        matches = MigrationClass.query.filter(
            (MigrationClass.mssql_sxclass_name == class_name) &
            (MigrationClass.mssql_sxclass_description == description) &
            (MigrationClass.batch_id != batch_id)  # Исключаем текущую загрузку
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

            # Попробуем использовать безопасный запрос без проверки столбцов
            try:
                # Проверим наличие колонки confidence_threshold напрямую через SQL
                from sqlalchemy import text
                from app import db

                # Выполняем SQL-запрос напрямую для проверки наличия колонки
                column_check_query = text("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'classification_rules' AND column_name = 'confidence_threshold'
                """)
                result = db.session.execute(column_check_query).fetchone()

                has_confidence_threshold = result is not None
                logging.info(f"[КЛАССИФИКАЦИЯ] Проверка наличия колонки confidence_threshold: {has_confidence_threshold}")

                # Получаем правила, безопасно извлекая только гарантированно существующие данные
                rules_query = text("""
                    SELECT id, pattern, field, priznak_value, priority
                    FROM classification_rules 
                    ORDER BY priority DESC
                """)

                rule_results = db.session.execute(rules_query).fetchall()
                logging.info(f"[КЛАССИФИКАЦИЯ] Найдено {len(rule_results)} правил классификации")

                # Обрабатываем правила
                for rule in rule_results:
                    confidence = 0.8  # Значение по умолчанию всегда

                    # Извлечем данные из результата запроса
                    rule_id = rule[0]
                    pattern = rule[1]
                    field = rule[2]
                    priznak_value = rule[3]


                    if field == 'name' and class_name and pattern in class_name:
                        logging.info(f"[КЛАССИФИКАЦИЯ] Найдено правило для имени: pattern='{pattern}', priznak='{priznak_value}'")
                        return {
                            'priznak': priznak_value,
                            'confidence': confidence,
                            'method': 'rule',
                            'rule_id': rule_id
                        }
                    elif field == 'description' and description and pattern in description:
                        logging.info(f"[КЛАССИФИКАЦИЯ] Найдено правило для описания: pattern='{pattern}', priznak='{priznak_value}'")
                        return {
                            'priznak': priznak_value,
                            'confidence': confidence,
                            'method': 'rule',
                            'rule_id': rule_id
                        }

            except Exception as e:
                # Если SQL-запросы не сработали, пробуем через ORM с обработкой ошибок
                logging.warning(f"[КЛАССИФИКАЦИЯ] Ошибка при прямом SQL-запросе: {str(e)}, пробуем через ORM")

                # Пробуем загрузить правила, игнорируя отсутствующие поля
                from sqlalchemy import select
                stmt = select(ClassificationRule).order_by(ClassificationRule.priority.desc())
                rules = db.session.execute(stmt).scalars().all()
                logging.info(f"[КЛАССИФИКАЦИЯ] Через ORM найдено {len(rules)} правил")

                for rule in rules:
                    confidence = 0.8  # Значение по умолчанию
                    try:
                        # Пробуем получить confidence_threshold, перехватываем AttributeError если поле не существует
                        confidence = getattr(rule, 'confidence_threshold', 0.8)
                    except:
                        pass

                    if rule.field == 'name' and class_name and rule.pattern in class_name:
                        logging.info(f"[КЛАССИФИКАЦИЯ] Найдено правило для имени: pattern='{rule.pattern}', priznak='{rule.priznak_value}'")
                        return {
                            'priznak': rule.priznak_value,
                            'confidence': confidence,
                            'method': 'rule',
                            'rule_id': rule.id
                        }
                    elif rule.field == 'description' and description and rule.pattern in description:
                        logging.info(f"[КЛАССИФИКАЦИЯ] Найдено правило для описания: pattern='{rule.pattern}', priznak='{rule.priznak_value}'")
                        return {
                            'priznak': rule.priznak_value,
                            'confidence': confidence,
                            'method': 'rule',
                            'rule_id': rule.id
                        }
        except Exception as e:
            logging.error(f"[КЛАССИФИКАЦИЯ] Ошибка при поиске правил: {str(e)}", exc_info=True)
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

# Остальные функции остаются без изменений
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