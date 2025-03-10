document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM загружен, скрипт upload.js инициализирован');

    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('excelFile');
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
                progress += 5;
                if (progress <= 90) {
                    progressBar.style.width = `${progress}%`;
                    progressBar.setAttribute('aria-valuenow', progress);
                    console.log(`Прогресс анимации: ${progress}%`);
                }
            }, 500);

            console.log(`Файл выбран: ${file.name}, размер: ${file.size} байт, тип: ${file.type}`);
            console.log('Начинаем отправку запроса на /upload');

            // Отправляем запрос
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log(`Получен ответ. Статус: ${response.status}`);
                if (!response.ok) {
                    return response.json().then(data => {
                        throw new Error(data.error || 'Неизвестная ошибка');
                    });
                }
                return response.json();
            })
            .then(data => {
                console.log(`Данные ответа получены: ${JSON.stringify(data)}`);

                // Останавливаем анимацию прогресса
                clearInterval(progressInterval);
                progressBar.style.width = '100%';
                progressBar.setAttribute('aria-valuenow', 100);

                // Отображаем сообщение об успехе
                showResult(`Файл успешно загружен и обработан. ${data.message}`, 'success');

                // Очистить форму после успешной загрузки
                uploadForm.reset();
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
        resultDiv.classList.add('d-none');
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', 0);
    }

    // Функция для отображения результата
    function showResult(message, type) {
        progressContainer.classList.add('d-none');
        resultDiv.classList.remove('d-none');
        resultDiv.className = `alert alert-${type} mt-3`;
        resultDiv.textContent = message;
    }
});