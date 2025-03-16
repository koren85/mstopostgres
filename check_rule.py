import os
from flask import Flask
from database import db
from models import TransferRule

# Создаем тестовое приложение
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    rule = TransferRule.query.get(75)
    if rule:
        print(f'Правило #{rule.id}: {rule.category_name} - {rule.condition_type} - {rule.condition_field} - {rule.condition_value} - {rule.transfer_action}')
    else:
        print('Правило с ID 75 не найдено')
        
    # Также проверим все правила с типом IS_EMPTY
    empty_rules = TransferRule.query.filter_by(condition_type='IS_EMPTY').all()
    print(f"\nНайдено {len(empty_rules)} правил с типом IS_EMPTY:")
    for rule in empty_rules:
        print(f'Правило #{rule.id}: {rule.category_name} - {rule.condition_type} - {rule.condition_field} - {rule.condition_value} - {rule.transfer_action}') 