import os
import logging
import json
from flask import Flask
from database import db
from models import TransferRule, AnalysisData, AnalysisResult
from classification import apply_transfer_rules

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Создаем тестовое приложение
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    # Получаем записи с пустыми значениями MSSQL_SXCLASS_MAP
    records = AnalysisData.query.filter(
        (AnalysisData.mssql_sxclass_map.is_(None)) | 
        (AnalysisData.mssql_sxclass_map == '')
    ).limit(5).all()
    
    print(f"Найдено {len(records)} записей с пустыми значениями MSSQL_SXCLASS_MAP")
    
    # Проверяем каждую запись
    for i, record in enumerate(records, 1):
        print(f"\n{i}. Запись: {record.mssql_sxclass_name}")
        print(f"   MSSQL_SXCLASS_MAP: '{record.mssql_sxclass_map}'")
        print(f"   Тип MSSQL_SXCLASS_MAP: {type(record.mssql_sxclass_map)}")
        print(f"   Текущий признак: {record.priznak}")
        
        # Применяем правила переноса
        result = apply_transfer_rules(record)
        
        # Выводим результат
        if result['priznak']:
            print(f"   Результат: {result['priznak']} (правило #{result['rule_id']})")
            
            # Обновляем запись с результатом применения правил
            record.priznak = result['priznak']
            record.confidence_score = result['confidence']
            record.classified_by = 'transfer_rule'
            record.rule_info = json.dumps({
                'rule_id': result['rule_id'],
                'category': result['category'],
                'transfer_action': result['transfer_action']
            })
            # Обновляем статус на "проанализировано"
            record.analysis_state = 'analyzed'
            
            print(f"   Запись обновлена: признак={record.priznak}, confidence={record.confidence_score}")
        else:
            print("   Не найдено подходящих правил")
    
    # Сохраняем изменения
    db.session.commit()
    print("\nИзменения сохранены в базе данных")
    
    # Проверяем правило с IS_EMPTY
    empty_rule = TransferRule.query.filter_by(condition_type='IS_EMPTY', condition_field='MSSQL_SXCLASS_MAP').first()
    if empty_rule:
        print(f'\nПравило для пустых значений: #{empty_rule.id}: {empty_rule.category_name} - {empty_rule.condition_type} - {empty_rule.condition_field} - {empty_rule.transfer_action}')
    else:
        print('\nПравило для пустых значений не найдено') 