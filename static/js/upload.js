
document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('uploadForm');
    const uploadProgress = document.getElementById('uploadProgress');
    const progressBar = uploadProgress.querySelector('.progress-bar');
    const uploadResult = document.getElementById('uploadResult');
    const errorDetails = document.getElementById('errorDetails');
    const errorDetailsText = document.getElementById('errorDetailsText');
    
    console.log("DOM загружен, скрипт upload.js инициализирован");
    
    if (uploadForm) {
        console.log("Форма uploadForm найдена, добавляем обработчик событий");
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            console.log("Форма отправлена, предотвращаем стандартное поведение");
            
            // Скрываем предыдущие результаты
            uploadResult.classList.add('d-none');
            if (errorDetails) {
                errorDetails.classList.add('d-none');
            }
            
            // Показываем индикатор загрузки
            uploadProgress.classList.remove('d-none');
            progressBar.style.width = '0%';
            console.log("Индикатор загрузки показан");
            
            // Подготавливаем данные формы
            const formData = new FormData(uploadForm);
            const fileInput = document.getElementById('excelFile');
            const file = fileInput.files[0];
            
            if (file) {
                console.log(`Файл выбран: ${file.name}, размер: ${file.size} байт, тип: ${file.type}`);
            } else {
                console.log("Файл не выбран!");
            }
            
            // Анимация прогресса (искусственная, т.к. у нас нет реального прогресса)
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress += 5;
                if (progress > 90) {
                    clearInterval(progressInterval);
                }
                progressBar.style.width = `${progress}%`;
                console.log(`Прогресс анимации: ${progress}%`);
            }, 300);
            
            // Отправляем запрос
            console.log("Начинаем отправку запроса на /upload");
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log(`Получен ответ. Статус: ${response.status}`);
                clearInterval(progressInterval);
                progressBar.style.width = '100%';
                
                return response.json().then(data => {
                    console.log("Данные ответа получены:", data);
                    return {
                        status: response.status,
                        data: data
                    };
                });
            })
            .then(({ status, data }) => {
                // Скрываем прогресс-бар через 0.5 секунды
                console.log("Обрабатываем результат");
                setTimeout(() => {
                    uploadProgress.classList.add('d-none');
                    uploadResult.classList.remove('d-none');
                    
                    if (status >= 200 && status < 300) {
                        // Успешная загрузка
                        console.log("Загрузка успешна");
                        uploadResult.classList.remove('alert-danger');
                        uploadResult.classList.add('alert-success');
                        uploadResult.innerHTML = `
                            <strong>Успешно!</strong> ${data.message}
                            <div class="mt-2">
                                <a href="/batches" class="btn btn-primary btn-sm">Перейти к загрузкам</a>
                            </div>
                        `;
                    } else {
                        // Ошибка при загрузке
                        console.log("Ошибка при загрузке:", data.error);
                        uploadResult.classList.remove('alert-success');
                        uploadResult.classList.add('alert-danger');
                        uploadResult.innerHTML = `<strong>Ошибка!</strong> ${data.error || 'Не удалось загрузить файл'}`;
                        
                        // Отображаем детали ошибки, если они есть
                        if (data.error && errorDetails) {
                            errorDetails.classList.remove('d-none');
                            errorDetailsText.textContent = data.error;
                        }
                    }
                }, 500);
            })
            .catch(error => {
                console.error("Ошибка при отправке запроса:", error);
                clearInterval(progressInterval);
                uploadProgress.classList.add('d-none');
                uploadResult.classList.remove('d-none');
                uploadResult.classList.remove('alert-success');
                uploadResult.classList.add('alert-danger');
                uploadResult.innerHTML = '<strong>Ошибка!</strong> Не удалось отправить запрос. Проверьте подключение к интернету.';
                console.error('Error:', error);
            });
        });
    } else {
        console.error("Форма загрузки не найдена на странице!");
    }
});
