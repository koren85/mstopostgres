import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, url_for, redirect, send_file
from sqlalchemy import func, or_
import uuid
import pandas as pd  # Явный импорт pandas
from dotenv import load_dotenv  # Добавляем импорт dotenv
from database import db  # Импортируем db из database.py
from routes import init_routes
import json
# Проверяем наличие openpyxl
try:
    import openpyxl
    logging.info("openpyxl успешно импортирован")
except ImportError:
    logging.error("Библиотека openpyxl не установлена! Она необходима для чтения Excel файлов")
    os.system("pip install openpyxl")
    logging.info("Установлена библиотека openpyxl")

# Загружаем переменные окружения из .env файла
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)  # Логирование SQL-запросов

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")

    # Database configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }

    # Создаем директорию для загрузок
    upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder

    # Initialize SQLAlchemy with app
    db.init_app(app)

    with app.app_context():
        # Import routes and models after db initialization
        from models import MigrationClass, ClassificationRule, Discrepancy, AnalysisData
        from utils import process_excel_file, analyze_discrepancies, get_batch_statistics
        from classification import classify_record, export_batch_results

        logging.info("======== ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ ========")
        
        # Create database tables if they don't exist
        logging.info("Создаем таблицы базы данных, если они не существуют...")
        db.create_all()
        logging.info("Таблицы базы данных созданы.")
        
        # Check if required columns exist, if not, add them
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        
        # Проверяем структуру БД
        logging.info("Проверяем структуру базы данных...")
        table_names = inspector.get_table_names()
        logging.info(f"Найдены таблицы: {table_names}")
        
        # Проверяем и добавляем отсутствующие колонки в таблицу migration_classes
        if 'migration_classes' in table_names:
            columns = [col['name'] for col in inspector.get_columns('migration_classes')]
            logging.info(f"Колонки в таблице migration_classes: {columns}")
            
            required_columns = {
                'batch_id': 'VARCHAR(36)',
                'file_name': 'VARCHAR(255)',
                'confidence_score': 'FLOAT',
                'classified_by': 'VARCHAR(50)'
            }
            
            for col_name, col_type in required_columns.items():
                if col_name not in columns:
                    logging.info(f"Добавляем отсутствующую колонку {col_name} в таблицу migration_classes")
                    try:
                        db.session.execute(text(f'ALTER TABLE migration_classes ADD COLUMN {col_name} {col_type}'))
                        db.session.commit()
                        logging.info(f"Успешно добавлена колонка {col_name} в таблицу migration_classes")
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"Ошибка при добавлении колонки {col_name}: {str(e)}")
        else:
            logging.warning("Таблица migration_classes не найдена. Будет создана автоматически.")
        
        # Проверяем и добавляем отсутствующие колонки в таблицу discrepancies
        if 'discrepancies' in table_names:
            columns = [col['name'] for col in inspector.get_columns('discrepancies')]
            logging.info(f"Колонки в таблице discrepancies: {columns}")
            
            discrepancy_required_columns = {
                'resolved': 'BOOLEAN DEFAULT FALSE',
                'resolution_note': 'TEXT'
            }
            
            for col_name, col_type in discrepancy_required_columns.items():
                if col_name not in columns:
                    logging.info(f"Добавляем отсутствующую колонку {col_name} в таблицу discrepancies")
                    try:
                        db.session.execute(text(f'ALTER TABLE discrepancies ADD COLUMN {col_name} {col_type}'))
                        db.session.commit()
                        logging.info(f"Успешно добавлена колонка {col_name} в таблицу discrepancies")
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"Ошибка при добавлении колонки {col_name}: {str(e)}")
        else:
            logging.warning("Таблица discrepancies не найдена. Будет создана автоматически.")
        
        # Пересоздаем таблицу classification_rules полностью
        logging.info("Работа с таблицей classification_rules...")
        if 'classification_rules' in table_names:
            columns = [col['name'] for col in inspector.get_columns('classification_rules')]
            logging.info(f"Текущие колонки в таблице classification_rules: {columns}")
            
            # Проверяем наличие необходимых колонок
            missing_columns = []
            required_columns = ['confidence_threshold', 'source_batch_id']
            for col in required_columns:
                if col not in columns:
                    missing_columns.append(col)
            
            if missing_columns:
                logging.warning(f"Отсутствуют колонки: {missing_columns}. Пересоздаем таблицу classification_rules")
                try:
                    # Сохраняем существующие данные
                    try:
                        existing_rules = []
                        rules = db.session.execute(text('SELECT pattern, field, priznak_value, priority FROM classification_rules')).fetchall()
                        for rule in rules:
                            existing_rules.append({
                                'pattern': rule[0],
                                'field': rule[1],
                                'priznak_value': rule[2],
                                'priority': rule[3]
                            })
                        logging.info(f"Сохранено {len(existing_rules)} существующих правил")
                    except Exception as e:
                        logging.error(f"Ошибка при чтении существующих правил: {str(e)}")
                        existing_rules = []
                    
                    # Удаляем существующую таблицу
                    logging.info("Удаляем существующую таблицу classification_rules")
                    db.session.execute(text('DROP TABLE IF EXISTS classification_rules'))
                    db.session.commit()
                    
                    # Создаем таблицу с нужной структурой
                    logging.info("Создаем таблицу classification_rules с новой структурой")
                    db.create_all()
                    
                    # Восстанавливаем данные
                    if existing_rules:
                        logging.info(f"Восстанавливаем {len(existing_rules)} правил классификации")
                        for rule in existing_rules:
                            sql = text(f"""
                                INSERT INTO classification_rules 
                                (pattern, field, priznak_value, priority, confidence_threshold) 
                                VALUES ('{rule['pattern']}', '{rule['field']}', '{rule['priznak_value']}', {rule['priority']}, 0.8)
                            """)
                            db.session.execute(sql)
                        db.session.commit()
                        logging.info("Правила классификации успешно восстановлены")
                except Exception as e:
                    db.session.rollback()
                    logging.error(f"Ошибка при пересоздании таблицы classification_rules: {str(e)}", exc_info=True)
        else:
            logging.info("Таблица classification_rules не существует, будет создана")
            db.create_all()

        # Initialize routes
        init_routes(app)

    @app.template_filter('from_json')
    def from_json_filter(s):
        try:
            return json.loads(s)
        except (TypeError, ValueError):
            return {}

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)