// ==================== Category Browse SPA Engine ====================
// 依赖：window.ROUTES（模板注入）、sessionStorage

(function() {
    'use strict';

    // ==================== 状态 ====================
    var navStack = [];
    var currentIndex = -1;
    var STORAGE_KEY = 'category_spa_stack';
    var RETURNING_KEY = 'category_spa_returning';
    var MAX_STACK = 60;

    // Grid 分页运行时状态
    var gridPageCache = {};
    var gridCurrentPage = 1;
    var gridHasMore = true;
    var gridFolderPath = '';
    var gridPageFirst = 35;
    var gridPageLoad = 35;
    var gridIsLoading = false;
    var gridAbortController = null;

    // ==================== HTML 转义 ====================
    function escHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escAttr(str) {
        return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ==================== 导航栈管理 ====================
    function saveStack() {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
                navStack: navStack,
                currentIndex: currentIndex
            }));
        } catch (ignore) {}
    }

    function loadStack() {
        try {
            var raw = sessionStorage.getItem(STORAGE_KEY);
            if (raw) {
                var parsed = JSON.parse(raw);
                if (parsed.navStack && parsed.navStack.length > 0) {
                    navStack = parsed.navStack;
                    currentIndex = parsed.currentIndex;
                    return true;
                }
            }
        } catch (ignore) {}
        return false;
    }

    function clearStack() {
        navStack = [];
        currentIndex = -1;
        try { sessionStorage.removeItem(STORAGE_KEY); } catch (ignore) {}
    }

    function pushEntry(entry) {
        // 截断当前位置之后的历史
        if (currentIndex < navStack.length - 1) {
            navStack = navStack.slice(0, currentIndex + 1);
        }
        navStack.push(entry);
        if (navStack.length > MAX_STACK) {
            navStack.shift();
        }
        currentIndex = navStack.length - 1;
        saveStack();
    }

    function currentEntry() {
        if (currentIndex >= 0 && currentIndex < navStack.length) {
            return navStack[currentIndex];
        }
        return null;
    }

    function canGoBack() {
        return currentIndex > 0;
    }

    // ==================== 导航 ====================
    function navigateToCategory(folderPath, pushHistory) {
        if (pushHistory === undefined) pushHistory = true;

        var url = window.ROUTES.categoryData + '?path=' + encodeURIComponent(folderPath);
        showLoading(true);

        fetch(url)
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.code !== 0) {
                    showError('加载失败: ' + (data.msg || '未知错误'));
                    return;
                }
                var info = data.data;
                var parentPath = getParentPath(folderPath);

                // 兜底：单个分类且无根文件 → 直接跳 grid
                if (info.single_leaf_override && info.total_categories === 1) {
                    var onlyPath = info.categories[0].path;
                    navigateToGrid(onlyPath, pushHistory);
                    return;
                }

                // 有非空子文件夹 → 渲染分类视图（与 SSR category_browse 一致）
                if (info.total_categories > 0) {
                    var entry = {
                        type: 'category',
                        path: folderPath,
                        data: info,
                        parentPath: parentPath,
                        isHomepage: folderPath === ''
                    };
                    if (pushHistory) {
                        pushEntry(entry);
                        var browseUrl = folderPath ? window.ROUTES.categoryBrowse + encodeURIComponent(folderPath) : '/';
                        history.pushState({ spaIndex: currentIndex }, '', browseUrl);
                    } else {
                        // 替换当前条目
                        if (currentIndex >= 0) {
                            navStack[currentIndex] = entry;
                            saveStack();
                        }
                    }
                    renderCategoryView(info, folderPath, parentPath, folderPath === '');
                } else {
                    // 叶子 → grid 视图
                    navigateToGrid(folderPath, pushHistory);
                }
            })
            .catch(function(err) {
                console.error('SPA navigateToCategory 失败:', err);
                showError('网络错误，请重试');
            });
    }

    function navigateToGrid(folderPath, page, pushHistory) {
        if (pushHistory === undefined) pushHistory = true;
        if (!page) page = 1;

        gridFolderPath = folderPath;
        // 页面尺寸从 SPA_INITIAL_STATE 读取，默认为 35
        if (window.SPA_INITIAL_STATE) {
            gridPageFirst = window.SPA_INITIAL_STATE.pageFirst || 35;
            gridPageLoad = window.SPA_INITIAL_STATE.pageLoad || 35;
        }
        gridPageCache = {};
        gridCurrentPage = page;
        gridHasMore = true;
        gridIsLoading = false;

        var parentPath = getParentPath(folderPath);
        var folderName = folderPath.split('/').filter(Boolean).pop() || (window.SPA_INITIAL_STATE && window.SPA_INITIAL_STATE.folderName) || '';

        // 立即渲染头部（刷新/返回按钮指向当前文件夹）
        renderGridHeader(folderName, folderPath, parentPath);

        var entry = {
            type: 'grid',
            path: folderPath,
            page: page,
            parentPath: parentPath,
            folderName: folderName,
            pageCache: {},
            gridPageFirst: gridPageFirst,
            gridPageLoad: gridPageLoad
        };

        if (pushHistory) {
            pushEntry(entry);
            var gridUrl = window.ROUTES.categoryGrid + encodeURIComponent(folderPath);
            history.pushState({ spaIndex: currentIndex }, '', gridUrl);
        }

        // 加载第一页数据
        gridLoadPage(page, false);
    }

    function restoreGridFromEntry(entry) {
        gridFolderPath = entry.path;
        gridPageFirst = entry.gridPageFirst || 35;
        gridPageLoad = entry.gridPageLoad || 35;
        gridPageCache = entry.pageCache || {};
        gridCurrentPage = entry.page || 1;
        gridHasMore = true;
        gridIsLoading = false;

        var cached = gridPageCache[gridCurrentPage];
        if (cached && cached.items && cached.items.length > 0) {
            renderGridView(cached.items, entry.path, gridCurrentPage, cached.hasMore, entry.folderName, entry.parentPath);
        } else {
            renderGridSkeleton(entry.folderName, entry.parentPath);
            gridLoadPage(gridCurrentPage, false);
        }
    }

    function navigateBack(fallbackHref) {
        if (!canGoBack()) {
            window.location.href = fallbackHref || '/';
            return;
        }

        currentIndex--;
        saveStack();
        var entry = currentEntry();
        if (!entry) return;

        var backUrl;
        if (entry.type === 'category') {
            backUrl = entry.path ? window.ROUTES.categoryBrowse + encodeURIComponent(entry.path) : '/';
        } else {
            backUrl = window.ROUTES.categoryGrid + encodeURIComponent(entry.path);
        }
        history.replaceState({ spaIndex: currentIndex }, '', backUrl);

        if (entry.type === 'category') {
            renderCategoryView(entry.data, entry.path, entry.parentPath, entry.isHomepage);
        } else {
            restoreGridFromEntry(entry);
        }
    }

    function navigateForward() {
        if (currentIndex >= navStack.length - 1) return;

        currentIndex++;
        saveStack();
        var entry = currentEntry();
        if (!entry) return;

        var forwardUrl;
        if (entry.type === 'category') {
            forwardUrl = entry.path ? window.ROUTES.categoryBrowse + encodeURIComponent(entry.path) : '/';
        } else {
            forwardUrl = window.ROUTES.categoryGrid + encodeURIComponent(entry.path);
        }
        history.replaceState({ spaIndex: currentIndex }, '', forwardUrl);

        if (entry.type === 'category') {
            renderCategoryView(entry.data, entry.path, entry.parentPath, entry.isHomepage);
        } else {
            restoreGridFromEntry(entry);
        }
    }

    function handlePopState(event) {
        if (!event.state || event.state.spaIndex === undefined) {
            // 没有 SPA 状态 → 可能是外部导航，刷新页面
            return;
        }

        var targetIndex = event.state.spaIndex;
        if (targetIndex === currentIndex) return;

        if (targetIndex < currentIndex) {
            // 后退
            while (currentIndex > targetIndex && currentIndex >= 0) {
                currentIndex--;
            }
        } else {
            // 前进
            currentIndex = Math.min(targetIndex, navStack.length - 1);
        }

        saveStack();
        var entry = currentEntry();
        if (!entry) return;

        if (entry.type === 'category') {
            renderCategoryView(entry.data, entry.path, entry.parentPath, entry.isHomepage);
        } else {
            restoreGridFromEntry(entry);
        }
    }

    function getParentPath(folderPath) {
        if (!folderPath) return '';
        var parts = folderPath.split('/').filter(Boolean);
        parts.pop();
        return parts.join('/');
    }

    // ==================== 渲染：分类视图 ====================
    function renderCategoryView(info, currentPath, parentPath, isHomepage) {
        // Header
        var headerHtml = '';
        if (!isHomepage) {
            headerHtml += '<a href="javascript:void(0)" class="back-btn" data-spa-nav="back">&larr; 返回</a>';
        }
        headerHtml += '<h1>' + escHtml(info.folder_name) + '</h1>';
        headerHtml += '<a href="/category/browse/' + encodeURIComponent(currentPath) + '?refresh=1" class="refresh-btn">刷新</a>';

        var header = document.getElementById('spaHeader');
        header.className = 'category-header';
        header.innerHTML = headerHtml;

        // Content
        var html = '';

        // 分类区块
        if (info.categories && info.categories.length > 0) {
            for (var ci = 0; ci < info.categories.length; ci++) {
                var cat = info.categories[ci];
                html += '<div class="category-section">';
                html += '<div class="category-title-bar">';
                html += '<span class="category-title">' + escHtml(cat.name) + '</span>';
                html += '<a href="' + window.ROUTES.categoryBrowse + encodeURIComponent(cat.path) + '" class="show-more-btn" data-spa-nav="category" data-spa-path="' + escAttr(cat.path) + '">显示更多</a>';
                html += '</div>';
                html += '<div class="video-grid">';
                if (cat.files && cat.files.length > 0) {
                    for (var fi = 0; fi < cat.files.length; fi++) {
                        html += buildVideoCard(cat.files[fi]);
                    }
                }
                html += '</div>';
                html += '</div>';
            }
        }

        // 根目录文件
        if (info.root_files && info.root_files.length > 0) {
            html += '<div class="category-section">';
            html += '<div class="category-title-bar">';
            html += '<span class="category-title">' + escHtml(info.folder_name) + ' / 文件</span>';
            html += '</div>';
            html += '<div class="video-grid">';
            for (var rfi = 0; rfi < info.root_files.length; rfi++) {
                html += buildVideoCard(info.root_files[rfi]);
            }
            html += '</div>';
            html += '</div>';
        }

        if ((!info.categories || info.categories.length === 0) && (!info.root_files || info.root_files.length === 0)) {
            html += '<div class="category-empty">该目录下没有可展示的内容。</div>';
        }

        var content = document.getElementById('spaContent');
        content.innerHTML = html;

        var footer = document.getElementById('spaFooter');
        footer.innerHTML = '';
        footer.style.display = 'none';

        window.scrollTo(0, 0);
    }

    function buildVideoCard(item) {
        var thumbHtml = '';
        if (item.is_video || item.is_image) {
            thumbHtml = '<img src="' + window.ROUTES.mediaThumbnail + encodeURIComponent(item.relative_path) + '" alt="' + escAttr(item.name) + '" loading="lazy">';
        }
        var safePath = item.relative_path.replace(/'/g, "\\'");
        return '<div class="video-card" onclick="openMedia(\'' + safePath + '\')">' +
            '<div class="video-thumb">' + thumbHtml + '</div>' +
            '<div class="video-info"><div class="video-name" title="' + escAttr(item.name) + '">' + escHtml(item.name) + '</div></div>' +
            '</div>';
    }

    // ==================== 渲染：Grid 视图 ====================
    function renderGridHeader(folderName, folderPath, parentPath) {
        var header = document.getElementById('spaHeader');
        header.className = 'grid-header';

        var html = '';
        if (parentPath || canGoBack()) {
            html += '<a href="' + (parentPath ? window.ROUTES.categoryBrowse + encodeURIComponent(parentPath) : '/') + '" class="back-btn" data-spa-nav="back">&larr; 返回</a>';
        }
        html += '<h1>' + escHtml(folderName) + '</h1>';
        // 路径编码：保留 / 不编码，其他字符用 encodeURIComponent 逐段处理
        var encodedPath = folderPath.split('/').map(function(seg) { return encodeURIComponent(seg); }).join('/');
        html += '<a href="/category/grid/' + encodedPath + '?refresh=1" class="refresh-btn">刷新</a>';
        header.innerHTML = html;
    }

    function renderGridView(items, folderPath, page, hasMore, folderName, parentPath) {
        renderGridHeader(folderName, folderPath, parentPath);
        gridRenderItems(items, page, hasMore);
    }

    function gridRenderItems(items, page, hasMore) {
        var content = document.getElementById('spaContent');
        var html = '<div id="mediaGrid" class="video-grid">';
        for (var i = 0; i < items.length; i++) {
            html += buildVideoCard(items[i]);
        }
        html += '</div>';
        content.innerHTML = html;

        gridHasMore = hasMore;
        gridCurrentPage = page;

        // 更新栈条目中的缓存
        var entry = currentEntry();
        if (entry && entry.type === 'grid') {
            entry.pageCache = entry.pageCache || {};
            entry.pageCache[page] = { items: items, hasMore: hasMore };
            entry.page = page;
            entry.folderName = entry.folderName || (document.getElementById('spaHeader').querySelector('h1') && document.getElementById('spaHeader').querySelector('h1').textContent) || '';
            saveStack();
        }

        gridRenderPagination();
        window.scrollTo(0, 0);

        var footer = document.getElementById('spaFooter');
        footer.style.display = hasMore || gridCurrentPage > 1 ? 'block' : 'none';

        // No-more 提示
        var noMoreEl = document.getElementById('spaNoMore');
        if (noMoreEl) {
            noMoreEl.style.display = hasMore ? 'none' : 'block';
        }
    }

    function gridRenderPagination() {
        var prevBtn = document.getElementById('gridPrevPage');
        var nextBtn = document.getElementById('gridNextPage');
        var pageNumbers = document.getElementById('gridPageNumbers');

        if (!prevBtn || !nextBtn || !pageNumbers) return;

        prevBtn.disabled = gridCurrentPage <= 1 || gridIsLoading;
        nextBtn.disabled = !gridHasMore || gridIsLoading;

        var pagesHtml = '';
        if (gridCurrentPage === 1) {
            pagesHtml += '<span class="page-number current">1</span>';
        } else {
            pagesHtml += '<span class="page-number" data-page="1">1</span>';
        }

        if (gridCurrentPage > 3) {
            pagesHtml += '<span class="page-dots">...</span>';
        }

        for (var i = Math.max(2, gridCurrentPage - 1); i <= gridCurrentPage + 1; i++) {
            if (i <= 1) continue;
            var cached = gridPageCache[i];
            if (i === gridCurrentPage) {
                pagesHtml += '<span class="page-number current">' + i + '</span>';
            } else if (cached) {
                pagesHtml += '<span class="page-number" data-page="' + i + '">' + i + '</span>';
            } else if (i === gridCurrentPage + 1 && gridHasMore) {
                pagesHtml += '<span class="page-number" data-page="' + i + '">' + i + '</span>';
            }
        }

        if (gridHasMore) {
            pagesHtml += '<span class="page-dots">...</span>';
        }

        pageNumbers.innerHTML = pagesHtml;
    }

    function gridLoadPage(page, pushEntry) {
        if (pushEntry === undefined) pushEntry = true;

        var cached = gridPageCache[page];
        if (cached && cached.items && cached.items.length > 0) {
            gridRenderItems(cached.items, page, cached.hasMore);
            return;
        }

        gridIsLoading = true;
        document.getElementById('spaLoading').style.display = 'block';
        gridRenderPagination();

        if (gridAbortController) {
            gridAbortController.abort();
        }
        gridAbortController = new AbortController();

        var pageSize = page === 1 ? gridPageFirst : gridPageLoad;
        var offset = page === 1 ? 0 : gridPageFirst + (page - 2) * gridPageLoad;
        var url = window.ROUTES.categoryGridMore
            + '?path=' + encodeURIComponent(gridFolderPath)
            + '&offset=' + offset
            + '&limit=' + pageSize;

        fetch(url, { signal: gridAbortController.signal })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.code === 0) {
                    gridPageCache[page] = { items: data.data, hasMore: data.has_more };
                    gridRenderItems(data.data, page, data.has_more);
                } else {
                    showError('加载失败: ' + (data.msg || '未知错误'));
                }
            })
            .catch(function(err) {
                if (err.name === 'AbortError') return;
                console.error('SPA gridLoadPage 失败:', err);
                showError('网络错误，请重试');
            })
            .finally(function() {
                gridIsLoading = false;
                document.getElementById('spaLoading').style.display = 'none';
                gridAbortController = null;
                gridRenderPagination();
            });
    }

    function gridChangePage(page) {
        if (page < 1 || page === gridCurrentPage || gridIsLoading) return;
        if (!gridHasMore && page > gridCurrentPage) return;

        gridCurrentPage = page;
        gridLoadPage(page);

        // 更新栈条目
        var entry = currentEntry();
        if (entry && entry.type === 'grid') {
            entry.page = page;
            saveStack();
        }
    }

    // ==================== UI 辅助 ====================
    function showLoading(show) {
        var el = document.getElementById('spaLoading');
        if (el) el.style.display = show ? 'block' : 'none';
    }

    function showError(msg) {
        var content = document.getElementById('spaContent');
        if (content) {
            content.innerHTML = '<div class="category-empty" style="padding:40px;text-align:center;color:#ff6b6b;">' + escHtml(msg) + '</div>';
        }
        var footer = document.getElementById('spaFooter');
        if (footer) footer.style.display = 'none';
    }

    // ==================== 事件委托 ====================
    function handleClick(event) {
        // 查找最近的 <a> 标签
        var anchor = event.target.closest('a');
        if (anchor) {
            // 刷新按钮 → 放过，完整 SSR
            if (anchor.classList.contains('refresh-btn')) {
                return;
            }

            // data-spa-nav 属性
            var spaNav = anchor.getAttribute('data-spa-nav');
            if (spaNav === 'back') {
                event.preventDefault();
                var fallback = anchor.getAttribute('href');
                if (fallback === 'javascript:void(0)') fallback = null;
                navigateBack(fallback);
                return;
            }
            if (spaNav === 'category') {
                event.preventDefault();
                var catPath = anchor.getAttribute('data-spa-path');
                if (catPath) {
                    navigateToCategory(catPath, true);
                }
                return;
            }
            return;
        }

        // 分页按钮（button/span）
        var pageBtn = event.target.closest('#gridPrevPage');
        if (pageBtn && !pageBtn.disabled) {
            event.preventDefault();
            gridChangePage(gridCurrentPage - 1);
            return;
        }
        var nextBtn = event.target.closest('#gridNextPage');
        if (nextBtn && !nextBtn.disabled) {
            event.preventDefault();
            gridChangePage(gridCurrentPage + 1);
            return;
        }
        var pageNum = event.target.closest('.page-number[data-page]');
        if (pageNum) {
            event.preventDefault();
            var pg = parseInt(pageNum.getAttribute('data-page'), 10);
            if (pg > 0) gridChangePage(pg);
            return;
        }
    }

    // ==================== 初始化 ====================
    function init() {
        document.addEventListener('click', handleClick);
        window.addEventListener('popstate', handlePopState);

        // 检查是否从 player 返回
        var returning = false;
        try {
            returning = sessionStorage.getItem(RETURNING_KEY) === '1';
            sessionStorage.removeItem(RETURNING_KEY);
        } catch (ignore) {}

        if (returning && loadStack()) {
            // 从 player 返回 → 恢复栈并渲染最后一个条目
            var entry = currentEntry();
            if (entry) {
                if (entry.type === 'category') {
                    renderCategoryView(entry.data, entry.path, entry.parentPath, entry.isHomepage);
                } else {
                    restoreGridFromEntry(entry);
                }
                return;
            }
        }

        // 全新加载 → 清空旧栈，从 SSR 初始状态创建
        clearStack();
        var initState = window.SPA_INITIAL_STATE;
        if (!initState) return; // 非 SPA 页面

        if (initState.viewType === 'grid') {
            gridFolderPath = initState.folderPath || '';
            gridPageFirst = initState.pageFirst || 35;
            gridPageLoad = initState.pageLoad || 35;
            gridCurrentPage = 1;
            gridHasMore = initState.hasMore !== undefined ? initState.hasMore : false;
            gridIsLoading = false;
            gridPageCache = {};

            // 缓存首页 SSR 数据
            if (initState.files && initState.files.length > 0) {
                gridPageCache[1] = { items: initState.files, hasMore: initState.hasMore };
            }

            var entry = {
                type: 'grid',
                path: initState.folderPath || '',
                page: 1,
                parentPath: initState.parentPath || '',
                folderName: initState.folderName || '',
                pageCache: gridPageCache,
                gridPageFirst: gridPageFirst,
                gridPageLoad: gridPageLoad
            };
            pushEntry(entry);
            history.replaceState({ spaIndex: currentIndex }, '', window.location.href);
        } else {
            // category 视图
            var catEntry = {
                type: 'category',
                path: initState.folderPath || '',
                data: {
                    folder_name: initState.folderName,
                    folder_path: initState.folderPath,
                    categories: initState.categories || [],
                    root_files: initState.rootFiles || [],
                    total_categories: initState.totalCategories || 0,
                    is_leaf: false
                },
                parentPath: initState.parentPath || '',
                isHomepage: initState.isHomepage || false
            };
            pushEntry(catEntry);
            history.replaceState({ spaIndex: currentIndex }, '', window.location.href);
        }
    }

    function renderGridSkeleton(folderName, parentPath) {
        renderGridHeader(folderName, gridFolderPath, parentPath);
        document.getElementById('spaContent').innerHTML = '';
        document.getElementById('spaLoading').style.display = 'block';
    }

    // ==================== 全局 openMedia ====================
    window.openMedia = function(relativePath) {
        try {
            sessionStorage.setItem(RETURNING_KEY, '1');
        } catch (ignore) {}
        saveStack(); // 确保最新栈已持久化
        window.location.href = window.ROUTES.mediaPlayer + '?path=' + encodeURIComponent(relativePath);
    };

    // ==================== 启动 ====================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
