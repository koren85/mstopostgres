from datetime import datetime
from typing import List, Dict, Any
from models import AnalysisData, MigrationClass, Discrepancy, AnalysisResult
from database import db

class AnalysisService:
    def analyze_historical_patterns(self, batch_id: str) -> Dict[str, Any]:
        """
        Анализ исторических паттернов для новых данных
        """
        try:
            # Получаем новые данные для анализа
            new_records = AnalysisData.query.filter_by(
                batch_id=batch_id, 
                analysis_state='pending'
            ).all()
            
            results = {
                'total_records': len(new_records),
                'analyzed_records': 0,
                'discrepancies_found': 0,
                'high_confidence_matches': 0
            }
            
            for record in new_records:
                # Поиск исторических паттернов
                historical_matches = self._find_historical_matches(record)
                
                # Группировка по признакам
                priznak_groups = self._group_by_priznaks(historical_matches)
                
                # Анализ расхождений
                discrepancies = self._analyze_discrepancies(record, priznak_groups)
                
                # Сохранение результатов
                analysis_result = self._save_analysis_result(record, priznak_groups, discrepancies)
                
                # Обновляем статистику
                results['analyzed_records'] += 1
                results['discrepancies_found'] += len(discrepancies)
                if analysis_result.confidence_score >= 0.8:
                    results['high_confidence_matches'] += 1
            
            return {
                'success': True,
                'results': results
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }

    def _find_historical_matches(self, record: AnalysisData) -> List[MigrationClass]:
        """
        Поиск похожих записей в исторических данных
        """
        return MigrationClass.query.filter(
            MigrationClass.mssql_sxclass_name == record.mssql_sxclass_name,
            MigrationClass.source_system != record.source_system,
            MigrationClass.priznak.isnot(None)
        ).all()

    def _group_by_priznaks(self, historical_records: List[MigrationClass]) -> Dict[str, Dict]:
        """
        Группировка исторических данных по признакам
        """
        priznak_groups = {}
        for record in historical_records:
            if record.priznak not in priznak_groups:
                priznak_groups[record.priznak] = {
                    'count': 0,
                    'systems': set(),
                    'examples': []
                }
            
            group = priznak_groups[record.priznak]
            group['count'] += 1
            group['systems'].add(record.source_system)
            group['examples'].append({
                'class_name': record.mssql_sxclass_name,
                'description': record.mssql_sxclass_description,
                'system': record.source_system,
                'created_date': record.created_date
            })
        
        return priznak_groups

    def _analyze_discrepancies(self, record: AnalysisData, priznak_groups: Dict[str, Dict]) -> List[Discrepancy]:
        """
        Анализ расхождений на основе групп признаков
        """
        discrepancies = []
        
        # Если есть несколько групп признаков
        if len(priznak_groups) > 1:
            # Сортируем группы по количеству записей
            sorted_groups = sorted(
                priznak_groups.items(), 
                key=lambda x: x[1]['count'], 
                reverse=True
            )
            
            # Создаем запись о расхождении
            discrepancy = Discrepancy(
                class_name=record.mssql_sxclass_name,
                description=f"Найдено {len(sorted_groups)} разных значений признака",
                different_priznaks={
                    group[0]: {
                        'count': group[1]['count'],
                        'systems': list(group[1]['systems'])
                    }
                    for group in sorted_groups
                },
                source_systems=list(set().union(
                    *[group[1]['systems'] for group in sorted_groups]
                ))
            )
            discrepancies.append(discrepancy)
        
        return discrepancies

    def _save_analysis_result(self, record: AnalysisData, priznak_groups: Dict[str, Dict], 
                            discrepancies: List[Discrepancy]) -> AnalysisResult:
        """
        Сохранение результатов анализа
        """
        try:
            # Создаем результат анализа
            result = AnalysisResult(
                batch_id=record.batch_id,
                mssql_sxclass_name=record.mssql_sxclass_name,
                priznak=max(priznak_groups.items(), key=lambda x: x[1]['count'])[0] if priznak_groups else None,
                confidence_score=self._calculate_confidence(priznak_groups),
                discrepancies=[{
                    'description': d.description,
                    'different_priznaks': d.different_priznaks
                } for d in discrepancies],
                status='analyzed',
                analyzed_by='historical'
            )
            
            # Обновляем статус записи
            record.analysis_state = 'analyzed'
            record.matched_historical_data = {
                'priznak_groups': priznak_groups,
                'analysis_result_id': result.id
            }
            record.analysis_date = datetime.utcnow()
            
            # Сохраняем в базу
            db.session.add(result)
            for discrepancy in discrepancies:
                discrepancy.analysis_result_id = result.id
                db.session.add(discrepancy)
            
            db.session.commit()
            return result
            
        except Exception as e:
            db.session.rollback()
            raise e

    def _calculate_confidence(self, priznak_groups: Dict[str, Dict]) -> float:
        """
        Расчет уверенности в результате анализа
        """
        if not priznak_groups:
            return 0.0
            
        total_records = sum(g['count'] for g in priznak_groups.values())
        max_group_count = max(g['count'] for g in priznak_groups.values())
        
        return max_group_count / total_records 