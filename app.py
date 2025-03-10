import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, url_for, redirect
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import func, or_

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
    from utils import process_excel_file, analyze_discrepancies, suggest_classification

    db.create_all()

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
        processed_records = process_excel_file(file, source_system)

        # Save to database
        for record in processed_records:
            migration_class = MigrationClass(**record)
            db.session.add(migration_class)

        db.session.commit()
        analyze_discrepancies()

        return jsonify({'success': True, 'message': f'Processed {len(processed_records)} records'})
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
    data = request.json
    suggestion = suggest_classification(
        data.get('mssql_sxclass_name'),
        data.get('mssql_sxclass_description')
    )
    return jsonify(suggestion)

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