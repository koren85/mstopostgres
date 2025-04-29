from datetime import datetime
from flask import Flask
from sqlalchemy import inspect
from database import db
from models import PriznakCorrectionHistory

def create_priznak_history_table():
    """
    Создает таблицу для истории корректировок признаков
    """
    # Проверяем, существует ли таблица
    inspector = inspect(db.engine)
    table_exists = 'priznak_correction_history' in inspector.get_table_names()
    
    if not table_exists:
        # Создаем таблицу
        PriznakCorrectionHistory.__table__.create(db.engine)
        print("Создана таблица priznak_correction_history")
    else:
        print("Таблица priznak_correction_history уже существует")
    
    return True

if __name__ == '__main__':
    # Создаем приложение Flask
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///migration.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Инициализируем базу данных
    db.init_app(app)
    
    # Выполняем миграцию в контексте приложения
    with app.app_context():
        create_priznak_history_table() 