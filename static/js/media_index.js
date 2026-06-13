// ==================== 媒体索引页面 ====================
// 依赖：modal.js（需先加载），以及模板注入的 MEDIA_CONFIG 和 MEDIA_PAGE_CACHE 全局变量

var offset = MEDIA_CONFIG.pageFirst;
var pageLoad = MEDIA_CONFIG.pageLoad;
var isLoading = false;
var hasMore = MEDIA_CONFIG.hasMore;
var totalPages = MEDIA_CONFIG.totalPages;
var currentPage = MEDIA_CONFIG.currentPage;
var pageFirst = MEDIA_CONFIG.pageFirst;
var currentController = null;
var isRandomMode = MEDIA_CONFIG.isRandom;
var isTraversalMode = isRandomMode;
var pageCache = MEDIA_PAGE_CACHE;

function openMedia(relativePath) {
    window.location.href = window.ROUTES.mediaPlayer + '?path=' + encodeURIComponent(relativePath);
}

function updatePagination() {
    var prevBtn = document.getElementById('prevPage');
    var nextBtn = document.getElementById('nextPage');
    var pageNumbers = document.getElementById('pageNumbers');

    if (isLoading) {
        var grid = document.getElementById('mediaGrid');
        var hasRealContent = grid.children.length > 0 &&
            !grid.querySelector('.loading-placeholder') &&
            grid.querySelector('.video-card:not(.loading-placeholder)');
        if (hasRealContent) {
            isLoading = false;
        }
    }

    if (isLoading) {
        prevBtn.disabled = true;
        nextBtn.disabled = true;
    } else {
        prevBtn.disabled = currentPage <= 1;
        nextBtn.disabled = !hasMore;
    }

    var pagesHtml = '';
    var maxVisible = 5;
    var startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    var endPage = Math.min(totalPages, startPage + maxVisible - 1);

    if (endPage - startPage + 1 < maxVisible) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }

    if (startPage > 1) {
        pagesHtml += '<span class="page-dots">...</span>';
    }

    for (var i = startPage; i <= endPage; i++) {
        if (i === currentPage) {
            pagesHtml += '<span class="page-number current">' + i + '</span>';
        } else {
            if (isLoading) {
                pagesHtml += '<span class="page-number disabled" onclick="return false;">' + i + '</span>';
            } else {
                pagesHtml += '<span class="page-number" onclick="changePage(' + i + ')">' + i + '</span>';
            }
        }
    }

    if (isTraversalMode && hasMore && endPage === totalPages) {
        pagesHtml += '<span class="page-dots">...</span>';
    } else if (endPage < totalPages) {
        pagesHtml += '<span class="page-dots">...</span>';
    }

    pageNumbers.innerHTML = pagesHtml;
}

function changePage(page) {
    if (page < 1 || page === currentPage) return;
    if (isTraversalMode && page > totalPages + 1) return;
    if (!isTraversalMode && page > totalPages) return;

    currentPage = page;
    updatePagination();
    loadPage(page);
}

function showLoadingPlaceholders() {
    var grid = document.getElementById('mediaGrid');
    grid.innerHTML = '';
    for (var i = 0; i < 6; i++) {
        var placeholder = document.createElement('div');
        placeholder.className = 'video-card loading-placeholder';
        placeholder.innerHTML = '<div class="video-thumb"><div class="thumb-placeholder loading"></div></div><div class="video-info"><div class="video-name loading-text"></div><div class="video-meta loading-text"></div></div>';
        grid.appendChild(placeholder);
    }
}

function loadPage(page) {
    if (isTraversalMode && pageCache[page]) {
        var cached = pageCache[page];
        renderPage(cached.data, page, cached.hasMore, cached.total, cached.nextOffset);
        return;
    }

    if (currentController) {
        currentController.abort();
        currentController = null;
    }

    var controller = new AbortController();
    currentController = controller;

    var timeoutId = setTimeout(function() {
        if (currentController === controller) {
            controller.abort();
            var grid = document.getElementById('mediaGrid');
            grid.innerHTML = '<div class="error-message" style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #ff6b6b;">请求超时，请重试</div>';
        }
    }, 30000);

    isLoading = true;
    document.getElementById('loading').style.display = 'block';
    showLoadingPlaceholders();

    var newOffset, newLimit;
    if (page === 1) {
        newOffset = 0;
        newLimit = pageFirst;
    } else {
        newOffset = pageFirst + (page - 2) * pageLoad;
        newLimit = pageLoad;
    }

    fetch(window.ROUTES.mediaLoadMore + '?offset=' + newOffset + '&limit=' + newLimit, { signal: controller.signal })
        .then(function(res) {
            if (res.ok) return res.json();
            throw new Error('HTTP error ' + res.status);
        })
        .then(function(data) {
            if (currentController !== controller) return;

            if (data.code === 0) {
                if (isTraversalMode) {
                    pageCache[page] = {
                        data: data.data,
                        hasMore: data.has_more,
                        total: data.total,
                        nextOffset: newOffset + data.data.length
                    };
                }
                renderPage(data.data, page, data.has_more, data.total, newOffset);
            } else {
                var grid = document.getElementById('mediaGrid');
                grid.innerHTML = '<div class="error-message" style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #ff6b6b;">加载失败: ' + data.msg + '</div>';
                isLoading = false;
                updatePagination();
            }
        })
        .catch(function(err) {
            if (err.name === 'AbortError') return;
            var grid = document.getElementById('mediaGrid');
            grid.innerHTML = '<div class="error-message" style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #ff6b6b;">网络错误，请重试</div>';
        })
        .finally(function() {
            clearTimeout(timeoutId);
            if (currentController === controller) {
                isLoading = false;
                currentController = null;
                document.getElementById('loading').style.display = 'none';
                updatePagination();
            }
        });
}

function renderPage(items, page, more, total, newOffset) {
    var grid = document.getElementById('mediaGrid');
    grid.innerHTML = '';

    items.forEach(function(item) {
        var card = document.createElement('div');
        card.className = 'video-card';
        card.onclick = function() { openMedia(item.relative_path); };
        var thumbHtml = (item.is_video || item.is_image)
            ? '<img src="' + window.ROUTES.mediaThumbnail + encodeURIComponent(item.relative_path) + '" alt="' + item.name + '" loading="lazy">'
            : '<div class="thumb-placeholder">' + (item.is_video ? 'VID' : 'IMG') + '</div>';
        card.innerHTML = '<div class="video-thumb">' + thumbHtml + '</div><div class="video-info"><div class="video-name" title="' + item.name + '">' + item.name + '</div></div>';
        grid.appendChild(card);
    });

    if (typeof newOffset !== 'undefined') {
        offset = newOffset + items.length;
    }
    currentPage = page;
    hasMore = more;

    if (typeof total === 'number' && total > 0) {
        totalPages = Math.max(1, Math.ceil(total / pageLoad));
    } else if (isTraversalMode && hasMore && currentPage >= totalPages) {
        totalPages = currentPage + 1;
    }

    isLoading = false;
    updatePagination();
    window.scrollTo(0, 0);

    if (!hasMore) {
        document.getElementById('noMore').style.display = 'block';
    } else {
        document.getElementById('noMore').style.display = 'none';
    }
}

updatePagination();
