import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

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