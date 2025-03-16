import os
import logging
from flask import Flask
from database import db
from models import TransferRule, AnalysisData
from classification import apply_transfer_rules

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Создаем тестовое приложение
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    # Проверяем правило с IS_EMPTY
    empty_rule = TransferRule.query.filter_by(condition_type='IS_EMPTY', condition_field='MSSQL_SXCLASS_MAP').first()
    if empty_rule:
        print(f'Найдено правило для пустых значений: #{empty_rule.id}: {empty_rule.category_name} - {empty_rule.condition_type} - {empty_rule.condition_field} - {empty_rule.transfer_action}')
    else:
        print('Правило для пустых значений не найдено')
    
    # Создаем тестовую запись с пустым значением MSSQL_SXCLASS_MAP
    test_record = type('TestRecord', (), {
        'mssql_sxclass_name': 'reestrIdentityLinkHadrProcessin',
        'mssql_sxclass_description': 'Тестовое описание',
        'mssql_sxclass_map': None,  # Пустое значение
        'parent_class': 'TestParent',
        'created_by': 'Test'
    })
    
    # Применяем правила переноса к тестовой записи
    print("\nПрименяем правила переноса к тестовой записи с пустым MSSQL_SXCLASS_MAP:")
    result = apply_transfer_rules(test_record)
    
    # Выводим результат
    if result['priznak']:
        print(f"Результат: {result['priznak']} (правило #{result['rule_id']})")
    else:
        print("Не найдено подходящих правил для тестовой записи")
    
    # Проверяем, почему не срабатывает правило для пустых значений
    print("\nПроверка условия IS_EMPTY для тестовой записи:")
    field_value = test_record.mssql_sxclass_map
    is_none = field_value is None
    is_empty_string = isinstance(field_value, str) and field_value.strip() == ''
    match = is_none or is_empty_string
    print(f"Значение поля: {field_value}, тип: {type(field_value)}")
    print(f"is_none: {is_none}, is_empty_string: {is_empty_string}, match: {match}")
    
    # Проверяем все правила с типом IS_EMPTY
    print("\nПроверяем все правила с типом IS_EMPTY:")
    empty_rules = TransferRule.query.filter_by(condition_type='IS_EMPTY').all()
    for rule in empty_rules:
        print(f'Правило #{rule.id}: {rule.category_name} - {rule.condition_type} - {rule.condition_field} - {rule.condition_value} - {rule.transfer_action}') 