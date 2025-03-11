import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, url_for, redirect, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import func, or_
import uuid
import pandas as pd  # Явный импорт pandas
# Проверяем наличие openpyxl
try:
    import openpyxl
    logging.info("openpyxl успешно импортирован")
except ImportError:
    logging.error("Библиотека openpyxl не установлена! Она необходима для чтения Excel файлов")
    os.system("pip install openpyxl")
    logging.info("Установлена библиотека openpyxl")

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)  # Логирование SQL-запросов

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize SQLAlchemy with app
db.init_app(app)

with app.app_context():
    # Import routes and models after db initialization
    from models import MigrationClass, ClassificationRule, Discrepancy, AnalysisData # Added AnalysisData import
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    logging.info("======== НАЧАЛО ОБРАБОТКИ ЗАГРУЗКИ ========")
    logging.info(f"Получен запрос на загрузку файла. Метод: {request.method}")
    logging.info(f"Заголовки запроса: {dict(request.headers)}")
    logging.info(f"Форма данных: {dict(request.form)}")
    logging.info(f"Файлы в запросе: {request.files.keys()}")

    if 'file' not in request.files:
        error_msg = "Файл не предоставлен в запросе! Ключи в request.files: " + str(list(request.files.keys()))
        logging.error(error_msg)
        return jsonify({'error': error_msg}), 400

    file = request.files['file']
    source_system = request.form.get('source_system', 'Unknown')
    
    try:
        file_size = len(file.read())
        file.seek(0)  # Сбрасываем указатель на начало файла
        logging.info(f"Получен файл: {file.filename}, размер: {file_size} байт, тип: {file.content_type or 'unknown'}")
    except Exception as e:
        logging.error(f"Ошибка при определении размера файла: {str(e)}")
        file_size = "unknown"
        
    logging.info(f"Источник: {source_system}")

    if file.filename == '':
        error_msg = "Пустое имя файла"
        logging.error(error_msg)
        return jsonify({'error': error_msg}), 400

    if not file.filename.endswith('.xlsx'):
        error_msg = f"Неподдерживаемый формат файла: {file.filename}"
        logging.error(error_msg)
        return jsonify({'error': 'Only Excel files (.xlsx) are supported'}), 400

    try:
        logging.info("[ОСНОВНОЙ ПРОЦЕСС] Шаг 1: Начинаем обработку файла...")
        batch_id, processed_records = process_excel_file(file, source_system)
        logging.info(f"[ОСНОВНОЙ ПРОЦЕСС] Шаг 1: Обработка файла завершена. Batch ID: {batch_id}, записей: {len(processed_records)}")

        # Save to database
        logging.info("[ОСНОВНОЙ ПРОЦЕСС] Шаг 2: Начинаем сохранение записей в базу данных")
        count = 0
        try:
            for record in processed_records:
                migration_class = MigrationClass(**record)
                db.session.add(migration_class)
                count += 1
                if count % 50 == 0:  # Логируем каждые 50 записей
                    logging.info(f"[ОСНОВНОЙ ПРОЦЕСС] Шаг 2: Добавлено {count} записей из {len(processed_records)}")
                    # Промежуточный коммит для больших загрузок
                    db.session.flush()
        except Exception as e:
            db.session.rollback()
            logging.error(f"[ОСНОВНОЙ ПРОЦЕСС] Шаг 2: Ошибка при добавлении записей в БД: {str(e)}", exc_info=True)
            raise ValueError(f"Ошибка при сохранении записей в базу данных: {str(e)}")

        logging.info("[ОСНОВНОЙ ПРОЦЕСС] Шаг 2: Фиксируем изменения в базе данных")
        try:
            db.session.commit()
            logging.info(f"[ОСНОВНОЙ ПРОЦЕСС] Шаг 2: Успешно сохранено {count} записей в базе данных")
        except Exception as e:
            db.session.rollback()
            logging.error(f"[ОСНОВНОЙ ПРОЦЕСС] Шаг 2: Ошибка при коммите транзакции: {str(e)}", exc_info=True)
            raise ValueError(f"Ошибка при фиксации изменений в базе данных: {str(e)}")

        logging.info("[ОСНОВНОЙ ПРОЦЕСС] Шаг 3: Анализируем несоответствия...")
        try:
            analyze_discrepancies()
            logging.info("[ОСНОВНОЙ ПРОЦЕСС] Шаг 3: Анализ несоответствий завершен")
        except Exception as e:
            logging.error(f"[ОСНОВНОЙ ПРОЦЕСС] Шаг 3: Ошибка при анализе несоответствий: {str(e)}", exc_info=True)
            # Продолжаем выполнение, даже если был сбой при анализе несоответствий

        logging.info("[ОСНОВНОЙ ПРОЦЕСС] Шаг 4: Формируем ответ клиенту")
        response = jsonify({
            'success': True, 
            'message': f'Processed {len(processed_records)} records', 
            'batch_id': batch_id
        })
        response.headers['Content-Type'] = 'application/json'
        logging.info("======== ЗАВЕРШЕНИЕ ОБРАБОТКИ ЗАГРУЗКИ ========")
        return response
    except Exception as e:
        db.session.rollback()  # Откатываем транзакцию при ошибке
        logging.error(f"[КРИТИЧЕСКАЯ ОШИБКА] Ошибка при обработке файла: {str(e)}", exc_info=True)
        
        # Подробная информация об ошибке для отладки
        error_details = {
            'error': str(e),
            'error_type': str(type(e).__name__),
            'trace': str(e.__traceback__)
        }
        
        from traceback import format_exc
        logging.error(f"Полный стек вызовов:\n{format_exc()}")
        
        response = jsonify(error_details)
        response.headers['Content-Type'] = 'application/json'
        logging.info("======== ЗАВЕРШЕНИЕ ОБРАБОТКИ ЗАГРУЗКИ С ОШИБКОЙ ========")
        return response, 500

@app.route('/analyze')
def analyze():
    try:
        source_systems = db.session.query(MigrationClass.source_system).distinct().all()
        sources = [s[0] for s in source_systems]

        discrepancies = Discrepancy.query.all()

        stats = {
            'total_records': MigrationClass.query.count(),
            'source_systems': len(sources),
            'discrepancies': len(discrepancies)
        }

        return render_template('analyze.html', stats=stats, sources=sources, discrepancies=discrepancies)
    except Exception as e:
        logging.error(f"Error on analyze page: {str(e)}")
        return render_template('analyze.html', stats={'total_records': 0, 'source_systems': 0, 'discrepancies': 0}, 
                              sources=[], discrepancies=[], error=str(e))

@app.route('/api/suggest_classification', methods=['POST'])
def get_classification_suggestion():
    """Получить предложение по классификации на основе исторических данных"""
    data = request.json
    result = classify_record(
        class_name=data.get('mssql_sxclass_name'),
        description=data.get('mssql_sxclass_description')
    )
    return jsonify({
        'priznak': result['priznak'],
        'confidence': result['confidence'],
        'method': result['method']
    })

@app.route('/manage')
def manage():
    page = request.args.get('page', 1, type=int)
    per_page = 20  # количество записей на странице

    # Базовый запрос
    query = MigrationClass.query

    # Применяем фильтры из параметров запроса
    source_system = request.args.get('source_system')
    priznak = request.args.get('priznak')
    class_name = request.args.get('class_name')
    upload_date = request.args.get('upload_date')

    if source_system:
        query = query.filter(MigrationClass.source_system == source_system)
    if priznak:
        query = query.filter(MigrationClass.priznak.ilike(f'%{priznak}%'))
    if class_name:
        query = query.filter(MigrationClass.mssql_sxclass_name.ilike(f'%{class_name}%'))
    if upload_date:
        date_obj = datetime.strptime(upload_date, '%Y-%m-%d')
        query = query.filter(func.date(MigrationClass.upload_date) == date_obj.date())

    # Получаем общее количество записей для пагинации
    total_items = query.count()
    total_pages = (total_items + per_page - 1) // per_page

    # Применяем пагинацию
    items = query.order_by(MigrationClass.upload_date.desc())\
                .offset((page - 1) * per_page)\
                .limit(per_page)\
                .all()

    # Получаем список уникальных источников для фильтра
    sources = db.session.query(MigrationClass.source_system)\
                       .distinct()\
                       .order_by(MigrationClass.source_system)\
                       .all()
    sources = [s[0] for s in sources]

    return render_template('manage.html',
                         items=items,
                         sources=sources,
                         page=page,
                         total_pages=total_pages)

@app.route('/api/delete/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    try:
        item = MigrationClass.query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting item {item_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/batches')
def batches():
    """Страница управления загрузками"""
    try:
        # Получаем уникальные batch_id
        batch_ids = db.session.query(
            MigrationClass.batch_id,
            MigrationClass.file_name,
            func.min(MigrationClass.upload_date).label('upload_date')
        ).group_by(
            MigrationClass.batch_id,
            MigrationClass.file_name
        ).order_by(
            func.min(MigrationClass.upload_date).desc()
        ).all()

        # Собираем информацию по каждой загрузке
        batches_info = []
        for record in batch_ids:
            batch_id = record[0]
            file_name = record[1] if record[1] else "Неизвестный файл"
            upload_date = record[2]
            
            stats = get_batch_statistics(batch_id)
            batches_info.append({
                'batch_id': batch_id,
                'file_name': file_name,
                'upload_date': upload_date,
                'stats': stats
            })

        return render_template('batches.html', batches=batches_info)
    except Exception as e:
        logging.error(f"Error on batches page: {str(e)}")
        return render_template('batches.html', batches=[], error=str(e))


@app.route('/run_classification/<batch_id>', methods=['POST'])
def run_classification(batch_id):
    try:
        # Получаем все записи из указанного batch_id
        records = MigrationClass.query.filter_by(batch_id=batch_id).all()
        
        for record in records:
            # Если priznak уже есть, пропускаем классификацию
            if record.priznak:
                continue
                
            # Классифицируем только записи с пустым priznak
            result = classify_record(
                record.mssql_sxclass_name, 
                record.mssql_sxclass_description,
                batch_id,
                existing_priznak=record.priznak
            )
            
            # Обновляем запись
            record.priznak = result['priznak']
            record.confidence_score = result['confidence']
            record.classified_by = result['method']
            
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/batch/<batch_id>', methods=['DELETE'])
def delete_batch(batch_id):
    """Удаление всех данных конкретной загрузки"""
    try:
        # Удаляем все записи с указанным batch_id
        MigrationClass.query.filter_by(batch_id=batch_id).delete()
        # Удаляем правила, созданные на основе этой загрузки
        ClassificationRule.query.filter_by(source_batch_id=batch_id).delete()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting batch {batch_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/batch/<batch_id>/export')
def export_batch(batch_id):
    """Экспорт данных загрузки в Excel"""
    try:
        output_file = export_batch_results(batch_id)
        return send_file(
            output_file,
            as_attachment=True,
            download_name=f"batch_{batch_id[:8]}_export.xlsx"
        )
    except Exception as e:
        logging.error(f"Error exporting batch {batch_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/analysis')
def analysis():
    """Страница анализа новых данных"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    batch_id = request.args.get('batch_id')

    # Базовый запрос
    base_query = AnalysisData.query
    
    # Фильтр по batch_id, если указан
    if batch_id:
        base_query = base_query.filter(AnalysisData.batch_id == batch_id)
        
    # Запрос с сортировкой
    query = base_query.order_by(AnalysisData.upload_date.desc())
    
    # Пагинация с total
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    total_records = pagination.total

    # Получаем информацию о всех батчах для фильтра
    batch_options = db.session.query(
        AnalysisData.batch_id,
        AnalysisData.file_name,
        func.min(AnalysisData.upload_date).label('upload_date')
    ).group_by(
        AnalysisData.batch_id,
        AnalysisData.file_name
    ).order_by(
        func.min(AnalysisData.upload_date).desc()
    ).all()
    
    # Преобразуем результаты в список словарей для шаблона
    batch_list = [
        {
            'id': b.batch_id,
            'file_name': b.file_name
        } for b in batch_options
    ]
    
    # Получаем информацию о статусе батчей
    batches = []
    for b in batch_options:
        # Количество записей в батче
        total_records = AnalysisData.query.filter_by(batch_id=b.batch_id).count()
        
        # Количество проанализированных записей
        analyzed_records = AnalysisData.query.filter_by(
            batch_id=b.batch_id,
            analysis_state='analyzed'
        ).count()
        
        # Количество записей с конфликтами
        conflict_records = AnalysisData.query.filter_by(
            batch_id=b.batch_id,
            analysis_state='conflict'
        ).count()
        
        # Рассчитываем прогресс
        if total_records > 0:
            progress = int((analyzed_records + conflict_records) / total_records * 100)
        else:
            progress = 0
            
        # Определяем цвет прогресса
        if progress == 100:
            progress_color = "success"
        elif progress > 0:
            progress_color = "info"
        else:
            progress_color = "warning"
            
        batches.append({
            'batch_id': b.batch_id,
            'file_name': b.file_name,
            'upload_date': b.upload_date,
            'records_count': total_records,
            'source_system': AnalysisData.query.filter_by(batch_id=b.batch_id).first().source_system,
            'progress': progress,
            'progress_color': progress_color
        })

    return render_template('analysis.html',
                           items=pagination.items,
                           page=page,
                           pages=pagination.pages,
                           pagination=pagination,
                           batch_id=batch_id,
                           batch_options=batch_list,
                           batches=batches)

@app.route('/upload_analysis', methods=['POST'])
def upload_analysis():
    """Загрузка новых данных для анализа"""
    logging.info("Получен запрос на загрузку данных для анализа")

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Файл не предоставлен'}), 400

    file = request.files['file']
    source_system = request.form.get('source_system', 'Unknown')

    if file.filename == '':
        return jsonify({'success': False, 'error': 'Пустое имя файла'}), 400

    if not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'error': 'Поддерживаются только файлы Excel (.xlsx)'}), 400

    try:
        # Чтение данных напрямую из Excel (заголовки на 2-й строке, данные с 3-й)
        logging.info(f"Начинаем обработку файла для анализа: {file.filename}")
        df = pd.read_excel(file, header=1, skiprows=2)  # header=1 означает, что заголовки на 2-й строке (индекс 1), skiprows=2 пропускает первые 2 строки
        
        # Выводим информацию о колонках для отладки
        logging.info(f"Колонки в Excel файле: {df.columns.tolist()}")
        
        # Создаем batch_id для группировки записей
        batch_id = str(uuid.uuid4())
        
        # Предполагаемое отображение колонок Excel на поля модели
        column_mapping = {
            'a_ouid': ['a_ouid', 'a-ouid', 'ouid', 'a ouid'],
            'mssql_sxclass_description': ['mssql_sxclass_description', 'mssql sxclass description', 'description', 'mssql sxclass_description'],
            'mssql_sxclass_name': ['mssql_sxclass_name', 'mssql sxclass name', 'name', 'class_name', 'mssql sxclass_name'],
            'mssql_sxclass_map': ['mssql_sxclass_map', 'mssql sxclass map', 'map', 'mssql sxclass_map'],
            'system_class': ['system_class', 'systemclass', 'system_class'],
            'is_link_table': ['is_link_table', 'islinktable', 'link_table', 'is link_table'],
            'parent_class': ['parent_class', 'parentclass', 'parent class'],
            'child_classes': ['child_classes', 'childclasses', 'child classes'],
            'child_count': ['child_count', 'childcount', 'child count'],
            'created_date': ['created_date', 'createddate', 'created date'],
            'created_by': ['created_by', 'createdby', 'created by'],
            'modified_date': ['modified_date', 'modifieddate', 'modified date'],
            'modified_by': ['modified_by', 'modifiedby', 'modified by'],
            'folder_paths': ['folder_paths', 'folderpaths', 'folder paths'],
            'object_count': ['object_count', 'objectcount', 'object count'],
            'last_object_created': ['last_object_created', 'lastobjectcreated', 'last object created'],
            'last_object_modified': ['last_object_modified', 'lastobjectmodified', 'last object modified'],
            'attribute_count': ['attribute_count', 'attributecount', 'attribute count'],
            'category': ['category'],
            'migration_flag': ['migration_flag', 'migrationflag', 'migration flag'],
            'rule_info': ['rule_info', 'ruleinfo', 'rule info'],
            'priznak': ['priznak']
        }
        
        # Находим фактические названия колонок в Excel-файле и сопоставляем их с полями модели
        excel_column_map = {}
        for model_field, possible_excel_columns in column_mapping.items():
            found = False
            # Сначала ищем точное совпадение
            for excel_column in df.columns:
                # Проверяем тип данных перед использованием strip()
                if isinstance(excel_column, str):
                    if excel_column.strip().lower() in possible_excel_columns:
                        excel_column_map[model_field] = excel_column
                        found = True
                        break
                else:
                    # Для числовых индексов преобразуем в строку
                    if str(excel_column).lower() in possible_excel_columns:
                        excel_column_map[model_field] = excel_column
                        found = True
                        break
            
            # Если не нашли точное совпадение, ищем по нормализованному имени
            if not found:
                for excel_column in df.columns:
                    # Обрабатываем разные типы данных
                    if isinstance(excel_column, str):
                        excel_column_normalized = excel_column.strip().lower().replace(' ', '_')
                    else:
                        # Для числовых индексов преобразуем в строку
                        excel_column_normalized = str(excel_column).lower()
                        
                    if excel_column_normalized in possible_excel_columns:
                        excel_column_map[model_field] = excel_column
                        found = True
                        break
                        
        logging.info(f"Сопоставление колонок Excel с полями модели: {excel_column_map}")
        
        # Проверяем наличие ключевых колонок
        if 'mssql_sxclass_name' not in excel_column_map and 'mssql_sxclass_description' not in excel_column_map:
            logging.warning("Не найдены ключевые колонки в Excel файле!")
            logging.warning(f"Доступные колонки: {df.columns.tolist()}")
            
            # Пробуем найти ближайшие совпадения для ключевых колонок
            for col in df.columns:
                col_lower = col.lower()
                if 'name' in col_lower or 'класс' in col_lower or 'class' in col_lower:
                    excel_column_map['mssql_sxclass_name'] = col
                    logging.info(f"Используем '{col}' как mssql_sxclass_name")
                elif 'desc' in col_lower or 'опис' in col_lower:
                    excel_column_map['mssql_sxclass_description'] = col
                    logging.info(f"Используем '{col}' как mssql_sxclass_description")
        
        # Обрабатываем каждую строку Excel
        processed_records = []
        for index, row in df.iterrows():
            # Создаем запись анализа
            analysis_record = AnalysisData()
            
            # Устанавливаем обязательные поля
            analysis_record.batch_id = batch_id
            analysis_record.file_name = file.filename
            analysis_record.source_system = source_system
            analysis_record.upload_date = datetime.utcnow()
            analysis_record.analysis_state = 'pending'
            analysis_record.matched_historical_data = []
            
            # Заполняем поля из Excel на основе сопоставления
            for model_field, excel_column in excel_column_map.items():
                try:
                    value = row[excel_column]
                    # Проверяем, является ли значение NaN 
                    if pd.isna(value):
                        value = None
                    elif model_field in ['a_ouid', 'child_count', 'object_count', 'attribute_count']:
                        # Числовые поля
                        if value is not None:
                            try:
                                value = int(value)
                            except (ValueError, TypeError):
                                value = None
                    elif model_field in ['system_class', 'is_link_table']:
                        # Булевы поля
                        if isinstance(value, str):
                            value = value.lower() in ['true', 'yes', 'да', '1', 'истина']
                    elif model_field in ['created_date', 'modified_date', 'last_object_created', 'last_object_modified']:
                        # Даты
                        if value is not None and not isinstance(value, datetime):
                            try:
                                value = pd.to_datetime(value)
                            except:
                                value = None
                                
                    # Устанавливаем значение атрибута
                    setattr(analysis_record, model_field, value)
                except Exception as field_error:
                    logging.warning(f"Ошибка при обработке поля {model_field}: {str(field_error)}")
            
            # Для отладки: выводим значения ключевых полей
            logging.info(f"Строка {index}: name={getattr(analysis_record, 'mssql_sxclass_name', None)}, "
                        f"description={getattr(analysis_record, 'mssql_sxclass_description', None)}")
            
            db.session.add(analysis_record)
            processed_records.append(analysis_record)
        
        logging.info(f"Обработано {len(processed_records)} записей из файла")
        db.session.commit()
        logging.info(f"Все записи успешно сохранены в базу данных")
        
        return jsonify({
            'success': True,
            'message': f'Обработано {len(processed_records)} записей',
            'batch_id': batch_id
        })

    except Exception as e:
        db.session.rollback()
        logging.error(f"Ошибка при загрузке данных для анализа: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/analyze_item/<int:item_id>', methods=['POST'])
def analyze_item(item_id):
    """Анализ отдельной записи"""
    try:
        # Получаем запись для анализа
        item = AnalysisData.query.get_or_404(item_id)

        # Ищем совпадения в исторических данных
        matches = MigrationClass.query.filter(
            MigrationClass.mssql_sxclass_name == item.mssql_sxclass_name,
            MigrationClass.mssql_sxclass_description == item.mssql_sxclass_description
        ).all()

        if not matches:
            item.analysis_state = 'analyzed'
            item.matched_historical_data = []
            item.analysis_date = datetime.utcnow()
            db.session.commit()
            return jsonify({'success': True, 'message': 'Совпадений не найдено'})

        # Собираем информацию о совпадениях
        historical_data = []
        priznaks = set()

        for match in matches:
            if match.priznak:  # Учитываем только записи с заполненным priznak
                historical_data.append({
                    'priznak': match.priznak,
                    'source_system': match.source_system,
                    'upload_date': match.upload_date.isoformat() if match.upload_date else None
                })
                priznaks.add(match.priznak)

        # Обновляем запись
        item.matched_historical_data = historical_data
        item.analysis_date = datetime.utcnow()

        # Если найден только один вариант priznak, используем его
        if len(priznaks) == 1:
            item.priznak = next(iter(priznaks))
            item.analysis_state = 'analyzed'
        else:
            item.analysis_state = 'conflict'

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Анализ завершен',
            'matches_count': len(matches),
            'unique_priznaks': len(priznaks)
        })

    except Exception as e:
        db.session.rollback()
        logging.error(f"Ошибка при анализе записи {item_id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analyze_batch/<batch_id>', methods=['POST'])
def analyze_batch(batch_id):
    """Анализ всех записей в батче"""
    try:
        # Получаем все записи из батча со статусом pending
        items = AnalysisData.query.filter_by(
            batch_id=batch_id, 
            analysis_state='pending'
        ).all()
        
        if not items:
            return jsonify({'success': False, 'error': 'Нет записей для анализа или батч не найден'}), 404
        
        total = len(items)
        processed = 0
        conflicts = 0
        
        # Анализируем каждую запись
        for item in items:
            # Ищем совпадения в исторических данных
            matches = MigrationClass.query.filter(
                MigrationClass.mssql_sxclass_name == item.mssql_sxclass_name,
                MigrationClass.mssql_sxclass_description == item.mssql_sxclass_description
            ).all()
            
            # Собираем информацию о совпадениях
            historical_data = []
            priznaks = set()
            
            for match in matches:
                if match.priznak:  # Учитываем только записи с заполненным priznak
                    historical_data.append({
                        'priznak': match.priznak,
                        'source_system': match.source_system,
                        'upload_date': match.upload_date.isoformat() if match.upload_date else None
                    })
                    priznaks.add(match.priznak)
            
            # Обновляем запись
            item.matched_historical_data = historical_data
            item.analysis_date = datetime.utcnow()
            
            # Если найден только один вариант priznak, используем его
            if len(priznaks) == 1:
                item.priznak = next(iter(priznaks))
                item.analysis_state = 'analyzed'
            elif len(priznaks) > 1:
                item.analysis_state = 'conflict'
                conflicts += 1
            else:
                # Если совпадений не найдено, отмечаем как проанализированную без результата
                item.analysis_state = 'analyzed'
                
            processed += 1
            
            # Коммитим каждые 100 записей, чтобы не держать транзакцию открытой слишком долго
            if processed % 100 == 0:
                db.session.commit()
                logging.info(f"Обработано {processed} из {total} записей в батче {batch_id}")
        
        # Финальный коммит
        db.session.commit()
        
        logging.info(f"Завершен анализ батча {batch_id}: обработано {processed} записей, найдено {conflicts} конфликтов")
        return jsonify({
            'success': True, 
            'message': f'Проанализировано {processed} записей', 
            'processed': processed,
            'conflicts': conflicts
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Ошибка при анализе батча {batch_id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analysis_batch/<batch_id>', methods=['DELETE'])
def delete_analysis_batch(batch_id):
    """Удаление загруженного батча данных для анализа"""
    try:
        # Проверяем, существует ли батч
        count = AnalysisData.query.filter_by(batch_id=batch_id).count()
        if count == 0:
            return jsonify({'success': False, 'error': 'Батч не найден'}), 404
            
        # Удаляем все записи с указанным batch_id
        AnalysisData.query.filter_by(batch_id=batch_id).delete()
        db.session.commit()
        
        logging.info(f"Успешно удален батч анализа {batch_id}, удалено {count} записей")
        return jsonify({'success': True, 'message': f'Удалено {count} записей'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Ошибка при удалении батча анализа {batch_id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)