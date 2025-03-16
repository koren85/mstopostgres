import os
import sys
import logging
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Получаем строку подключения к базе данных из переменной окружения или используем значение по умолчанию
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/mstopostgres')

def migrate_classification_rules():
    """
    Миграция данных из таблицы classification_rules в таблицу transfer_rules
    """
    try:
        # Создаем подключение к базе данных
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Проверяем существование таблицы classification_rules
        check_table_query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'classification_rules'
            )
        """)
        table_exists = session.execute(check_table_query).scalar()
        
        if not table_exists:
            logging.info("Таблица classification_rules не существует, миграция не требуется")
            return
        
        # Проверяем, есть ли данные в таблице classification_rules
        count_query = text("SELECT COUNT(*) FROM classification_rules")
        count = session.execute(count_query).scalar()
        
        if count == 0:
            logging.info("Таблица classification_rules пуста, миграция не требуется")
            return
        
        logging.info(f"Найдено {count} правил классификации для миграции")
        
        # Добавляем необходимые колонки в таблицу transfer_rules, если их еще нет
        add_columns_query = text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transfer_rules' AND column_name = 'confidence_threshold') THEN
                    ALTER TABLE transfer_rules ADD COLUMN confidence_threshold FLOAT DEFAULT 0.8;
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transfer_rules' AND column_name = 'source_batch_id') THEN
                    ALTER TABLE transfer_rules ADD COLUMN source_batch_id VARCHAR(36);
                END IF;
                
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transfer_rules' AND column_name = 'priznak_value') THEN
                    ALTER TABLE transfer_rules ADD COLUMN priznak_value VARCHAR(50);
                END IF;
            END
            $$;
        """)
        session.execute(add_columns_query)
        
        # Получаем все правила классификации
        rules_query = text("""
            SELECT id, pattern, field, priznak_value, priority, created_date, confidence_threshold, 
                   source_batch_id, category_name, condition_type, transfer_action, comment
            FROM classification_rules
        """)
        rules = session.execute(rules_query).fetchall()
        
        # Мигрируем каждое правило в таблицу transfer_rules
        for rule in rules:
            # Проверяем, существует ли уже правило с таким же приоритетом
            check_priority_query = text("""
                SELECT COUNT(*) FROM transfer_rules WHERE priority = :priority
            """)
            priority_exists = session.execute(check_priority_query, {"priority": rule.priority}).scalar() > 0
            
            # Если приоритет уже существует, увеличиваем его на 1000
            priority = rule.priority + 1000 if priority_exists else rule.priority
            
            # Вставляем правило в таблицу transfer_rules
            insert_query = text("""
                INSERT INTO transfer_rules (
                    priority, category_name, transfer_action, condition_type, condition_field, 
                    condition_value, comment, created_at, updated_at, confidence_threshold, 
                    source_batch_id, priznak_value
                ) VALUES (
                    :priority, :category_name, :transfer_action, :condition_type, :field, 
                    :pattern, :comment, :created_date, :created_date, :confidence_threshold, 
                    :source_batch_id, :priznak_value
                )
            """)
            
            session.execute(insert_query, {
                "priority": priority,
                "category_name": rule.category_name or "Автоматически созданное правило",
                "transfer_action": rule.transfer_action or rule.priznak_value,
                "condition_type": rule.condition_type or "CONTAINS",
                "field": rule.field,
                "pattern": rule.pattern,
                "comment": rule.comment or "",
                "created_date": rule.created_date or datetime.utcnow(),
                "confidence_threshold": rule.confidence_threshold or 0.8,
                "source_batch_id": rule.source_batch_id,
                "priznak_value": rule.priznak_value
            })
        
        # Сохраняем изменения
        session.commit()
        logging.info(f"Успешно мигрировано {len(rules)} правил классификации")
        
        # Спрашиваем пользователя, хочет ли он удалить таблицу classification_rules
        answer = input("Хотите удалить таблицу classification_rules? (y/n): ")
        if answer.lower() == 'y':
            drop_table_query = text("DROP TABLE classification_rules")
            session.execute(drop_table_query)
            session.commit()
            logging.info("Таблица classification_rules успешно удалена")
        
    except Exception as e:
        logging.error(f"Ошибка при миграции данных: {str(e)}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()

if __name__ == "__main__":
    migrate_classification_rules() 