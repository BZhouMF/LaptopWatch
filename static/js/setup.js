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
        actionBtn: document.getElementById('actionBtn'),
        urlDisplay: document.getElementById('urlDisplay'),
        openBrowserBtn: document.getElementById('openBrowserBtn'),
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

    var running = false;
    var sessionStart = null;
    var currentMode = 'normal';
    var footerTimer = null;  // 错误高亮恢复定时器

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

        var baseState = isAnyMedia;
        setDisabled(el.mediaDir, !baseState);
        setDisabled(el.browseBtn, !baseState);

        var sortState = isAnyMedia && !sortIrrelevant;
        setDisabled(el.sortType, !sortState);
        setDisabled(el.sortOrder, !sortState);
        setDisabled(el.randomMode, !sortState);

        setDisabled(el.douyinRandom, !isDouyin);
        setDisabled(el.categoryBrowse, !isMedia);

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
        updateRunningState(false);
    }

    function handleStop() {
        log('[STOP] 服务已彻底停止');
        updateRunningState(false);
    }

    // ── 启动/停止（单按钮切换）──
    el.actionBtn.addEventListener('click', function () {
        if (running) {
            // 停止
            el.actionBtn.disabled = true;
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.stop_service().then(function () {
                    handleStop();
                }).catch(function () {});
                return;
            }
            fetch('/api/stop_service', { method: 'POST' }).finally(function () {
                handleStop();
            });
            return;
        }

        // 启动
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

        el.actionBtn.disabled = true;

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
    function updateRunningState(on) {
        running = on;
        el.statusDot.classList.toggle('on', on);
        el.statusText.textContent = on ? '运行中（' + currentMode + '模式）' : '未运行';
        el.actionBtn.disabled = false;
        el.actionBtn.innerHTML = on
            ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg><span>停止服务</span>'
            : '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>启动服务</span>';
        el.actionBtn.className = on ? 'btn btn-stop btn-lg' : 'btn btn-start btn-lg';
        el.openBrowserBtn.disabled = !on;

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
