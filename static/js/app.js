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

            if (data.error) {
                resultDiv.className = 'alert alert-danger mt-3';
                resultDiv.textContent = `Ошибка: ${data.error}`;
            } else {
                resultDiv.className = 'alert alert-success mt-3';
                resultDiv.textContent = data.message;
            }
        }, 500);
    })
    .catch(error => {
        clearInterval(progressInterval);
        progressBar.classList.add('d-none');
        resultDiv.classList.remove('d-none');
        resultDiv.className = 'alert alert-danger mt-3';
        let errorMessage = error.message;
        if (error instanceof TypeError && error.message === "Ожидался JSON в ответе!") {
            errorMessage = "Сервер вернул неправильный формат ответа. Пожалуйста, попробуйте позже.";
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
    });
}