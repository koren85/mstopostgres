/**
 * Скрипт для отображения всплывающих подсказок с детальной информацией о записи
 * при наведении на строки в таблице результатов анализа
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Инициализация модуля всплывающих подсказок для записей...');
    
    // Создаем элемент всплывающей подсказки, если его еще нет
    let tooltip = document.getElementById('record-details-tooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'record-details-tooltip';
        tooltip.className = 'record-tooltip';
        document.body.appendChild(tooltip);
        console.log('Создан элемент всплывающей подсказки');
    }
    
    // Удаляем существующие стили, если они есть
    const existingStyle = document.getElementById('record-tooltip-styles');
    if (existingStyle) {
        existingStyle.remove();
        console.log('Удалены существующие стили для всплывающих подсказок');
    }
    
    // Добавляем стили для всплывающей подсказки
    const styleElement = document.createElement('style');
    styleElement.id = 'record-tooltip-styles';
    styleElement.textContent = `
        .record-tooltip {
            position: absolute;
            display: none;
            background-color: #ffffff;
            border: 2px solid #007bff;
            border-radius: 6px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
            padding: 15px;
            z-index: 1000;
            min-width: 350px;
            max-width: 500px;
            font-size: 0.9rem;
            opacity: 0;
            transition: opacity 0.2s ease;
            color: #333333;
            font-family: Arial, sans-serif;
        }
        
        .record-tooltip.visible {
            display: block;
            opacity: 1;
        }
        
        .record-tooltip-header {
            font-weight: bold;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #dee2e6;
            font-size: 16px;
            color: #000000;
            text-align: center;
        }
        
        .record-tooltip-row {
            display: flex;
            margin-bottom: 8px;
            padding-bottom: 4px;
            border-bottom: 1px dotted #eeeeee;
        }
        
        .record-tooltip-label {
            flex: 0 0 45%;
            font-weight: 600;
            color: #495057;
            font-size: 14px;
            padding-right: 10px;
        }
        
        .record-tooltip-value {
            flex: 0 0 55%;
            word-break: break-word;
            color: #212529;
            font-size: 14px;
        }
        
        .record-tooltip-loading {
            text-align: center;
            padding: 15px;
            color: #6c757d;
            font-size: 14px;
            font-weight: 500;
        }
        
        .record-tooltip-error {
            color: #dc3545;
            text-align: center;
            padding: 15px;
            font-size: 14px;
            font-weight: 500;
            background-color: #f8d7da;
            border-radius: 4px;
        }
        
        .record-tooltip .btn {
            padding: 3px 8px;
            font-size: 12px;
            margin-right: 5px;
            text-decoration: none;
            display: inline-block;
            margin-bottom: 4px;
        }
        
        .record-tooltip .btn-outline-primary {
            color: #007bff;
            border-color: #007bff;
        }
        
        .record-tooltip .btn-outline-primary:hover {
            color: #fff;
            background-color: #007bff;
        }
        
        .record-tooltip .btn-outline-info {
            color: #17a2b8;
            border-color: #17a2b8;
        }
        
        .record-tooltip .btn-outline-info:hover {
            color: #fff;
            background-color: #17a2b8;
        }
    `;
    document.head.appendChild(styleElement);
    console.log('Добавлены стили для всплывающей подсказки');
    
    // Переменная для хранения текущего таймера
    let showTimeout;
    let hideTimeout;
    // Добавляем переменную для отслеживания замирания тултипа
    let tooltipFrozen = false;
    let lastResultId = null;
    
    // Находим все строки в таблице результатов анализа и добавляем обработчики событий
    const tableRows = document.querySelectorAll('#results-table tbody tr');
    console.log(`Найдено ${tableRows.length} строк в таблице результатов анализа`);
    
    tableRows.forEach((row, index) => {
        // Получаем ID результата анализа из чекбокса
        const checkbox = row.querySelector('.result-checkbox');
        if (!checkbox) {
            console.log(`Строка #${index+1}: чекбокс не найден`);
            return;
        }
        
        const resultId = checkbox.dataset.id;
        if (!resultId) {
            console.log(`Строка #${index+1}: ID результата не найден в data-id`);
            return;
        }
        
        console.log(`Строка #${index+1}: найден ID результата ${resultId}`);
        
        // Добавляем атрибуты данных к строке
        row.dataset.resultId = resultId;
        
        // Получаем первые три ячейки в строке (Описание, Имя класса, Таблица)
        const firstThreeCells = Array.from(row.querySelectorAll('td')).slice(1, 4);
        console.log(`Строка #${index+1}: найдено ${firstThreeCells.length} ячеек для добавления всплывающих подсказок`);
        
        // Добавляем обработчики событий только для первых трёх ячеек
        firstThreeCells.forEach((cell, cellIndex) => {
            // Добавляем стиль, чтобы показать, что на эти ячейки можно навести для получения дополнительной информации
            cell.style.cursor = 'help';
            // Для отладки: добавляем границу, чтобы видеть, к каким ячейкам применены обработчики
            // cell.style.border = '1px dashed #007bff';
            
            cell.addEventListener('mouseenter', (event) => {
                // Передаем ID результата из строки в обработчик
                handleCellMouseEnter(event, resultId);
            });
            cell.addEventListener('mouseleave', handleCellMouseLeave);
            cell.addEventListener('mousemove', handleCellMouseMove);
            
            console.log(`Строка #${index+1}, Ячейка #${cellIndex+1}: обработчики добавлены`);
        });
    });
    
    // Функция для безопасного позиционирования подсказки внутри видимой области экрана
    function positionTooltipSafely(mouseX, mouseY) {
        // Размеры области просмотра
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        
        // Размеры подсказки
        const tooltipWidth = tooltip.offsetWidth || 350; // Используем значение по умолчанию, если подсказка еще не отображена
        const tooltipHeight = tooltip.offsetHeight || 200;
        
        // Начальные координаты для подсказки
        let top = window.scrollY + mouseY + 15; // 15px ниже курсора
        let left = window.scrollX + mouseX + 5; // 5px правее курсора
        
        // Проверяем, чтобы подсказка не выходила за правый край
        if (left + tooltipWidth > window.scrollX + viewportWidth) {
            left = window.scrollX + viewportWidth - tooltipWidth - 10; // 10px отступ от края
        }
        
        // Проверяем, чтобы подсказка не выходила за нижний край
        if (top + tooltipHeight > window.scrollY + viewportHeight) {
            top = window.scrollY + mouseY - tooltipHeight - 10; // Показываем над курсором с отступом
        }
        
        // Проверяем, чтобы подсказка не выходила за верхний край
        if (top < window.scrollY) {
            top = window.scrollY + 10; // Отступ от верхнего края
        }
        
        // Проверяем, чтобы подсказка не выходила за левый край
        if (left < window.scrollX) {
            left = window.scrollX + 10; // Отступ от левого края
        }
        
        // Применяем вычисленные координаты
        tooltip.style.top = `${top}px`;
        tooltip.style.left = `${left}px`;
        
        // Возвращаем вычисленные координаты для отладки
        return { top, left };
    }
    
    // Обработчик наведения мыши на ячейку
    function handleCellMouseEnter(event, resultId) {
        const cell = event.currentTarget;
        
        console.log(`Наведение на ячейку для записи с ID ${resultId}`);
        
        // Сбрасываем таймер скрытия, если он есть
        if (hideTimeout) {
            clearTimeout(hideTimeout);
            hideTimeout = null;
        }
        
        // Получаем координаты курсора относительно страницы
        const mouseX = event.clientX;
        const mouseY = event.clientY;
        
        // Проверяем, не показываем ли уже тултип для этой же записи
        if (resultId === lastResultId && tooltip.classList.contains('visible')) {
            // Если тултип уже показан для этой записи, просто выходим
            return;
        }
        
        // Устанавливаем таймер перед показом, чтобы избежать моргания
        showTimeout = setTimeout(() => {
            // Устанавливаем позицию подсказки относительно курсора
            const position = positionTooltipSafely(mouseX, mouseY);
            
            console.log(`Устанавливаем позицию подсказки: top=${position.top}px, left=${position.left}px`);
            
            // Показываем индикатор загрузки
            tooltip.innerHTML = '<div class="record-tooltip-loading"><i class="bi bi-hourglass-split me-2"></i>Загрузка данных...</div>';
            tooltip.classList.add('visible');
            
            // Запоминаем текущий ID результата
            lastResultId = resultId;
            
            // Устанавливаем флаг замирания на 1 секунду
            tooltipFrozen = true;
            setTimeout(() => {
                tooltipFrozen = false;
                console.log('Тултип разморожен и может следовать за курсором');
            }, 3000);
            
            console.log(`Подсказка отображена с индикатором загрузки и заморожена на 3 секунды`);
            
            // Получаем данные о записи
            fetchRecordDetails(resultId);
        }, 300); // Уменьшаем задержку до 300 мс
    }
    
    // Обработчик ухода мыши с ячейки
    function handleCellMouseLeave(event) {
        // Сбрасываем таймер показа, если он есть
        if (showTimeout) {
            clearTimeout(showTimeout);
            showTimeout = null;
        }
        
        // Устанавливаем таймер перед скрытием
        hideTimeout = setTimeout(() => {
            tooltip.classList.remove('visible');
            lastResultId = null;
            console.log('Подсказка скрыта');
        }, 300); // Задержка в 300 мс
    }
    
    // Обработчик движения мыши в ячейке
    function handleCellMouseMove(event) {
        // Обновляем позицию только если подсказка уже видима И не заморожена
        if (tooltip.classList.contains('visible') && !tooltipFrozen) {
            const mouseX = event.clientX;
            const mouseY = event.clientY;
            
            // Обновляем позицию подсказки относительно курсора с небольшой задержкой
            // для плавности движения
            requestAnimationFrame(() => {
                positionTooltipSafely(mouseX, mouseY);
            });
        }
    }
    
    // Добавляем обработчики для самой подсказки, чтобы она не исчезала при наведении
    tooltip.addEventListener('mouseenter', () => {
        // Отменяем скрытие при наведении на подсказку
        if (hideTimeout) {
            clearTimeout(hideTimeout);
            hideTimeout = null;
            console.log('Отменено скрытие подсказки при наведении на неё');
        }
    });
    
    tooltip.addEventListener('mouseleave', () => {
        // Скрываем подсказку при уходе мыши
        hideTimeout = setTimeout(() => {
            tooltip.classList.remove('visible');
            console.log('Подсказка скрыта после ухода с неё');
        }, 300);
    });
    
    // Функция для получения данных о записи
    function fetchRecordDetails(resultId) {
        console.log(`Запрос данных о записи с ID ${resultId}`);
        
        fetch(`/api/record_details/${resultId}`)
            .then(response => {
                console.log(`Получен ответ от сервера для ID ${resultId}, статус: ${response.status}`);
                if (!response.ok) {
                    throw new Error(`Ошибка HTTP: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log(`Получены данные о записи:`, data);
                
                if (data.success) {
                    console.log(`Успешно получены данные:`, data.details);
                    displayRecordDetails(data.details);
                } else {
                    throw new Error(data.error || 'Не удалось получить данные о записи');
                }
            })
            .catch(error => {
                console.error('Ошибка при получении данных о записи:', error);
                tooltip.innerHTML = `
                    <div class="record-tooltip-error">
                        <i class="bi bi-exclamation-triangle-fill me-2"></i>
                        Ошибка при получении данных: ${error.message}
                    </div>
                `;
            });
    }
    
    // Функция для отображения данных в подсказке
    function displayRecordDetails(details) {
        console.log('Формирование содержимого подсказки с данными:', details);
        
        let tooltipContent = `
            <div class="record-tooltip-header">
                ${details.mssql_sxclass_name || 'Запись'} - Детальная информация
            </div>
        `;
        
        // Добавляем строки с данными с проверкой на пустые значения
        tooltipContent += createTooltipRow('Дата создания', details.created_date);
        tooltipContent += createTooltipRow('Создал', details.created_by);
        tooltipContent += createTooltipRow('Дата изменения', details.modified_date);
        tooltipContent += createTooltipRow('Изменил', details.modified_by);
        tooltipContent += createTooltipRow('Пути папок в консоли', details.folder_paths);
        
        const hasObjects = details.object_count && parseInt(details.object_count) > 0 ? 'Да' : 'Нет';
        tooltipContent += createTooltipRow('Наличие объектов', hasObjects);
        tooltipContent += createTooltipRow('Количество объектов', details.object_count);
        tooltipContent += createTooltipRow('Дата создания последнего объекта', details.last_object_created);
        tooltipContent += createTooltipRow('Дата последнего изменения', details.last_object_modified);
        
        // Добавляем ссылки на контекст, если есть базовый URL
        if (details.base_url) {
            let linksHtml = '';
            
            // Ссылка на объект в контексте (если есть a_ouid)
            if (details.a_ouid && details.a_ouid !== 'Нет данных') {
                const objectUrl = `${details.base_url}admin/edit.htm?id=${details.a_ouid}%40SXClass`;
                linksHtml += `<div><a href="${objectUrl}" target="_blank" class="btn btn-sm btn-outline-primary mt-1">
                    <i class="bi bi-box-arrow-up-right"></i> Перейти к объекту</a></div>`;
            }
            
            // Ссылка на объекты класса
            if (details.mssql_sxclass_name && details.mssql_sxclass_name !== 'Нет данных') {
                const classObjectsUrl = `${details.base_url}admin/objectsofclass.htm?cls=${details.mssql_sxclass_name}`;
                linksHtml += `<div><a href="${classObjectsUrl}" target="_blank" class="btn btn-sm btn-outline-info mt-1">
                    <i class="bi bi-boxes"></i> Объекты класса</a></div>`;
            }
            
            if (linksHtml) {
                tooltipContent += `
                    <div class="record-tooltip-row">
                        <div class="record-tooltip-label">Ссылки:</div>
                        <div class="record-tooltip-value">${linksHtml}</div>
                    </div>
                `;
            }
        }
        
        // Обновляем содержимое подсказки
        console.log('Итоговое содержимое подсказки:', tooltipContent);
        tooltip.innerHTML = tooltipContent;
    }
    
    // Вспомогательная функция для создания строки в подсказке
    function createTooltipRow(label, value) {
        // Проверяем, есть ли значение
        if (!value || value === 'null' || value === 'undefined' || value === 'Нет данных') {
            value = 'Нет данных';
        }
        
        return `
            <div class="record-tooltip-row">
                <div class="record-tooltip-label">${label}:</div>
                <div class="record-tooltip-value">${value}</div>
            </div>
        `;
    }
    
    console.log('Модуль всплывающих подсказок инициализирован');
}); 