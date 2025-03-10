
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM загружен, скрипт upload.js инициализирован');
    
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('excelFile'); // Исправлено с fileInput на excelFile
    const sourceSystemInput = document.getElementById('sourceSystem');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const resultDiv = document.getElementById('uploadResult');
    
    if (uploadForm) {
        console.log('Форма uploadForm найдена, добавляем обработчик событий');
        
        uploadForm.addEventListener('submit', function(event) {
            event.preventDefault();
            console.log('Форма отправлена, предотвращаем стандартное поведение');
            
            const file = fileInput.files[0];
            if (!file) {
                showResult('Пожалуйста, выберите файл', 'danger');
                return;
            }
            
            if (!file.name.endsWith('.xlsx')) {
                showResult('Поддерживаются только файлы Excel (.xlsx)', 'danger');
                return;
            }
            
            const sourceSystem = sourceSystemInput.value.trim();
            if (!sourceSystem) {
                showResult('Пожалуйста, укажите источник данных', 'danger');
                return;
            }
            
            const formData = new FormData(uploadForm);
            
            // Отображаем индикатор загрузки
            showProgress();
            console.log('Индикатор загрузки показан');
            
            // Анимация прогресса загрузки
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress += 20;
                if (progress <= 100) {
                    progressBar.style.width = `${progress}%`;
                    progressBar.setAttribute('aria-valuenow', progress);
                    console.log(`Прогресс анимации: ${progress}%`);
                }
            }, 1000);
            
            console.log(`Файл выбран: ${file.name}, размер: ${file.size} байт, тип: ${file.type}`);
            console.log('Начинаем отправку запроса на /upload');
            
            // Отправляем запрос
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log(`Получен ответ. Статус: ${response.status}`);
                return response.json().then(data => {
                    return {
                        status: response.status,
                        data: data
                    };
                });
            })
            .then(result => {
                console.log(`Данные ответа получены: ${JSON.stringify(result.data)}`);
                console.log(`Обрабатываем результат: ${JSON.stringify(result)}`);
                
                // Останавливаем анимацию прогресса
                clearInterval(progressInterval);
                
                if (result.status === 200) {
                    showResult(`Файл успешно загружен и обработан. ${result.data.message}`, 'success');
                    // Очистить форму после успешной загрузки
                    uploadForm.reset();
                } else {
                    showResult(`Ошибка при загрузке: ${result.data.error}`, 'danger');
                }
            })
            .catch(err => {
                console.log(`Ошибка: ${err}`);
                // Останавливаем анимацию прогресса
                clearInterval(progressInterval);
                showResult(`Ошибка при загрузке: ${err}`, 'danger');
            });
        });
    }
    
    // Функция для отображения индикатора загрузки
    function showProgress() {
        progressContainer.classList.remove('d-none');
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', 0);
        resultDiv.classList.add('d-none');
        // Отключаем кнопку отправки, если она есть
        const submitButton = document.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
        }
    }
    
    // Функция для отображения результата
    function showResult(message, type) {
        progressContainer.classList.add('d-none');
        resultDiv.classList.remove('d-none');
        resultDiv.className = `alert alert-${type} mt-3`;
        resultDiv.textContent = message;
        
        // Включаем кнопку отправки, если она есть
        const submitButton = document.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = false;
        }
    }
    
    // Функция для остановки анимации прогресса (для предотвращения возможных утечек памяти)
    function stopProgressAnimation() {
        // Предполагается, что эта функция вызывается из обработчиков промисов
        const submitButton = document.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = false;
        }
    }
});
