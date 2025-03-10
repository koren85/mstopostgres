
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM загружен, скрипт upload.js инициализирован');
    
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const sourceSystemInput = document.getElementById('sourceSystem');
    const submitButton = document.getElementById('submitButton');
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
            
            // Показываем индикатор загрузки и скрываем результат
            showProgress();
            console.log('Индикатор загрузки показан');
            console.log(`Файл выбран: ${file.name}, размер: ${file.size} байт, тип: ${file.type}`);
            
            // Создаем FormData и добавляем данные
            const formData = new FormData();
            formData.append('file', file);
            formData.append('source_system', sourceSystem);
            
            // Отправляем запрос
            console.log('Начинаем отправку запроса на /upload');
            
            // Запускаем анимацию прогресса
            startProgressAnimation();
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log(`Получен ответ. Статус: ${response.status}`);
                return response.json().then(data => ({status: response.status, data: data}));
            })
            .then(result => {
                console.log(`Данные ответа получены: ${JSON.stringify(result.data)}`);
                console.log(`Обрабатываем результат: ${JSON.stringify(result)}`);
                
                // Останавливаем анимацию прогресса
                stopProgressAnimation();
                
                if (result.status === 200) {
                    showResult(`Файл успешно загружен и обработан. Обработано ${result.data.message}`, 'success');
                    // Опционально: очистить форму после успешной загрузки
                    uploadForm.reset();
                } else {
                    showResult(`Ошибка при загрузке: ${result.data.error}`, 'danger');
                }
            })
            .catch(err => {
                console.log(`Ошибка: ${err}`);
                // Останавливаем анимацию прогресса
                stopProgressAnimation();
                showResult(`Ошибка при загрузке: ${err}`, 'danger');
            });
        });
    }
    
    // Функция для отображения индикатора загрузки
    function showProgress() {
        progressContainer.classList.remove('d-none');
        progressBar.style.width = '0%';
        resultDiv.classList.add('d-none');
        submitButton.disabled = true;
    }
    
    // Функция для отображения результата
    function showResult(message, type) {
        progressContainer.classList.add('d-none');
        resultDiv.classList.remove('d-none');
        resultDiv.className = `alert alert-${type} mt-3`;
        resultDiv.textContent = message;
        submitButton.disabled = false;
    }
    
    // Переменная для хранения ID интервала анимации
    let progressAnimationInterval = null;
    
    // Функция для запуска анимации прогресса
    function startProgressAnimation() {
        let progress = 0;
        progressAnimationInterval = setInterval(() => {
            // Увеличиваем прогресс, но не до 100% (максимум 90%)
            if (progress < 90) {
                progress += Math.random() * 5;
                progress = Math.min(progress, 90);
                progressBar.style.width = `${progress}%`;
                console.log(`Прогресс анимации: ${Math.round(progress)}%`);
            }
        }, 300);
    }
    
    // Функция для остановки анимации прогресса
    function stopProgressAnimation() {
        if (progressAnimationInterval) {
            clearInterval(progressAnimationInterval);
            progressAnimationInterval = null;
            // Устанавливаем 100% по завершении
            progressBar.style.width = '100%';
            // Через секунду скрываем прогресс
            setTimeout(() => {
                progressContainer.classList.add('d-none');
            }, 1000);
        }
    }
});
