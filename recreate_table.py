from app import create_app
from database import db
from models import MigrationClass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recreate_migration_table():
    app = create_app()
    with app.app_context():
        try:
            # Удаляем существующую таблицу
            logger.info("Удаляем существующую таблицу migration_classes...")
            MigrationClass.__table__.drop(db.engine)
            
            # Создаем новую таблицу
            logger.info("Создаем новую таблицу migration_classes...")
            db.create_all()
            
            logger.info("Таблица migration_classes успешно пересоздана")
            
        except Exception as e:
            logger.error(f"Ошибка при пересоздании таблицы: {str(e)}", exc_info=True)
            raise

if __name__ == '__main__':
    recreate_migration_table() 