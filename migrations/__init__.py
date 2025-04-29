"""
Пакет для миграций базы данных
"""

def run_migrations():
    """
    Запускает все миграции
    """
    try:
        from migrations.create_priznak_history import create_priznak_history_table
        create_priznak_history_table()
    except ImportError:
        # Файл миграции может еще не существовать
        pass 