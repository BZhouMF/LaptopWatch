// ==================== 通用工具函数 ====================

function updateOrderButton() {
    const btn = document.getElementById('orderToggle');
    if (btn) {
        btn.innerHTML = (currentOrder === 'asc' ? ' 升序' : ' 降序');
    }
}

function copyToClipboard() {
    const text = document.getElementById('textContent').textContent;
    navigator.clipboard.writeText(text).then(() => {
        alert('内容已复制到剪贴板');
    }).catch(() => {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        alert('内容已复制到剪贴板');
    });
}

function addLineNumbers() {
    const contentElement = document.getElementById('textContent');
    if (!contentElement) return;

    const lines = contentElement.textContent.split('\n');
    const lineCountElement = document.getElementById('lineCount');
    if (lineCountElement) {
        lineCountElement.textContent = lines.length;
    }

    let numberedContent = '';
    lines.forEach((line, index) => {
        const lineNumber = (index + 1).toString().padStart(4, ' ');
        numberedContent += `<span class="line-numbers">${lineNumber}</span>${line}\n`;
    });

    contentElement.innerHTML = numberedContent;
}

document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('textContent')) {
        addLineNumbers();
    }
});
