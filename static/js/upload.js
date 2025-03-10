
document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('uploadForm');
    const uploadProgress = document.getElementById('uploadProgress');
    const progressBar = uploadProgress.querySelector('.progress-bar');
    const uploadResult = document.getElementById('uploadResult');
    const errorDetails = document.getElementById('errorDetails');
    const errorDetailsText = document.getElementById('errorDetailsText');
    const uploadStatus = document.getElementById('uploadStatus');
    
    // Функция для обновления статуса загрузки
    function updateStatus(message) {
        if (uploadStatus) {
            const timestamp = new Date().toLocaleTimeString();
            uploadStatus.textContent += `\n[${timestamp}] ${message}`;
            uploadStatus.scrollTop = uploadStatus.scrollHeight;
        }
        console.log(message);
    }
    
    updateStatus("DOM загружен, скрипт upload.js инициализирован");
    
    if (uploadForm) {
        updateStatus("Форма uploadForm найдена, добавляем обработчик событий");
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            updateStatus("Форма отправлена, предотвращаем стандартное поведение");
            
            // Скрываем предыдущие результаты
            uploadResult.classList.add('d-none');
            if (errorDetails) {
                errorDetails.classList.add('d-none');
            }
            
            // Показываем индикатор загрузки
            uploadProgress.classList.remove('d-none');
            progressBar.style.width = '0%';
            updateStatus("Индикатор загрузки показан");
            
            // Подготавливаем данные формы
            const formData = new FormData(uploadForm);
            const fileInput = document.getElementById('excelFile');
            const file = fileInput.files[0];
            
            if (file) {
                updateStatus(`Файл выбран: ${file.name}, размер: ${file.size} байт, тип: ${file.type}`);
            } else {
                updateStatus("Файл не выбран!");
                uploadProgress.classList.add('d-none');
                uploadResult.classList.remove('d-none');
                uploadResult.classList.remove('alert-success');
                uploadResult.classList.add('alert-danger');
                uploadResult.innerHTML = '<strong>Ошибка!</strong> Пожалуйста, выберите файл для загрузки.';
                return;
            }
            
            // Анимация прогресса (искусственная, т.к. у нас нет реального прогресса)
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress += 5;
                if (progress > 90) {
                    clearInterval(progressInterval);
                }
                progressBar.style.width = `${progress}%`;
                if (progress % 20 === 0) {
                    updateStatus(`Прогресс анимации: ${progress}%`);
                }
            }, 300);
            
            // Отправляем запрос
            updateStatus("Начинаем отправку запроса на /upload");
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                updateStatus(`Получен ответ. Статус: ${response.status}`);
                clearInterval(progressInterval);
                progressBar.style.width = '100%';
                
                return response.json().then(data => {
                    updateStatus(`Данные ответа получены: ${JSON.stringify(data).substring(0, 100)}...`);
                    return {
                        status: response.status,
                        data: data
                    };
                });
            })
            .then(result => {
                // Скрываем прогресс-бар через 0.5 секунды
                updateStatus(`Обрабатываем результат: ${JSON.stringify(result).substring(0, 100)}...`);
                setTimeout(() => {
                    uploadProgress.classList.add('d-none');
                    uploadResult.classList.remove('d-none');
                    
                    if (result.status >= 200 && result.status < 300 && result.data.success) {
                        // Успешная загрузка
                        updateStatus("Загрузка успешна");
                        uploadResult.classList.remove('alert-danger');
                        uploadResult.classList.add('alert-success');
                        uploadResult.innerHTML = `
                            <strong>Успешно!</strong> ${result.data.message}
                            <div class="mt-2">
                                <a href="/batches" class="btn btn-primary btn-sm">Перейти к загрузкам</a>
                            </div>
                        `;
                    } else {
                        // Ошибка при загрузке
                        updateStatus(`Ошибка при загрузке: ${result.data.error}`);
                        uploadResult.classList.remove('alert-success');
                        uploadResult.classList.add('alert-danger');
                        uploadResult.innerHTML = `<strong>Ошибка!</strong> ${result.data.error || 'Не удалось загрузить файл'}`;
                        
                        // Отображаем детали ошибки, если они есть
                        if (result.data.error && errorDetails) {
                            errorDetails.classList.remove('d-none');
                            errorDetailsText.textContent = result.data.error;
                        }
                    }
                }, 500);
            })
            .catch(error => {
                updateStatus(`Ошибка при отправке запроса: ${error.toString()}`);
                clearInterval(progressInterval);
                
                // Показываем сообщение об ошибке
                setTimeout(() => {
                    uploadProgress.classList.add('d-none');
                    uploadResult.classList.remove('d-none');
                    uploadResult.classList.remove('alert-success');
                    uploadResult.classList.add('alert-danger');
                    uploadResult.innerHTML = '<strong>Ошибка!</strong> Не удалось отправить запрос. Проверьте подключение к интернету.';
                    
                    if (errorDetails) {
                        errorDetails.classList.remove('d-none');
                        errorDetailsText.textContent = error.toString();
                    }
                }, 500);
            });
        });
    } else {
        updateStatus("Форма uploadForm не найдена на странице!");
    }
});
