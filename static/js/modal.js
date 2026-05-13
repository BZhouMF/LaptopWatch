// ==================== 通用模态框（图片/视频）Hash 方案 + 滚动恢复 ====================

let currentMedia = null;
let savedScrollPos = { x: 0, y: 0 };

// ==================== 媒体导航全局状态 ====================
window.mediaNav = {
    enabled: false,
    currentPath: null
};

// 刷新上一个/下一个按钮的禁用状态
function refreshNavButtons() {
    if (!window.mediaNav || !window.mediaNav.enabled) return;
    const currentPath = window.mediaNav.currentPath;
    if (!currentPath) return;

    Promise.all([
        fetch(`${window.ROUTES.mediaNavigate}?current_path=${encodeURIComponent(currentPath)}&direction=prev`),
        fetch(`${window.ROUTES.mediaNavigate}?current_path=${encodeURIComponent(currentPath)}&direction=next`)
    ]).then(async ([prevRes, nextRes]) => {
        const prevData = await prevRes.json();
        const nextData = await nextRes.json();
        const prevBtn = document.getElementById('prevMediaBtn');
        const nextBtn = document.getElementById('nextMediaBtn');
        if (prevBtn) prevBtn.disabled = prevData.code !== 0;
        if (nextBtn) nextBtn.disabled = nextData.code !== 0;
    }).catch(err => console.error('导航检查失败', err));
}

// 导航函数（供按钮点击调用）
function navigateMedia(direction) {
    if (!window.mediaNav || !window.mediaNav.enabled) return;
    const currentPath = window.mediaNav.currentPath;
    if (!currentPath) return;

    fetch(`${window.ROUTES.mediaNavigate}?current_path=${encodeURIComponent(currentPath)}&direction=${direction}`)
        .then(res => res.json())
        .then(data => {
            if (data.code === 0) {
                const newPath = data.data.relative_path;
                const name = data.data.name;
                const isVideo = data.data.is_video;
                window.mediaNav.currentPath = newPath;
                const url = `${window.ROUTES.mediaServe}${encodeURIComponent(newPath)}`;
                const modalContent = document.getElementById('modalContent');
                const downloadLink = document.getElementById('modalDownload');
                modalContent.innerHTML = '';
                if (isVideo) {
                    const video = document.createElement('video');
                    video.controls = true;
                    video.autoplay = true;
                    video.muted = true;
                    video.playsInline = true;
                    video.className = 'modal-content';
                    const source = document.createElement('source');
                    source.src = url;
                    video.appendChild(source);
                    video.onerror = function() {
                        console.error('导航视频加载失败:', video.error);
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'modal-error';
                        errorDiv.innerHTML = `<div style="padding:20px;text-align:center;color:#ff6b6b;"><p>视频加载失败</p><p>错误: ${video.error?.message || '未知格式错误'}</p></div>`;
                        modalContent.appendChild(errorDiv);
                        video.style.display = 'none';
                    };
                    modalContent.appendChild(video);
                } else {
                    const img = document.createElement('img');
                    img.className = 'modal-content';
                    img.alt = name;
                    img.src = url;
                    img.onerror = function() {
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'modal-error';
                        errorDiv.innerHTML = `<div style="padding:20px;text-align:center;color:#ff6b6b;"><p>图片加载失败</p></div>`;
                        modalContent.appendChild(errorDiv);
                        img.style.display = 'none';
                    };
                    modalContent.appendChild(img);
                }
                downloadLink.href = url;
                downloadLink.download = name;
                refreshNavButtons();
            }
        })
        .catch(err => console.error('导航失败', err));
}

// 显示模态框（内部使用）
function displayModal() {
    if (!currentMedia) return;
    const modal = document.getElementById('previewModal');
    const content = document.getElementById('modalContent');
    const download = document.getElementById('modalDownload');
    if (!modal || !content || !download) return;
    const { url, name, isVideo } = currentMedia;

    content.innerHTML = '';
    if (isVideo) {
        const video = document.createElement('video');
        video.controls = true;
        video.autoplay = true;
        video.muted = true;
        video.playsInline = true;
        video.className = 'modal-content';
        const source = document.createElement('source');
        source.src = url;
        video.appendChild(source);
        video.onerror = function() {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'modal-error';
            errorDiv.innerHTML = `<div style="padding:20px;text-align:center;color:#ff6b6b;"><p>视频加载失败</p><p>错误: ${video.error?.message || '未知格式错误'}</p></div>`;
            content.appendChild(errorDiv);
            video.style.display = 'none';
        };
        content.appendChild(video);
    } else {
        const img = document.createElement('img');
        img.className = 'modal-content';
        img.alt = name;
        img.src = url;
        img.onerror = function() {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'modal-error';
            errorDiv.innerHTML = `<div style="padding:20px;text-align:center;color:#ff6b6b;"><p>图片加载失败</p></div>`;
            content.appendChild(errorDiv);
            img.style.display = 'none';
        };
        content.appendChild(img);
    }

    download.href = url;
    download.download = name;
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    if (window.mediaNav && window.mediaNav.enabled) {
        const match = url.match(new RegExp(window.ROUTES.mediaServe.replace(/\//g, '\\/') + '(.+)'));
        if (match) {
            window.mediaNav.currentPath = decodeURIComponent(match[1]);
        }
        refreshNavButtons();
    }
}

function hideModal() {
    const modal = document.getElementById('previewModal');
    if (!modal) return;
    modal.style.display = 'none';
    const content = document.getElementById('modalContent');
    if (content) content.innerHTML = '';
    document.body.style.overflow = 'auto';
}

function openModal(url, name, isVideo) {
    savedScrollPos = { x: window.scrollX, y: window.scrollY };
    currentMedia = { url, name, isVideo };
    location.hash = 'preview';
}

function closeModal() {
    location.hash = '';
}

window.addEventListener('hashchange', function () {
    if (window.location.hash === '#preview') {
        displayModal();
        window.scrollTo(savedScrollPos.x, savedScrollPos.y);
    } else {
        hideModal();
        window.scrollTo(savedScrollPos.x, savedScrollPos.y);
    }
});

if (window.location.hash === '#preview' && !currentMedia) {
    location.hash = '';
}

document.addEventListener('click', function (e) {
    const modal = document.getElementById('previewModal');
    if (modal && e.target === modal) {
        closeModal();
    }
});

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});
