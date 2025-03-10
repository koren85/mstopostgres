
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
                progress += 20;
                if (progress <= 100) {
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
                // Проверяем Content-Type ответа
                const contentType = response.headers.get("content-type");
                if (contentType && contentType.indexOf("application/json") !== -1) {
                    return response.json().then(data => {
                        console.log(`Данные ответа получены: ${JSON.stringify(data)}`);
                        return {
                            status: response.status,
                            data: data
                        };
                    });
                } else {
                    // Если ответ не JSON, получаем текст и возвращаем ошибку
                    return response.text().then(text => {
                        console.error(`Получен не JSON ответ: ${text.substring(0, 100)}...`);
                        return {
                            status: response.status,
                            data: { error: "Сервер вернул ошибку. Проверьте логи сервера." }
                        };
                    });
                }
            })
            .then(result => {
                console.log(`Обрабатываем результат: ${JSON.stringify(result)}`);

                // Останавливаем анимацию прогресса
                clearInterval(progressInterval);
                progressBar.style.width = '100%';
                progressBar.setAttribute('aria-valuenow', 100);

                hideProgress();
                if (result.status === 200) {
                    if (result.data.success) {
                        showResult(result.data.message, 'success');
                    } else {
                        showResult(`Ошибка: ${result.data.error}`, 'danger');
                    }
                } else {
                    const errorMessage = result.data.error || 'Неизвестная ошибка';
                    const errorDetails = result.data.error_type ? ` (${result.data.error_type})` : '';
                    showResult(`Ошибка при загрузке: ${errorMessage}${errorDetails}`, 'danger');

                    // Выводим дополнительную информацию в консоль для отладки
                    console.error('Подробная информация об ошибке:', result.data);
                }

                // Очистить форму после успешной загрузки
                uploadForm.reset();
            })
            .catch(err => {
                console.log(`Ошибка: ${err}`);
                // Останавливаем анимацию прогресса
                clearInterval(progressInterval);
                hideProgress();
                showResult(`Ошибка при загрузке: ${err}`, 'danger');
            });
        });
    }

    // Функция для отображения индикатора загрузки
    function showProgress() {
        resultDiv.classList.add('d-none');
        progressContainer.classList.remove('d-none');
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', 0);
    }

    // Функция для скрытия индикатора загрузки
    function hideProgress() {
        progressContainer.classList.add('d-none');
    }

    // Функция для отображения результата
    function showResult(message, type) {
        resultDiv.textContent = message;
        resultDiv.className = `alert alert-${type} mt-3`;
        resultDiv.classList.remove('d-none');
    }
});
