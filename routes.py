from flask import render_template, request, jsonify, url_for, redirect, send_file, flash, session
from datetime import datetime
import uuid
import logging
import pandas as pd
import json
from database import db
from models import MigrationClass, Discrepancy, AnalysisData, FieldMapping, AnalysisResult, TransferRule, PriznakCorrectionHistory
from utils import process_excel_file, analyze_discrepancies, get_batch_statistics
from classification import classify_record, export_batch_results, apply_transfer_rules
from sqlalchemy import func, case
from werkzeug.utils import secure_filename
import os
from io import BytesIO
import xlsxwriter
import io

def init_routes(app):
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/upload', methods=['POST'])
    def upload_file():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'Файл не найден'}), 400
            
            file = request.files['file']
            source_system = request.form.get('source_system', 'unknown')
            
            if file.filename == '':
                return jsonify({'success': False, 'error': 'Файл не выбран'}), 400
            
            if not file.filename.endswith('.xlsx'):
                return jsonify({'success': False, 'error': 'Поддерживаются только Excel файлы (.xlsx)'}), 400
            
            # Обрабатываем файл
            batch_id, records = process_excel_file(file, source_system)
            
            # Сохраняем записи в базу данных
            for record in records:
                migration_class = MigrationClass(**record)
                db.session.add(migration_class)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Файл успешно загружен',
                'batch_id': batch_id,
                'records_count': len(records)
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при загрузке файла: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/analyze')
    def analyze():
        try:
            # Получаем общую статистику
            total_records = MigrationClass.query.count()
            source_systems = db.session.query(func.count(func.distinct(MigrationClass.source_system))).scalar()
            discrepancies = Discrepancy.query.count()
            
            # Получаем данные о расхождениях
            discrepancy_data = []
            discrepancy_classes = db.session.query(Discrepancy.class_name).distinct().all()
            for disc_class in discrepancy_classes:
                class_name = disc_class[0]
                
                # Получаем описание класса
                class_desc = db.session.query(MigrationClass.mssql_sxclass_description).filter_by(
                    mssql_sxclass_name=class_name
                ).first()
                description = class_desc[0] if class_desc else ""
                
                # Получаем различные признаки для этого класса
                different_priznaks = db.session.query(func.distinct(MigrationClass.priznak)).filter_by(
                    mssql_sxclass_name=class_name
                ).all()
                different_priznaks = [p[0] for p in different_priznaks if p[0]]
                
                # Получаем источники для этого класса
                class_sources = db.session.query(func.distinct(MigrationClass.source_system)).filter_by(
                    mssql_sxclass_name=class_name
                ).all()
                class_sources = [s[0] for s in class_sources if s[0]]
                
                discrepancy_data.append({
                    'class_name': class_name,
                    'description': description,
                    'different_priznaks': different_priznaks,
                    'source_systems': class_sources
                })
            
            # Получаем статистику по историческим источникам данных
            historical_sources = db.session.query(
                MigrationClass.source_system,
                func.count(MigrationClass.id).label('records_count'),
                func.min(MigrationClass.upload_date).label('upload_date')
            ).group_by(
                MigrationClass.source_system
            ).having(
                func.count(MigrationClass.id) > 0
            ).all()
            
            # Преобразуем результаты запроса в список словарей
            historical_sources_data = [{
                'source_system': src.source_system,
                'records_count': src.records_count,
                'upload_date': src.upload_date.isoformat() if src.upload_date else None
            } for src in historical_sources]
            
            # Получаем статистику по новым данным для анализа
            analysis_sources = db.session.query(
                AnalysisData.source_system,
                func.count(AnalysisData.id).label('records_count'),
                func.min(AnalysisData.upload_date).label('upload_date')
            ).group_by(
                AnalysisData.source_system
            ).having(
                func.count(AnalysisData.id) > 0
            ).all()
            
            # Преобразуем результаты запроса в список словарей
            analysis_sources_data = [{
                'source_system': src.source_system,
                'records_count': src.records_count,
                'upload_date': src.upload_date.isoformat() if src.upload_date else None
            } for src in analysis_sources]
            
            # Получаем распределение признаков в исторических данных
            priznak_stats = db.session.query(
                MigrationClass.priznak,
                func.count(MigrationClass.id).label('count')
            ).filter(
                MigrationClass.priznak.isnot(None)
            ).group_by(
                MigrationClass.priznak
            ).all()
            
            # Преобразуем в словарь для передачи в шаблон
            priznak_stats_dict = {p.priznak: p.count for p in priznak_stats if p.priznak}
            
            # Если нет признаков, добавляем пустые значения для графика
            if not priznak_stats_dict:
                priznak_stats_dict = {"Нет данных": 0}
            
            stats = {
                'total_records': total_records,
                'source_systems': source_systems,
                'discrepancies': discrepancies
            }
            
            return render_template('analyze.html', 
                                stats=stats,
                                historical_sources=historical_sources_data,
                                analysis_sources=analysis_sources_data,
                                priznak_stats=priznak_stats_dict,
                                discrepancies=discrepancy_data)
            
        except Exception as e:
            logging.error(f"Ошибка при формировании страницы анализа: {str(e)}", exc_info=True)
            return f"Ошибка: {str(e)}", 500

    @app.route('/api/suggest_classification', methods=['POST'])
    def get_classification_suggestion():
        try:
            data = request.get_json()
            class_name = data.get('class_name')
            description = data.get('description')
            
            if not class_name or not description:
                return jsonify({'success': False, 'error': 'Необходимо указать имя класса и описание'}), 400
            
            # Ищем похожие записи в исторических данных
            similar_records = MigrationClass.query.filter(
                MigrationClass.mssql_sxclass_name == class_name,
                MigrationClass.priznak.isnot(None)
            ).all()
            
            if not similar_records:
                return jsonify({'success': False, 'error': 'Похожих записей не найдено'}), 404
            
            # Возвращаем наиболее часто встречающееся значение priznak
            priznak_counts = {}
            for record in similar_records:
                priznak_counts[record.priznak] = priznak_counts.get(record.priznak, 0) + 1
            
            suggested_priznak = max(priznak_counts.items(), key=lambda x: x[1])[0]
            
            return jsonify({
                'success': True,
                'suggested_priznak': suggested_priznak,
                'confidence': len(similar_records) / len(priznak_counts)
            })
            
        except Exception as e:
            logging.error(f"Ошибка при получении предложения по классификации: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/manage')
    def manage():
        try:
            # Получаем все правила классификации
            rules = TransferRule.query.filter(TransferRule.priznak_value.isnot(None)).order_by(TransferRule.priority.desc()).all()
            
            # Получаем все несоответствия
            discrepancies = Discrepancy.query.all()
            
            # Получаем список источников для фильтра
            sources = db.session.query(MigrationClass.source_system).distinct().all()
            sources = [source[0] for source in sources]
            
            # Получаем список уникальных значений priznak для фильтра
            priznaks = db.session.query(MigrationClass.priznak).distinct().filter(MigrationClass.priznak.isnot(None)).all()
            priznaks = [priznak[0] for priznak in priznaks]
            
            # Получаем параметры фильтрации
            source_system = request.args.get('source_system')
            priznak = request.args.get('priznak')
            class_name = request.args.get('class_name')
            upload_date = request.args.get('upload_date')
            
            # Формируем базовый запрос
            query = MigrationClass.query
            
            # Применяем фильтры
            if source_system:
                query = query.filter(MigrationClass.source_system == source_system)
            if priznak:
                query = query.filter(MigrationClass.priznak == priznak)
            if class_name:
                query = query.filter(MigrationClass.mssql_sxclass_name.ilike(f'%{class_name}%'))
            if upload_date:
                query = query.filter(func.date(MigrationClass.upload_date) == upload_date)
            
            # Пагинация
            page = request.args.get('page', 1, type=int)
            per_page = 20
            pagination = query.order_by(MigrationClass.upload_date.desc()).paginate(
                page=page, per_page=per_page, error_out=False)
            
            return render_template('manage.html', 
                                 rules=rules, 
                                 discrepancies=discrepancies,
                                 sources=sources,
                                 priznaks=priznaks,
                                 items=pagination.items,
                                 page=page,
                                 total_pages=pagination.pages,
                                 current_priznak=priznak)
            
        except Exception as e:
            logging.error(f"Ошибка при отображении страницы управления: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/delete/<int:item_id>', methods=['DELETE'])
    def delete_item(item_id):
        try:
            item = MigrationClass.query.get_or_404(item_id)
            db.session.delete(item)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Запись успешно удалена'})
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при удалении записи: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/batches')
    def batches():
        try:
            # Получаем все batch_id с информацией о файлах
            batches = db.session.query(
                MigrationClass.batch_id,
                MigrationClass.file_name,
                func.count(MigrationClass.id).label('total_records'),
                func.count(func.distinct(MigrationClass.source_system)).label('source_systems'),
                func.max(MigrationClass.upload_date).label('upload_date'),
                func.avg(MigrationClass.confidence_score).label('avg_confidence'),
                func.sum(case((MigrationClass.classified_by == 'manual', 1), else_=0)).label('manual_classifications'),
                func.sum(case((MigrationClass.classified_by == 'historical', 1), else_=0)).label('historical_classifications'),
                func.sum(case((MigrationClass.classified_by == 'rule', 1), else_=0)).label('rule_based_classifications')
            ).group_by(
                MigrationClass.batch_id,
                MigrationClass.file_name
            ).order_by(
                func.max(MigrationClass.upload_date).desc()
            ).all()
            
            # Форматируем данные для шаблона
            formatted_batches = []
            for batch in batches:
                formatted_batches.append({
                    'batch_id': batch.batch_id,
                    'file_name': batch.file_name or 'Неизвестный файл',
                    'upload_date': batch.upload_date,
                    'stats': {
                        'total_records': batch.total_records,
                        'source_systems': batch.source_systems,
                        'avg_confidence': batch.avg_confidence or 0,
                        'classifications': {
                            'manual': batch.manual_classifications or 0,
                            'historical': batch.historical_classifications or 0,
                            'rule_based': batch.rule_based_classifications or 0
                        }
                    }
                })
            
            return render_template('batches.html', batches=formatted_batches)
            
        except Exception as e:
            logging.error(f"Ошибка при отображении списка загрузок: {str(e)}", exc_info=True)
            return render_template('error.html', error=str(e)), 500

    @app.route('/run_classification/<batch_id>', methods=['POST'])
    def run_classification(batch_id):
        try:
            # Получаем все записи для данного batch_id
            records = MigrationClass.query.filter_by(batch_id=batch_id).all()
            
            # Применяем классификацию к каждой записи
            for record in records:
                if not record.priznak:  # Классифицируем только записи без priznak
                    result = classify_record(record)
                    if result:
                        record.priznak = result['priznak']
                        record.confidence_score = result['confidence']
                        record.classified_by = 'rule'
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Классификация успешно выполнена',
                'processed_records': len(records)
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при выполнении классификации: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/batch/<batch_id>', methods=['DELETE'])
    def delete_batch(batch_id):
        try:
            # Удаляем все записи с данным batch_id
            MigrationClass.query.filter_by(batch_id=batch_id).delete()
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Загрузка успешно удалена'})
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при удалении загрузки: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/batch/<batch_id>/export')
    def export_batch(batch_id):
        try:
            # Получаем все записи для данного batch_id
            records = MigrationClass.query.filter_by(batch_id=batch_id).all()
            
            # Экспортируем результаты
            return export_batch_results(records, batch_id)
            
        except Exception as e:
            logging.error(f"Ошибка при экспорте результатов: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/analysis')
    def analysis():
        try:
            # Получаем все batch_id для анализа
            batch_ids = db.session.query(AnalysisData.batch_id).distinct().order_by(AnalysisData.batch_id.desc()).all()
            batch_ids = [batch[0] for batch in batch_ids]
            
            # Получаем параметры пагинации
            page = request.args.get('page', 1, type=int)
            per_page = 20
            
            # Получаем данные анализа с пагинацией
            query = AnalysisData.query.order_by(AnalysisData.batch_id.desc())
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            
            # Получаем список батчей с информацией о прогрессе и результатах
            batches = []
            for batch_id in batch_ids:
                total_records = AnalysisData.query.filter_by(batch_id=batch_id).count()
                analyzed_records = AnalysisData.query.filter_by(
                    batch_id=batch_id,
                    analysis_state='analyzed'
                ).count()
                
                # Проверяем наличие результатов анализа
                has_results = AnalysisResult.query.filter_by(batch_id=batch_id).first() is not None
                
                progress = (analyzed_records / total_records * 100) if total_records > 0 else 0
                progress_color = 'success' if progress == 100 else 'warning' if progress > 0 else 'danger'
                
                # Получаем информацию о первой записи в батче для извлечения дополнительных данных
                batch_info = AnalysisData.query.filter_by(batch_id=batch_id).first()
                file_name = batch_info.file_name if batch_info else f'Анализ {batch_id[:8]}'
                source_system = batch_info.source_system if batch_info else 'Не указан'
                upload_date = batch_info.upload_date if batch_info else datetime.now()
                
                batches.append({
                    'batch_id': batch_id,
                    'file_name': file_name,
                    'source_system': source_system,
                    'upload_date': upload_date,
                    'records_count': total_records,
                    'progress': round(progress),
                    'progress_color': progress_color,
                    'has_results': has_results
                })
            
            # Формируем опции для фильтра по батчам
            batch_options = [{'id': batch_id} for batch_id in batch_ids]
            
            # Получаем batch_id из параметров запроса, если он есть
            batch_id = request.args.get('batch_id')
            
            return render_template('analysis.html', 
                                 batch_ids=batch_ids,
                                 items=pagination.items,
                                 page=page,
                                 total_pages=pagination.pages,
                                 batches=batches,
                                 batch_options=batch_options,
                                 pagination=pagination,
                                 batch_id=batch_id)
            
        except Exception as e:
            logging.error(f"Ошибка при отображении страницы анализа: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/field_mapping')
    def field_mapping():
        try:
            # Получаем все маппинги
            mappings = FieldMapping.query.all()
            
            # Если маппингов нет, создаем их из модели AnalysisData с предустановленными значениями
            if not mappings:
                # Предустановленные значения для маппинга
                default_mappings = {
                    'a_ouid': 'A_OUID',
                    'mssql_sxclass_description': 'MSSQL_SXCLASS_DESCRIPTION',
                    'mssql_sxclass_name': 'MSSQL_SXCLASS_NAME',
                    'mssql_sxclass_map': 'MSSQL_SXCLASS_MAP',
                    'system_class': 'Системный класс',
                    'is_link_table': 'Используется как таблица связи',
                    'parent_class': 'Родительский класс',
                    'child_classes': 'Дочерние классы',
                    'child_count': 'Количество дочерних классов',
                    'created_date': 'Дата создания',
                    'created_by': 'Создал',
                    'modified_date': 'Дата изменения',
                    'modified_by': 'Изменил',
                    'folder_paths': 'Пути папок в консоли',
                    'object_count': 'Количество объектов',
                    'last_object_created': 'Дата создания последнего объекта',
                    'last_object_modified': 'Дата последнего изменения',
                    'attribute_count': 'Всего атрибутов',
                    'category': 'Категория (итог)',
                    'migration_flag': 'Признак миграции (итог)',
                    'rule_info': 'Rule Info (какое правило сработало)',
                    'priznak': 'priznak'
                }
                
                # Создаем маппинги для каждого поля
                for field, excel_header in default_mappings.items():
                    mapping = FieldMapping(
                        db_field=field,
                        excel_header=excel_header,
                        is_enabled=True
                    )
                    db.session.add(mapping)
                
                db.session.commit()
                mappings = FieldMapping.query.all()
            
            return render_template('field_mapping.html', mappings=mappings)
            
        except Exception as e:
            app.logger.error(f"Ошибка при отображении страницы маппинга полей: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/save_field_mapping', methods=['POST'])
    def save_field_mapping():
        try:
            # Получаем все маппинги
            mappings = FieldMapping.query.all()
            
            # Обновляем каждый маппинг
            for mapping in mappings:
                excel_header = request.form.get(f'excel_header_{mapping.id}')
                is_enabled = request.form.get(f'is_enabled_{mapping.id}') == 'on'
                
                mapping.excel_header = excel_header
                mapping.is_enabled = is_enabled
            
            db.session.commit()
            
            return redirect(url_for('field_mapping'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Ошибка при сохранении маппинга полей: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/test_mapping', methods=['POST'])
    def test_mapping():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'Файл не найден'}), 400
            
            file = request.files['file']
            field = request.form.get('field')
            header = request.form.get('header')
            
            if not file or not field or not header:
                return jsonify({'success': False, 'error': 'Не все параметры указаны'}), 400
            
            # Читаем Excel файл
            df = pd.read_excel(file, header=1)
            
            # Ищем заголовок
            found_headers = [col for col in df.columns if str(col).lower() == str(header).lower()]
            
            if not found_headers:
                return jsonify({
                    'success': False,
                    'error': f'Заголовок "{header}" не найден в файле'
                }), 400
            
            # Получаем пример значения
            sample_value = str(df[found_headers[0]].iloc[0]) if not df.empty else 'Нет данных'
            
            return jsonify({
                'success': True,
                'found_headers': len(found_headers),
                'sample_value': sample_value
            })
            
        except Exception as e:
            app.logger.error(f"Ошибка при тестировании маппинга: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/upload_analysis', methods=['POST'])
    def upload_analysis():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'Файл не найден'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'Файл не выбран'}), 400
            
            if not file.filename.endswith('.xlsx'):
                return jsonify({'success': False, 'error': 'Поддерживаются только файлы Excel (.xlsx)'}), 400
            
            source_system = request.form.get('source_system')
            if not source_system:
                return jsonify({'success': False, 'error': 'Не указан источник данных'}), 400
            
            # Получаем значение базового URL, если есть
            base_url = request.form.get('base_url', '')
            
            # Получаем максимальный batch_id и увеличиваем его на 1
            max_batch_id = db.session.query(func.max(AnalysisData.batch_id)).scalar()
            batch_id = 1 if max_batch_id is None else int(max_batch_id) + 1
            
            # Читаем данные из Excel, пропуская первую строку
            df = pd.read_excel(file, header=1)
            
            # Логируем подробную информацию о структуре Excel файла
            app.logger.info("=== Информация о загруженном Excel файле ===")
            app.logger.info(f"Имя файла: {file.filename}")
            app.logger.info(f"Количество строк: {len(df)}")
            app.logger.info(f"Количество колонок: {len(df.columns)}")
            app.logger.info(f"Заголовки колонок: {df.columns.tolist()}")
            app.logger.info(f"Типы данных колонок: {df.dtypes.to_dict()}")
            app.logger.info(f"Первая строка данных: {df.iloc[0].to_dict()}")
            
            # Получаем активные маппинги
            mappings = FieldMapping.query.filter_by(is_enabled=True).all()
            
            # Создаем словарь для хранения найденных колонок
            found_columns = {}
            
            # Ищем нужные колонки в DataFrame (игнорируя регистр)
            for mapping in mappings:
                for excel_column in df.columns:
                    if str(excel_column).lower() == str(mapping.excel_header).lower():
                        found_columns[mapping.db_field] = excel_column
                        app.logger.info(f"Найдено соответствие: {excel_column} -> {mapping.db_field}")
                        break
            
            # Проверяем наличие всех необходимых колонок
            missing_columns = [mapping.db_field for mapping in mappings if mapping.db_field not in found_columns]
            
            if missing_columns:
                app.logger.error(f"Отсутствуют обязательные колонки: {missing_columns}")
                app.logger.error(f"Доступные колонки в Excel: {df.columns.tolist()}")
                return jsonify({
                    'success': False, 
                    'error': f'В файле отсутствуют обязательные колонки: {", ".join(missing_columns)}'
                }), 400
            
            # Добавляем записи в базу данных
            records_added = 0
            failed_records = []  # Список для хранения записей, которые не удалось загрузить
            
            for index, row in df.iterrows():
                try:
                    # Логируем данные каждой строки
                    app.logger.info(f"=== Обработка строки {index + 1} ===")
                    app.logger.info(f"Данные строки: {row.to_dict()}")
                    
                    # Создаем словарь с данными для AnalysisData
                    data = {
                        'batch_id': batch_id,
                        'file_name': file.filename,
                        'source_system': source_system,
                        'base_url': base_url,
                        'analysis_state': 'pending'
                    }
                    
                    # Добавляем все поля из Excel
                    for db_field, excel_column in found_columns.items():
                        value = row[excel_column]
                        # Преобразуем значение в строку, если оно не пустое
                        data[db_field] = str(value) if pd.notna(value) else ''
                    
                    analysis_data = AnalysisData(**data)
                    db.session.add(analysis_data)
                    records_added += 1
                    app.logger.info(f"Запись успешно добавлена: {analysis_data.mssql_sxclass_name}")
                except Exception as row_error:
                    app.logger.error(f"Ошибка при обработке строки {index + 1}: {str(row_error)}")
                    # Сохраняем информацию о неудачной записи
                    failed_record = {
                        'index': index + 1,
                        'error': str(row_error),
                        'data': {}
                    }
                    # Добавляем основные поля для идентификации записи
                    for field in ['MSSQL_SXCLASS_DESCRIPTION', 'MSSQL_SXCLASS_NAME', 'MSSQL_SXCLASS_MAP']:
                        if field in row:
                            failed_record['data'][field] = str(row[field]) if pd.notna(row[field]) else ''
                    failed_records.append(failed_record)
                    continue
            
            db.session.commit()
            app.logger.info(f"=== Загрузка завершена ===")
            app.logger.info(f"Всего добавлено записей: {records_added}")
            app.logger.info(f"Не удалось загрузить записей: {len(failed_records)}")
            
            # Проверяем, все ли записи были загружены
            if len(df) != records_added:
                app.logger.warning(f"Не все записи были загружены! В Excel: {len(df)}, загружено: {records_added}")
                for failed in failed_records:
                    app.logger.warning(f"Не загружена строка {failed['index']}: {failed['data']}, ошибка: {failed['error']}")
                
                return jsonify({
                    'success': True,
                    'message': f'Файл загружен, но не все записи были обработаны. Загружено {records_added} из {len(df)} записей.',
                    'batch_id': batch_id,
                    'records_added': records_added,
                    'total_records': len(df),
                    'failed_records': failed_records,
                    'warning': True
                })
            
            return jsonify({
                'success': True,
                'message': f'Файл успешно загружен. Добавлено {records_added} записей.',
                'batch_id': batch_id,
                'records_added': records_added,
                'total_records': len(df)
            })
            
        except Exception as e:
            app.logger.error(f"Ошибка при загрузке файла: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/analyze_item/<int:item_id>', methods=['POST'])
    def analyze_item(item_id):
        try:
            item = MigrationClass.query.get_or_404(item_id)
            
            # Анализируем запись
            result = classify_record(item)
            
            if result:
                item.priznak = result['priznak']
                item.confidence_score = result['confidence']
                item.classified_by = 'rule'
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'message': 'Анализ успешно выполнен',
                    'priznak': result['priznak'],
                    'confidence': result['confidence']
                })
            else:
                return jsonify({'success': False, 'error': 'Не удалось определить priznak'}), 400
                
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при анализе записи: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/analyze_batch/<batch_id>', methods=['POST'])
    def analyze_batch(batch_id):
        try:
            # Получаем все записи для данного batch_id
            records = MigrationClass.query.filter_by(batch_id=batch_id).all()
            
            # Анализируем каждую запись
            analyzed_count = 0
            for record in records:
                if not record.priznak:  # Анализируем только записи без priznak
                    result = classify_record(record)
                    if result:
                        record.priznak = result['priznak']
                        record.confidence_score = result['confidence']
                        record.classified_by = 'rule'
                        analyzed_count += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Анализ успешно выполнен',
                'analyzed_records': analyzed_count
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при анализе загрузки: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/analysis_batch/<batch_id>', methods=['DELETE'])
    def delete_analysis_batch(batch_id):
        try:
            # Удаляем все записи анализа для данного batch_id
            AnalysisData.query.filter_by(batch_id=batch_id).delete()
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Данные анализа успешно удалены'})
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при удалении данных анализа: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    def convert_value_type(value, field_type):
        """Преобразует значение в нужный тип данных"""
        if pd.isna(value) or value == '':
            return None
        
        if field_type == bool:
            return str(value).lower() in ('true', '1', 'yes', 'да', 'истина')
        elif field_type == datetime:
            try:
                return pd.to_datetime(value)
            except:
                return None
        elif field_type == int:
            try:
                return int(float(value))
            except:
                return None
        elif field_type == float:
            try:
                return float(value)
            except:
                return None
        else:
            return str(value)

    @app.route('/upload_history', methods=['POST'])
    def upload_history():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'Файл не найден'}), 400
            
            file = request.files['file']
            source_system = request.form.get('source_system', 'unknown')
            
            if file.filename == '':
                return jsonify({'success': False, 'error': 'Файл не выбран'}), 400
            
            if not file.filename.endswith('.xlsx'):
                return jsonify({'success': False, 'error': 'Поддерживаются только Excel файлы (.xlsx)'}), 400
            
            # Генерируем уникальный batch_id
            batch_id = str(uuid.uuid4())
            app.logger.info(f"Создан batch_id: {batch_id} для файла {file.filename}")
            
            # Получаем активные маппинги полей
            mappings = FieldMapping.query.filter_by(is_enabled=True).all()
            if not mappings:
                return jsonify({'success': False, 'error': 'Не настроены маппинги полей'}), 400
            
            # Создаем словарь маппингов
            field_mappings = {m.db_field: m.excel_header for m in mappings}
            
            # Читаем Excel файл
            df = pd.read_excel(file, header=1)
            app.logger.info(f"Прочитан Excel файл: {len(df)} строк, {len(df.columns)} колонок")
            app.logger.info(f"Заголовки колонок: {df.columns.tolist()}")
            
            # Проверяем наличие необходимых колонок
            found_columns = {}
            for db_field, excel_header in field_mappings.items():
                if excel_header in df.columns:
                    found_columns[db_field] = excel_header
                else:
                    app.logger.warning(f"Колонка '{excel_header}' не найдена в Excel файле")
            
            if not found_columns:
                return jsonify({'success': False, 'error': 'Не найдено ни одной соответствующей колонки в Excel файле'}), 400
            
            records_added = 0
            for index, row in df.iterrows():
                try:
                    # Логируем данные каждой строки
                    app.logger.info(f"=== Обработка строки {index + 1} ===")
                    app.logger.info(f"Данные строки: {row.to_dict()}")
                    
                    # Создаем словарь с данными для MigrationClass
                    data = {
                        'batch_id': batch_id,
                        'file_name': file.filename,
                        'source_system': source_system,
                        'upload_date': datetime.now()
                    }
                    
                    # Добавляем все поля из Excel
                    for db_field, excel_column in found_columns.items():
                        value = row[excel_column]
                        # Преобразуем значение в строку, если оно не пустое
                        if pd.notna(value):
                            # Для числовых значений используем str() для корректного преобразования
                            if isinstance(value, (int, float)):
                                data[db_field] = str(value)
                            else:
                                data[db_field] = str(value).strip()
                        else:
                            data[db_field] = ''
                    
                    migration_class = MigrationClass(**data)
                    db.session.add(migration_class)
                    records_added += 1
                    app.logger.info(f"Запись успешно добавлена: {migration_class.mssql_sxclass_name}")
                except Exception as row_error:
                    app.logger.error(f"Ошибка при обработке строки {index + 1}: {str(row_error)}")
                    continue
            
            db.session.commit()
            app.logger.info(f"=== Загрузка завершена ===")
            app.logger.info(f"Всего добавлено записей: {records_added}")
            
            return jsonify({
                'success': True,
                'message': f'Успешно загружено {records_added} записей',
                'batch_id': batch_id
            })
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Ошибка при загрузке исторических данных: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/analyze_all', methods=['POST'])
    def analyze_all():
        try:
            batch_id = request.json.get('batch_id')
            if not batch_id:
                return jsonify({'success': False, 'error': 'Не указан batch_id'}), 400

            # Проверяем, есть ли уже результаты анализа
            existing_results = AnalysisResult.query.filter_by(batch_id=batch_id).first()
            if existing_results:
                return jsonify({
                    'success': False, 
                    'error': 'Для этого батча уже есть результаты анализа. Сначала очистите существующие результаты.'
                }), 400

            # Получаем все записи для анализа
            analysis_records = AnalysisData.query.filter_by(batch_id=batch_id).all()
            
            # Получаем все исторические записи
            historical_records = MigrationClass.query.all()
            
            # Создаем словарь для хранения результатов анализа
            results = []
            
            for record in analysis_records:
                # Ищем совпадения в исторических данных
                historical_matches = [
                    h for h in historical_records 
                    if h.mssql_sxclass_name == record.mssql_sxclass_name
                ]
                
                if historical_matches:
                    # Проверяем совпадение priznak
                    priznaks = set(h.priznak for h in historical_matches)
                    
                    if len(priznaks) == 1:
                        # Если все значения priznak совпадают
                        result = AnalysisResult(
                            batch_id=batch_id,
                            mssql_sxclass_name=record.mssql_sxclass_name,
                            priznak=priznaks.pop(),
                            confidence_score=1.0,
                            analyzed_by='historical',
                            status='analyzed'
                        )
                    else:
                        # Если есть расхождения
                        discrepancies = {}
                        for h in historical_matches:
                            if h.batch_id not in discrepancies:
                                discrepancies[h.batch_id] = h.priznak
                        
                        result = AnalysisResult(
                            batch_id=batch_id,
                            mssql_sxclass_name=record.mssql_sxclass_name,
                            discrepancies=discrepancies,
                            status='pending'
                        )
                else:
                    # Если совпадений не найдено
                    result = AnalysisResult(
                        batch_id=batch_id,
                        mssql_sxclass_name=record.mssql_sxclass_name,
                        status='pending'
                    )
                
                db.session.add(result)
                results.append(result)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Проанализировано {len(results)} записей',
                'results_count': len(results)
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при анализе данных: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/analysis_results/<batch_id>')
    def analysis_results(batch_id):
        try:
            # Получаем параметры пагинации
            page = request.args.get('page', 1, type=int)
            per_page = 20  # количество записей на странице
            
            # Логируем параметры запроса
            logging.info(f"Параметры запроса analysis_results: {dict(request.args)}")
            
            # Получаем результаты анализа с пагинацией
            query = AnalysisResult.query.filter_by(batch_id=batch_id)
            
            # Применяем фильтры, если они есть
            status_filter = request.args.get('status')
            current_discrepancy = request.args.get('discrepancy_filter')
            card_filter = request.args.get('card_filter')  # Новый параметр для фильтрации по карточке
            
            logging.info(f"Фильтры: status={status_filter}, discrepancy_filter={current_discrepancy}, card_filter={card_filter}")
            
            if status_filter:
                if status_filter == 'no_matches':
                    query = query.filter(AnalysisResult.status == 'pending', AnalysisResult.discrepancies.is_(None))
                elif status_filter == 'discrepancies':
                    query = query.filter(AnalysisResult.status == 'pending', AnalysisResult.discrepancies.isnot(None))
                elif status_filter == 'analyzed_empty_priznak':
                    query = query.filter(AnalysisResult.status == 'analyzed').filter((AnalysisResult.priznak == None) | (AnalysisResult.priznak == ''))
                else:
                    query = query.filter(AnalysisResult.status == status_filter)
            
            # Применяем фильтр по расхождениям
            if current_discrepancy:
                logging.info(f"Применяем фильтр по расхождениям: {current_discrepancy}")
                # В PostgreSQL нельзя напрямую сравнивать JSON-поле со строкой
                # Вместо этого получаем все результаты и фильтруем их в Python
                discrepancy_results = []
                all_results_for_discrepancy = query.all()
                
                for result in all_results_for_discrepancy:
                    # Учитываем только записи со статусом 'pending'
                    if result.status == 'pending' and result.discrepancies and str(result.discrepancies) == current_discrepancy:
                        discrepancy_results.append(result.id)
                
                if discrepancy_results:
                    query = AnalysisResult.query.filter(AnalysisResult.id.in_(discrepancy_results))
                else:
                    # Если нет совпадений, возвращаем пустой результат
                    query = AnalysisResult.query.filter(AnalysisResult.id == -1)
            
            # Применяем фильтр по карточке расхождения
            if card_filter:
                logging.info(f"Применяем фильтр по карточке: {card_filter}")
                # Разбираем параметры карточки (источники и признаки)
                try:
                    card_data = json.loads(card_filter)
                    sources = card_data.get('sources', [])
                    priznaks = card_data.get('priznaks', [])
                    
                    logging.info(f"Данные карточки: sources={sources}, priznaks={priznaks}")
                    
                    # Фильтруем результаты, у которых есть расхождения с указанными источниками и признаками
                    filtered_results = []
                    # Используем текущий query, который может уже быть отфильтрован по discrepancy_filter
                    all_results = query.all()
                    
                    for result in all_results:
                        # Учитываем только записи со статусом 'pending'
                        if result.status != 'pending' or not result.discrepancies:
                            continue
                            
                        # Проверяем, содержит ли результат расхождения с указанными источниками и признаками
                        match = False
                        for batch_id, priznak in result.discrepancies.items():
                            # Получаем source_system для этого batch_id
                            source = db.session.query(MigrationClass.source_system).filter_by(
                                batch_id=batch_id
                            ).first()
                            
                            if source and source[0] in sources and priznak in priznaks:
                                match = True
                                logging.info(f"Найдено совпадение: result_id={result.id}, source={source[0]}, priznak={priznak}")
                                break
                                
                        if match:
                            filtered_results.append(result.id)
                    
                    logging.info(f"Отфильтрованные результаты: {filtered_results}")
                    
                    # Применяем фильтр по ID
                    if filtered_results:
                        query = AnalysisResult.query.filter(AnalysisResult.id.in_(filtered_results))
                    else:
                        # Если нет совпадений, возвращаем пустой результат
                        query = AnalysisResult.query.filter(AnalysisResult.id == -1)
                except Exception as e:
                    logging.error(f"Ошибка при применении фильтра по карточке: {str(e)}", exc_info=True)
                    # Откатываем транзакцию в случае ошибки
                    db.session.rollback()
            
            # Применяем поиск, если он есть
            search = request.args.get('search')
            if search:
                query = query.filter(AnalysisResult.mssql_sxclass_name.ilike(f'%{search}%'))
            
            # Получаем пагинацию
            pagination = query.order_by(AnalysisResult.mssql_sxclass_name).paginate(
                page=page, per_page=per_page, error_out=False)
            
            # Получаем все результаты для подсчета статистики
            all_results = AnalysisResult.query.filter_by(batch_id=batch_id).all()
            
            # Группируем результаты по статусу
            status_counts = {
                'no_matches': len([r for r in all_results if r.status == 'pending' and not r.discrepancies]),
                'discrepancies': len([r for r in all_results if r.status == 'pending' and r.discrepancies]),
                'analyzed': len([r for r in all_results if r.status == 'analyzed']),
                'confirmed': len([r for r in all_results if r.status == 'confirmed'])
            }

            # Получаем статистику по расхождениям
            discrepancy_stats = {}
            for result in all_results:
                # Учитываем только записи со статусом 'pending' (необработанные)
                if result.status == 'pending' and result.discrepancies:
                    # Создаем ключ для группировки расхождений
                    discrepancy_key = str(result.discrepancies)
                    if discrepancy_key not in discrepancy_stats:
                        discrepancy_stats[discrepancy_key] = {
                            'count': 0,
                            'sources': set(),
                            'priznaks': set()
                        }
                    
                    # Увеличиваем счетчик
                    discrepancy_stats[discrepancy_key]['count'] += 1
                    
                    # Добавляем источники и признаки
                    for historical_batch_id, priznak in result.discrepancies.items():
                        # Получаем source_system для исторического batch_id
                        source = db.session.query(MigrationClass.source_system).filter_by(
                            batch_id=historical_batch_id
                        ).first()
                        if source:
                            discrepancy_stats[discrepancy_key]['sources'].add(source[0])
                        discrepancy_stats[discrepancy_key]['priznaks'].add(priznak)

            # Логируем статистику по расхождениям
            logging.info(f"Статистика по расхождениям (до преобразования): {discrepancy_stats}")

            # Преобразуем множества в списки для JSON-сериализации
            for key in discrepancy_stats:
                discrepancy_stats[key]['sources'] = list(discrepancy_stats[key]['sources'])
                discrepancy_stats[key]['priznaks'] = list(discrepancy_stats[key]['priznaks'])
                discrepancy_stats[key]['count'] = discrepancy_stats[key]['count']
            
            # Логируем статистику по расхождениям после преобразования
            logging.info(f"Статистика по расхождениям (после преобразования): {discrepancy_stats}")
            
            # Логируем текущий фильтр по расхождениям и карточке
            logging.info(f"Текущий фильтр по расхождениям: {current_discrepancy}")
            logging.info(f"Текущий фильтр по карточке: {card_filter}")

            # Получаем список уникальных значений priznak из исторических данных
            priznaks = db.session.query(MigrationClass.priznak).distinct().filter(
                MigrationClass.priznak.isnot(None)
            ).order_by(MigrationClass.priznak).all()
            priznaks = [priznak[0] for priznak in priznaks]

            # Получаем source_system для каждого батча
            batch_sources = {}
            for result in all_results:
                if result.discrepancies:
                    for historical_batch_id in result.discrepancies.keys():
                        if historical_batch_id not in batch_sources:
                            # Получаем source_system для этого batch_id из исторических данных
                            source = db.session.query(MigrationClass.source_system).filter_by(
                                batch_id=historical_batch_id
                            ).first()
                            batch_sources[historical_batch_id] = source[0] if source else 'Неизвестный источник'
            
            # Получаем описания классов из таблицы analysis_data
            class_descriptions = {}
            class_tables = {}  # Новый словарь для хранения таблиц
            for result in pagination.items:
                if result.mssql_sxclass_name not in class_descriptions:
                    # Ищем описание и таблицу в таблице analysis_data
                    class_data = db.session.query(
                        AnalysisData.mssql_sxclass_description,
                        AnalysisData.mssql_sxclass_map
                    ).filter_by(
                        batch_id=batch_id,
                        mssql_sxclass_name=result.mssql_sxclass_name
                    ).first()
                    
                    class_descriptions[result.mssql_sxclass_name] = class_data[0] if class_data else ''
                    class_tables[result.mssql_sxclass_name] = class_data[1] if class_data else ''
            
            # Получаем source_system для текущего batch_id
            batch_info = AnalysisData.query.filter_by(batch_id=batch_id).first()
            source_system = batch_info.source_system if batch_info else 'Не указан'
            
            return render_template('analysis_results.html',
                                 results=pagination.items,
                                 pagination=pagination,
                                 status_counts=status_counts,
                                 batch_id=batch_id,
                                 current_search=search,
                                 current_status=status_filter,
                                 current_discrepancy=current_discrepancy,
                                 current_card_filter=card_filter,
                                 class_descriptions=class_descriptions,
                                 class_tables=class_tables,
                                 priznaks=priznaks,
                                 batch_sources=batch_sources,
                                 source_system=source_system,
                                 discrepancy_stats=discrepancy_stats)
            
        except Exception as e:
            logging.error(f"Ошибка при отображении результатов анализа: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/export_analysis/<batch_id>')
    def export_analysis_results(batch_id):
        try:
            # Получаем результаты анализа
            results = AnalysisResult.query.filter_by(batch_id=batch_id).all()
            
            # Создаем DataFrame
            data = []
            for result in results:
                row = {
                    'Имя класса': result.mssql_sxclass_name,
                    'Признак': result.priznak if result.priznak else '',
                    'Уверенность': result.confidence_score if result.confidence_score else '',
                    'Статус': result.status,
                    'Дата анализа': result.analysis_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'Метод анализа': result.analyzed_by if result.analyzed_by else ''
                }
                
                # Добавляем информацию о расхождениях
                if result.discrepancies:
                    row['Расхождения'] = str(result.discrepancies)
                
                data.append(row)
            
            df = pd.DataFrame(data)
            
            # Создаем Excel файл
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Результаты анализа')
                
                # Форматирование
                workbook = writer.book
                worksheet = writer.sheets['Результаты анализа']
                
                # Форматы
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#D9E1F2',
                    'border': 1
                })
                
                # Применяем форматирование к заголовкам
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    worksheet.set_column(col_num, col_num, 15)
            
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'analysis_results_{batch_id}.xlsx'
            )
            
        except Exception as e:
            logging.error(f"Ошибка при экспорте результатов анализа: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/analyze_record/<int:record_id>', methods=['POST'])
    def analyze_record(record_id):
        try:
            # Получаем запись для анализа
            result = AnalysisResult.query.get_or_404(record_id)
            
            # Получаем исторические записи с таким же именем класса
            historical_records = MigrationClass.query.filter_by(
                mssql_sxclass_name=result.mssql_sxclass_name
            ).all()
            
            if historical_records:
                # Проверяем совпадение priznak
                priznaks = set(h.priznak for h in historical_records)
                
                if len(priznaks) == 1:
                    # Если все значения priznak совпадают
                    result.priznak = priznaks.pop()
                    result.confidence_score = 1.0
                    result.analyzed_by = 'historical'
                    result.status = 'analyzed'
                else:
                    # Если есть расхождения
                    discrepancies = {}
                    for h in historical_records:
                        if h.batch_id not in discrepancies:
                            discrepancies[h.batch_id] = h.priznak
                    
                    result.discrepancies = discrepancies
                    result.status = 'pending'
            else:
                # Если совпадений не найдено
                result.status = 'pending'
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Запись успешно проанализирована'
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при анализе записи: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/clear_analysis_results/<batch_id>', methods=['DELETE'])
    def clear_analysis_results(batch_id):
        try:
            # Удаляем все результаты анализа для данного batch_id
            AnalysisResult.query.filter_by(batch_id=batch_id).delete()
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Результаты анализа успешно очищены'})
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при очистке результатов анализа: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/confirm_analysis_result/<int:result_id>', methods=['POST'])
    def confirm_analysis_result(result_id):
        try:
            # Получаем результат анализа
            result = AnalysisResult.query.get_or_404(result_id)
            
            # Меняем статус на подтвержденный
            result.status = 'confirmed'
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Результат анализа успешно подтвержден'
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при подтверждении результата анализа: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/update_priznak/<int:result_id>', methods=['POST'])
    def update_priznak(result_id):
        try:
            # Получаем результат анализа
            result = AnalysisResult.query.get_or_404(result_id)
            
            # Получаем новое значение priznak из запроса
            data = request.get_json()
            new_priznak = data.get('priznak')
            
            if new_priznak is None:
                return jsonify({'success': False, 'error': 'Не указано значение priznak'}), 400
            
            # Обновляем значение priznak
            result.priznak = new_priznak
            result.analyzed_by = 'manual'  # Устанавливаем метод анализа как ручной
            result.status = 'analyzed'  # Меняем статус на проанализированный
            result.confidence_score = 1.0  # Устанавливаем максимальную уверенность для ручного ввода
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Значение priznak успешно обновлено'
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при обновлении значения priznak: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/normalize_priznaks')
    def normalize_priznaks():
        try:
            # Получаем список уникальных значений priznak с количеством записей
            priznaks = db.session.query(
                MigrationClass.priznak,
                func.count(MigrationClass.id).label('count')
            ).filter(
                MigrationClass.priznak.isnot(None)
            ).group_by(
                MigrationClass.priznak
            ).order_by(
                MigrationClass.priznak
            ).all()
            
            # Форматируем данные для шаблона
            priznaks_data = [
                {'value': p[0], 'count': p[1]} 
                for p in priznaks
            ]
            
            return render_template('normalize_priznaks.html', priznaks=priznaks_data)
            
        except Exception as e:
            logging.error(f"Ошибка при отображении страницы нормализации: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/normalize_priznaks', methods=['POST'])
    def normalize_priznaks_api():
        try:
            data = request.get_json()
            values = data.get('values', [])
            target_value = data.get('target_value')
            
            if not values or not target_value or target_value not in values:
                return jsonify({
                    'success': False,
                    'error': 'Необходимо указать список значений и целевое значение'
                }), 400
            
            # Получаем все записи с указанными значениями priznak
            records = MigrationClass.query.filter(
                MigrationClass.priznak.in_(values)
            ).all()
            
            # Обновляем значения в MigrationClass
            updated_count = 0
            for record in records:
                if record.priznak != target_value:
                    record.priznak = target_value
                    updated_count += 1
            
            # Обновляем значения в AnalysisResult
            analysis_results = AnalysisResult.query.filter(
                AnalysisResult.priznak.in_(values)
            ).all()
            
            analysis_updated_count = 0
            for result in analysis_results:
                if result.priznak != target_value:
                    result.priznak = target_value
                    result.analyzed_by = 'normalized'  # Отмечаем, что значение было нормализовано
                    analysis_updated_count += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Успешно обновлено {updated_count} записей в исторических данных и {analysis_updated_count} записей в результатах анализа',
                'updated_count': updated_count,
                'analysis_updated_count': analysis_updated_count
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при нормализации значений priznak: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/update_priznak_batch', methods=['POST'])
    def update_priznak_batch():
        try:
            data = request.get_json()
            ids = data.get('ids', [])
            priznak = data.get('priznak')
            
            if not ids or not priznak:
                return jsonify({
                    'success': False,
                    'error': 'Необходимо указать список ID и значение priznak'
                }), 400
            
            # Обновляем значения для всех указанных записей
            updated_count = 0
            for result_id in ids:
                result = AnalysisResult.query.get(result_id)
                if result:
                    result.priznak = priznak
                    result.analyzed_by = 'batch_update'  # Отмечаем, что значение было обновлено массово
                    result.status = 'analyzed'
                    result.confidence_score = 1.0
                    updated_count += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Успешно обновлено {updated_count} записей',
                'updated_count': updated_count
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при массовом обновлении значений priznak: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/update_priznak_all_filtered', methods=['POST'])
    def update_priznak_all_filtered():
        try:
            data = request.get_json()
            batch_id = data.get('batch_id')
            priznak = data.get('priznak')
            status_filter = data.get('status_filter')
            discrepancy_filter = data.get('discrepancy_filter')
            card_filter = data.get('card_filter')
            search = data.get('search')
            
            if not batch_id or not priznak:
                return jsonify({
                    'success': False,
                    'error': 'Необходимо указать batch_id и значение priznak'
                }), 400
            
            # Базовый запрос
            query = AnalysisResult.query.filter_by(batch_id=batch_id)
            
            # Применяем фильтры
            if status_filter:
                if status_filter == 'no_matches':
                    query = query.filter(AnalysisResult.status == 'pending', AnalysisResult.discrepancies.is_(None))
                elif status_filter == 'discrepancies':
                    query = query.filter(AnalysisResult.status == 'pending', AnalysisResult.discrepancies.isnot(None))
                elif status_filter == 'analyzed_empty_priznak':
                    query = query.filter(AnalysisResult.status == 'analyzed').filter((AnalysisResult.priznak == None) | (AnalysisResult.priznak == ''))
                else:
                    query = query.filter(AnalysisResult.status == status_filter)
            
            # Применяем поиск, если он есть
            if search:
                query = query.filter(AnalysisResult.mssql_sxclass_name.ilike(f'%{search}%'))
            
            # Для фильтров, требующих дополнительной обработки, получаем все результаты и фильтруем их в Python
            all_results = query.all()
            filtered_results = all_results
            
            # Применяем фильтр по расхождениям
            if discrepancy_filter:
                discrepancy_results = []
                for result in all_results:
                    if result.discrepancies and str(result.discrepancies) == discrepancy_filter:
                        discrepancy_results.append(result)
                filtered_results = discrepancy_results
            
            # Применяем фильтр по карточке расхождения
            if card_filter:
                try:
                    card_data = json.loads(card_filter)
                    sources = card_data.get('sources', [])
                    priznaks = card_data.get('priznaks', [])
                    
                    card_filtered_results = []
                    for result in filtered_results:
                        if not result.discrepancies:
                            continue
                            
                        # Проверяем, содержит ли результат расхождения с указанными источниками и признаками
                        match = False
                        for batch_id, priznak_value in result.discrepancies.items():
                            # Получаем source_system для этого batch_id
                            source = db.session.query(MigrationClass.source_system).filter_by(
                                batch_id=batch_id
                            ).first()
                            
                            if source and source[0] in sources and priznak_value in priznaks:
                                match = True
                                break
                                
                        if match:
                            card_filtered_results.append(result)
                    
                    filtered_results = card_filtered_results
                except Exception as e:
                    logging.error(f"Ошибка при применении фильтра по карточке: {str(e)}", exc_info=True)
            
            # Обновляем значения для всех отфильтрованных записей
            updated_count = 0
            for result in filtered_results:
                result.priznak = priznak
                result.analyzed_by = 'batch_update'  # Отмечаем, что значение было обновлено массово
                result.status = 'analyzed'
                result.confidence_score = 1.0
                updated_count += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Успешно обновлено {updated_count} записей',
                'updated_count': updated_count
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при массовом обновлении всех отфильтрованных записей: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/analyze/batch/<batch_id>', methods=['POST'])
    def analyze_batch_v2(batch_id):
        """
        Запуск анализа для указанного batch_id
        """
        try:
            analysis_service = AnalysisService()
            result = analysis_service.analyze_historical_patterns(batch_id)
            
            if result['success']:
                return jsonify(result)
            else:
                return jsonify(result), 500
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/analysis/results', methods=['GET'])
    def get_analysis_results():
        """
        Получение результатов анализа с фильтрацией
        """
        try:
            # Параметры фильтрации
            batch_id = request.args.get('batch_id')
            confidence_threshold = float(request.args.get('confidence', 0.0))
            priznak = request.args.get('priznak')
            has_discrepancies = request.args.get('has_discrepancies', '').lower() == 'true'
            
            # Базовый запрос
            query = AnalysisResult.query
            
            # Применяем фильтры
            if batch_id:
                query = query.filter_by(batch_id=batch_id)
            if confidence_threshold > 0:
                query = query.filter(AnalysisResult.confidence_score >= confidence_threshold)
            if priznak:
                query = query.filter_by(priznak=priznak)
            if has_discrepancies:
                query = query.filter(AnalysisResult.discrepancies != None)
            
            # Получаем результаты с пагинацией
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            pagination = query.order_by(AnalysisResult.analysis_date.desc()).paginate(
                page=page, per_page=per_page, error_out=False)
            
            results = [{
                'id': r.id,
                'class_name': r.mssql_sxclass_name,
                'priznak': r.priznak,
                'confidence': r.confidence_score,
                'discrepancies': r.discrepancies,
                'status': r.status,
                'analysis_date': r.analysis_date.isoformat() if r.analysis_date else None
            } for r in pagination.items]
            
            return jsonify({
                'success': True,
                'results': results,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': pagination.total,
                    'pages': pagination.pages
                }
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/analysis/statistics', methods=['GET'])
    def get_analysis_statistics():
        """
        Получение статистики по анализу
        """
        try:
            batch_id = request.args.get('batch_id')
            
            # Базовый запрос
            query = AnalysisResult.query
            
            if batch_id:
                query = query.filter_by(batch_id=batch_id)
            
            # Общая статистика
            total_analyzed = query.count()
            high_confidence = query.filter(AnalysisResult.confidence_score >= 0.8).count()
            with_discrepancies = query.filter(AnalysisResult.discrepancies != None).count()
            
            # Распределение по признакам
            priznak_distribution = db.session.query(
                AnalysisResult.priznak,
                func.count(AnalysisResult.id).label('count')
            ).group_by(AnalysisResult.priznak).all()
            
            return jsonify({
                'success': True,
                'statistics': {
                    'total_analyzed': total_analyzed,
                    'high_confidence_matches': high_confidence,
                    'with_discrepancies': with_discrepancies,
                    'priznak_distribution': {
                        p[0]: p[1] for p in priznak_distribution if p[0]
                    }
                }
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/transfer_rules')
    def transfer_rules():
        page = request.args.get('page', 1, type=int)
        per_page = 50  # Количество правил на странице
        search_query = request.args.get('search', '')
        
        # Формируем запрос с фильтрацией, если указан поисковый запрос
        query = TransferRule.query.order_by(TransferRule.priority)
        
        if search_query:
            query = query.filter(TransferRule.condition_value.ilike(f'%{search_query}%'))
        
        # Получаем правила с пагинацией
        pagination = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        rules = pagination.items
        total_pages = pagination.pages
        
        # Если есть правила, находим похожие условия для каждого
        if rules:
            find_similar_conditions(rules)
        
        return render_template(
            'transfer_rules.html',
            rules=rules,
            page=page,
            total_pages=total_pages,
            search_query=search_query
        )

    def find_similar_conditions(rules):
        """
        Для каждого правила находит другие правила с похожими условиями
        
        Args:
            rules: список объектов TransferRule
        """
        # Получаем все правила для поиска совпадений
        all_rules = TransferRule.query.all()
        all_rules_dict = {rule.id: rule for rule in all_rules}
        
        # Индекс условий для быстрого поиска
        condition_index = {}
        
        # Сначала проиндексируем все правила по частям условий
        for rule in all_rules:
            if not rule.condition_value:
                continue
                
            # Разбиваем составное условие на части и нормализуем их
            condition_parts = [part.strip() for part in rule.condition_value.split(';') if part.strip()]
            
            # Добавляем каждую часть условия в индекс
            for part in condition_parts:
                if part not in condition_index:
                    condition_index[part] = set()
                condition_index[part].add(rule.id)
        
        # Теперь находим похожие правила для каждого правила в списке
        for rule in rules:
            # Пропускаем пустые условия
            if not rule.condition_value:
                rule.similar_rules = []
                continue
                
            # Разбиваем составное условие на части и нормализуем их
            condition_parts = [part.strip() for part in rule.condition_value.split(';') if part.strip()]
            
            # Множество ID правил с похожими условиями
            similar_rule_ids = set()
            
            # Для каждой части условия текущего правила
            for part in condition_parts:
                # Если эта часть условия есть в индексе, добавляем все правила с таким же условием
                if part in condition_index:
                    # Добавляем все правила, кроме текущего
                    similar_rule_ids.update(rule_id for rule_id in condition_index[part] if rule_id != rule.id)
            
            # Формируем список правил с похожими условиями с дополнительной информацией
            rule.similar_rules = []
            for rule_id in similar_rule_ids:
                similar_rule = all_rules_dict[rule_id]
                # Находим общие части условий
                common_parts = []
                for part in condition_parts:
                    if part in similar_rule.condition_value:
                        common_parts.append(part)
                
                rule.similar_rules.append({
                    "id": rule_id, 
                    "value": similar_rule.condition_value,
                    "common_parts": common_parts,
                    "transfer_action": similar_rule.transfer_action  # Добавляем информацию о действии
                })
            
            # Сортируем похожие правила по количеству общих частей (по убыванию)
            rule.similar_rules.sort(key=lambda x: len(x["common_parts"]), reverse=True)

    @app.route('/classification_rules')
    def classification_rules():
        page = request.args.get('page', 1, type=int)
        per_page = 50  # Количество правил на странице
        
        # Получаем правила с пагинацией
        pagination = TransferRule.query.filter(TransferRule.priznak_value.isnot(None)).order_by(TransferRule.priority).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        rules = pagination.items
        total_pages = pagination.pages
        
        logging.info(f"[СТРАНИЦА] Загружено {len(rules)} правил классификации из {pagination.total}")
        
        return render_template(
            'classification_rules.html',
            rules=rules,
            page=page,
            total_pages=total_pages
        )
    
    @app.route('/api/transfer_rules', methods=['POST'])
    def create_transfer_rule():
        try:
            data = request.json
            
            # Проверяем обязательные поля
            required_fields = ['priority', 'category_name', 'transfer_action', 'condition_type', 'condition_field', 'condition_value']
            for field in required_fields:
                if field not in data or not data[field]:
                    return jsonify({'success': False, 'error': f'Поле {field} обязательно'}), 400
            
            # Если создается правило не с типом ALWAYS_TRUE, проверяем, что его приоритет не конфликтует с ALWAYS_TRUE
            if data['condition_type'] != 'ALWAYS_TRUE':
                # Получаем минимальный приоритет правил с типом ALWAYS_TRUE
                min_always_true_priority = db.session.query(func.min(TransferRule.priority)).filter(
                    TransferRule.condition_type == 'ALWAYS_TRUE'
                ).scalar()
                
                # Если есть правила ALWAYS_TRUE и приоритет нового правила больше или равен минимальному приоритету ALWAYS_TRUE,
                # то сдвигаем все правила ALWAYS_TRUE и с большим приоритетом на +10
                if min_always_true_priority and int(data['priority']) >= min_always_true_priority:
                    # Получаем все правила с приоритетом >= min_always_true_priority
                    rules_to_update = TransferRule.query.filter(
                        TransferRule.priority >= min_always_true_priority
                    ).all()
                    
                    # Увеличиваем приоритет каждого правила на 10
                    for rule in rules_to_update:
                        rule.priority += 10
                    
                    db.session.commit()
            
            # Создаем новое правило
            rule = TransferRule(
                priority=data['priority'],
                category_name=data['category_name'],
                transfer_action=data['transfer_action'],
                condition_type=data['condition_type'],
                condition_field=data['condition_field'],
                condition_value=data['condition_value'],
                comment=data.get('comment', '')
            )
            
            db.session.add(rule)
            db.session.commit()
            
            return jsonify({'success': True, 'rule_id': rule.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/transfer_rules/<int:rule_id>', methods=['GET'])
    def get_transfer_rule(rule_id):
        try:
            rule = TransferRule.query.get(rule_id)
            if not rule:
                return jsonify({'success': False, 'error': 'Правило не найдено'}), 404
            
            return jsonify({
                'success': True,
                'rule': {
                    'id': rule.id,
                    'priority': rule.priority,
                    'category_name': rule.category_name,
                    'transfer_action': rule.transfer_action,
                    'condition_type': rule.condition_type,
                    'condition_field': rule.condition_field,
                    'condition_value': rule.condition_value,
                    'comment': rule.comment
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/transfer_rules/<int:rule_id>', methods=['PUT'])
    def update_transfer_rule(rule_id):
        try:
            rule = TransferRule.query.get(rule_id)
            if not rule:
                return jsonify({'success': False, 'error': 'Правило не найдено'}), 404
            
            data = request.json
            
            # Проверяем, изменился ли приоритет и не является ли правило типа ALWAYS_TRUE
            old_priority = rule.priority
            new_priority = data.get('priority', old_priority)
            new_condition_type = data.get('condition_type', rule.condition_type)
            
            # Если изменился приоритет и новый тип условия не ALWAYS_TRUE
            if int(new_priority) != old_priority and new_condition_type != 'ALWAYS_TRUE':
                # Получаем минимальный приоритет правил с типом ALWAYS_TRUE
                min_always_true_priority = db.session.query(func.min(TransferRule.priority)).filter(
                    TransferRule.condition_type == 'ALWAYS_TRUE'
                ).scalar()
                
                # Если есть правила ALWAYS_TRUE и новый приоритет больше или равен минимальному приоритету ALWAYS_TRUE,
                # то сдвигаем все правила ALWAYS_TRUE и с большим приоритетом на +10
                if min_always_true_priority and int(new_priority) >= min_always_true_priority:
                    # Получаем все правила с приоритетом >= min_always_true_priority
                    rules_to_update = TransferRule.query.filter(
                        TransferRule.priority >= min_always_true_priority
                    ).all()
                    
                    # Увеличиваем приоритет каждого правила на 10
                    for r in rules_to_update:
                        r.priority += 10
                    
                    db.session.commit()
            
            # Обновляем поля правила
            rule.priority = new_priority
            rule.category_name = data.get('category_name', rule.category_name)
            rule.transfer_action = data.get('transfer_action', rule.transfer_action)
            rule.condition_type = new_condition_type
            rule.condition_field = data.get('condition_field', rule.condition_field)
            rule.condition_value = data.get('condition_value', rule.condition_value)
            rule.comment = data.get('comment', rule.comment)
            
            db.session.commit()
            
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/transfer_rules/<int:rule_id>', methods=['DELETE'])
    def delete_transfer_rule(rule_id):
        try:
            rule = TransferRule.query.get(rule_id)
            if not rule:
                return jsonify({'success': False, 'error': 'Правило не найдено'}), 404
            
            db.session.delete(rule)
            db.session.commit()
            
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/apply_transfer_rules/<batch_id>', methods=['POST'])
    def apply_transfer_rules_batch(batch_id):
        """
        Применяет правила переноса к записям из указанного батча.
        
        Важно: Записи с пустыми значениями MSSQL_SXCLASS_MAP обрабатываются правилом с типом IS_EMPTY,
        поэтому мы не исключаем их из обработки.
        """
        try:
            logging.info(f"[API] Запрос на применение правил переноса для батча {batch_id}")
            
            # Получаем записи из указанного батча, которые соответствуют фильтру "Не найдено в исторических данных"
            # В интерфейсе этот фильтр соответствует записям, у которых:
            # 1. Нет соответствий в исторических данных (matched_historical_data is None)
            # 2. Статус 'pending' (не проанализировано)
            
            # Сначала получаем ID записей из AnalysisResult, которые соответствуют фильтру "Не найдено в исторических данных"
            analysis_results = AnalysisResult.query.filter(
                AnalysisResult.batch_id == batch_id,
                AnalysisResult.status == 'pending',
                AnalysisResult.discrepancies.is_(None)
            ).all()
            
            logging.info(f"[API] Найдено {len(analysis_results)} записей в AnalysisResult, соответствующих фильтру 'Не найдено в исторических данных'")
            
            if not analysis_results:
                logging.warning(f"[API] Не найдено записей для применения правил в батче {batch_id}")
                return jsonify({
                    'success': False, 
                    'error': 'Не найдено записей для применения правил или все записи уже имеют соответствия в исторических данных'
                }), 400
            
            # Получаем имена классов из результатов анализа
            class_names = [result.mssql_sxclass_name for result in analysis_results]
            
            # Получаем соответствующие записи из AnalysisData
            records = AnalysisData.query.filter(
                AnalysisData.batch_id == batch_id,
                AnalysisData.mssql_sxclass_name.in_(class_names),
                AnalysisData.matched_historical_data.is_(None)
            ).all()
            
            logging.info(f"[API] Найдено {len(records)} соответствующих записей в AnalysisData")
            
            if not records:
                logging.warning(f"[API] Не найдено соответствующих записей в AnalysisData для батча {batch_id}")
                return jsonify({
                    'success': False, 
                    'error': 'Не найдено записей для применения правил'
                }), 400
            
            processed_count = 0
            updated_class_names = []
            
            # Статистика по причинам необработки записей
            unprocessed_stats = {
                'no_matching_rule': 0,  # Нет подходящего правила
                'empty_field_values': {},  # Пустые значения полей
                'processed': 0  # Успешно обработано
            }
            
            # Список необработанных записей с причинами
            unprocessed_records = []
            
            for record in records:
                logging.info(f"[API] Обработка записи: {record.mssql_sxclass_name}")
                
                # Проверяем наличие значений в ключевых полях перед применением правил
                empty_fields = []
                if not record.mssql_sxclass_name:
                    empty_fields.append('MSSQL_SXCLASS_NAME')
                if not record.mssql_sxclass_description:
                    empty_fields.append('MSSQL_SXCLASS_DESCRIPTION')
                # Удаляем проверку на пустое значение MSSQL_SXCLASS_MAP
                # if not record.mssql_sxclass_map:
                #     empty_fields.append('MSSQL_SXCLASS_MAP')
                
                # Если есть пустые поля (кроме MSSQL_SXCLASS_MAP), добавляем их в статистику
                if empty_fields:
                    for field in empty_fields:
                        unprocessed_stats['empty_field_values'][field] = unprocessed_stats['empty_field_values'].get(field, 0) + 1
                    
                    # Добавляем запись в список необработанных с причиной
                    unprocessed_records.append({
                        'class_name': record.mssql_sxclass_name or 'Нет имени класса',
                        'reason': f"Пустые значения полей: {', '.join(empty_fields)}"
                    })
                    continue
                
                # Применяем правила переноса
                result = apply_transfer_rules(record)
                
                if result['priznak']:
                    logging.info(f"[API] Установлен признак '{result['priznak']}' для {record.mssql_sxclass_name}")
                    # Обновляем запись с результатом применения правил
                    record.priznak = result['priznak']
                    record.confidence_score = result['confidence']
                    record.classified_by = 'transfer_rule'
                    record.rule_info = json.dumps({
                        'rule_id': result['rule_id'],
                        'category': result['category'],
                        'transfer_action': result['transfer_action']
                    })
                    # Обновляем статус на "проанализировано"
                    record.analysis_state = 'analyzed'
                    processed_count += 1
                    updated_class_names.append(record.mssql_sxclass_name)
                    unprocessed_stats['processed'] += 1
                else:
                    logging.info(f"[API] Не найдено подходящих правил для {record.mssql_sxclass_name}")
                    unprocessed_stats['no_matching_rule'] += 1
                    
                    # Добавляем запись в список необработанных с причиной
                    unprocessed_records.append({
                        'class_name': record.mssql_sxclass_name,
                        'reason': 'Нет подходящего правила переноса'
                    })
            
            # Обновляем соответствующие записи в AnalysisResult
            if updated_class_names:
                for result in analysis_results:
                    if result.mssql_sxclass_name in updated_class_names:
                        # Находим соответствующую запись в AnalysisData
                        analysis_data = next((r for r in records if r.mssql_sxclass_name == result.mssql_sxclass_name), None)
                        if analysis_data and analysis_data.priznak:
                            result.priznak = analysis_data.priznak
                            result.confidence_score = analysis_data.confidence_score
                            result.analyzed_by = 'transfer_rule'
                            result.status = 'analyzed'
            
            db.session.commit()
            logging.info(f"[API] Правила применены к {processed_count} из {len(records)} записей")
            
            # Формируем статистику для отображения пользователю
            total_records = len(records)
            unprocessed_count = total_records - processed_count
            
            # Формируем сообщение с детальной статистикой
            message = f'Правила применены к {processed_count} из {total_records} записей.'
            
            if unprocessed_count > 0:
                message += f'\n\nНе обработано: {unprocessed_count} записей.'
                
                if unprocessed_stats['no_matching_rule'] > 0:
                    message += f'\n- {unprocessed_stats["no_matching_rule"]} записей не имеют подходящих правил переноса.'
                
                if unprocessed_stats['empty_field_values']:
                    message += '\n- Записи с пустыми значениями полей:'
                    for field, count in unprocessed_stats['empty_field_values'].items():
                        message += f'\n  • {field}: {count} записей'
                
                # Добавляем примеры необработанных записей (максимум 5)
                if unprocessed_records:
                    examples = unprocessed_records[:5]
                    message += '\n\nПримеры необработанных записей:'
                    for i, example in enumerate(examples, 1):
                        message += f'\n{i}. {example["class_name"]} - {example["reason"]}'
                    
                    if len(unprocessed_records) > 5:
                        message += f'\n... и еще {len(unprocessed_records) - 5} записей'
            
            return jsonify({
                'success': True,
                'message': message,
                'statistics': {
                    'total': total_records,
                    'processed': processed_count,
                    'unprocessed': unprocessed_count,
                    'unprocessed_stats': unprocessed_stats,
                    'unprocessed_examples': unprocessed_records[:5] if unprocessed_records else []
                }
            })
        except Exception as e:
            db.session.rollback()
            logging.error(f"[API] Ошибка при применении правил: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500 

    @app.route('/api/classification_rules', methods=['POST'])
    def create_classification_rule():
        """
        Создает новое правило классификации на основе переданных данных.
        """
        try:
            data = request.json
            logging.info(f"[API] Получены данные для создания правила: {data}")
            
            # Проверяем обязательные поля
            required_fields = ['pattern', 'field', 'priznak_value', 'condition_type', 'category_name']
            for field in required_fields:
                if field not in data or not data[field]:
                    logging.error(f"[API] Отсутствует обязательное поле: {field}")
                    return jsonify({'success': False, 'error': f'Поле {field} обязательно'}), 400
            
            # Если приоритет не указан, вычисляем его
            if 'priority' not in data or not data['priority']:
                # Получаем минимальный приоритет правил с типом ALWAYS_TRUE
                min_always_true_priority = db.session.query(func.min(TransferRule.priority)).filter(
                    TransferRule.condition_type == 'ALWAYS_TRUE'
                ).scalar()
                
                if min_always_true_priority:
                    # Находим максимальный приоритет среди правил с приоритетом меньше, чем у ALWAYS_TRUE
                    max_priority_before_always_true = db.session.query(func.max(TransferRule.priority)).filter(
                        TransferRule.priority < min_always_true_priority
                    ).scalar() or 0
                    
                    # Следующий приоритет = максимальный приоритет до ALWAYS_TRUE + 10
                    priority = max_priority_before_always_true + 10
                    
                    # Проверяем, что новый приоритет не превышает минимальный приоритет ALWAYS_TRUE
                    if priority >= min_always_true_priority:
                        priority = min_always_true_priority - 10
                else:
                    # Если нет правил ALWAYS_TRUE, просто берем максимальный приоритет + 10
                    max_priority = db.session.query(func.max(TransferRule.priority)).scalar() or 0
                    priority = max_priority + 10
                
                logging.info(f"[API] Установлен приоритет: {priority}")
            else:
                priority = data['priority']
            
            # Если создается правило не с типом ALWAYS_TRUE, проверяем, что его приоритет не конфликтует с ALWAYS_TRUE
            if data['condition_type'] != 'ALWAYS_TRUE':
                # Получаем минимальный приоритет правил с типом ALWAYS_TRUE
                min_always_true_priority = db.session.query(func.min(TransferRule.priority)).filter(
                    TransferRule.condition_type == 'ALWAYS_TRUE'
                ).scalar()
                
                # Если есть правила ALWAYS_TRUE и приоритет нового правила больше или равен минимальному приоритету ALWAYS_TRUE,
                # то сдвигаем все правила ALWAYS_TRUE и с большим приоритетом на +10
                if min_always_true_priority and int(priority) >= min_always_true_priority:
                    # Получаем все правила с приоритетом >= min_always_true_priority
                    rules_to_update = TransferRule.query.filter(
                        TransferRule.priority >= min_always_true_priority
                    ).all()
                    
                    # Увеличиваем приоритет каждого правила на 10
                    for rule in rules_to_update:
                        rule.priority += 10
                    
                    db.session.commit()
            
            # Создаем новое правило
            rule = TransferRule(
                priority=priority,
                category_name=data['category_name'],
                transfer_action=data.get('transfer_action', 'Переносим'),
                condition_type=data['condition_type'],
                condition_field=data['field'],
                condition_value=data['pattern'],
                comment=data.get('comment', ''),
                confidence_threshold=data.get('confidence_threshold', 0.8),
                source_batch_id=data.get('source_batch_id'),
                priznak_value=data['priznak_value']
            )
            
            logging.info(f"[API] Создаем правило: {rule.condition_value}, {rule.condition_field}, {rule.priznak_value}")
            db.session.add(rule)
            db.session.commit()
            logging.info(f"[API] Правило успешно создано с ID: {rule.id}")
            
            return jsonify({
                'success': True, 
                'rule_id': rule.id,
                'message': 'Правило классификации успешно создано'
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при создании правила классификации: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
            
    @app.route('/api/classification_rules/<int:rule_id>', methods=['GET'])
    def get_classification_rule(rule_id):
        try:
            rule = TransferRule.query.get(rule_id)
            if not rule:
                return jsonify({'success': False, 'error': 'Правило не найдено'}), 404
            
            rule_data = {
                'id': rule.id,
                'priority': rule.priority,
                'field': rule.condition_field,
                'pattern': rule.condition_value,
                'priznak_value': rule.priznak_value,
                'confidence_threshold': rule.confidence_threshold,
                'category_name': rule.category_name,
                'condition_type': rule.condition_type,
                'transfer_action': rule.transfer_action,
                'comment': rule.comment
            }
            
            return jsonify({'success': True, 'rule': rule_data})
        except Exception as e:
            app.logger.error(f"Ошибка при получении правила классификации: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
            
    @app.route('/api/classification_rules/<int:rule_id>', methods=['PUT'])
    def update_classification_rule(rule_id):
        try:
            rule = TransferRule.query.get(rule_id)
            if not rule:
                return jsonify({'success': False, 'error': 'Правило не найдено'}), 404
            
            data = request.get_json()
            
            # Проверяем, изменился ли приоритет и не является ли правило типа ALWAYS_TRUE
            old_priority = rule.priority
            new_priority = data.get('priority', old_priority)
            new_condition_type = data.get('condition_type', rule.condition_type)
            
            # Если изменился приоритет и новый тип условия не ALWAYS_TRUE
            if int(new_priority) != old_priority and new_condition_type != 'ALWAYS_TRUE':
                # Получаем минимальный приоритет правил с типом ALWAYS_TRUE
                min_always_true_priority = db.session.query(func.min(TransferRule.priority)).filter(
                    TransferRule.condition_type == 'ALWAYS_TRUE'
                ).scalar()
                
                # Если есть правила ALWAYS_TRUE и новый приоритет больше или равен минимальному приоритету ALWAYS_TRUE,
                # то сдвигаем все правила ALWAYS_TRUE и с большим приоритетом на +10
                if min_always_true_priority and int(new_priority) >= min_always_true_priority:
                    # Получаем все правила с приоритетом >= min_always_true_priority
                    rules_to_update = TransferRule.query.filter(
                        TransferRule.priority >= min_always_true_priority
                    ).all()
                    
                    # Увеличиваем приоритет каждого правила на 10
                    for r in rules_to_update:
                        r.priority += 10
                    
                    db.session.commit()
            
            # Обновляем поля правила
            rule.priority = new_priority
            rule.condition_field = data.get('field', rule.condition_field)
            rule.condition_value = data.get('pattern', rule.condition_value)
            rule.priznak_value = data.get('priznak_value', rule.priznak_value)
            rule.confidence_threshold = data.get('confidence_threshold', rule.confidence_threshold)
            rule.category_name = data.get('category_name', rule.category_name)
            rule.condition_type = new_condition_type
            rule.transfer_action = data.get('transfer_action', rule.transfer_action)
            rule.comment = data.get('comment', rule.comment)
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': 'Правило классификации успешно обновлено',
                'rule_id': rule.id
            })
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Ошибка при обновлении правила классификации: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
      
    @app.route('/api/classification_rules/<int:rule_id>', methods=['DELETE'])
    def delete_classification_rule(rule_id):            
        try:
            rule = TransferRule.query.get(rule_id)
            if not rule:
                return jsonify({'success': False, 'error': 'Правило не найдено'}), 404
            
            db.session.delete(rule)
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': 'Правило классификации успешно удалено',
                'rule_id': rule.id
            })
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Ошибка при удалении правила классификации: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500
            
    @app.route('/api/get_max_priority', methods=['GET'])
    def get_max_priority():
        """
        Возвращает максимальный приоритет из существующих правил классификации.
        Учитывает правила с типом ALWAYS_TRUE, чтобы новые правила имели приоритет ниже них.
        """
        try:
            # Получаем минимальный приоритет правил с типом ALWAYS_TRUE
            min_always_true_priority = db.session.query(func.min(TransferRule.priority)).filter(
                TransferRule.condition_type == 'ALWAYS_TRUE'
            ).scalar()
            
            if min_always_true_priority:
                # Находим максимальный приоритет среди правил с приоритетом меньше, чем у ALWAYS_TRUE
                max_priority_before_always_true = db.session.query(func.max(TransferRule.priority)).filter(
                    TransferRule.priority < min_always_true_priority
                ).scalar() or 0
                
                # Следующий приоритет = максимальный приоритет до ALWAYS_TRUE + 10
                next_priority = max_priority_before_always_true + 10
                
                # Проверяем, что новый приоритет не превышает минимальный приоритет ALWAYS_TRUE
                if next_priority >= min_always_true_priority:
                    next_priority = min_always_true_priority - 10
            else:
                # Если нет правил ALWAYS_TRUE, просто берем максимальный приоритет + 10
                max_priority = db.session.query(func.max(TransferRule.priority)).scalar() or 0
                next_priority = max_priority + 10
            
            return jsonify({
                'success': True,
                'max_priority': max_priority_before_always_true if min_always_true_priority else (db.session.query(func.max(TransferRule.priority)).scalar() or 0),
                'next_priority': next_priority,
                'min_always_true_priority': min_always_true_priority
            })
            
        except Exception as e:
            logging.error(f"Ошибка при получении максимального приоритета: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
            
    @app.route('/api/get_max_transfer_rule_priority', methods=['GET'])
    def get_max_transfer_rule_priority():
        """
        Возвращает максимальный приоритет из существующих правил переноса.
        Учитывает правила с типом ALWAYS_TRUE, чтобы новые правила имели приоритет ниже них.
        """
        try:
            # Получаем минимальный приоритет правил с типом ALWAYS_TRUE
            min_always_true_priority = db.session.query(func.min(TransferRule.priority)).filter(
                TransferRule.condition_type == 'ALWAYS_TRUE'
            ).scalar()
            
            if min_always_true_priority:
                # Находим максимальный приоритет среди правил с приоритетом меньше, чем у ALWAYS_TRUE
                max_priority_before_always_true = db.session.query(func.max(TransferRule.priority)).filter(
                    TransferRule.priority < min_always_true_priority
                ).scalar() or 0
                
                # Следующий приоритет = максимальный приоритет до ALWAYS_TRUE + 10
                next_priority = max_priority_before_always_true + 10
                
                # Проверяем, что новый приоритет не превышает минимальный приоритет ALWAYS_TRUE
                if next_priority >= min_always_true_priority:
                    next_priority = min_always_true_priority - 10
            else:
                # Если нет правил ALWAYS_TRUE, просто берем максимальный приоритет + 10
                max_priority = db.session.query(func.max(TransferRule.priority)).scalar() or 0
                next_priority = max_priority + 10
            
            return jsonify({
                'success': True,
                'max_priority': max_priority_before_always_true if min_always_true_priority else (db.session.query(func.max(TransferRule.priority)).scalar() or 0),
                'next_priority': next_priority,
                'min_always_true_priority': min_always_true_priority
            })
            
        except Exception as e:
            logging.error(f"Ошибка при получении максимального приоритета правил переноса: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/export_analysis/<batch_id>', methods=['GET'])
    def export_analysis(batch_id):
        try:
            # Получаем данные анализа
            analysis_data = AnalysisData.query.filter_by(batch_id=batch_id).all()
            analysis_results = AnalysisResult.query.filter_by(batch_id=batch_id).all()
            
            if not analysis_data or not analysis_results:
                return jsonify({"success": False, "error": "Данные не найдены"}), 404

            # Создаем словарь для быстрого доступа к результатам анализа по имени класса
            results_dict = {r.mssql_sxclass_name: r.priznak for r in analysis_results}

            # Создаем файл Excel в памяти
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet()

            # Заголовки в точном соответствии с требуемым порядком
            headers = [
                ('a_ouid', 'A_OUID'),
                ('mssql_sxclass_description', 'MSSQL_SXCLASS_DESCRIPTION'),
                ('mssql_sxclass_name', 'MSSQL_SXCLASS_NAME'),
                ('mssql_sxclass_map', 'MSSQL_SXCLASS_MAP'),
                ('priznak', 'priznak'),
                ('system_class', 'Системный класс'),
                ('is_link_table', 'Используется как таблица связи'),
                ('parent_class', 'Родительский класс'),
                ('child_classes', 'Дочерние классы'),
                ('child_count', 'Количество дочерних классов'),
                ('created_date', 'Дата создания'),
                ('created_by', 'Создал'),
                ('modified_date', 'Дата изменения'),
                ('modified_by', 'Изменил'),
                ('folder_paths', 'Пути папок в консоли'),
                ('attribute_count', 'Наличие объектов'),
                ('object_count', 'Количество объектов'),
                ('last_object_created', 'Дата создания последнего объекта'),
                ('last_object_modified', 'Дата последнего изменения'),
                ('category', 'Категория (итог)'),
                ('migration_flag', 'Признак миграции (итог)'),
                ('rule_info', 'Rule Info (какое правило сработало)')
            ]

            # Форматирование
            header_format = workbook.add_format({
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#D3D3D3'
            })

            # Записываем заголовки на второй строке (индекс 1)
            for col, (field, header) in enumerate(headers):
                worksheet.write(1, col, header, header_format)
                worksheet.set_column(col, col, 20)

            # Записываем данные начиная с третьей строки (индекс 2)
            for row_idx, record in enumerate(analysis_data, start=2):
                data = [
                    record.a_ouid,
                    record.mssql_sxclass_description,
                    record.mssql_sxclass_name,
                    record.mssql_sxclass_map,
                    results_dict.get(record.mssql_sxclass_name, ''),  # Получаем priznak из результатов анализа
                    record.system_class,
                    record.is_link_table,
                    record.parent_class,
                    record.child_classes,
                    record.child_count,
                    record.created_date,
                    record.created_by,
                    record.modified_date,
                    record.modified_by,
                    record.folder_paths,
                    record.attribute_count,
                    record.object_count,
                    record.last_object_created,
                    record.last_object_modified,
                    record.category,
                    record.migration_flag,
                    record.rule_info
                ]

                for col, value in enumerate(data):
                    worksheet.write(row_idx, col, str(value) if value is not None else '')

            workbook.close()
            output.seek(0)

            # Получаем имя файла из первой записи
            filename = f"{analysis_data[0].file_name}_проанализировано.xlsx" if analysis_data else "analysis_export.xlsx"
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )

        except Exception as e:
            logging.error(f"Ошибка при экспорте в Excel: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/get_available_sources', methods=['GET'])
    def get_available_sources():
        """
        Получает список доступных источников для копирования признаков
        """
        try:
            current_batch_id = request.args.get('current_batch_id')
            if not current_batch_id:
                return jsonify({'success': False, 'error': 'Не указан текущий batch_id'}), 400
                
            # Получаем исторические источники
            historical_sources = db.session.query(
                MigrationClass.batch_id,
                MigrationClass.source_system,
                MigrationClass.file_name,
                func.count(MigrationClass.id).label('records_count'),
                func.min(MigrationClass.upload_date).label('upload_date')
            ).group_by(
                MigrationClass.batch_id,
                MigrationClass.source_system,
                MigrationClass.file_name
            ).all()
            
            # Получаем источники анализа (кроме текущего)
            analysis_sources = db.session.query(
                AnalysisData.batch_id,
                AnalysisData.source_system,
                AnalysisData.file_name,
                func.count(AnalysisData.id).label('records_count'),
                func.min(AnalysisData.upload_date).label('upload_date')
            ).filter(
                AnalysisData.batch_id != current_batch_id
            ).group_by(
                AnalysisData.batch_id,
                AnalysisData.source_system,
                AnalysisData.file_name
            ).all()
            
            # Форматируем результат
            sources = {
                'historical': [{
                    'batch_id': src.batch_id,
                    'source_system': src.source_system,
                    'file_name': src.file_name,
                    'records_count': src.records_count,
                    'upload_date': src.upload_date.isoformat() if src.upload_date else None,
                    'type': 'historical'
                } for src in historical_sources],
                'analysis': [{
                    'batch_id': src.batch_id,
                    'source_system': src.source_system,
                    'file_name': src.file_name,
                    'records_count': src.records_count,
                    'upload_date': src.upload_date.isoformat() if src.upload_date else None,
                    'type': 'analysis'
                } for src in analysis_sources]
            }
            
            return jsonify({'success': True, 'sources': sources})
            
        except Exception as e:
            logging.error(f"Ошибка при получении списка источников: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/copy_priznaks_from_source', methods=['POST'])
    def copy_priznaks_from_source():
        """
        Копирует признаки из выбранного источника с учетом фильтров
        """
        try:
            data = request.json
            current_batch_id = data.get('current_batch_id')
            source_batch_id = data.get('source_batch_id')
            source_type = data.get('source_type')  # 'historical' или 'analysis'
            filters = data.get('filters', {})  # текущие примененные фильтры
            
            if not all([current_batch_id, source_batch_id, source_type]):
                return jsonify({'success': False, 'error': 'Не все параметры указаны'}), 400
                
            # Получаем записи из текущего батча с учетом фильтров
            query = AnalysisResult.query.filter_by(batch_id=current_batch_id)
            
            # Применяем фильтры
            status_filter = filters.get('status')
            discrepancy_filter = filters.get('discrepancy_filter')
            card_filter = filters.get('card_filter')
            search = filters.get('search')
            
            if status_filter:
                if status_filter == 'no_matches':
                    query = query.filter(AnalysisResult.status == 'pending', 
                                      AnalysisResult.discrepancies.is_(None))
                elif status_filter == 'discrepancies':
                    query = query.filter(AnalysisResult.status == 'pending', 
                                      AnalysisResult.discrepancies.isnot(None))
                else:
                    query = query.filter(AnalysisResult.status == status_filter)
            
            if search:
                query = query.filter(AnalysisResult.mssql_sxclass_name.ilike(f'%{search}%'))
            
            # Получаем все результаты для дальнейшей фильтрации
            current_results = query.all()
            filtered_results = current_results
            
            # Применяем фильтр по расхождениям
            if discrepancy_filter:
                filtered_results = [
                    result for result in filtered_results
                    if result.discrepancies and str(result.discrepancies) == discrepancy_filter
                ]
            
            # Применяем фильтр по карточке
            if card_filter:
                try:
                    card_data = json.loads(card_filter)
                    sources = card_data.get('sources', [])
                    priznaks = card_data.get('priznaks', [])
                    
                    filtered_results = [
                        result for result in filtered_results
                        if result.discrepancies and any(
                            db.session.query(MigrationClass.source_system).filter_by(
                                batch_id=batch_id
                            ).first()[0] in sources and priznak in priznaks
                            for batch_id, priznak in result.discrepancies.items()
                        )
                    ]
                except Exception as e:
                    logging.error(f"Ошибка при применении фильтра по карточке: {str(e)}")
            
            # Получаем признаки из источника
            if source_type == 'historical':
                source_records = db.session.query(
                    MigrationClass.mssql_sxclass_name,
                    MigrationClass.priznak
                ).filter(
                    MigrationClass.batch_id == source_batch_id,
                    MigrationClass.priznak.isnot(None)
                ).all()
            else:
                source_records = db.session.query(
                    AnalysisData.mssql_sxclass_name,
                    AnalysisData.priznak
                ).filter(
                    AnalysisData.batch_id == source_batch_id,
                    AnalysisData.priznak.isnot(None)
                ).all()
            
            # Создаем словарь признаков из источника
            source_priznaks = {r.mssql_sxclass_name: r.priznak for r in source_records}
            
            # Обновляем признаки в текущем батче
            updated_count = 0
            not_found_count = 0
            for result in filtered_results:
                if result.mssql_sxclass_name in source_priznaks:
                    # Обновляем признак в AnalysisResult
                    result.priznak = source_priznaks[result.mssql_sxclass_name]
                    result.status = 'analyzed'
                    result.analyzed_by = f'copied_from_{source_type}'
                    result.confidence_score = 1.0
                    
                    # Обновляем признак в AnalysisData
                    analysis_data = AnalysisData.query.filter_by(
                        batch_id=current_batch_id,
                        mssql_sxclass_name=result.mssql_sxclass_name
                    ).first()
                    
                    if analysis_data:
                        analysis_data.priznak = source_priznaks[result.mssql_sxclass_name]
                        analysis_data.analysis_state = 'analyzed'
                    
                    updated_count += 1
                else:
                    not_found_count += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Обновлено {updated_count} записей. Не найдено соответствий для {not_found_count} записей.',
                'updated_count': updated_count,
                'not_found_count': not_found_count
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при копировании признаков: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    # Новая функция для экспорта всех данных анализа
    @app.route('/export_all_analysis', methods=['GET'])
    def export_all_analysis():
        try:
            # Получаем все наборы данных анализа
            all_analysis_data = AnalysisData.query.all()
            all_analysis_results = AnalysisResult.query.all()
            
            if not all_analysis_data or not all_analysis_results:
                return jsonify({"success": False, "error": "Данные не найдены"}), 404

            # Создаем словарь для быстрого доступа к результатам анализа по имени класса
            results_dict = {r.mssql_sxclass_name: r.priznak for r in all_analysis_results}

            # Создаем словарь для группировки записей по batch_id
            batch_groups = {}
            
            # Словарь для хранения имен файлов по batch_id
            batch_file_names = {}
            
            for record in all_analysis_data:
                if record.batch_id not in batch_groups:
                    batch_groups[record.batch_id] = []
                    # Сохраняем имя файла для данного batch_id
                    batch_file_names[record.batch_id] = record.file_name
                batch_groups[record.batch_id].append(record)

            # Создаем файл Excel в памяти
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output)

            # Заголовки в точном соответствии с требуемым порядком
            headers = [
                ('file_name', 'Имя файла'),
                ('a_ouid', 'A_OUID'),
                ('mssql_sxclass_description', 'MSSQL_SXCLASS_DESCRIPTION'),
                ('mssql_sxclass_name', 'MSSQL_SXCLASS_NAME'),
                ('mssql_sxclass_map', 'MSSQL_SXCLASS_MAP'),
                ('priznak', 'priznak'),
                ('system_class', 'Системный класс'),
                ('is_link_table', 'Используется как таблица связи'),
                ('parent_class', 'Родительский класс'),
                ('child_classes', 'Дочерние классы'),
                ('child_count', 'Количество дочерних классов'),
                ('created_date', 'Дата создания'),
                ('created_by', 'Создал'),
                ('modified_date', 'Дата изменения'),
                ('modified_by', 'Изменил'),
                ('folder_paths', 'Пути папок в консоли'),
                ('attribute_count', 'Наличие объектов'),
                ('object_count', 'Количество объектов'),
                ('last_object_created', 'Дата создания последнего объекта'),
                ('last_object_modified', 'Дата последнего изменения'),
                ('category', 'Категория (итог)'),
                ('migration_flag', 'Признак миграции (итог)'),
                ('rule_info', 'Rule Info (какое правило сработало)')
            ]

            # Создаем форматы
            header_format = workbook.add_format({
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#D3D3D3'
            })
            
            batch_header_format = workbook.add_format({
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 14,
                'bg_color': '#4472C4',
                'font_color': 'white'
            })

            # Создаем общий лист со всеми данными
            all_data_sheet = workbook.add_worksheet('Все данные')
            
            # Записываем заголовки
            for col, (field, header) in enumerate(headers):
                all_data_sheet.write(0, col, header, header_format)
                all_data_sheet.set_column(col, col, 20)
                
            # Записываем все данные на общем листе
            row_idx = 1
            for batch_id, records in batch_groups.items():
                file_name = batch_file_names.get(batch_id, f"Batch_{batch_id}")
                for record in records:
                    data = [
                        file_name,  # Используем имя файла вместо batch_id
                        record.a_ouid,
                        record.mssql_sxclass_description,
                        record.mssql_sxclass_name,
                        record.mssql_sxclass_map,
                        results_dict.get(record.mssql_sxclass_name, ''),  # Получаем priznak из результатов анализа
                        record.system_class,
                        record.is_link_table,
                        record.parent_class,
                        record.child_classes,
                        record.child_count,
                        record.created_date,
                        record.created_by,
                        record.modified_date,
                        record.modified_by,
                        record.folder_paths,
                        record.attribute_count,
                        record.object_count,
                        record.last_object_created,
                        record.last_object_modified,
                        record.category,
                        record.migration_flag,
                        record.rule_info
                    ]

                    for col, value in enumerate(data):
                        all_data_sheet.write(row_idx, col, str(value) if value is not None else '')
                    row_idx += 1

            # Также создаем отдельные листы для каждого батча
            for batch_id, records in batch_groups.items():
                file_name = batch_file_names.get(batch_id, f"Batch_{batch_id}")
                # Ограничиваем имя листа до 31 символа (ограничение Excel)
                sheet_name = file_name[:30] if len(file_name) > 30 else file_name
                worksheet = workbook.add_worksheet(sheet_name)
                
                # Добавляем заголовок файла
                worksheet.merge_range(0, 0, 0, len(headers) - 1, f'Файл: {file_name}', batch_header_format)
                
                # Записываем заголовки на второй строке (пропускаем file_name, т.к. это уже в заголовке)
                for col, (field, header) in enumerate(headers[1:], start=0):
                    worksheet.write(1, col, header, header_format)
                    worksheet.set_column(col, col, 20)
                
                # Записываем данные начиная с третьей строки
                for row_idx, record in enumerate(records, start=2):
                    data = [
                        record.a_ouid,
                        record.mssql_sxclass_description,
                        record.mssql_sxclass_name,
                        record.mssql_sxclass_map,
                        results_dict.get(record.mssql_sxclass_name, ''),  # Получаем priznak из результатов анализа
                        record.system_class,
                        record.is_link_table,
                        record.parent_class,
                        record.child_classes,
                        record.child_count,
                        record.created_date,
                        record.created_by,
                        record.modified_date,
                        record.modified_by,
                        record.folder_paths,
                        record.attribute_count,
                        record.object_count,
                        record.last_object_created,
                        record.last_object_modified,
                        record.category,
                        record.migration_flag,
                        record.rule_info
                    ]

                    for col, value in enumerate(data):
                        worksheet.write(row_idx, col, str(value) if value is not None else '')

            # Закрываем и возвращаем файл
            workbook.close()
            output.seek(0)
            
            current_date = datetime.now().strftime('%Y-%m-%d')
            filename = f"all_analysis_data_{current_date}.xlsx"
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )

        except Exception as e:
            logging.error(f"Ошибка при экспорте всех данных в Excel: {str(e)}", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/analyze_new_classes', methods=['GET'])
    def analyze_new_classes():
        """
        Автоматический анализ новых классов на основе исторических данных
        """
        try:
            # Получаем все новые записи для анализа
            new_records = AnalysisData.query.filter(
                AnalysisData.priznak.is_(None),
                AnalysisData.analysis_state == 'pending'
            ).all()
            
            if not new_records:
                flash('Нет новых записей для анализа.', 'warning')
                return redirect('/analyze')
            
            # Получаем исторические данные
            historical_records = MigrationClass.query.filter(
                MigrationClass.priznak.isnot(None)
            ).all()
            
            # Создаем индекс для быстрого поиска
            historical_index = {}
            for record in historical_records:
                if record.mssql_sxclass_name in historical_index:
                    historical_index[record.mssql_sxclass_name].append(record)
                else:
                    historical_index[record.mssql_sxclass_name] = [record]
            
            # Анализируем новые записи
            analyzed_count = 0
            matched_count = 0
            for record in new_records:
                if record.mssql_sxclass_name in historical_index:
                    # Находим соответствующие исторические записи
                    matches = historical_index[record.mssql_sxclass_name]
                    
                    # Проверяем совпадение priznaks
                    priznaks = {}
                    for match in matches:
                        if match.priznak:
                            if match.priznak in priznaks:
                                priznaks[match.priznak] += 1
                            else:
                                priznaks[match.priznak] = 1
                    
                    if priznaks:
                        # Находим наиболее часто встречающийся priznak
                        max_count = 0
                        max_priznak = None
                        for priznak, count in priznaks.items():
                            if count > max_count:
                                max_count = count
                                max_priznak = priznak
                        
                        # Устанавливаем priznak и обновляем статус
                        record.priznak = max_priznak
                        record.confidence_score = max_count / len(matches)
                        record.classified_by = 'historical'
                        record.analysis_state = 'analyzed'
                        matched_count += 1
                    
                    analyzed_count += 1
            
            # Сохраняем изменения
            db.session.commit()
            
            flash(f'Проанализировано {analyzed_count} записей, найдено соответствий: {matched_count}', 'success')
            return redirect('/analyze')
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при анализе новых классов: {str(e)}", exc_info=True)
            flash(f'Ошибка при анализе: {str(e)}', 'error')
            return redirect('/analyze')

    @app.route('/api/analyze_consistency', methods=['GET'])
    def analyze_consistency():
        """
        Анализ консистентности признаков между разными источниками данных
        """
        try:
            # Получаем список классов, которые встречаются в разных источниках
            multi_source_classes = db.session.query(
                MigrationClass.mssql_sxclass_name
            ).group_by(
                MigrationClass.mssql_sxclass_name
            ).having(
                func.count(func.distinct(MigrationClass.source_system)) > 1
            ).all()
            
            classes = [cls[0] for cls in multi_source_classes]
            
            # Анализируем консистентность признаков для каждого класса
            inconsistencies = []
            for class_name in classes:
                # Получаем все записи для данного класса
                class_records = MigrationClass.query.filter_by(
                    mssql_sxclass_name=class_name
                ).all()
                
                # Группируем по источникам и признакам
                source_priznaks = {}
                for record in class_records:
                    if record.source_system and record.priznak:
                        if record.source_system not in source_priznaks:
                            source_priznaks[record.source_system] = set()
                        source_priznaks[record.source_system].add(record.priznak)
                
                # Проверяем, есть ли несоответствия между источниками
                unique_priznaks = set()
                for priznaks in source_priznaks.values():
                    unique_priznaks.update(priznaks)
                
                if len(unique_priznaks) > 1:
                    # Есть несоответствие - разные признаки в разных источниках
                    # Проверяем, есть ли уже запись о расхождении
                    existing_disc = Discrepancy.query.filter_by(
                        class_name=class_name
                    ).first()
                    
                    if not existing_disc:
                        # Создаем новую запись о расхождении
                        description = db.session.query(
                            MigrationClass.mssql_sxclass_description
                        ).filter_by(
                            mssql_sxclass_name=class_name
                        ).first()
                        
                        discrepancy = Discrepancy(
                            class_name=class_name,
                            description=description[0] if description else "",
                            different_priznaks=list(unique_priznaks),
                            source_systems=list(source_priznaks.keys())
                        )
                        db.session.add(discrepancy)
                        inconsistencies.append(class_name)
            
            db.session.commit()
            
            message = f'Выполнен анализ консистентности. Найдено {len(inconsistencies)} новых несоответствий.'
            flash(message, 'success')
            return redirect('/analyze')
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при анализе консистентности: {str(e)}", exc_info=True)
            flash(f'Ошибка при анализе: {str(e)}', 'error')
            return redirect('/analyze')

    @app.route('/api/analyze_rules_efficiency', methods=['GET'])
    def analyze_rules_efficiency():
        """
        Анализ эффективности существующих правил классификации
        """
        try:
            # Получаем все правила переноса
            rules = TransferRule.query.all()
            
            # Получаем записи с установленными вручную признаками
            manual_records = MigrationClass.query.filter(
                MigrationClass.priznak.isnot(None),
                MigrationClass.classified_by == 'manual'
            ).all()
            
            # Статистика для правил
            rule_stats = {rule.id: {'matches': 0, 'mismatches': 0, 'rule': rule} for rule in rules}
            
            # Применяем правила к записям с ручной классификацией
            for record in manual_records:
                # Применяем правила по порядку
                for rule in rules:
                    result = apply_rule_to_record(rule, record)
                    if result:
                        if result == record.priznak:
                            rule_stats[rule.id]['matches'] += 1
                        else:
                            rule_stats[rule.id]['mismatches'] += 1
                        break
            
            # Сортируем правила по эффективности (процент совпадений)
            sorted_rules = []
            for rule_id, stats in rule_stats.items():
                total = stats['matches'] + stats['mismatches']
                if total > 0:
                    efficiency = (stats['matches'] / total) * 100
                    sorted_rules.append({
                        'rule_id': rule_id,
                        'rule': stats['rule'],
                        'matches': stats['matches'],
                        'mismatches': stats['mismatches'],
                        'total': total,
                        'efficiency': efficiency
                    })
            
            # Сортируем по эффективности (убывание)
            sorted_rules.sort(key=lambda x: x['efficiency'], reverse=True)
            
            # Сохраняем результаты в сессии для отображения
            session['rule_efficiency'] = [
                {
                    'id': r['rule_id'],
                    'category': r['rule'].category_name,
                    'action': r['rule'].transfer_action,
                    'condition_type': r['rule'].condition_type,
                    'condition_field': r['rule'].condition_field,
                    'condition_value': r['rule'].condition_value,
                    'efficiency': f"{r['efficiency']:.1f}%",
                    'matches': r['matches'],
                    'mismatches': r['mismatches'],
                    'total': r['total']
                } for r in sorted_rules if r['total'] > 0
            ]
            
            return redirect('/rules_efficiency')
            
        except Exception as e:
            logging.error(f"Ошибка при анализе эффективности правил: {str(e)}", exc_info=True)
            flash(f'Ошибка при анализе: {str(e)}', 'error')
            return redirect('/analyze')

    @app.route('/rules_efficiency')
    def rules_efficiency():
        """
        Страница с результатами анализа эффективности правил
        """
        rule_efficiency = session.get('rule_efficiency', [])
        return render_template('rules_efficiency.html', rules=rule_efficiency)

    @app.route('/api/record_details/<int:result_id>', methods=['GET'])
    def get_record_details(result_id):
        """
        API endpoint для получения детальной информации о записи результата анализа
        """
        try:
            logging.info(f"[API] Запрос детальной информации о записи с ID {result_id}")
            
            # Находим результат анализа
            analysis_result = AnalysisResult.query.get_or_404(result_id)
            logging.info(f"[API] Найден результат анализа: batch_id={analysis_result.batch_id}, class_name={analysis_result.mssql_sxclass_name}")
            
            # Находим исходные данные в таблице analysis_data по batch_id и имени класса
            record_data = AnalysisData.query.filter_by(
                batch_id=analysis_result.batch_id,
                mssql_sxclass_name=analysis_result.mssql_sxclass_name
            ).first()
            
            if not record_data:
                logging.warning(f"[API] Не найдены исходные данные для результата анализа: batch_id={analysis_result.batch_id}, class_name={analysis_result.mssql_sxclass_name}")
                
                # Если не найдены в analysis_data, попробуем найти в MigrationClass
                record_data = MigrationClass.query.filter_by(
                    mssql_sxclass_name=analysis_result.mssql_sxclass_name
                ).first()
                
                if not record_data:
                    logging.error(f"[API] Не найдены данные ни в таблице analysis_data, ни в таблице migration_classes")
                    return jsonify({
                        'success': False,
                        'error': 'Не найдены исходные данные для результата анализа'
                    }), 404
                
                logging.info(f"[API] Найдены данные в таблице migration_classes")
            else:
                logging.info(f"[API] Найдены данные в таблице analysis_data")
            
            # Собираем детальную информацию о записи
            details = {
                'mssql_sxclass_name': record_data.mssql_sxclass_name or 'Нет данных',
                'created_date': record_data.created_date or 'Нет данных',
                'created_by': record_data.created_by or 'Нет данных',
                'modified_date': record_data.modified_date or 'Нет данных',
                'modified_by': record_data.modified_by or 'Нет данных',
                'folder_paths': record_data.folder_paths or 'Нет данных',
                'object_count': record_data.object_count or 'Нет данных',
                'last_object_created': record_data.last_object_created or 'Нет данных',
                'last_object_modified': record_data.last_object_modified or 'Нет данных',
                'a_ouid': record_data.a_ouid or 'Нет данных',
                'base_url': record_data.base_url or ''
            }
            
            # Добавляем дополнительную проверку на None
            for key, value in details.items():
                if value is None:
                    details[key] = 'Нет данных'
            
            logging.info(f"[API] Возвращаем детальную информацию о записи: {details}")
            
            return jsonify({
                'success': True,
                'details': details
            })
            
        except Exception as e:
            logging.error(f"Ошибка при получении данных о записи: {str(e)}", exc_info=True)
            
            # Более подробное сообщение об ошибке
            error_message = f"Ошибка при получении данных о записи (ID {result_id}): {str(e)}"
            logging.error(error_message)
            
            return jsonify({
                'success': False,
                'error': error_message
            }), 500

    @app.route('/test_record_details/<int:result_id>')
    def test_record_details_view(result_id):
        """
        Тестовый HTML-endpoint для просмотра детальной информации о записи
        """
        try:
            # Находим результат анализа
            analysis_result = AnalysisResult.query.get_or_404(result_id)
            
            # Находим исходные данные в таблице analysis_data по batch_id и имени класса
            record_data = AnalysisData.query.filter_by(
                batch_id=analysis_result.batch_id,
                mssql_sxclass_name=analysis_result.mssql_sxclass_name
            ).first()
            
            if not record_data:
                # Если не найдены в analysis_data, попробуем найти в MigrationClass
                record_data = MigrationClass.query.filter_by(
                    mssql_sxclass_name=analysis_result.mssql_sxclass_name
                ).first()
                
                if not record_data:
                    return f"""
                    <html>
                    <head><title>Детали записи</title></head>
                    <body>
                        <h1>Ошибка</h1>
                        <p>Не найдены исходные данные для результата анализа: 
                        batch_id={analysis_result.batch_id}, 
                        class_name={analysis_result.mssql_sxclass_name}</p>
                    </body>
                    </html>
                    """
            
            # Собираем детальную информацию о записи
            details = {
                'mssql_sxclass_name': record_data.mssql_sxclass_name or 'Нет данных',
                'created_date': record_data.created_date or 'Нет данных',
                'created_by': record_data.created_by or 'Нет данных',
                'modified_date': record_data.modified_date or 'Нет данных',
                'modified_by': record_data.modified_by or 'Нет данных',
                'folder_paths': record_data.folder_paths or 'Нет данных',
                'object_count': record_data.object_count or 'Нет данных',
                'last_object_created': record_data.last_object_created or 'Нет данных',
                'last_object_modified': record_data.last_object_modified or 'Нет данных',
                'a_ouid': record_data.a_ouid or 'Нет данных',
                'base_url': record_data.base_url or ''
            }
            
            # Создаем HTML для ссылок
            links_html = ""
            if details['base_url']:
                if details['a_ouid'] and details['a_ouid'] != 'Нет данных':
                    object_url = f"{details['base_url']}admin/edit.htm?id={details['a_ouid']}%40SXClass"
                    links_html += f"""
                    <div><a href="{object_url}" target="_blank" class="btn btn-sm btn-outline-primary mt-1">
                        <i class="bi bi-box-arrow-up-right"></i> Перейти к объекту</a></div>
                    """
                
                if details['mssql_sxclass_name'] and details['mssql_sxclass_name'] != 'Нет данных':
                    class_objects_url = f"{details['base_url']}objectsofclass.htm?cls={details['mssql_sxclass_name']}"
                    links_html += f"""
                    <div><a href="{class_objects_url}" target="_blank" class="btn btn-sm btn-outline-info mt-1">
                        <i class="bi bi-boxes"></i> Объекты класса</a></div>
                    """
            
            # Генерируем HTML для отображения данных
            html = f"""
            <html>
            <head>
                <title>Детали записи</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .details-card {{ border: 2px solid #007bff; border-radius: 6px; padding: 15px; max-width: 500px; }}
                    .details-header {{ font-weight: bold; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #dee2e6; font-size: 16px; color: #000; text-align: center; }}
                    .details-row {{ display: flex; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px dotted #eee; }}
                    .details-label {{ flex: 0 0 45%; font-weight: 600; color: #495057; padding-right: 10px; }}
                    .details-value {{ flex: 0 0 55%; word-break: break-word; color: #212529; }}
                    .btn {{ padding: 3px 8px; font-size: 12px; margin-right: 5px; text-decoration: none; display: inline-block; margin-bottom: 4px; border-radius: 3px; border-width: 1px; border-style: solid; }}
                    .btn-outline-primary {{ color: #007bff; border-color: #007bff; }}
                    .btn-outline-primary:hover {{ color: #fff; background-color: #007bff; }}
                    .btn-outline-info {{ color: #17a2b8; border-color: #17a2b8; }}
                    .btn-outline-info:hover {{ color: #fff; background-color: #17a2b8; }}
                </style>
            </head>
            <body>
                <h1>Тестовая страница деталей записи</h1>
                <p>Эта страница показывает то же самое, что будет видно во всплывающей подсказке</p>
                
                <div class="details-card">
                    <div class="details-header">
                        {details['mssql_sxclass_name']} - Детальная информация
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Дата создания:</div>
                        <div class="details-value">{details['created_date']}</div>
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Создал:</div>
                        <div class="details-value">{details['created_by']}</div>
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Дата изменения:</div>
                        <div class="details-value">{details['modified_date']}</div>
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Изменил:</div>
                        <div class="details-value">{details['modified_by']}</div>
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Пути папок в консоли:</div>
                        <div class="details-value">{details['folder_paths']}</div>
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Наличие объектов:</div>
                        <div class="details-value">{"Да" if details['object_count'] and details['object_count'] != 'Нет данных' and int(details['object_count']) > 0 else "Нет"}</div>
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Количество объектов:</div>
                        <div class="details-value">{details['object_count']}</div>
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Дата создания последнего объекта:</div>
                        <div class="details-value">{details['last_object_created']}</div>
                    </div>
                    
                    <div class="details-row">
                        <div class="details-label">Дата последнего изменения:</div>
                        <div class="details-value">{details['last_object_modified']}</div>
                    </div>
                    
                    {f'''
                    <div class="details-row">
                        <div class="details-label">Ссылки:</div>
                        <div class="details-value">
                            {links_html}
                        </div>
                    </div>
                    ''' if links_html else ''}
                </div>
                
                <h2>Исходные данные из API:</h2>
                <pre style="background: #f5f5f5; padding: 10px; border-radius: 5px; overflow: auto;">
                {str(details)}
                </pre>
                
                <p>
                    <a href="/analysis_results?batch_id={analysis_result.batch_id}" class="btn btn-outline-primary">
                        Вернуться к результатам анализа
                    </a>
                </p>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            error_message = f"Ошибка при получении данных о записи (ID {result_id}): {str(e)}"
            logging.error(error_message, exc_info=True)
            
            return f"""
            <html>
            <head><title>Ошибка</title></head>
            <body>
                <h1>Ошибка</h1>
                <p>{error_message}</p>
            </body>
            </html>
            """

    @app.route('/api/update_priznak_all_classes', methods=['POST'])
    def update_priznak_all_classes():
        """
        Применяет текущее значение признака ко всем записям с таким же именем класса во всех батчах анализа
        """
        try:
            data = request.get_json()
            result_id = data.get('result_id')
            
            if not result_id:
                return jsonify({
                    'success': False,
                    'error': 'Не указан ID записи'
                }), 400
            
            # Получаем запись, с которой будем работать
            source_result = AnalysisResult.query.get_or_404(result_id)
            class_name = source_result.mssql_sxclass_name
            priznak_value = source_result.priznak
            
            if not priznak_value:
                return jsonify({
                    'success': False,
                    'error': 'В исходной записи не установлено значение признака'
                }), 400
            
            # Обновляем записи в AnalysisResult с таким же именем класса
            update_result = AnalysisResult.query.filter(
                AnalysisResult.mssql_sxclass_name == class_name,
                AnalysisResult.id != result_id  # Исключаем текущую запись
            ).update({
                'priznak': priznak_value,
                'analyzed_by': 'global_update',
                'status': 'analyzed',
                'confidence_score': 1.0
            }, synchronize_session=False)
            
            # Обновляем записи в MigrationClass с таким же именем класса
            migration_update = MigrationClass.query.filter(
                MigrationClass.mssql_sxclass_name == class_name
            ).update({
                'priznak': priznak_value,
                'classified_by': 'global_update',
                'confidence_score': 1.0
            }, synchronize_session=False)
            
            # Обновляем записи в AnalysisData с таким же именем класса
            analysis_data_update = AnalysisData.query.filter(
                AnalysisData.mssql_sxclass_name == class_name
            ).update({
                'priznak': priznak_value,
                'classified_by': 'global_update',
                'analysis_state': 'analyzed',
                'confidence_score': 1.0
            }, synchronize_session=False)
            
            db.session.commit()
            
            # Подсчитываем общее количество обновленных записей
            total_updated = update_result + migration_update + analysis_data_update
            
            return jsonify({
                'success': True,
                'message': f'Значение признака "{priznak_value}" применено ко всем записям класса "{class_name}"',
                'updated_count': total_updated,
                'updated_analysis_results': update_result,
                'updated_migration_classes': migration_update,
                'updated_analysis_data': analysis_data_update
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при обновлении всех записей класса: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/correct_priznaks')
    def correct_priznaks():
        """
        Страница для коррекции признаков по имени класса
        """
        # Получаем список уникальных значений признаков
        priznaks = db.session.query(AnalysisResult.priznak)\
                            .filter(AnalysisResult.priznak.isnot(None))\
                            .distinct()\
                            .order_by(AnalysisResult.priznak)\
                            .all()
        priznaks = [p[0] for p in priznaks if p[0]]
        
        # Получаем список уникальных имен таблиц из MigrationClass
        migration_tables = db.session.query(MigrationClass.mssql_sxclass_map)\
                                   .filter(MigrationClass.mssql_sxclass_map.isnot(None))\
                                   .distinct()\
                                   .order_by(MigrationClass.mssql_sxclass_map)\
                                   .all()
        migration_tables = [t[0] for t in migration_tables if t[0]]
        
        # Также получаем таблицы из AnalysisData
        analysis_tables = db.session.query(AnalysisData.mssql_sxclass_map)\
                                   .filter(AnalysisData.mssql_sxclass_map.isnot(None))\
                                   .distinct()\
                                   .order_by(AnalysisData.mssql_sxclass_map)\
                                   .all()
        analysis_tables = [t[0] for t in analysis_tables if t[0]]
        
        # Дополняем список таблиц именами классов, так как они часто совпадают с именами таблиц
        class_names = db.session.query(AnalysisResult.mssql_sxclass_name)\
                               .filter(AnalysisResult.mssql_sxclass_name.isnot(None))\
                               .distinct()\
                               .order_by(AnalysisResult.mssql_sxclass_name)\
                               .all()
        class_names_list = [c[0] for c in class_names if c[0]]
        
        # Объединяем все списки и удаляем дубликаты
        tables = list(set(migration_tables + analysis_tables + class_names_list))
        tables.sort()
        
        # Получаем историю корректировок из базы данных
        history = PriznakCorrectionHistory.query\
                 .order_by(PriznakCorrectionHistory.timestamp.desc())\
                 .limit(50)\
                 .all()
        
        return render_template('correct_priznaks.html', 
                              priznaks=priznaks,
                              tables=tables,
                              class_names=class_names_list,
                              history=history)
    
    @app.route('/api/update_priznak_by_class_name', methods=['POST'])
    def update_priznak_by_class_name():
        """
        Применяет значение признака ко всем записям с указанным именем класса или таблицы во всех батчах анализа
        """
        try:
            data = request.get_json()
            search_field = data.get('search_field', 'class_name')
            search_value = data.get('search_value')
            priznak_value = data.get('priznak')
            
            if not search_value:
                return jsonify({
                    'success': False,
                    'error': 'Не указано значение для поиска'
                }), 400
                
            if not priznak_value:
                return jsonify({
                    'success': False,
                    'error': 'Не указано значение признака'
                }), 400
            
            # Определяем фильтр в зависимости от типа поиска
            if search_field == 'class_name':
                # Поиск по имени класса
                filter_condition_result = AnalysisResult.mssql_sxclass_name == search_value
                filter_condition_migration = MigrationClass.mssql_sxclass_name == search_value
                filter_condition_analysis_data = AnalysisData.mssql_sxclass_name == search_value
                
                # Проверяем существование класса
                exists = db.session.query(
                    db.exists().where(filter_condition_result)
                ).scalar()
                
                error_message = f'Класс с именем "{search_value}" не найден'
                message_success = f'Значение признака "{priznak_value}" применено ко всем записям класса "{search_value}"'
                affected_class_name = search_value
                
            elif search_field == 'table_name':
                # Поиск по имени таблицы - используем mssql_sxclass_map
                # В AnalysisResult нет поля mssql_sxclass_map, поэтому сначала получаем 
                # имена классов из MigrationClass и AnalysisData
                
                # Получаем имена классов из MigrationClass
                class_names_query = db.session.query(MigrationClass.mssql_sxclass_name)\
                                             .filter(MigrationClass.mssql_sxclass_map == search_value)\
                                             .distinct()\
                                             .all()
                
                # Если не нашли, ищем в AnalysisData
                if not class_names_query:
                    class_names_query = db.session.query(AnalysisData.mssql_sxclass_name)\
                                                 .filter(AnalysisData.mssql_sxclass_map == search_value)\
                                                 .distinct()\
                                                 .all()
                
                # Если все еще не нашли, проверяем совпадение mssql_sxclass_name с именем таблицы
                if not class_names_query:
                    # Ищем классы в MigrationClass с именем как таблица
                    class_names_query = db.session.query(MigrationClass.mssql_sxclass_name)\
                                                 .filter(MigrationClass.mssql_sxclass_name == search_value)\
                                                 .distinct()\
                                                 .all()
                
                # Если все еще не нашли, ищем в AnalysisData
                if not class_names_query:
                    # Ищем классы в AnalysisData с именем как таблица
                    class_names_query = db.session.query(AnalysisData.mssql_sxclass_name)\
                                                 .filter(AnalysisData.mssql_sxclass_name == search_value)\
                                                 .distinct()\
                                                 .all()
                
                # Если все еще не нашли, ищем в AnalysisResult
                if not class_names_query:
                    # Ищем классы в AnalysisResult с именем как таблица
                    class_names_query = db.session.query(AnalysisResult.mssql_sxclass_name)\
                                                 .filter(AnalysisResult.mssql_sxclass_name == search_value)\
                                                 .distinct()\
                                                 .all()
                
                if not class_names_query:
                    return jsonify({
                        'success': False,
                        'error': f'Таблица с именем "{search_value}" не найдена или не связана ни с одним классом'
                    }), 404
                
                # Получаем имена классов
                class_names = [row[0] for row in class_names_query]
                
                # Создаем фильтр для AnalysisResult по именам классов
                filter_condition_result = AnalysisResult.mssql_sxclass_name.in_(class_names)
                filter_condition_migration = MigrationClass.mssql_sxclass_name.in_(class_names)
                filter_condition_analysis_data = AnalysisData.mssql_sxclass_name.in_(class_names)
                
                exists = True  # Мы уже проверили существование выше
                error_message = f'Таблица с именем "{search_value}" не найдена'
                message_success = f'Значение признака "{priznak_value}" применено ко всем записям таблицы "{search_value}"'
                
                if len(class_names) == 1:
                    affected_class_name = class_names[0]
                else:
                    affected_class_name = f"Разные классы ({len(class_names)})"
            else:
                return jsonify({
                    'success': False,
                    'error': 'Неверный тип поиска'
                }), 400
            
            if not exists:
                return jsonify({
                    'success': False,
                    'error': error_message
                }), 404
            
            # Обновляем записи в AnalysisResult
            update_result = AnalysisResult.query.filter(
                filter_condition_result
            ).update({
                'priznak': priznak_value,
                'analyzed_by': 'global_update',
                'status': 'analyzed',
                'confidence_score': 1.0
            }, synchronize_session=False)
            
            # Обновляем записи в MigrationClass
            migration_update = MigrationClass.query.filter(
                filter_condition_migration
            ).update({
                'priznak': priznak_value,
                'classified_by': 'global_update',
                'confidence_score': 1.0
            }, synchronize_session=False)
            
            # Обновляем записи в AnalysisData
            analysis_data_update = AnalysisData.query.filter(
                filter_condition_analysis_data
            ).update({
                'priznak': priznak_value,
                'classified_by': 'global_update',
                'analysis_state': 'analyzed',
                'confidence_score': 1.0
            }, synchronize_session=False)
            
            db.session.commit()
            
            # Подсчитываем общее количество обновленных записей
            total_updated = update_result + migration_update + analysis_data_update
            
            # Сохраняем историю корректировки
            history_entry = PriznakCorrectionHistory(
                search_type=search_field,
                search_value=search_value,
                class_name=affected_class_name,
                priznak=priznak_value,
                updated_analysis_results=update_result,
                updated_migration_classes=migration_update,
                updated_analysis_data=analysis_data_update,
                updated_count=total_updated,
                user="system"  # можно добавить идентификацию пользователей в будущем
            )
            db.session.add(history_entry)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': message_success,
                'updated_count': total_updated,
                'updated_analysis_results': update_result,
                'updated_migration_classes': migration_update,
                'updated_analysis_data': analysis_data_update,
                'affected_class_name': affected_class_name
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Ошибка при обновлении записей: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500

def apply_rule_to_record(rule, record):
    """
    Применяет правило к записи и проверяет, соответствует ли она правилу
    
    Args:
        rule: объект TransferRule
        record: объект MigrationClass или AnalysisData
        
    Returns:
        priznak, если правило применимо, None в противном случае
    """
    # Получаем значение поля для проверки
    field_value = None
    if rule.condition_field == 'MSSQL_SXCLASS_NAME':
        field_value = record.mssql_sxclass_name
    elif rule.condition_field == 'MSSQL_SXCLASS_DESCRIPTION':
        field_value = record.mssql_sxclass_description
    elif rule.condition_field == 'MSSQL_SXCLASS_MAP':
        field_value = record.mssql_sxclass_map
    elif rule.condition_field == 'Родительский класс':
        field_value = record.parent_class
    elif rule.condition_field == 'Создал':
        field_value = record.created_by

    # Проверяем на соответствие
    if not field_value and rule.condition_type != 'ALWAYS_TRUE':
        return None

    match = False
    if rule.condition_type == 'EQUALS':
        match = field_value == rule.condition_value
    elif rule.condition_type == 'STARTS_WITH':
        match = field_value and field_value.startswith(rule.condition_value)
    elif rule.condition_type == 'ENDS_WITH':
        match = field_value and field_value.endswith(rule.condition_value)
    elif rule.condition_type == 'CONTAINS':
        match = field_value and rule.condition_value in field_value
    elif rule.condition_type == 'ALWAYS_TRUE':
        match = True

    if match:
        return rule.transfer_action
    
    return None