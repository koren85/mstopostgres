document.getElementById('exportBtn').addEventListener('click', function() {
    const batchId = window.location.pathname.split('/').pop();
    window.location.href = `/export_analysis/${batchId}`;
}); 