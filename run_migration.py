from app import create_app
from database import db
from migrations.create_priznak_history import create_priznak_history_table

if __name__ == '__main__':
    app = create_app()  # Создаем экземпляр приложения Flask
    with app.app_context():
        # Выполняем миграцию для создания таблицы истории корректировок
        create_priznak_history_table()
        print("Миграция успешно выполнена") 