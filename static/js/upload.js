document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('uploadForm');
    const uploadProgress = document.getElementById('uploadProgress');
    const progressBar = uploadProgress.querySelector('.progress-bar');
    const uploadResult = document.getElementById('uploadResult');

    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();

            // Скрываем предыдущие результаты
            uploadResult.classList.add('d-none');

            // Показываем индикатор загрузки
            uploadProgress.classList.remove('d-none');
            progressBar.style.width = '0%';

            // Подготавливаем данные формы
            const formData = new FormData(uploadForm);
            const fileInput = document.getElementById('excelFile');
            const file = fileInput.files[0];

            if (!file) {
                uploadProgress.classList.add('d-none');
                uploadResult.classList.remove('d-none');
                uploadResult.classList.add('alert-danger');
                uploadResult.innerHTML = '<strong>Ошибка!</strong> Файл не выбран.';
                return;
            }

            // Переименовываем поле файла для соответствия ожиданиям сервера
            formData.append('file', file);
            formData.delete('excelFile');

            // Эмулируем прогресс
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress += 5;
                if (progress <= 90) {
                    progressBar.style.width = `${progress}%`;
                }
            }, 300);

            // Отправляем запрос
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                clearInterval(progressInterval);
                progressBar.style.width = '100%';

                setTimeout(() => {
                    uploadProgress.classList.add('d-none');
                    uploadResult.classList.remove('d-none');

                    if (data.error) {
                        uploadResult.classList.remove('alert-success');
                        uploadResult.classList.add('alert-danger');
                        uploadResult.innerHTML = `<strong>Ошибка!</strong> ${data.error || 'Не удалось загрузить файл'}`;
                    } else {
                        uploadResult.classList.remove('alert-danger');
                        uploadResult.classList.add('alert-success');
                        uploadResult.innerHTML = `
                            <strong>Успешно!</strong> ${data.message}
                            <div class="mt-2">
                                <a href="/batches" class="btn btn-primary btn-sm">Перейти к загрузкам</a>
                            </div>
                        `;
                    }
                }, 500);
            })
            .catch(error => {
                clearInterval(progressInterval);
                uploadProgress.classList.add('d-none');
                uploadResult.classList.remove('d-none');
                uploadResult.classList.add('alert-danger');
                uploadResult.innerHTML = '<strong>Ошибка!</strong> Не удалось отправить запрос на сервер.';
            });
        });
    }
});