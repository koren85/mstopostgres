import os
import logging
from sqlalchemy import create_engine, text
import sys

def setup_database():
    """Проверяет структуру базы данных и добавляет необходимые колонки"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logging.info("Начинаем проверку структуры базы данных...")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logging.error("Не установлена переменная DATABASE_URL")
        return

    engine = create_engine(database_url)

    try:
        with engine.connect() as connection:
            # Проверка таблицы classification_rules
            check_and_fix_table(connection, 'classification_rules', [
                ('pattern', 'VARCHAR(255) NOT NULL'),
                ('field', 'VARCHAR(50) NOT NULL'),
                ('priznak_value', 'VARCHAR(50) NOT NULL'),
                ('priority', 'INTEGER DEFAULT 0'),
                ('created_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('confidence_threshold', 'FLOAT DEFAULT 0.8'),
                ('source_batch_id', 'VARCHAR(36)')
            ])

            # Проверка таблицы migration_classes
            check_and_fix_table(connection, 'migration_classes', [
                ('batch_id', 'VARCHAR(36)'),
                ('file_name', 'VARCHAR(255)'),
                ('a_ouid', 'VARCHAR(255)'),
                ('mssql_sxclass_description', 'VARCHAR(255)'),
                ('mssql_sxclass_name', 'VARCHAR(255)'),
                ('mssql_sxclass_map', 'VARCHAR(255)'),
                ('priznak', 'VARCHAR(255)'),
                ('system_class', 'VARCHAR(255)'),
                ('is_link_table', 'VARCHAR(255)'),
                ('parent_class', 'VARCHAR(255)'),
                ('child_classes', 'VARCHAR(255)'),
                ('child_count', 'VARCHAR(255)'),
                ('created_date', 'VARCHAR(255)'),
                ('created_by', 'VARCHAR(255)'),
                ('modified_date', 'VARCHAR(255)'),
                ('modified_by', 'VARCHAR(255)'),
                ('folder_paths', 'VARCHAR(255)'),
                ('object_count', 'VARCHAR(255)'),
                ('last_object_created', 'VARCHAR(255)'),
                ('last_object_modified', 'VARCHAR(255)'),
                ('attribute_count', 'VARCHAR(255)'),
                ('category', 'VARCHAR(255)'),
                ('migration_flag', 'VARCHAR(255)'),
                ('rule_info', 'VARCHAR(255)'),
                ('source_system', 'TEXT'),
                ('upload_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('confidence_score', 'FLOAT'),
                ('classified_by', 'VARCHAR(50)')
            ])

            # Проверка таблицы discrepancies
            check_and_fix_table(connection, 'discrepancies', [
                ('class_name', 'TEXT'),
                ('description', 'TEXT'),
                ('different_priznaks', 'JSON'),
                ('source_systems', 'JSON'),
                ('detected_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('resolved', 'BOOLEAN DEFAULT FALSE'),
                ('resolution_note', 'TEXT')
            ])

            # Проверка таблицы analysis_data
            check_and_fix_table(connection, 'analysis_data', [
                ('batch_id', 'VARCHAR(36) NOT NULL'),
                ('file_name', 'VARCHAR(255)'),
                ('a_ouid', 'VARCHAR(255)'),
                ('mssql_sxclass_description', 'VARCHAR(255)'),
                ('mssql_sxclass_name', 'VARCHAR(255)'),
                ('mssql_sxclass_map', 'VARCHAR(255)'),
                ('priznak', 'VARCHAR(255)'),
                ('system_class', 'VARCHAR(255)'),
                ('is_link_table', 'VARCHAR(255)'),
                ('parent_class', 'VARCHAR(255)'),
                ('child_classes', 'VARCHAR(255)'),
                ('child_count', 'VARCHAR(255)'),
                ('created_date', 'VARCHAR(255)'),
                ('created_by', 'VARCHAR(255)'),
                ('modified_date', 'VARCHAR(255)'),
                ('modified_by', 'VARCHAR(255)'),
                ('folder_paths', 'VARCHAR(255)'),
                ('object_count', 'VARCHAR(255)'),
                ('last_object_created', 'VARCHAR(255)'),
                ('last_object_modified', 'VARCHAR(255)'),
                ('attribute_count', 'VARCHAR(255)'),
                ('category', 'VARCHAR(255)'),
                ('migration_flag', 'VARCHAR(255)'),
                ('rule_info', 'VARCHAR(255)'),
                ('source_system', 'TEXT'),
                ('upload_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('confidence_score', 'FLOAT'),
                ('classified_by', 'VARCHAR(50)'),
                ('analysis_state', 'VARCHAR(50) DEFAULT \'pending\''),
                ('matched_historical_data', 'JSON'),
                ('analysis_date', 'TIMESTAMP')
            ])

            logging.info("Проверка структуры базы данных успешно завершена")

    except Exception as e:
        logging.error(f"Ошибка при проверке/обновлении базы данных: {str(e)}", exc_info=True)

def check_and_fix_table(connection, table_name, required_columns):
    """Проверяет существование таблицы и наличие всех необходимых колонок"""
    logging.info(f"Проверка таблицы {table_name}...")

    # Проверяем существование таблицы
    result = connection.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = '{table_name}'
                );
            """))

    if not result.scalar():
        logging.info(f"Таблица {table_name} не существует. Будет создана автоматически.")
        create_table(connection, table_name, required_columns)
        return

    # Проверяем наличие всех необходимых колонок
    existing_columns = get_table_columns(connection, table_name)

    for col_name, col_type in required_columns:
        if col_name.lower() not in (col.lower() for col in existing_columns):
            logging.info(f"Добавляем отсутствующую колонку {col_name} в таблицу {table_name}")
            try:
                connection.execute(text(f"""
                    ALTER TABLE {table_name} 
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type};
                """))
                logging.info(f"Успешно добавлена колонка {col_name}")
            except Exception as e:
                logging.error(f"Ошибка при добавлении колонки {col_name}: {str(e)}")

def create_table(connection, table_name, columns):
    """Создает новую таблицу с указанными колонками"""
    try:
        # Формируем SQL для создания таблицы
        columns_sql = ", ".join([f"{name} {type_}" for name, type_ in columns])

        # Добавляем id колонку если она не указана
        if not any(col[0].lower() == 'id' for col in columns):
            columns_sql = f"id SERIAL PRIMARY KEY, {columns_sql}"

        # Используем форматирование строки для имени таблицы напрямую,
        # так как text() не поддерживает bindparams для имени таблицы
        sql = f"CREATE TABLE {table_name} ({columns_sql});"

        connection.execute(text(sql))
        connection.commit()
        logging.info(f"Таблица {table_name} успешно создана")
    except Exception as e:
        connection.rollback()
        logging.error(f"Ошибка при создании таблицы {table_name}: {str(e)}")

def get_table_columns(connection, table_name):
    """Возвращает список колонок таблицы"""
    result = connection.execute(text(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}'
    """))
    return [row[0] for row in result]

def init_transfer_rules():
    """Инициализация таблицы правил переноса данных"""
    from models import TransferRule
    from database import db
    
    # Проверяем, есть ли уже правила в таблице
    if TransferRule.query.count() > 0:
        print("Таблица правил переноса уже содержит данные. Пропускаем инициализацию.")
        return
    
    # Список правил для инициализации
    rules = [
        {"priority": 10, "category_name": "Класс задач", "transfer_action": "Переносим пакетом", "condition_type": "EXACT_EQUALS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "cmsTask", "comment": "Чтобы переопределить «cmsTask» (иначе попадёт в «Контекстные - Не переносим»)"},
        {"priority": 15, "category_name": "Класс утилит", "transfer_action": "Переносим пакетом", "condition_type": "EXACT_EQUALS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "cmsUtil", "comment": "Аналогично, исключение из «контекстных»"},
        {"priority": 16, "category_name": "Системные", "transfer_action": "Не переносим", "condition_type": "EXACT_EQUALS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "sxlink", "comment": ""},
        {"priority": 17, "category_name": "Системные", "transfer_action": "Не переносим", "condition_type": "EXACT_EQUALS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "secConfig", "comment": ""},
        {"priority": 18, "category_name": "Системные", "transfer_action": "Не переносим", "condition_type": "EXACT_EQUALS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "registerConfig", "comment": ""},
        {"priority": 19, "category_name": "Классы задач", "transfer_action": "Переносим пакетом", "condition_type": "EXACT_EQUALS", "condition_field": "Родительский класс", "condition_value": "cmsTask", "comment": "Если ещё не попали в «Исключение» (строка 10), то родитель = cmsTask → переносим пакетом"},
        {"priority": 20, "category_name": "Контекстные", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "cms;ao_", "comment": "Имя начинается с «cms» или «ao_». Исключения выше (cmsTask, cmsUtil)"},
        {"priority": 21, "category_name": "Контекстные", "transfer_action": "Не переносим", "condition_type": "EXACT_EQUALS", "condition_field": "Родительский класс", "condition_value": "cmsProfile;baseInfSet", "comment": ""},
        {"priority": 22, "category_name": "Контекстные", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "CMS_", "comment": ""},
        {"priority": 25, "category_name": "Системные", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "sx;FileMasks;SqlDialect;servCanceledTime;stepsUnversalPrintUtiil;licenses", "comment": "Имя начинается с sx (исключение: если «registerConfig» у вас переносится, нужно отдельное правило)"},
        {"priority": 26, "category_name": "Системные", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "SYNC_;WEB_", "comment": ""},
        {"priority": 30, "category_name": "Виртуальные", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "null", "comment": "Нет сопоставленной таблицы (map пустой)"},
        {"priority": 40, "category_name": "Конвертации", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "conv", "comment": "Имя начинается с «conv»"},
        {"priority": 41, "category_name": "Конвертации", "transfer_action": "Не переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "конвертац", "comment": ""},
        {"priority": 50, "category_name": "Конвертации", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "CONV_", "comment": "map начинается с «CONV_»"},
        {"priority": 60, "category_name": "Временные классы", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "Временная таблица;Временное;Времмен", "comment": "Описание начинается с «Временная таблица»"},
        {"priority": 70, "category_name": "Временные таблицы", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "tmp;temp", "comment": "Имя начинается с «tmp» или «temp»"},
        {"priority": 80, "category_name": "Не ЭСРН", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "shop", "comment": "Проверять, что имя начинается с «shop» + Автор = «omikhalyova» (В макросе нужна логика «AND»)"},
        {"priority": 81, "category_name": "Не ЭСРН", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "Создал", "condition_value": "omikhalyova", "comment": ""},
        {"priority": 82, "category_name": "Классы задач", "transfer_action": "Переносим пакетом", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "task", "comment": ""},
        {"priority": 90, "category_name": "Платформенные", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "baseInfSet;configUson;ReferenceInf;WSCallConfiguration;sprServiceGender;discriptionFildUI;interactionServerConf;InvocServiceIterator;sign;UIJavaHandlerMethod;EDSBelongingToUsers", "comment": "Если родитель = baseInfSet или configUson"},
        {"priority": 100, "category_name": "Логи", "transfer_action": "Не переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "log", "comment": "Имя содержит «log» (logInfoobmen, logSteepInfoobmen, task66732Log и т.д.)"},
        {"priority": 120, "category_name": "Классы задач", "transfer_action": "Переносим пакетом", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "task", "comment": "Имя содержит «task»"},
        {"priority": 121, "category_name": "Классы задач", "transfer_action": "Переносим пакетом", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "Задача", "comment": ""},
        {"priority": 130, "category_name": "Базовые классы", "transfer_action": "Переносим", "condition_type": "EXACT_EQUALS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "SignReportFile;queriesConstants;rollbackInfoobmen;TelegramAccount", "comment": "Если класс называется «SignReportFile»"},
        {"priority": 140, "category_name": "Наполняемые справочники", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "sd_;spr;ident;BasePost;Basis_for_making_a_decision", "comment": "Имя начинается с «sd_» или «spr»"},
        {"priority": 141, "category_name": "Наполняемые справочники", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "spr;SPR_;FIAS_;PC_;PPR_;SP_;SOST_FAM", "comment": "(Новый) ловим map начинающиеся на SPR_"},
        {"priority": 150, "category_name": "Задачи универсалки", "transfer_action": "Переносим пакетом", "condition_type": "EXACT_EQUALS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "unInfoobmenTask;unInfoobmenTaskList", "comment": ""},
        {"priority": 160, "category_name": "Классы утилит", "transfer_action": "Переносим пакетом", "condition_type": "EXACT_EQUALS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "cmsUtil", "comment": "(Дублирует «исключение» на 15-м приоритете — оставлено здесь для наглядности или если будут другие «util»)"},
        {"priority": 170, "category_name": "Класс соответствий", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "config;corr;sootvet;catConversion", "comment": "Имя начинается с config, corr, sootvet"},
        {"priority": 180, "category_name": "Класс соответствий", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "соответ", "comment": "Если в описании есть слово «соответ»"},
        {"priority": 190, "category_name": "Класс отчётов", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "отчет;report;Report;REPORT_", "comment": "Имя содержит «отчет»"},
        {"priority": 191, "category_name": "Класс отчётов", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "REPORT_", "comment": ""},
        {"priority": 195, "category_name": "Класс отчётов", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "протокол", "comment": "Описание содержит «протокол»"},
        {"priority": 200, "category_name": "Класс статусов", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "status", "comment": "Имя содержит «status»"},
        {"priority": 210, "category_name": "Классы связок", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "link", "comment": "Имя начинается с «link»"},
        {"priority": 211, "category_name": "Классы связок", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "связка;Класс связки;связки", "comment": "Любой из слов «связка», «Класс связки», «связки»"},
        {"priority": 212, "category_name": "Классы связок", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "MSP_", "comment": "map содержит «MSP_»"},
        {"priority": 220, "category_name": "Функциональные классы", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "kcr_;wm;mse;hcs;list;TAMBOV_;tsr;uchet;importDostUch;individProgram;verschiedeneLeute;workerEvent101Info;zagsPC;zapVihForm", "comment": "Имя начинается с «kcr_» или «wm»"},
        {"priority": 221, "category_name": "Функциональные классы", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "кцр;ТСР", "comment": ""},
        {"priority": 222, "category_name": "Функциональные классы", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "egisso;ticketSko", "comment": ""},
        {"priority": 225, "category_name": "Функциональные классы", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "WM_;HCS;HIST", "comment": "(Новый) если карта начинается с WM_ (например, WM_APPEAL_EF)"},
        {"priority": 230, "category_name": "Классы ВС", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "sved;smev", "comment": "Имя начинается с «sved» или «smev»"},
        {"priority": 231, "category_name": "Классы ВС", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "Родительский класс", "condition_value": "smev", "comment": ""},
        {"priority": 232, "category_name": "Классы ВС", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "Fgis;response;rsChildBirthDateInfo", "comment": ""},
        {"priority": 240, "category_name": "Реестры/регистры", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "реестр;регистр", "comment": "Описание содержит «реестр», «регистр»"},
        {"priority": 241, "category_name": "Реестры/регистры", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "REGISTER_;REESTR;EGR_;EGRN;POST;SPISOK_DOUBLE_NAZ_3TO7;stores_VIP_L;DATE_GIVEUDOST_RADIATION", "comment": "map содержит REGISTER_, REESTR, EGR_, EGRN"},
        {"priority": 250, "category_name": "Документы", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "МСП;документ;сведения", "comment": "Любое из слов «МСП», «документ», «сведения»"},
        {"priority": 251, "category_name": "Документы", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "DOC;CERTIFICATE;PASSPORT;ACT_;EDK_", "comment": "map содержит «DOC», «CERTIFICATE», «PASSPORT», «ACT_», «EDK_»"},
        {"priority": 260, "category_name": "Социальные услуги", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "услуга;ЕДК;абилит", "comment": "Любое из слов «услуга», «ЕДК»"},
        {"priority": 261, "category_name": "Социальные услуги", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "SOC_;BENEFIT;SOC;USE_;USON_;FREE_SEATS", "comment": "map содержит «SOC_» или «BENEFIT»"},
        {"priority": 271, "category_name": "ЖКХ", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "hcs;jkh;gku", "comment": "(Новый) для calcPayGku, ioHCSImport, и т.д."},
        {"priority": 272, "category_name": "ЖКХ", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "HCS;JKH;GKU", "comment": "(При желании дублировать по map)"},
        {"priority": 275, "category_name": "Классы ПФР", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "pfr", "comment": "(Новый) для pfrData..., pfrImport"},
        {"priority": 276, "category_name": "Классы ПФР", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "PFR;FSD", "comment": "(Если нужно)"},
        {"priority": 280, "category_name": "Классы SMEV/EPGU", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "smev;epgu;SMEV;twinDataSnils;ElApplicationMessageHistory", "comment": "(Новый) AddressAttrFromSmevEPGU, EPGUProcessPetition, и т.д."},
        {"priority": 281, "category_name": "Классы SMEV/EPGU", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "SV_;EPGU_;SMEV", "comment": ""},
        {"priority": 282, "category_name": "Классы SMEV/EPGU", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "СМЭВ", "comment": ""},
        {"priority": 283, "category_name": "Классы SMEV/EPGU", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "Родительский класс", "condition_value": "smev3", "comment": ""},
        {"priority": 285, "category_name": "Финансы/расчёты", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "calc;pay;fin;budget;money;avans", "comment": "(Новый) calcPayGku, avansProc, financeOGBD etc."},
        {"priority": 290, "category_name": "Записи на приём", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "apt", "comment": "(Новый) aptAppointment, aptBaseConfig"},
        {"priority": 295, "category_name": "Справочник не ЭСРН", "transfer_action": "Не переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "car;yacht;buildCompany;buildings;catParticip;eDonorKrovi", "comment": "(Новый) carOwner, Cars, eaYacht, etc."},
        {"priority": 296, "category_name": "Аналитические классы", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "analy", "comment": "(Новый) analyticReportInfoFile"},
        {"priority": 297, "category_name": "Классы FNS/NDFL (налоги)", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "fns;ndfl;doh;envd;eshn;usn;nal;upl;predpr;vozv", "comment": "(Новый) fnsIncomeIndividualInfo, ndfl3dohRf"},
        {"priority": 298, "category_name": "Классы настроек/конфига", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "config;setting;query;RecordsStructure;ExpAddParams;optRun;Synch;IMPORT_Settings", "comment": "(Новый) attrsConfigForExtQuery, extQueryClassConfig, etc."},
        {"priority": 299, "category_name": "Справочник не ЭСРН", "transfer_action": "Не переносим", "condition_type": "CONTAINS", "condition_field": "Родительский класс", "condition_value": "tstVehicle", "comment": ""},
        {"priority": 300, "category_name": "Справочник не ЭСРН", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "SKO_;E_;MO_;AO_;OWNER;PATIENT;SKU_;ST_;VB_;Репициент", "comment": ""},
        {"priority": 301, "category_name": "Справочник не ЭСРН", "transfer_action": "Не переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "prg;salon;schedule;teach;tst;ugra;csv_users;directionPlace;efrOks;emplExt;frguService;helpOverBarriers", "comment": ""},
        {"priority": 303, "category_name": "Класс отчетов", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "отчет", "comment": ""},
        {"priority": 302, "category_name": "Класс отчетов", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "DATA_;DECISION_", "comment": ""},
        {"priority": 350, "category_name": "Справочники", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_DESCRIPTION", "condition_value": "Справочник", "comment": ""},
        {"priority": 351, "category_name": "Справочники", "transfer_action": "Переносим", "condition_type": "STARTS_WITH", "condition_field": "MSSQL_SXCLASS_NAME", "condition_value": "eftt;ogbd;list;type;vid;reason;table;place;category;home;spr;catalog;classList;emplExt;familyInfo31;for_making_a_decision_kompens;gorodaNaGaz;gspCategory;laborActivity101Info;lifeSituation;lifecycleRecords;detServiceData;nonMSPLKNPD;periodError;name;petAttachMfc;PurposeBuilding;rayCityMse;reconciliationTicketsView;regNotifyRecipients;regStandartPloshchad;REMOTE_IDENTIFICATION;requestProlongation;restricFundamentalCat;seasonHeating;sed_in_org_type", "comment": ""},
        {"priority": 352, "category_name": "Справочники", "transfer_action": "Переносим", "condition_type": "CONTAINS", "condition_field": "MSSQL_SXCLASS_MAP", "condition_value": "LIST_;TYPE_;TABLE_;CAT_;HOME_", "comment": ""},
        {"priority": 999, "category_name": "Не удалось определить", "transfer_action": "Нет данных", "condition_type": "ALWAYS_TRUE", "condition_field": "-", "condition_value": "", "comment": "«заглушка», если класс не попал ни под одно правило"}
    ]
    
    # Добавляем правила в базу данных
    for rule_data in rules:
        rule = TransferRule(**rule_data)
        db.session.add(rule)
    
    db.session.commit()
    print(f"Инициализировано {len(rules)} правил переноса данных.")

if __name__ == "__main__":
    setup_database()
    init_transfer_rules()