import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, url_for, redirect, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import func, or_
import uuid

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

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
    from models import MigrationClass, ClassificationRule, Discrepancy
    from utils import process_excel_file, analyze_discrepancies, get_batch_statistics
    from classification import classify_record, export_batch_results

    # Create database tables if they don't exist
    db.create_all()
    
    # Check if required columns exist, if not, add them
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    if 'migration_classes' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('migration_classes')]
        
        # Проверяем и добавляем отсутствующие колонки
        required_columns = {
            'batch_id': 'VARCHAR(36)',
            'file_name': 'VARCHAR(255)',
            'confidence_score': 'FLOAT',
            'classified_by': 'VARCHAR(50)'
        }
        
        for col_name, col_type in required_columns.items():
            if col_name not in columns:
                db.session.execute(text(f'ALTER TABLE migration_classes ADD COLUMN {col_name} {col_type}'))
                db.session.commit()
                logging.info(f"Added {col_name} column to migration_classes table")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    source_system = request.form.get('source_system', 'Unknown')

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.endswith('.xlsx'):
        return jsonify({'error': 'Only Excel files (.xlsx) are supported'}), 400

    try:
        # batch_id и records теперь возвращаются из process_excel_file
        batch_id, processed_records = process_excel_file(file, source_system)

        # Save to database
        for record in processed_records:
            migration_class = MigrationClass(**record)
            db.session.add(migration_class)

        db.session.commit()
        analyze_discrepancies()

        return jsonify({'success': True, 'message': f'Processed {len(processed_records)} records', 'batch_id': batch_id})
    except Exception as e:
        logging.error(f"Error processing file: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/analyze')
def analyze():
    source_systems = db.session.query(MigrationClass.source_system).distinct().all()
    sources = [s[0] for s in source_systems]

    discrepancies = Discrepancy.query.all()

    stats = {
        'total_records': MigrationClass.query.count(),
        'source_systems': len(sources),
        'discrepancies': len(discrepancies)
    }

    return render_template('analyze.html', stats=stats, sources=sources, discrepancies=discrepancies)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)