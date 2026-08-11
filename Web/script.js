// ==========================================
// 1. التحكم في النوافذ المنبثقة (About & Contact)
// ==========================================

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
};

// ==========================================
// 2. معالجة نموذج توليد الشهادات (Form Submission)
// ==========================================

document.getElementById('certForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    const statusDiv = document.getElementById('status');
    const btnStart = document.getElementById('btnStart');

    const formData = new FormData();
    formData.append('drive_folder_id', document.getElementById('drive_folder_id').value.trim());
    formData.append('folder_name', document.getElementById('folder_name').value.trim());
    formData.append('template', document.getElementById('template').files[0]);
    formData.append('csv', document.getElementById('csv').files[0]);
    formData.append('font', document.getElementById('font').files[0]);

    statusDiv.style.color = '#ffc107';
    statusDiv.innerText = 'جاري توليد الشهادات ورفعها إلى Google Drive، يرجى الانتظار...';
    btnStart.disabled = true;

    try {
        const response = await fetch('/generate', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            statusDiv.style.color = '#28a745';
            statusDiv.innerText = result.message;
        } else {
            statusDiv.style.color = '#dc3545';
            statusDiv.innerText = result.message;
        }
    } catch (error) {
        statusDiv.style.color = '#dc3545';
        statusDiv.innerText = 'حدث خطأ أثناء الاتصال بالخادم أو الرفع لـ Drive.';
    } finally {
        btnStart.disabled = false;
    }
});