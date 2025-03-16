# Исправление обработки записей с пустыми значениями полей

## Проблема

При нажатии на кнопку "Применить правила переноса" не обрабатывались записи с пустыми значениями поля MSSQL_SXCLASS_MAP, хотя в системе было создано правило с ID 75, где:
- Тип условия: IS_EMPTY
- Поле условия: MSSQL_SXCLASS_MAP
- Действие: Переносим пакетом

Примеры необработанных записей:
1. reestrIdentityLinkHadrProcessin - Пустые значения полей: MSSQL_SXCLASS_MAP
2. reestrIdentityLink - Пустые значения полей: MSSQL_SXCLASS_MAP
3. reestrIdentityAntiLink - Пустые значения полей: MSSQL_SXCLASS_MAP
4. itogSpisGspCalc - Пустые значения полей: MSSQL_SXCLASS_MAP
5. itogSpisGspVyp - Пустые значения полей: MSSQL_SXCLASS_MAP

## Причина проблемы

В функции `apply_transfer_rules_batch` в файле `routes.py` была проверка на наличие значений в ключевых полях перед применением правил:

```python
# Проверяем наличие значений в ключевых полях перед применением правил
empty_fields = []
if not record.mssql_sxclass_name:
    empty_fields.append('MSSQL_SXCLASS_NAME')
if not record.mssql_sxclass_description:
    empty_fields.append('MSSQL_SXCLASS_DESCRIPTION')
if not record.mssql_sxclass_map:
    empty_fields.append('MSSQL_SXCLASS_MAP')

# Если есть пустые поля, добавляем их в статистику
if empty_fields:
    # ... пропускаем запись ...
    continue
```

Эта проверка исключала записи с пустыми значениями MSSQL_SXCLASS_MAP из обработки, хотя в функции `apply_transfer_rules` есть специальная обработка для пустых значений:

```python
# Проверяем условие
if rule.condition_type == 'IS_EMPTY':
    # Проверяем, что поле пустое
    is_none = field_value is None
    is_empty_string = isinstance(field_value, str) and field_value.strip() == ''
    match = is_none or is_empty_string
    logging.info(f"[ПРАВИЛА ПЕРЕНОСА] IS_EMPTY: поле={field_value}, is_none={is_none}, is_empty_string={is_empty_string}, match={match}")
```

## Решение

Мы удалили проверку на пустое значение MSSQL_SXCLASS_MAP в функции `apply_transfer_rules_batch`:

```python
# Проверяем наличие значений в ключевых полях перед применением правил
empty_fields = []
if not record.mssql_sxclass_name:
    empty_fields.append('MSSQL_SXCLASS_NAME')
if not record.mssql_sxclass_description:
    empty_fields.append('MSSQL_SXCLASS_DESCRIPTION')
# Удалили проверку на пустое значение MSSQL_SXCLASS_MAP
```

Также добавили комментарий в начале функции, чтобы объяснить, почему мы не проверяем пустые значения MSSQL_SXCLASS_MAP:

```python
"""
Применяет правила переноса к записям из указанного батча.

Важно: Записи с пустыми значениями MSSQL_SXCLASS_MAP обрабатываются правилом с типом IS_EMPTY,
поэтому мы не исключаем их из обработки.
"""
```

## Тестирование

Мы создали несколько тестовых скриптов для проверки обработки записей с пустыми значениями полей:

1. `test_empty_fields.py` - проверяет обработку тестовой записи с пустым значением MSSQL_SXCLASS_MAP
2. `test_real_records.py` - проверяет обработку реальных записей из базы данных с пустыми значениями MSSQL_SXCLASS_MAP
3. `test_api_empty_fields.py` - проверяет обработку записей с пустыми значениями MSSQL_SXCLASS_MAP через API

Все тесты показали, что правило с ID 75 для пустых значений MSSQL_SXCLASS_MAP работает корректно и устанавливает признак "Переносим пакетом" для записей с пустыми значениями MSSQL_SXCLASS_MAP. 