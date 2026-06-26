/**
 * LaptopWatch 启动配置 — PyWebView GUI 前端
 */
(function () {
    'use strict';

    // ── DOM ──
    var el = {
        tabBtns: document.querySelectorAll('.tab-btn'),
        tabConsole: document.getElementById('tabConsole'),
        tabLogs: document.getElementById('tabLogs'),
        tabAdvanced: document.getElementById('tabAdvanced'),
        statusDot: document.getElementById('statusDot'),
        statusText: document.getElementById('statusText'),
        mediaDir: document.getElementById('mediaDir'),
        browseBtn: document.getElementById('browseBtn'),
        sortType: document.getElementById('sortType'),
        sortOrder: document.getElementById('sortOrder'),
        randomMode: document.getElementById('randomMode'),
        douyinRandom: document.getElementById('douyinRandom'),
        categoryBrowse: document.getElementById('categoryBrowse'),
        startServerBtn: document.getElementById('startServerBtn'),
        activateServiceBtn: document.getElementById('activateServiceBtn'),
        stopServerBtn: document.getElementById('stopServerBtn'),
        deactivateServiceBtn: document.getElementById('deactivateServiceBtn'),
        stopServiceBtn: document.getElementById('stopServiceBtn'),
        applyConfigServerOnBtn: document.getElementById('applyConfigServerOnBtn'),
        applyConfigActiveBtn: document.getElementById('applyConfigActiveBtn'),
        btnColOff: document.getElementById('btnColOff'),
        btnColServerOn: document.getElementById('btnColServerOn'),
        btnColActive: document.getElementById('btnColActive'),
        urlDisplay: document.getElementById('urlDisplay'),
        openBrowserBtn: document.getElementById('openBrowserBtn'),
        urlGroup: document.getElementById('urlGroup'),
        qrBox: document.getElementById('qrBox'),
        qrPlaceholder: document.getElementById('qrPlaceholder'),
        qrImage: document.getElementById('qrImage'),
        qidStatus: document.getElementById('qidStatus'),
        qidActionBtn: document.getElementById('qidActionBtn'),
        qidOpenBtn: document.getElementById('qidOpenBtn'),
        qidUrlField: document.getElementById('qidUrlField'),
        qidUrlDisplay: document.getElementById('qidUrlDisplay'),
        changePasswordBtn: document.getElementById('changePasswordBtn'),
        passwordModal: document.getElementById('passwordModal'),
        passwordForm: document.getElementById('passwordForm'),
        newPassword: document.getElementById('newPassword'),
        confirmPassword: document.getElementById('confirmPassword'),
        cancelPasswordBtn: document.getElementById('cancelPasswordBtn'),
        pwdCharError: document.getElementById('pwdCharError'),
        confirmError: document.getElementById('confirmError'),
        modalError: document.getElementById('modalError'),
        logViewer: document.getElementById('logViewer'),
        footerStatus: document.getElementById('footerStatus'),
        footerRuntime: document.getElementById('footerRuntime'),
    };

    var serverState = 'off';  // 'off' | 'server_on' | 'service_active'
    var sessionStart = null;
    var currentMode = 'normal';
    var footerTimer = null;  // 错误高亮恢复定时器
    var _pendingLanUrl = '';     // 服务器 URL（启动后暂存）
    var _pendingQrBase64 = '';  // QR 码（启动后暂存）

    // ── 操作类型中文映射 ──
    var ACTION_MAP = {
        'INDEX': '首页访问',
        'BROWSE': '浏览目录',
        'RAW_PREVIEW': '文件预览',
        'DOWNLOAD': '文件下载',
        'DOWNLOAD_FOLDER': '文件夹下载',
        'DOWNLOAD_SELECTED': '批量下载',
        'VIEW_TEXT': '文本查看',
        'LOAD_MORE': '加载更多',
        'MEDIA_SERVE': '媒体播放',
        'DOWNLOAD_MEDIA': '媒体下载',
        'MEDIA_NAV': '媒体导航',
        'MEDIA_PLAY': '开始播放视频',
        'MEDIA_VIEW': '查看图片',
        'MEDIA_STREAM': '视频流传输',
        'MEDIA_PLAY_END': '视频播放结束',
        'MEDIA_VIEW_END': '图片查看结束',
        'MEDIA_ACCESS_ERROR': '媒体访问错误',
        'DOUYIN_INIT': '抖音初始化',
        'DOUYIN_NEXT': '抖音下一个视频',
        'LOGIN': '登录',
        'LOGOUT': '登出',
    };

    // ── 日志级别自动检测 ──
    function detectLogClass(text) {
        if (text.indexOf('[ERROR]') !== -1 || text.indexOf('Exception') !== -1 ||
            text.indexOf('Traceback') !== -1 || text.indexOf('Failed') !== -1) {
            return 'error';
        }
        if (text.indexOf('[WARN]') !== -1 || text.indexOf('[STOP]') !== -1) {
            return 'warn';
        }
        if (text.indexOf('[OK]') !== -1 || text.indexOf('初始化完成') !== -1) {
            return 'ok';
        }
        if (text.indexOf('[SYNC]') !== -1 || text.indexOf('[INFO]') !== -1 ||
            text.indexOf('[QID]') !== -1) {
            return 'info';
        }
        if (text.indexOf('[ACCESS]') !== -1) {
            return 'access';
        }
        return '';
    }

    // ── 从 [ACCESS][ACTION_TYPE] 行提取活动信息 ──
    function parseAccessLine(text) {
        var match = text.match(/\[ACCESS\]\[(\w+)\]/);
        if (!match) return null;
        var action = match[1];
        var actionText = ACTION_MAP[action] || action;
        // 提取 IP
        var ipMatch = text.match(/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/);
        var ip = ipMatch ? ipMatch[1] : '';
        // 提取文件路径
        var filePath = '';
        var detailsMatch = text.match(/原始路径:\s*([^,\]]+)/);
        if (detailsMatch) {
            filePath = detailsMatch[1];
        } else {
            var parts = text.split(' | ');
            if (parts.length >= 3) {
                filePath = parts[2].split(' ')[0];
                if (filePath.length > 50) {
                    var segments = filePath.split('/');
                    if (segments.length > 3) {
                        filePath = '.../' + segments.slice(-3).join('/');
                    }
                }
            }
        }
        var activity = ip ? (ip + '  ' + actionText) : actionText;
        if (filePath) {
            activity += '  ' + filePath;
        }
        if (activity.length > 100) {
            activity = activity.substring(0, 100) + '...';
        }
        return activity;
    }

    // ── 错误高亮底部状态栏 ──
    function highlightError() {
        el.footerStatus.style.color = 'var(--danger)';
        if (footerTimer) clearTimeout(footerTimer);
        footerTimer = setTimeout(function () {
            el.footerStatus.style.color = '';
        }, 3000);
    }

    // ── 日志输出 ──
    function log(text, cls) {
        // 同步写入 Python 会话日志文件
        if (window.pywebview && window.pywebview.api) {
            try { window.pywebview.api.add_log(text); } catch (e) { /* 静默 */ }
        }
        var detected = cls || detectLogClass(text);
        var line = document.createElement('div');
        line.className = 'log-line' + (detected ? ' ' + detected : '');
        line.textContent = text;
        el.logViewer.appendChild(line);
        el.logViewer.scrollTop = el.logViewer.scrollHeight;
        if (el.logViewer.children.length > 500) {
            el.logViewer.removeChild(el.logViewer.firstChild);
        }
        // 活动解析 → 底部状态栏
        var activity = parseAccessLine(text);
        if (activity) {
            el.footerStatus.textContent = activity;
        }
        // 错误高亮
        if (detected === 'error') {
            highlightError();
        }
    }

    // ── 标签切换 ──
    el.tabBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var tab = btn.dataset.tab;
            el.tabBtns.forEach(function (b) { b.classList.toggle('active', b === btn); });
            el.tabConsole.classList.toggle('active', tab === 'console');
            el.tabLogs.classList.toggle('active', tab === 'logs');
            el.tabAdvanced.classList.toggle('active', tab === 'advanced');
        });
    });

    // ── 控件工具 ──
    function setDisabled(elt, disabled) {
        elt.disabled = disabled;
    }

    // ── 模式切换（与原版 _on_mode_change 对齐）──
    var modeBtns = document.querySelectorAll('.mode-card');

    function onModeChange() {
        var isMedia = currentMode === 'video' || currentMode === 'image';
        var isDouyin = currentMode === 'douyin';
        var isAnyMedia = isMedia || isDouyin;
        var sortIrrelevant = isDouyin && el.douyinRandom.checked;
        var isRunning = serverState !== 'off';

        // 启动前：所有控件按模式启用/禁用；运行中：仅启动配置锁定，运行时可改的照常
        if (!isRunning) {
            setDisabled(el.mediaDir, false);
            setDisabled(el.browseBtn, false);
            var sortState = isAnyMedia && !sortIrrelevant;
            setDisabled(el.sortType, !sortState);
            setDisabled(el.sortOrder, !sortState);
        }
        setDisabled(el.randomMode, isRunning ? false : !(isAnyMedia && !sortIrrelevant));
        setDisabled(el.douyinRandom, !isDouyin);
        setDisabled(el.categoryBrowse, !isMedia);
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

    // ── 运行时配置更新 ──
    function updateRuntimeConfig(settings) {
        if (window.pywebview && window.pywebview.api) {
            return window.pywebview.api.update_runtime_config(settings).catch(function (e) {
                return { code: 1, msg: e.message || String(e) };
            });
        }
        return fetch('/api/admin/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Auth-Password': '574406731',
            },
            body: JSON.stringify(settings),
        }).then(function (r) { return r.json(); }).catch(function (e) {
            return { code: 1, msg: e.message };
        });
    }

    // ── 收集当前原始控件的运行时配置 ──
    function _collectRuntimeSettings() {
        return {
            mode: currentMode,
            media_dir: el.mediaDir.value.trim(),
            random_mode: el.randomMode.checked,
            douyin_random_media: el.douyinRandom.checked,
            category_browse: el.categoryBrowse.checked,
        };
    }

    // ── 更新配置按钮（SERVER_ON 和 SERVICE_ACTIVE 共用逻辑）──
    function _onApplyConfig(btn) {
        var settings = _collectRuntimeSettings();
        btn.disabled = true;

        updateRuntimeConfig(settings).then(function (result) {
            btn.disabled = false;
            if (result.code === 0) {
                log('[运行时] 配置已更新（版本 ' + (result.config && result.config.config_version || '?') + '）', 'ok');
                if (result.config) {
                    if (serverState === 'service_active') {
                        el.statusText.textContent = '运行中（' + (result.config.run_mode || currentMode) + '模式）';
                    }
                    // 在 SERVER_ON 状态下保持 "服务器已启动（未激活）"
                }
            } else {
                log('[运行时] 配置更新失败: ' + (result.msg || '未知错误'), 'error');
            }
        }).catch(function (e) {
            btn.disabled = false;
            log('[运行时] 配置更新异常: ' + (e.message || e), 'error');
        });
    }

    el.applyConfigServerOnBtn.addEventListener('click', function () {
        _onApplyConfig(el.applyConfigServerOnBtn);
    });
    el.applyConfigActiveBtn.addEventListener('click', function () {
        _onApplyConfig(el.applyConfigActiveBtn);
    });

    // ── 浏览按钮 ──
    el.browseBtn.addEventListener('click', function () {
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
    function handleStartError(msg) {
        log('启动失败: ' + (msg || '未知错误'), 'error');
        updateServerState('off');
    }

    function handleActivateSuccess(d) {
        updateServerState('service_active');
        el.urlDisplay.value = d.lan_url || _pendingLanUrl;
        if (d.qr_base64) {
            el.qrPlaceholder.style.display = 'none';
            el.qrImage.src = 'data:image/png;base64,' + d.qr_base64;
            el.qrImage.style.display = 'block';
        }
        log('服务已激活！');
        log('访问地址：' + (d.lan_url || _pendingLanUrl));
        log('服务初始化完成，可以访问页面', 'ok');
    }

    function handleStop() {
        log('[STOP] 服务已彻底停止');
        _pendingLanUrl = '';
        updateServerState('off');
    }

    // ── 启动服务器 ──
    el.startServerBtn.addEventListener('click', function () {
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

        el.startServerBtn.disabled = true;

        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.start_service(settings).then(function (d) {
                if (d.code === 0) {
                    _pendingLanUrl = d.lan_url || '';
                    _pendingQrBase64 = d.qr_base64 || '';
                    sessionStart = Date.now();
                    updateServerState('server_on');
                    log(currentMode + '模式服务器已启动（服务未激活）');
                    log('服务器地址：' + (d.lan_url || ''));
                } else {
                    handleStartError(d.msg);
                }
            }).catch(function (e) {
                handleStartError(e.message);
            });
            return;
        }
        fetch('/api/start_service', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        }).then(function (r) { return r.json(); }).then(function (d) {
            if (d.code === 0) {
                _pendingLanUrl = d.lan_url || '';
                _pendingQrBase64 = d.qr_base64 || '';
                sessionStart = Date.now();
                updateServerState('server_on');
                log('服务器已启动（服务未激活）');
            } else {
                handleStartError(d.msg);
            }
        }).catch(function (e) {
            handleStartError(e.message);
        });
    });

    // ── 启动服务（激活）──
    el.activateServiceBtn.addEventListener('click', function () {
        el.activateServiceBtn.disabled = true;

        var runtimeSettings = _collectRuntimeSettings();

        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.activate_service(runtimeSettings).then(function (d) {
                if (d.code === 0) {
                    handleActivateSuccess(d);
                } else {
                    log('服务激活失败: ' + (d.msg || '未知错误'), 'error');
                    el.activateServiceBtn.disabled = false;
                }
            }).catch(function (e) {
                log('服务激活失败: ' + e.message, 'error');
                el.activateServiceBtn.disabled = false;
            });
            return;
        }
        runtimeSettings.service_active = true;
        fetch('/api/admin/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Auth-Password': '574406731',
            },
            body: JSON.stringify(runtimeSettings),
        }).then(function (r) { return r.json(); }).then(function (d) {
            if (d.code === 0) {
                handleActivateSuccess({ lan_url: _pendingLanUrl, qr_base64: '' });
            } else {
                log('服务激活失败: ' + (d.msg || '未知错误'), 'error');
                el.activateServiceBtn.disabled = false;
            }
        }).catch(function (e) {
            log('服务激活失败: ' + e.message, 'error');
            el.activateServiceBtn.disabled = false;
        });
    });

    // ── 停用服务（SERVICE_ACTIVE → SERVER_ON）──
    el.deactivateServiceBtn.addEventListener('click', function () {
        el.deactivateServiceBtn.disabled = true;
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.deactivate_service().then(function (d) {
                if (d.code === 0) {
                    log('[INFO] 服务已停用（服务器仍在运行）');
                    updateServerState('server_on');
                } else {
                    log('服务停用失败: ' + (d.msg || '未知错误'), 'error');
                    el.deactivateServiceBtn.disabled = false;
                }
            }).catch(function (e) {
                log('服务停用失败: ' + e.message, 'error');
                el.deactivateServiceBtn.disabled = false;
            });
            return;
        }
        updateRuntimeConfig({ service_active: false }).then(function (result) {
            if (result.code === 0) {
                log('[INFO] 服务已停用（服务器仍在运行）');
                updateServerState('server_on');
            } else {
                log('服务停用失败: ' + (result.msg || '未知错误'), 'error');
                el.deactivateServiceBtn.disabled = false;
            }
        }).catch(function (e) {
            log('服务停用失败: ' + e.message, 'error');
            el.deactivateServiceBtn.disabled = false;
        });
    });

    // ── 停止服务器（SERVER_ON 状态）──
    el.stopServerBtn.addEventListener('click', function () {
        el.stopServerBtn.disabled = true;
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.stop_service().then(function () {
                handleStop();
            }).catch(function () {
                handleStop();
            });
            return;
        }
        fetch('/api/stop_service', { method: 'POST' }).finally(function () {
            handleStop();
        });
    });

    // ── 停止服务（SERVICE_ACTIVE 状态）──
    el.stopServiceBtn.addEventListener('click', function () {
        el.stopServiceBtn.disabled = true;
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.stop_service().then(function () {
                handleStop();
            }).catch(function () {
                handleStop();
            });
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

    function _updateQidUI(running_qid, url) {
        el.qidStatus.textContent = running_qid ? '运行中' : '未启动';
        el.qidStatus.classList.toggle('running', running_qid);
        el.qidActionBtn.disabled = false;
        el.qidActionBtn.textContent = running_qid ? '停止管理台' : '启动管理台';
        el.qidActionBtn.className = running_qid ? 'btn btn-stop btn-full' : 'btn btn-outline btn-full';
        el.qidOpenBtn.disabled = !running_qid;
        el.qidUrlDisplay.value = url || '';
        el.qidUrlField.style.display = running_qid ? 'flex' : 'none';
    }

    function refreshQidStatus() {
        _qidApi('get_qid_status').then(function (status) {
            _updateQidUI(status.running, status.url);
        }).catch(function () {});
    }

    el.qidActionBtn.addEventListener('click', function () {
        var isRunning = el.qidStatus.textContent === '运行中';
        if (isRunning) {
            el.qidActionBtn.disabled = true;
            _qidApi('stop_qid').then(function () {
                log('管理台已停止');
                _updateQidUI(false, '');
            }).catch(function () {
                el.qidActionBtn.disabled = false;
            });
            return;
        }
        el.qidActionBtn.disabled = true;
        _qidApi('start_qid').then(function (result) {
            if (result.code === 0) {
                log('管理台已启动: ' + (result.qid_url || ''));
                _updateQidUI(true, result.qid_url);
            } else {
                log('管理台启动失败: ' + (result.msg || '未知错误'), 'error');
                _updateQidUI(false, '');
            }
        }).catch(function (e) {
            log('管理台启动失败: ' + e.message, 'error');
            _updateQidUI(false, '');
        });
    });

    el.qidOpenBtn.addEventListener('click', function () {
        _qidApi('open_qid').catch(function () {});
        var ip = '127.0.0.1';
        window.open('http://' + ip + ':5001', '_blank');
    });

    // ── 状态更新 ──
    function updateServerState(state) {
        serverState = state;
        var isOff = state === 'off';
        var isServerOn = state === 'server_on';
        var isActive = state === 'service_active';
        var isRunning = !isOff;

        // Status dot / text
        el.statusDot.classList.toggle('on', isRunning);
        if (isOff) {
            el.statusText.textContent = '未运行';
        } else if (isServerOn) {
            el.statusText.textContent = '服务器已启动（未激活）';
        } else {
            el.statusText.textContent = '运行中（' + currentMode + '模式）';
        }

        // Button visibility
        el.btnColOff.style.display = isOff ? 'flex' : 'none';
        el.btnColServerOn.style.display = isServerOn ? 'flex' : 'none';
        el.btnColActive.style.display = isActive ? 'flex' : 'none';

        // Controls: mode / mediaDir / sort 运行时可改; 仅 normal 模式下部分控件禁用
        modeBtns.forEach(function (b) { b.disabled = false; });
        el.mediaDir.disabled = false;
        el.browseBtn.disabled = false;
        el.sortType.disabled = false;
        el.sortOrder.disabled = false;
        el.randomMode.disabled = isOff;
        el.douyinRandom.disabled = isOff;
        el.categoryBrowse.disabled = isOff;

        // QR / URL visible when server is running (both SERVER_ON and SERVICE_ACTIVE)
        el.qrBox.style.display = isRunning ? '' : 'none';
        el.urlGroup.style.display = isRunning ? 'flex' : 'none';
        el.openBrowserBtn.disabled = !isActive;

        // Show URL/QR from pending values in SERVER_ON state
        if (isServerOn) {
            el.urlDisplay.value = _pendingLanUrl || '—';
            if (_pendingQrBase64) {
                el.qrPlaceholder.style.display = 'none';
                el.qrImage.src = 'data:image/png;base64,' + _pendingQrBase64;
                el.qrImage.style.display = 'block';
            }
        }

        // Re-enable buttons appropriately
        el.startServerBtn.disabled = !isOff;
        el.activateServiceBtn.disabled = !isServerOn;
        el.stopServerBtn.disabled = !isServerOn;
        el.deactivateServiceBtn.disabled = !isActive;
        el.stopServiceBtn.disabled = !isActive;

        // Reset on stop
        if (isOff) {
            el.urlDisplay.value = '—';
            _pendingLanUrl = '';
            _pendingQrBase64 = '';
            sessionStart = null;
            el.footerRuntime.textContent = '';
            el.qrPlaceholder.style.display = '';
            el.qrImage.style.display = 'none';
            el.qrImage.src = '';
            onModeChange();
            el.footerStatus.textContent = '就绪';
            el.footerStatus.style.color = '';
        }
    }

    // ── 运行时长 ──
    setInterval(function () {
        if (sessionStart && serverState !== 'off') {
            var sec = Math.floor((Date.now() - sessionStart) / 1000);
            var h = String(Math.floor(sec / 3600)).padStart(2, '0');
            var m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
            var s = String(sec % 60).padStart(2, '0');
            el.footerRuntime.textContent = '已运行 ' + h + ':' + m + ':' + s;
        }
    }, 500);

    // ── Flask 子进程日志轮询 + 崩溃检测 ──
    setInterval(function () {
        if (serverState === 'off') return;
        if (!window.pywebview || !window.pywebview.api) return;
        window.pywebview.api.get_flask_logs().then(function (result) {
            (result.logs || []).forEach(function (line) { log(line); });
        }).catch(function () {});
    }, 1000);

    setInterval(function () {
        if (serverState === 'off') return;
        if (!window.pywebview || !window.pywebview.api) return;
        window.pywebview.api.get_service_status().then(function (status) {
            if (!status.running) {
                log('服务进程已意外退出', 'error');
                _pendingLanUrl = '';
                updateServerState('off');
            }
        }).catch(function () {});
    }, 3000);

    // ── Toast ──
    function showToast(msg) {
        var toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = msg;
        document.body.appendChild(toast);
        requestAnimationFrame(function () { toast.classList.add('show'); });
        setTimeout(function () {
            toast.classList.remove('show');
            setTimeout(function () { document.body.removeChild(toast); }, 300);
        }, 2000);
    }

    // ── 密码弹窗 ──
    var ALLOWED_CHARS = /^[a-zA-Z0-9@._\-!#$%&*+]+$/;

    function _showPasswordModal() {
        el.passwordModal.style.display = 'flex';
        el.newPassword.value = '';
        el.confirmPassword.value = '';
        el.pwdCharError.style.display = 'none';
        el.confirmError.style.display = 'none';
        el.modalError.style.display = 'none';
        el.newPassword.classList.remove('field-error');
        el.confirmPassword.classList.remove('field-error');
        el.newPassword.focus();
    }

    function _hidePasswordModal() {
        el.passwordModal.style.display = 'none';
    }

    el.changePasswordBtn.addEventListener('click', function () {
        _showPasswordModal();
    });

    el.cancelPasswordBtn.addEventListener('click', function () {
        _hidePasswordModal();
    });

    // ESC 关闭弹窗
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && el.passwordModal.style.display === 'flex') {
            _hidePasswordModal();
        }
    });

    el.passwordForm.addEventListener('submit', function (e) {
        e.preventDefault();

        var pwd = el.newPassword.value;
        var confirmPwd = el.confirmPassword.value;
        var valid = true;

        // 隐藏之前的错误
        el.pwdCharError.style.display = 'none';
        el.confirmError.style.display = 'none';
        el.modalError.style.display = 'none';
        el.newPassword.classList.remove('field-error');
        el.confirmPassword.classList.remove('field-error');

        if (!ALLOWED_CHARS.test(pwd)) {
            el.newPassword.classList.add('field-error');
            el.pwdCharError.style.display = 'block';
            valid = false;
        }

        if (pwd.length < 4) {
            el.newPassword.classList.add('field-error');
            el.modalError.textContent = '密码至少需要4个字符';
            el.modalError.style.display = 'block';
            valid = false;
        }

        if (pwd !== confirmPwd) {
            el.confirmPassword.classList.add('field-error');
            el.confirmError.style.display = 'block';
            valid = false;
        }

        if (!valid) return;

        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.set_password(pwd).then(function (result) {
                if (result.code === 0) {
                    log('密码已更新', 'ok');
                    _hidePasswordModal();
                    showToast('密码修改成功');
                } else {
                    el.modalError.textContent = result.msg || '设置失败';
                    el.modalError.style.display = 'block';
                }
            }).catch(function (e) {
                el.modalError.textContent = '操作失败: ' + e.message;
                el.modalError.style.display = 'block';
            });
        }
    });

    // 实时清除错误状态
    el.newPassword.addEventListener('input', function () {
        this.classList.remove('field-error');
        el.pwdCharError.style.display = 'none';
        el.modalError.style.display = 'none';
    });
    el.confirmPassword.addEventListener('input', function () {
        this.classList.remove('field-error');
        el.confirmError.style.display = 'none';
    });

    // ── 初始化 ──
    onModeChange();
    refreshQidStatus();
    log('就绪', 'dim');
})();
