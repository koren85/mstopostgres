/**
 * Функционал для копирования признаков из выбранного источника
 */
document.addEventListener('DOMContentLoaded', function() {
    // Элементы DOM
    const copyFromSourceBtn = document.getElementById('copyFromSourceBtn');
    const applySourceBtn = document.getElementById('applySourceBtn');
    const historicalSourcesTable = document.getElementById('historical-sources-table');
    const analysisSourcesTable = document.getElementById('analysis-sources-table');
    
    // Текущий выбранный источник
    let selectedSource = null;
    
    // Получаем batch_id из URL
    const batchId = window.location.pathname.split('/').pop();
    
    // Обработчик нажатия на кнопку "Установить как в источнике"
    copyFromSourceBtn.addEventListener('click', function() {
        // Показываем модальное окно
        const modal = new bootstrap.Modal(document.getElementById('copyFromSourceModal'));
        modal.show();
        
        // Загружаем список источников
        loadSources();
    });
    
    // Загрузка списка источников
    function loadSources() {
        // Очищаем выбор
        selectedSource = null;
        applySourceBtn.disabled = true;
        
        // Показываем индикатор загрузки
        historicalSourcesTable.querySelector('tbody').innerHTML = '<tr><td colspan="5" class="text-center">Загрузка источников...</td></tr>';
        analysisSourcesTable.querySelector('tbody').innerHTML = '<tr><td colspan="5" class="text-center">Загрузка источников...</td></tr>';
        
        // Запрашиваем список источников
        fetch(`/api/get_available_sources?current_batch_id=${batchId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Заполняем таблицы источников
                    fillSourcesTable(historicalSourcesTable, data.sources.historical, 'historical');
                    fillSourcesTable(analysisSourcesTable, data.sources.analysis, 'analysis');
                } else {
                    showError('Ошибка при загрузке источников: ' + data.error);
                }
            })
            .catch(error => {
                showError('Ошибка при загрузке источников: ' + error);
            });
    }
    
    // Заполнение таблицы источников
    function fillSourcesTable(table, sources, sourceType) {
        const tbody = table.querySelector('tbody');
        
        if (sources.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center">Нет доступных источников</td></tr>';
            return;
        }
        
        // Форматируем дату
        function formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleString('ru-RU');
        }
        
        // Создаем строки таблицы
        tbody.innerHTML = sources.map(source => `
            <tr data-batch-id="${source.batch_id}" data-source-type="${sourceType}" style="cursor: pointer;">
                <td>
                    <input type="radio" name="source_selection" class="form-check-input source-select" 
                           data-batch-id="${source.batch_id}" 
                           data-source-type="${sourceType}">
                </td>
                <td>${source.source_system}</td>
                <td>${source.file_name}</td>
                <td>${source.records_count}</td>
                <td>${formatDate(source.upload_date)}</td>
            </tr>
        `).join('');
        
        // Добавляем обработчики выбора источника
        tbody.querySelectorAll('tr').forEach(row => {
            row.addEventListener('click', function() {
                const radio = this.querySelector('input[type="radio"]');
                radio.checked = true;
                
                // Обновляем выбранный источник
                selectedSource = {
                    batch_id: this.dataset.batchId,
                    source_type: this.dataset.sourceType
                };
                
                // Разблокируем кнопку применения
                applySourceBtn.disabled = false;
                
                // Снимаем выделение с других строк
                document.querySelectorAll('input[name="source_selection"]').forEach(input => {
                    if (input !== radio) {
                        input.checked = false;
                    }
                });
            });
        });
    }
    
    // Обработчик нажатия на кнопку "Установить признак"
    applySourceBtn.addEventListener('click', function() {
        if (!selectedSource) {
            showError('Выберите источник');
            return;
        }
        
        // Получаем текущие фильтры
        const filters = {
            status: document.getElementById('statusFilter')?.value,
            search: document.getElementById('searchInput')?.value,
            discrepancy_filter: document.getElementById('discrepancyFilter')?.value,
            card_filter: document.getElementById('cardFilterInput')?.value
        };
        
        // Показываем индикатор загрузки
        applySourceBtn.disabled = true;
        applySourceBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Применение...';
        
        // Отправляем запрос на копирование признаков
        fetch('/api/copy_priznaks_from_source', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                current_batch_id: batchId,
                source_batch_id: selectedSource.batch_id,
                source_type: selectedSource.source_type,
                filters: filters
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Закрываем модальное окно
                bootstrap.Modal.getInstance(document.getElementById('copyFromSourceModal')).hide();
                
                // Показываем сообщение об успехе
                showSuccess(`Признаки успешно скопированы. ${data.message}`);
                
                // Перезагружаем страницу через 2 секунды
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            } else {
                showError('Ошибка при копировании признаков: ' + data.error);
                applySourceBtn.disabled = false;
                applySourceBtn.innerHTML = 'Установить признак';
            }
        })
        .catch(error => {
            showError('Ошибка при копировании признаков: ' + error);
            applySourceBtn.disabled = false;
            applySourceBtn.innerHTML = 'Установить признак';
        });
    });
    
    // Функция для отображения ошибки
    function showError(message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger alert-dismissible fade show';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        // Добавляем сообщение в начало страницы
        document.querySelector('.container').prepend(alertDiv);
        
        // Автоматически скрываем через 5 секунд
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
    
    // Функция для отображения сообщения об успехе
    function showSuccess(message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-success alert-dismissible fade show';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        // Добавляем сообщение в начало страницы
        document.querySelector('.container').prepend(alertDiv);
        
        // Автоматически скрываем через 5 секунд
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}); 