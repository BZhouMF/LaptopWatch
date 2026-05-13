// ==================== 文件浏览器 ====================
// 依赖：utils.js（需先加载），以及模板注入的 absPath / MAX_HISTORY_LENGTH 全局变量

(function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const toggle = document.getElementById('sidebarToggle');
    if (!sidebar || !overlay || !toggle) return;

    if (localStorage.getItem('sidebarOpen') === 'true') {
        document.body.classList.add('sidebar-open');
    }

    toggle.addEventListener('click', function () {
        document.body.classList.toggle('sidebar-open');
        localStorage.setItem('sidebarOpen', document.body.classList.contains('sidebar-open'));
    });

    overlay.addEventListener('click', function () {
        document.body.classList.remove('sidebar-open');
        localStorage.setItem('sidebarOpen', 'false');
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && document.body.classList.contains('sidebar-open')) {
            document.body.classList.remove('sidebar-open');
            localStorage.setItem('sidebarOpen', 'false');
        }
    });
})();

let currentView = localStorage.getItem('currentView') || 'large';
let currentSort = localStorage.getItem('currentSort') || 'name';
let currentOrder = localStorage.getItem('currentOrder') || 'asc';

let offset = 0;
const limit = 20;
const isMobile = /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
const initialLoadLimit = isMobile ? 20 : 40;
let isLoading = false;
let hasMore = true;
let foldersLoaded = false;

let selectionMode = false;
let selectedPaths = [];

let globalAbortController = null;

// 初始化下拉框和按钮文本
document.getElementById('viewSelect').value = currentView;
document.getElementById('sortSelect').value = currentSort;
updateOrderButton();

// 事件委托：处理下载模式下的点击
function setupClickDelegation() {
    ['folderContainer', 'fileContainer'].forEach(containerId => {
        const container = document.getElementById(containerId);
        if (container) {
            container.addEventListener('click', function(e) {
                if (!selectionMode) return;
                const item = e.target.closest('.item');
                if (!item) return;
                e.preventDefault();
                const path = item.dataset.path;
                const isDir = item.dataset.isDir === 'true';
                if (path) {
                    toggleSelectItem(path, isDir);
                    const checkbox = item.querySelector('.item-checkbox');
                    if (checkbox) {
                        checkbox.checked = selectedPaths.some(p => p.path === path);
                    }
                }
            });
        }
    });
}

window.onload = () => {
    addToHistory(absPath);
    changeView();
    setupClickDelegation();

    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('refresh')) {
        urlParams.delete('refresh');
        const newUrl = window.location.pathname + (urlParams.toString() ? '?' + urlParams.toString() : '');
        window.history.replaceState({}, '', newUrl);
        refreshCurrentDir();
        return;
    }

    loadFolders().catch(e => console.log('文件夹加载异常', e)).then(() => {
        loadInitialFiles().catch(e => console.log('文件加载异常', e));
    });
};

// 滚动加载
window.addEventListener('scroll', () => {
    const fileContainer = document.getElementById('fileContainer');
    const containerRect = fileContainer.getBoundingClientRect();
    const containerBottom = containerRect.bottom;
    const viewportHeight = window.innerHeight;
    const triggerDistance = isMobile ? 200 : 300;
    if (containerBottom <= viewportHeight + triggerDistance) {
        loadMoreFiles();
    }
});

window.addEventListener('resize', () => {
    clearTimeout(window.resizeTimer);
    window.resizeTimer = setTimeout(() => {
        const fileContainer = document.getElementById('fileContainer');
        const containerRect = fileContainer.getBoundingClientRect();
        const containerBottom = containerRect.bottom;
        const viewportHeight = window.innerHeight;
        const triggerDistance = isMobile ? 200 : 300;
        if (containerBottom <= viewportHeight + triggerDistance) {
            loadMoreFiles();
        }
    }, 150);
});

// 历史记录
function addToHistory(path) {
    let historyStack = JSON.parse(localStorage.getItem('fileHistory') || '[]');
    if (historyStack[historyStack.length-1] !== path) {
        historyStack.push(path);
        if (historyStack.length > MAX_HISTORY_LENGTH) historyStack.shift();
        localStorage.setItem('fileHistory', JSON.stringify(historyStack));
    }
    document.getElementById('backPageBtn').disabled = historyStack.length <= 1;
}

async function goBackPage() {
    let historyStack = JSON.parse(localStorage.getItem('fileHistory') || '[]');
    if (historyStack.length <= 1) return;

    historyStack.pop();
    let targetPath = historyStack[historyStack.length-1];

    while (targetPath) {
        const res = await fetch(`${window.ROUTES.apiCheckPath}?path=${encodeURIComponent(targetPath)}`);
        const data = await res.json();

        if (data.exists && data.is_dir) {
            localStorage.setItem('fileHistory', JSON.stringify(historyStack));
            window.location.href = targetPath === '/' ? '/' : `${window.ROUTES.browse}${targetPath.replace(/\\/g, '/')}`;
            return;
        } else {
            historyStack.pop();
            targetPath = historyStack.length === 0 ? '/' : historyStack[historyStack.length-1];
        }
    }
    window.location.href = '/';
}

function changeView() {
    var oldView = currentView;
    currentView = document.getElementById('viewSelect').value;
    localStorage.setItem('currentView', currentView);

    var gridViews = ['large', 'medium', 'small'];
    var wasGrid = gridViews.indexOf(oldView) !== -1;
    var isGrid = gridViews.indexOf(currentView) !== -1;

    if (wasGrid !== isGrid) {
        // 网格 ↔ 列表切换需要重建 DOM（HTML 结构不同）
        resetAndLoad();
        return;
    }

    // 同在网格模式内切换：纯 CSS 切换即可
    ['folderContainer', 'fileContainer'].forEach(function (id) {
        var el = document.getElementById(id);
        el.classList.remove('view-large', 'view-medium', 'view-small', 'view-list');
        el.classList.add('view-' + currentView);
    });
    document.getElementById('listHeader').style.display = (currentView === 'list') ? 'flex' : 'none';
}

function changeSort() {
    currentSort = document.getElementById('sortSelect').value;
    localStorage.setItem('currentSort', currentSort);
    resetAndLoad();
}

function toggleOrder() {
    currentOrder = (currentOrder === 'asc' ? 'desc' : 'asc');
    localStorage.setItem('currentOrder', currentOrder);
    updateOrderButton();
    resetAndLoad();
}

function refreshCurrentDir() {
    resetAndLoad();
}

async function resetAndLoad() {
    if (globalAbortController) {
        globalAbortController.abort();
        globalAbortController = null;
    }

    offset = 0;
    hasMore = true;
    foldersLoaded = false;
    isLoading = false;

    const folderContainer = document.getElementById('folderContainer');
    const fileContainer = document.getElementById('fileContainer');
    const header = document.getElementById('listHeader');

    if (header && fileContainer.contains(header)) {
        fileContainer.removeChild(header);
    }

    folderContainer.innerHTML = '';
    fileContainer.innerHTML = '';

    if (header) {
        fileContainer.appendChild(header);
    }

    document.getElementById('errorMsg').style.display = 'none';
    document.getElementById('emptyMsg').style.display = 'none';
    document.getElementById('endMsg').style.display = 'none';

    changeView();

    try {
        await loadFolders();
    } catch (e) {
        console.error('文件夹加载失败', e);
        showError(' 文件夹加载失败，请刷新重试');
    }
    try {
        await loadInitialFiles();
    } catch (e) {
        console.error('文件加载失败', e);
        showError(' 文件加载失败，请刷新重试');
    }
}

function renderItem(item, isFolder) {
    if (!item || !item.name) {
        console.warn('无效的项目数据:', item);
        return '';
    }

    let iconHtml = '';
    let playBadge = '';

    if ((item.is_video || item.is_image) && item.path) {
        const fallbackIcon = item.icon || (item.is_video ? '🎬' : '🖼️');
        iconHtml = `<img src="${window.ROUTES.mediaThumbnail}_?path=${encodeURIComponent(item.path)}" loading="lazy" alt="${item.name}" onerror="this.replaceWith(document.createTextNode('${fallbackIcon}'))">`;
        if (item.is_video) playBadge = '<div class="play-badge"></div>';
    } else {
        iconHtml = item.icon || '📄';
    }

    let linkHref = 'javascript:void(0)';
    if (!selectionMode) {
        if (isFolder) {
            linkHref = `${window.ROUTES.browse}${encodeURIComponent(item.path.replace(/\\/g, '/'))}`;
        } else if (item.is_text_readable) {
            linkHref = `${window.ROUTES.fileText}${encodeURIComponent(item.path.replace(/\\/g, '/'))}`;
        }
    }

    let clickAction = '';
    if (!selectionMode && item.is_previewable && !isFolder) {
        const safeUrl = item.raw_url.replace(/'/g, "\\'");
        const safeName = item.name.replace(/'/g, "\\'");
        clickAction = `onclick="openModal('${safeUrl}', '${safeName}', ${!!item.is_video}); return false;"`;
    }

    let checkboxHtml = '';
    if (selectionMode) {
        const checked = selectedPaths.some(p => p.path === item.path) ? 'checked' : '';
        const escapedPath = item.path.replace(/'/g, "\\'");
        checkboxHtml = `<input type="checkbox" class="item-checkbox" value="${item.path}" data-is-dir="${isFolder}" ${checked} onclick="event.stopPropagation(); toggleSelectItem('${escapedPath}', ${isFolder})">`;
    }

    const displayName = item.name || '未知文件';
    let displayDate = item.date || '';
    if (displayDate) {
        displayDate = displayDate.split(' ')[0];
    }
    const displaySize = item.size || (isFolder ? '--' : '0B');

    if (currentView === 'list') {
        return `
            <a href="${linkHref}" class="item" ${clickAction} data-path="${item.path || ''}" data-is-dir="${isFolder}">
                <div class="col-checkbox">${checkboxHtml}</div>
                <div class="item-icon col-icon">${iconHtml}${playBadge}</div>
                <div class="item-name col-name">${displayName}</div>
                <div class="item-meta col-date">${displayDate}</div>
                <div class="item-meta col-size">${displaySize}</div>
            </a>
        `;
    } else if (currentView === 'large' || currentView === 'medium') {
        return `
            <a href="${linkHref}" class="item" ${clickAction} data-path="${item.path || ''}" data-is-dir="${isFolder}">
                <div class="item-checkbox-wrapper">${checkboxHtml}</div>
                <div class="item-icon col-icon">${iconHtml}${playBadge}</div>
                <div class="item-name col-name">${displayName}</div>
                ${displayDate ? `<div class="item-meta">${displayDate}</div>` : ''}
            </a>
        `;
    } else {
        return `
            <a href="${linkHref}" class="item" ${clickAction} data-path="${item.path || ''}" data-is-dir="${isFolder}">
                <div class="item-checkbox-wrapper">${checkboxHtml}</div>
                <div class="item-icon col-icon">${iconHtml}${playBadge}</div>
                <div class="item-name col-name">${displayName}</div>
                ${displayDate ? `<div class="item-meta">${displayDate}</div>` : ''}
            </a>
        `;
    }
}

function showError(msg) {
    const errorEl = document.getElementById('errorMsg');
    errorEl.innerHTML = msg;
    errorEl.style.display = 'block';
}

function checkEmpty() {
    const folderContainer = document.getElementById('folderContainer');
    const fileContainer = document.getElementById('fileContainer');
    const header = document.getElementById('listHeader');
    const fileChildren = Array.from(fileContainer.children).filter(el => el !== header);
    if (folderContainer.children.length === 0 && fileChildren.length === 0) {
        document.getElementById('emptyMsg').style.display = 'block';
    } else {
        document.getElementById('emptyMsg').style.display = 'none';
    }
}

async function loadFolders() {
    if (foldersLoaded) return;

    const controller = new AbortController();
    globalAbortController = controller;

    try {
        const res = await fetch(`${window.ROUTES.apiList}?path=${encodeURIComponent(absPath)}&type=folders&sort=${currentSort}&order=${currentOrder}`, {
            signal: controller.signal
        });

        if (controller.signal.aborted) throw new Error('请求被取消');
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || `接口错误 ${res.status}`);
        }

        const data = await res.json();
        const grid = document.getElementById('folderContainer');

        if (data.length > 0) {
            data.forEach(item => {
                grid.innerHTML += renderItem({...item, size: '--'}, true);
            });
        }
        foldersLoaded = true;
        checkEmpty();
    } catch (e) {
        if (e.name === 'AbortError') return;
        console.error('文件夹加载失败', e);
        showError(' 文件夹加载失败: ' + e.message);
        throw e;
    } finally {
        globalAbortController = null;
    }
}

async function loadInitialFiles() {
    if (isLoading || !hasMore) return;

    isLoading = true;
    document.getElementById('loader').style.display = 'block';

    const controller = new AbortController();
    globalAbortController = controller;

    try {
        const res = await fetch(`${window.ROUTES.apiList}?path=${encodeURIComponent(absPath)}&type=files&sort=${currentSort}&order=${currentOrder}&offset=${offset}&limit=${initialLoadLimit}`, {
            signal: controller.signal
        });

        if (controller.signal.aborted) return;
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || `接口错误 ${res.status}`);
        }

        const data = await res.json();
        const grid = document.getElementById('fileContainer');

        if (data.items.length > 0) {
            data.items.forEach(item => {
                grid.innerHTML += renderItem(item, false);
            });
        }

        offset += data.items.length;
        hasMore = data.has_more;
        checkEmpty();
    } catch (e) {
        if (e.name === 'AbortError') return;
        console.error('初始文件加载失败', e);
        showError(' 文件加载失败: ' + e.message);
        throw e;
    } finally {
        isLoading = false;
        document.getElementById('loader').style.display = 'none';
        if (!hasMore) document.getElementById('endMsg').style.display = 'block';
        globalAbortController = null;
    }
}

async function loadMoreFiles() {
    if (isLoading || !hasMore) return;

    isLoading = true;
    document.getElementById('loader').style.display = 'block';

    const controller = new AbortController();
    globalAbortController = controller;

    try {
        const res = await fetch(`${window.ROUTES.apiList}?path=${encodeURIComponent(absPath)}&type=files&sort=${currentSort}&order=${currentOrder}&offset=${offset}&limit=${limit}`, {
            signal: controller.signal
        });

        if (controller.signal.aborted) return;
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || `接口错误 ${res.status}`);
        }

        const data = await res.json();
        const grid = document.getElementById('fileContainer');

        if (data.items.length > 0) {
            data.items.forEach(item => {
                grid.innerHTML += renderItem(item, false);
            });
        }

        offset += data.items.length;
        hasMore = data.has_more;
        checkEmpty();
    } catch (e) {
        if (e.name === 'AbortError') return;
        console.error('加载文件失败', e);
        showError(' 文件加载失败: ' + e.message);
    } finally {
        isLoading = false;
        document.getElementById('loader').style.display = 'none';
        if (!hasMore) document.getElementById('endMsg').style.display = 'block';
        globalAbortController = null;
    }
}

// ========== 多选模式 ==========
function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (selectionMode) {
        selectedPaths = [];
        document.getElementById('downloadBtn').innerHTML = '[X] 取消';
        document.getElementById('selectionBar').style.display = 'flex';
    } else {
        document.getElementById('downloadBtn').innerHTML = ' 下载';
        document.getElementById('selectionBar').style.display = 'none';
    }
    resetAndLoad();
}

function cancelSelection() {
    toggleSelectionMode();
}

function updateSelectedCount() {
    document.getElementById('selectedCount').innerText = selectedPaths.length;
}

function toggleSelectItem(path, isDir) {
    const index = selectedPaths.findIndex(p => p.path === path);
    if (index === -1) {
        selectedPaths.push({path, isDir});
    } else {
        selectedPaths.splice(index, 1);
    }
    updateSelectedCount();
}

function selectAll() {
    fetch(`${window.ROUTES.apiListAll}?path=${encodeURIComponent(absPath)}`)
        .then(res => res.json())
        .then(items => {
            selectedPaths = items.map(item => ({path: item.path, isDir: item.is_dir}));
            document.querySelectorAll('.item-checkbox').forEach(cb => {
                const path = cb.value;
                cb.checked = selectedPaths.some(p => p.path === path);
            });
            updateSelectedCount();
        })
        .catch(err => {
            alert('获取列表失败：' + err.message);
        });
}

function downloadSeparate() {
    let index = 0;
    function next() {
        if (index >= selectedPaths.length) {
            toggleSelectionMode();
            return;
        }
        const {path, isDir} = selectedPaths[index];
        index++;
        let url;
        if (isDir) {
            url = `${window.ROUTES.fileDownloadFolder}?path=${encodeURIComponent(path)}`;
        } else {
            url = `${window.ROUTES.fileView}${encodeURIComponent(path.replace(/\\/g, '/'))}`;
        }
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(next, 500);
    }
    next();
}

function downloadSelected() {
    if (selectedPaths.length === 0) {
        alert('请至少选择一个项目');
        return;
    }
    const mode = document.querySelector('input[name="downloadMode"]:checked').value;
    if (mode === 'merge') {
        fetch(window.ROUTES.fileDownloadSelected, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                base: absPath,
                paths: selectedPaths.map(p => p.path)
            })
        })
        .then(response => {
            if (response.ok) {
                return response.blob();
            } else {
                return response.text().then(text => { throw new Error(text); });
            }
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = '下载.zip';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
            toggleSelectionMode();
        })
        .catch(err => {
            alert('下载失败：' + err.message);
        });
    } else {
        downloadSeparate();
    }
}

// 弹窗预览
function openModal(url, name, isVideo) {
    const modal = document.getElementById('previewModal');
    const content = document.getElementById('modalContent');
    const download = document.getElementById('modalDownload');

    if (isVideo) {
        content.innerHTML = `<video controls autoplay playsinline class="modal-content"><source src="${url}"></video>`;
    } else {
        content.innerHTML = `<img src="${url}" class="modal-content">`;
    }

    download.href = url;
    download.download = name;
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    document.getElementById('previewModal').style.display = 'none';
    document.getElementById('modalContent').innerHTML = '';
    document.body.style.overflow = 'auto';
}

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
document.querySelector('.modal-close').onclick = (e) => {
    e.stopPropagation();
    closeModal();
};
