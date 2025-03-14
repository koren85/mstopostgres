from datetime import datetime
from database import db

class MigrationClass(db.Model):
    __tablename__ = 'migration_classes'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), nullable=False)  # UUID для группировки загрузок
    file_name = db.Column(db.String(255))  # Имя загруженного файла
    a_ouid = db.Column(db.String(255))
    mssql_sxclass_description = db.Column(db.Text)
    mssql_sxclass_name = db.Column(db.String(255))
    mssql_sxclass_map = db.Column(db.Text)
    priznak = db.Column(db.String(50))
    system_class = db.Column(db.String(255))
    is_link_table = db.Column(db.String(255))
    parent_class = db.Column(db.Text)
    child_classes = db.Column(db.Text)
    child_count = db.Column(db.String(255))
    created_date = db.Column(db.String(255))
    created_by = db.Column(db.Text)
    modified_date = db.Column(db.String(255))
    modified_by = db.Column(db.Text)
    folder_paths = db.Column(db.Text)
    object_count = db.Column(db.String(255))
    last_object_created = db.Column(db.String(255))
    last_object_modified = db.Column(db.String(255))
    attribute_count = db.Column(db.String(255))
    category = db.Column(db.Text)
    migration_flag = db.Column(db.Text)
    rule_info = db.Column(db.Text)
    source_system = db.Column(db.String(100), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    confidence_score = db.Column(db.Float)  # Уверенность классификации
    classified_by = db.Column(db.String(50))  # manual, rule, or ai

class ClassificationRule(db.Model):
    __tablename__ = 'classification_rules'

    id = db.Column(db.Integer, primary_key=True)
    pattern = db.Column(db.String(255), nullable=False)
    field = db.Column(db.String(50), nullable=False)  # name, description
    priznak_value = db.Column(db.String(50), nullable=False)
    priority = db.Column(db.Integer, default=0)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    confidence_threshold = db.Column(db.Float, default=0.8)
    source_batch_id = db.Column(db.String(36), nullable=True)

class Discrepancy(db.Model):
    __tablename__ = 'discrepancies'

    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.Text)
    description = db.Column(db.Text)
    different_priznaks = db.Column(db.JSON)
    source_systems = db.Column(db.JSON)
    detected_date = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)
    resolution_note = db.Column(db.Text)
    analysis_result_id = db.Column(db.Integer, db.ForeignKey('analysis_results.id'))

class AnalysisData(db.Model):
    """Таблица для данных требующих анализа"""
    __tablename__ = 'analysis_data'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    a_ouid = db.Column(db.String(255))
    mssql_sxclass_description = db.Column(db.Text)
    mssql_sxclass_name = db.Column(db.String(255))
    mssql_sxclass_map = db.Column(db.Text)
    priznak = db.Column(db.String(50))
    system_class = db.Column(db.String(255))
    is_link_table = db.Column(db.String(255))
    parent_class = db.Column(db.Text)
    child_classes = db.Column(db.Text)
    child_count = db.Column(db.String(255))
    created_date = db.Column(db.String(255))
    created_by = db.Column(db.Text)
    modified_date = db.Column(db.String(255))
    modified_by = db.Column(db.Text)
    folder_paths = db.Column(db.Text)
    object_count = db.Column(db.String(255))
    last_object_created = db.Column(db.String(255))
    last_object_modified = db.Column(db.String(255))
    attribute_count = db.Column(db.String(255))
    category = db.Column(db.Text)
    migration_flag = db.Column(db.Text)
    rule_info = db.Column(db.Text)
    source_system = db.Column(db.String(100), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    confidence_score = db.Column(db.Float)
    classified_by = db.Column(db.String(50))
    analysis_state = db.Column(db.String(20), default='pending')
    matched_historical_data = db.Column(db.JSON)
    analysis_date = db.Column(db.DateTime)

class FieldMapping(db.Model):
    __tablename__ = 'field_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    db_field = db.Column(db.String(100), nullable=False, unique=True)
    excel_header = db.Column(db.String(255), nullable=False)
    is_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<FieldMapping {self.db_field} -> {self.excel_header}>'

class AnalysisResult(db.Model):
    __tablename__ = 'analysis_results'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), nullable=False)
    mssql_sxclass_name = db.Column(db.String(255), nullable=False)
    priznak = db.Column(db.String(50))
    confidence_score = db.Column(db.Float)
    analysis_date = db.Column(db.DateTime, default=datetime.utcnow)
    discrepancies = db.Column(db.JSON)
    status = db.Column(db.String(20), default='pending')
    analyzed_by = db.Column(db.String(50))