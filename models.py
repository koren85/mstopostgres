from datetime import datetime
from app import db

class MigrationClass(db.Model):
    __tablename__ = 'migration_classes'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), nullable=False)  # UUID для группировки загрузок
    file_name = db.Column(db.String(255))  # Имя загруженного файла
    a_ouid = db.Column(db.BigInteger)
    mssql_sxclass_description = db.Column(db.Text)
    mssql_sxclass_name = db.Column(db.Text)
    mssql_sxclass_map = db.Column(db.Text)
    priznak = db.Column(db.Text)
    system_class = db.Column(db.Boolean)
    is_link_table = db.Column(db.Boolean)
    parent_class = db.Column(db.Text)
    child_classes = db.Column(db.Text)
    child_count = db.Column(db.Integer)
    created_date = db.Column(db.DateTime)
    created_by = db.Column(db.Text)
    modified_date = db.Column(db.DateTime)
    modified_by = db.Column(db.Text)
    folder_paths = db.Column(db.Text)
    object_count = db.Column(db.Integer)
    last_object_created = db.Column(db.DateTime)
    last_object_modified = db.Column(db.DateTime)
    attribute_count = db.Column(db.Integer)
    category = db.Column(db.Text)
    migration_flag = db.Column(db.Text)
    rule_info = db.Column(db.Text)
    source_system = db.Column(db.Text)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    confidence_score = db.Column(db.Float)  # Уверенность классификации
    classified_by = db.Column(db.String(50))  # manual, rule, or ai

class ClassificationRule(db.Model):
    __tablename__ = 'classification_rules'

    id = db.Column(db.Integer, primary_key=True)
    pattern = db.Column(db.Text)
    field = db.Column(db.Text)
    priznak_value = db.Column(db.Text)
    priority = db.Column(db.Integer)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    confidence_threshold = db.Column(db.Float, default=0.8)  # Порог уверенности для применения правила
    source_batch_id = db.Column(db.String(36))  # ID загрузки, из которой создано правило

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