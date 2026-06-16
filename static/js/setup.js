/**
 * LaptopWatch 启动配置 — 行为与原版 tkinter GUI 对齐
 */
(function () {
    'use strict';

    // ── DOM ──
    var el = {
        tabBtns: document.querySelectorAll('.tab-btn'),
        tabConsole: document.getElementById('tabConsole'),
        tabLogs: document.getElementById('tabLogs'),
        statusDot: document.getElementById('statusDot'),
        statusText: document.getElementById('statusText'),
        mediaDir: document.getElementById('mediaDir'),
        browseBtn: document.getElementById('browseBtn'),
        sortType: document.getElementById('sortType'),
        sortOrder: document.getElementById('sortOrder'),
        randomMode: document.getElementById('randomMode'),
        douyinRandom: document.getElementById('douyinRandom'),
        categoryBrowse: document.getElementById('categoryBrowse'),
        startBtn: document.getElementById('startBtn'),
        stopBtn: document.getElementById('stopBtn'),
        urlDisplay: document.getElementById('urlDisplay'),
        openBrowserBtn: document.getElementById('openBrowserBtn'),
        qrBox: document.getElementById('qrBox'),
        qrPlaceholder: document.getElementById('qrPlaceholder'),
        qrImage: document.getElementById('qrImage'),
        qidStatus: document.getElementById('qidStatus'),
        qidStartBtn: document.getElementById('qidStartBtn'),
        qidStopBtn: document.getElementById('qidStopBtn'),
        qidOpenBtn: document.getElementById('qidOpenBtn'),
        logViewer: document.getElementById('logViewer'),
        footerStatus: document.getElementById('footerStatus'),
        footerRuntime: document.getElementById('footerRuntime'),
    };

    var running = false;
    var sessionStart = null;
    var currentMode = 'normal';

    // ── 日志 ──
    function log(text, cls) {
        var line = document.createElement('div');
        line.className = 'log-line' + (cls ? ' ' + cls : '');
        line.textContent = text;
        el.logViewer.appendChild(line);
        el.logViewer.scrollTop = el.logViewer.scrollHeight;
        if (el.logViewer.children.length > 500) {
            el.logViewer.removeChild(el.logViewer.firstChild);
        }
    }

    // ── 标签切换 ──
    el.tabBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var tab = btn.dataset.tab;
            el.tabBtns.forEach(function (b) { b.classList.toggle('active', b === btn); });
            el.tabConsole.classList.toggle('active', tab === 'console');
            el.tabLogs.classList.toggle('active', tab === 'logs');
        });
    });

    // ── 控件工具 ──
    function setDisabled(elt, disabled) {
        elt.disabled = disabled;
    }

    // ── 模式切换（与原版 _on_mode_change 对齐）──
    var modeBtns = document.querySelectorAll('.seg-btn');

    function onModeChange() {
        var isMedia = currentMode === 'video' || currentMode === 'image';
        var isDouyin = currentMode === 'douyin';
        var isAnyMedia = isMedia || isDouyin;
        var sortIrrelevant = isDouyin && el.douyinRandom.checked;

        // 目录 & 浏览：任何媒体模式启用
        var baseState = isAnyMedia;
        setDisabled(el.mediaDir, !baseState);
        setDisabled(el.browseBtn, !baseState);

        // 排序 & 随机位置：媒体模式启用，但抖音+随机媒体时禁用
        var sortState = isAnyMedia && !sortIrrelevant;
        setDisabled(el.sortType, !sortState);
        setDisabled(el.sortOrder, !sortState);
        setDisabled(el.randomMode, !sortState);

        // 随机媒体：仅抖音模式
        setDisabled(el.douyinRandom, !isDouyin);

        // 目录浏览：仅 video/image 模式
        setDisabled(el.categoryBrowse, !isMedia);

        // 非媒体模式清空
        if (!isAnyMedia) {
            el.mediaDir.value = '';
            el.sortType.value = 'name';
            el.sortOrder.value = 'asc';
            el.randomMode.checked = false;
            el.douyinRandom.checked = false;
        }
    }

    modeBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            modeBtns.forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            currentMode = btn.dataset.mode;
            onModeChange();
        });
    });

    // ── Checkbox 互斥 ──
    el.randomMode.addEventListener('change', function () {
        if (el.randomMode.checked) el.douyinRandom.checked = false;
        onModeChange();
    });
    el.douyinRandom.addEventListener('change', function () {
        if (el.douyinRandom.checked) el.randomMode.checked = false;
        onModeChange();
    });
    el.categoryBrowse.addEventListener('change', function () {
        // 无互斥逻辑，仅触发刷新
    });

    // ── 浏览按钮 ──
    el.browseBtn.addEventListener('click', function () {
        // disabled 时无法点击，这里只处理 enabled 状态
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.select_folder().then(function (path) {
                if (path) el.mediaDir.value = path;
            });
            return;
        }
        var path = prompt('请输入媒体目录路径:', el.mediaDir.value || '');
        if (path) el.mediaDir.value = path;
    });

    // ── 启动/停止结果处理 ──
    function handleStartSuccess(d) {
        running = true;
        sessionStart = Date.now();
        updateRunningState(true);
        el.urlDisplay.value = d.lan_url || '';
        if (d.qr_base64) {
            el.qrPlaceholder.style.display = 'none';
            el.qrImage.src = 'data:image/png;base64,' + d.qr_base64;
            el.qrImage.style.display = 'block';
        }
        log(currentMode + '模式服务启动成功！');
        log('访问地址：' + (d.lan_url || ''));
        if (el.randomMode.checked) log('随机模式已开启，媒体浏览将从随机位置开始');
        log('服务初始化完成，可以访问页面', 'ok');
    }

    function handleStartError(msg) {
        log('启动失败: ' + (msg || '未知错误'), 'error');
        el.startBtn.disabled = false;
    }

    function handleStop() {
        log('[STOP] 服务已彻底停止');
        updateRunningState(false);
    }

    // ── 启动 ──
    el.startBtn.addEventListener('click', function () {
        var dir = el.mediaDir.value.trim();
        if ((currentMode === 'video' || currentMode === 'image' || currentMode === 'douyin') && !dir) {
            log('错误：请先选择媒体目录', 'error');
            return;
        }

        var settings = {
            mode: currentMode,
            media_dir: dir,
            sort_type: el.sortType.value,
            sort_order: el.sortOrder.value,
            random: el.randomMode.checked,
            douyin_random: el.douyinRandom.checked,
            category_browse: el.categoryBrowse.checked,
        };

        el.startBtn.disabled = true;

        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.start_service(settings).then(function (d) {
                if (d.code === 0) {
                    handleStartSuccess(d);
                } else {
                    handleStartError(d.msg);
                }
            }).catch(function (e) {
                handleStartError(e.message);
            });
            return;
        }
        // 浏览器模式兜底
        fetch('/api/start_service', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        }).then(function (r) { return r.json(); }).then(function (d) {
            if (d.code === 0) {
                handleStartSuccess(d);
            } else {
                handleStartError(d.msg);
            }
        }).catch(function (e) {
            handleStartError(e.message);
        });
    });

    // ── 停止 ──
    el.stopBtn.addEventListener('click', function () {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.stop_service().then(function () {
                handleStop();
            }).catch(function () {});
            return;
        }
        fetch('/api/stop_service', { method: 'POST' }).finally(function () {
            handleStop();
        });
    });

    // ── 打开浏览器 ──
    el.openBrowserBtn.addEventListener('click', function () {
        var url = el.urlDisplay.value;
        if (url && url !== '—') window.open(url, '_blank');
    });

    // ── 管理台控制 ──
    function _qidApi(method) {
        if (window.pywebview && window.pywebview.api) {
            return window.pywebview.api[method]();
        }
        return Promise.reject(new Error('PyWebView API 不可用'));
    }

    function _updateQidUI(running, url) {
        el.qidStatus.textContent = running ? (url || '') : '未启动';
        el.qidStartBtn.disabled = running;
        el.qidStopBtn.disabled = !running;
        el.qidOpenBtn.disabled = !running;
    }

    function refreshQidStatus() {
        _qidApi('get_qid_status').then(function (status) {
            _updateQidUI(status.running, status.url);
        }).catch(function () {});
    }

    el.qidStartBtn.addEventListener('click', function () {
        el.qidStartBtn.disabled = true;
        _qidApi('start_qid').then(function (result) {
            if (result.code === 0) {
                log('管理台已启动: ' + (result.qid_url || ''));
                _updateQidUI(true, result.qid_url);
            } else {
                log('管理台启动失败: ' + (result.msg || '未知错误'), 'error');
                el.qidStartBtn.disabled = false;
            }
        }).catch(function (e) {
            log('管理台启动失败: ' + e.message, 'error');
            el.qidStartBtn.disabled = false;
        });
    });

    el.qidStopBtn.addEventListener('click', function () {
        _qidApi('stop_qid').then(function () {
            log('管理台已停止');
            _updateQidUI(false, '');
        }).catch(function () {});
    });

    el.qidOpenBtn.addEventListener('click', function () {
        _qidApi('open_qid').catch(function () {});
        var ip = '127.0.0.1';
        window.open('http://' + ip + ':5001', '_blank');
    });

    // ── 状态更新 ──
    function updateRunningState(on) {
        running = on;
        el.statusDot.classList.toggle('on', on);
        el.statusText.textContent = on ? '运行中（' + currentMode + '模式）' : '未运行';
        el.startBtn.disabled = on;
        el.stopBtn.disabled = !on;
        el.openBrowserBtn.disabled = !on;

        // 启动后禁用所有配置控件（与原版 _disable_config_controls 对齐）
        modeBtns.forEach(function (b) { b.disabled = on; });
        el.mediaDir.disabled = on;
        el.browseBtn.disabled = on;
        el.sortType.disabled = on;
        el.sortOrder.disabled = on;
        el.randomMode.disabled = on;
        el.douyinRandom.disabled = on;
        el.categoryBrowse.disabled = on;

        if (!on) {
            el.urlDisplay.value = '—';
            sessionStart = null;
            el.footerRuntime.textContent = '';
            // 清除二维码
            el.qrPlaceholder.style.display = '';
            el.qrImage.style.display = 'none';
            el.qrImage.src = '';
            // 恢复配置控件状态
            onModeChange();
        }
    }

    // ── 运行时长 ──
    setInterval(function () {
        if (sessionStart && running) {
            var sec = Math.floor((Date.now() - sessionStart) / 1000);
            var h = String(Math.floor(sec / 3600)).padStart(2, '0');
            var m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
            var s = String(sec % 60).padStart(2, '0');
            el.footerRuntime.textContent = '已运行 ' + h + ':' + m + ':' + s;
        }
    }, 500);

    // ── Flask 子进程日志轮询 + 崩溃检测 ──
    setInterval(function () {
        if (!running) return;
        if (!window.pywebview || !window.pywebview.api) return;
        window.pywebview.api.get_flask_logs().then(function (result) {
            (result.logs || []).forEach(function (line) { log(line); });
        }).catch(function () {});
    }, 1000);

    setInterval(function () {
        if (!running) return;
        if (!window.pywebview || !window.pywebview.api) return;
        window.pywebview.api.get_service_status().then(function (status) {
            if (!status.running) {
                log('服务进程已意外退出', 'error');
                updateRunningState(false);
            }
        }).catch(function () {});
    }, 3000);

    // ── 初始化 ──
    onModeChange();
    refreshQidStatus();
    log('就绪', 'dim');
})();
