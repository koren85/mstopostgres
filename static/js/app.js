
document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleFileUpload);
    }
});

function handleFileUpload(e) {
    e.preventDefault();

    const formData = new FormData(e.target);
    const progressBar = document.querySelector('#uploadProgress');
    const progressBarInner = progressBar.querySelector('.progress-bar');
    const resultDiv = document.getElementById('uploadResult');

    // Show progress bar
    progressBar.classList.remove('d-none');
    progressBarInner.style.width = '0%';
    resultDiv.classList.add('d-none');

    // Simulate progress
    let progress = 0;
    const progressInterval = setInterval(() => {
        progress += 5;
        if (progress <= 90) {
            progressBarInner.style.width = `${progress}%`;
        }
    }, 100);

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            throw new TypeError("Ожидался JSON в ответе!");
        }
        return response.json();
    })
    .then(data => {
        clearInterval(progressInterval);
        progressBarInner.style.width = '100%';

        setTimeout(() => {
            progressBar.classList.add('d-none');
            resultDiv.classList.remove('d-none');
            
            if (data.success) {
                resultDiv.className = 'alert alert-success';
                resultDiv.textContent = `Успешно! ${data.message}`;
                if (data.batch_id) {
                    // Добавим кнопку для перехода к загрузке
                    const batchLink = document.createElement('a');
                    batchLink.href = '/batches';
                    batchLink.textContent = 'Перейти к загрузкам';
                    batchLink.className = 'btn btn-primary ml-2';
                    resultDiv.appendChild(document.createElement('br'));
                    resultDiv.appendChild(batchLink);
                }
            } else {
                resultDiv.className = 'alert alert-danger';
                resultDiv.textContent = `Ошибка: ${data.error || 'Неизвестная ошибка'}`;
            }
        }, 500);
    })
    .catch(error => {
        clearInterval(progressInterval);
        progressBar.classList.add('d-none');
        resultDiv.classList.remove('d-none');
        resultDiv.className = 'alert alert-danger';
        
        let errorMessage = error.message || 'Неизвестная ошибка';
        if (errorMessage.includes('JSON')) {
            errorMessage = 'Сервер вернул неправильный формат данных. Возможно, произошла внутренняя ошибка.';
        }
        resultDiv.textContent = `Ошибка при загрузке: ${errorMessage}`;
    });
}

function suggestClassification(className, description) {
    return fetch('/api/suggest_classification', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            mssql_sxclass_name: className,
            mssql_sxclass_description: description
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        return data;
    })
    .catch(error => {
        console.error('Ошибка при получении предложений классификации:', error);
        return { priznak: null, confidence: 0, method: null };
    });
}
