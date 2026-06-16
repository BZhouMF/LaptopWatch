(function() {
    // ==================== 元素引用 ====================
    const container = document.getElementById('container');
    const videoA = document.getElementById('videoA');
    const videoB = document.getElementById('videoB');
    const loading = document.getElementById('loading');
    const endEl = document.getElementById('end');
    const errorEl = document.getElementById('error');
    const infoName = document.getElementById('infoName');
    const fileName = document.getElementById('fileName');
    const hint = document.getElementById('hint');
    const speedIndicator = document.getElementById('speedIndicator');
    const seekIndicator = document.getElementById('seekIndicator');
    const seekTime = document.getElementById('seekTime');
    const brightnessOverlay = document.getElementById('brightnessOverlay');
    const volIndicator = document.getElementById('volIndicator');
    const volFill = document.getElementById('volFill');
    const volPct = document.getElementById('volPct');
    const brightIndicator = document.getElementById('brightIndicator');
    const brightFill = document.getElementById('brightFill');
    const brightPct = document.getElementById('brightPct');
    const controls = document.getElementById('controls');
    const btnPlay = document.getElementById('btnPlay');
    const btnPlaySvg = document.getElementById('btnPlaySvg');
    const btnSettings = document.getElementById('btnSettings');
    const settingsMenu = document.getElementById('settingsMenu');
    const btnFullscreen = document.getElementById('btnFullscreen');
    const btnFullscreenSvg = document.getElementById('btnFullscreenSvg');
    const btnSkipBack = document.getElementById('btnSkipBack');
    const btnSkipFwd = document.getElementById('btnSkipFwd');
    const progressWrap = document.getElementById('progressWrap');
    const progressFill = document.getElementById('progressFill');
    const progressThumb = document.getElementById('progressThumb');
    const timeDisplay = document.getElementById('timeDisplay');
    const topBar = document.getElementById('topBar');
    const navBtns = document.getElementById('navBtns');
    const btnPrev = document.getElementById('btnPrev');
    const btnNext = document.getElementById('btnNext');
    const btnBack = document.getElementById('btnBack');
    const playerImage = document.getElementById('playerImage');
    const videoWrap = document.getElementById('videoWrap');

    // ==================== 图标 ====================
    const PLAY_ICON = '<path d="M8 5v14l11-7z"/>';
    const PAUSE_ICON = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
    const FULLSCREEN_ENTER_ICON = '<path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>';
    const FULLSCREEN_EXIT_ICON = '<path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>';
    const MUTE_ON_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="#fff"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>';
    const MUTE_OFF_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="#fff"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>';

    // ==================== 模式 ====================
    const mode = (window.DOUYIN_CONFIG && window.DOUYIN_CONFIG.mode) || 'douyin';
    const isGrid = mode === 'grid';
    const AUTO_PLAY = !isGrid && window.DOUYIN_CONFIG.autoPlay;
    const IS_MUTED = window.DOUYIN_CONFIG.muted;

    // ==================== 状态 ====================
    let playHistory = [];
    let historyIndex = -1;
    let isLoading = false;
    let isEnded = false;
    let isTransitioning = false;
    let preloadedIndex = -1;
    let isPreloading = false;
    let currentVideo = null;
    let controlsTimer = null;
    let controlsVisible = true;
    let globalMuted = IS_MUTED;
    let activeVideo = videoA;
    let inactiveVideo = videoB;
    let animatingSlide = false;
    let orientationLocked = false;
    let isDragging = false;
    let clickTimer = null;
    let safetyTimer = null;
    let transitionTimer = null;
    let selectedSpeed = 1;
    let adjustType = null;
    let touchStartY = 0, touchStartX = 0, touchMoved = false, touchOnControls = false;
    let isSeeking = false, seekStartTime = 0;
    const SWIPE_THRESHOLD = 60, SEEK_PX_PER_SEC = 5, ADJUST_SENSITIVITY = 400;
    let longPressTimer = null;

    // 网格模式状态
    let gridCurrentPath = null;
    let gridIsVideo = null;

    activeVideo.muted = globalMuted;
    inactiveVideo.muted = globalMuted;

    function swapVideoRefs() {
        var tmp = activeVideo;
        activeVideo = inactiveVideo;
        inactiveVideo = tmp;
    }

    // ==================== 核心 UI ====================
    function formatTime(seconds) {
        if (isNaN(seconds) || !isFinite(seconds)) return '0:00';
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    function updateProgress() {
        if (!activeVideo.duration) return;
        const pct = (activeVideo.currentTime / activeVideo.duration) * 100;
        progressFill.style.width = pct + '%';
        progressThumb.style.left = pct + '%';
        timeDisplay.textContent = formatTime(activeVideo.currentTime) + ' / ' + formatTime(activeVideo.duration);
    }

    function updatePlayBtn() {
        btnPlaySvg.innerHTML = activeVideo.paused ? PLAY_ICON : PAUSE_ICON;
    }

    function togglePlay() {
        if (activeVideo.paused) {
            activeVideo.play().catch(function(){});
        } else {
            activeVideo.pause();
        }
        updatePlayBtn();
    }

    function showControls() {
        controls.classList.remove('hidden');
        if (topBar) topBar.classList.remove('hidden');
        if (btnSkipBack) btnSkipBack.classList.add('show');
        if (btnSkipFwd) btnSkipFwd.classList.add('show');
        if (navBtns) navBtns.classList.add('show');
        controlsVisible = true;
        resetControlsTimer();
    }

    function hideControls() {
        controls.classList.add('hidden');
        if (topBar) topBar.classList.add('hidden');
        if (btnSkipBack) btnSkipBack.classList.remove('show');
        if (btnSkipFwd) btnSkipFwd.classList.remove('show');
        if (navBtns) navBtns.classList.remove('show');
        controlsVisible = false;
    }

    function resetControlsTimer() {
        if (controlsTimer) clearTimeout(controlsTimer);
        controlsTimer = setTimeout(hideControls, 7000);
    }

    function toggleFullscreen() {
        // 退出全屏
        var fsEl = document.fullscreenElement || document.webkitFullscreenElement;
        if (fsEl) {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            }
            return;
        }

        // 进入全屏：优先 video 元素（移动端兼容性最好）
        var el = activeVideo;
        if (el.webkitEnterFullscreen) {
            // iOS Safari < 12：只支持 video 原生全屏
            el.webkitEnterFullscreen();
            updateFullscreenBtn();
            return;
        }
        if (el.webkitSetPresentationMode) {
            // iOS Safari 12+ iPad：支持 presentation mode
            el.webkitSetPresentationMode('fullscreen');
            updateFullscreenBtn();
            return;
        }

        var promise = null;
        if (el.requestFullscreen) {
            promise = el.requestFullscreen();
        } else if (el.webkitRequestFullscreen) {
            promise = el.webkitRequestFullscreen();
        } else if (container.requestFullscreen) {
            // 最后兜底：容器全屏（某些旧 Android 设备）
            promise = container.requestFullscreen();
        }

        if (promise) {
            promise.then(function() {
                autoLockOrientation();
                // 移动端全屏后强制 video 重绘，修复黑屏
                el.style.opacity = '0.99';
                requestAnimationFrame(function() {
                    el.style.opacity = '';
                });
            }).catch(function() {
                // video 全屏失败，尝试容器全屏
                if (el !== container && container.requestFullscreen) {
                    container.requestFullscreen().catch(function(){});
                }
            });
        }
    }

    function updateFullscreenBtn() {
        var isFS = document.fullscreenElement || document.webkitFullscreenElement;
        btnFullscreenSvg.innerHTML = isFS ? FULLSCREEN_EXIT_ICON : FULLSCREEN_ENTER_ICON;
    }

    // iOS 专用全屏事件
    if (activeVideo) {
        activeVideo.addEventListener('webkitbeginfullscreen', function() {
            updateFullscreenBtn();
            autoLockOrientation();
        });
        activeVideo.addEventListener('webkitendfullscreen', function() {
            updateFullscreenBtn();
            unlockOrientation();
        });
    }

    function autoLockOrientation() {
        if (!screen.orientation || !screen.orientation.lock) return;
        var vw = activeVideo.videoWidth || 0;
        var vh = activeVideo.videoHeight || 0;
        var target = (vw > vh) ? 'landscape-primary' : 'portrait-primary';
        screen.orientation.lock(target).then(function() {
            orientationLocked = true;
        }).catch(function(){});
    }

    function unlockOrientation() {
        if (screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock();
        }
        orientationLocked = false;
    }

    function skipTime(delta) {
        if (!activeVideo.duration) return;
        activeVideo.currentTime = Math.max(0, Math.min(activeVideo.currentTime + delta, activeVideo.duration));
        updateProgress();
    }

    // ==================== 加载/错误 UI ====================
    function showLoading() {
        isLoading = true;
        loading.classList.add('active');
        if (endEl) endEl.classList.remove('active');
        errorEl.classList.remove('active');
    }

    function hideLoading() {
        isLoading = false;
        loading.classList.remove('active');
    }

    function showEnd() {
        isEnded = true;
        if (endEl) endEl.classList.add('active');
    }

    function hideEnd() {
        isEnded = false;
        if (endEl) endEl.classList.remove('active');
    }

    function showError(msg) {
        errorEl.textContent = msg;
        errorEl.classList.add('active');
        setTimeout(function() { errorEl.classList.remove('active'); }, 3000);
    }

    // ==================== 设置菜单 ====================
    const SPEED_OPTIONS = [2, 1.75, 1.5, 1.25, 1, 0.75];

    function buildSettingsMenu() {
        settingsMenu.innerHTML = '';

        var muteBtn = document.createElement('button');
        muteBtn.className = 'settings-btn mute-btn';
        muteBtn.innerHTML = '<span class="mute-icon">' + MUTE_ON_SVG + '</span>';
        muteBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleMute();
            updateSettingsMenu();
            hideSettingsMenu();
            resetControlsTimer();
        });
        settingsMenu.appendChild(muteBtn);

        var speedBtn = document.createElement('button');
        speedBtn.className = 'settings-btn speed-toggle-btn';
        speedBtn.id = 'speedToggleBtn';
        speedBtn.textContent = '1.00x';
        speedBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleSpeedOptions();
            resetControlsTimer();
        });
        settingsMenu.appendChild(speedBtn);

        var speedOptions = document.createElement('div');
        speedOptions.className = 'speed-options';
        speedOptions.id = 'speedOptions';
        SPEED_OPTIONS.forEach(function(speed) {
            var opt = document.createElement('div');
            opt.className = 'speed-opt';
            opt.textContent = speed.toFixed(2) + 'x';
            opt.addEventListener('click', function(e) {
                e.stopPropagation();
                setSpeed(speed);
                hideSpeedOptions();
                hideSettingsMenu();
                resetControlsTimer();
            });
            speedOptions.appendChild(opt);
        });
        settingsMenu.appendChild(speedOptions);

        updateSettingsMenu();
        updateSpeedUI();
    }

    function updateSettingsMenu() {
        var muteIcon = settingsMenu.querySelector('.mute-icon');
        if (muteIcon) {
            muteIcon.innerHTML = activeVideo.muted ? MUTE_OFF_SVG : MUTE_ON_SVG;
        }
    }

    function setSpeed(speed) {
        selectedSpeed = speed;
        activeVideo.playbackRate = speed;
        updateSpeedUI();
    }

    function updateSpeedUI() {
        var speedBtn = document.getElementById('speedToggleBtn');
        if (speedBtn) {
            speedBtn.textContent = selectedSpeed.toFixed(2) + 'x';
        }
        var opts = document.querySelectorAll('#speedOptions .speed-opt');
        opts.forEach(function(opt) {
            opt.classList.toggle('active', parseFloat(opt.textContent) === selectedSpeed);
        });
    }

    function toggleSpeedOptions() {
        var opts = document.getElementById('speedOptions');
        if (opts) opts.classList.toggle('show');
    }

    function hideSpeedOptions() {
        var opts = document.getElementById('speedOptions');
        if (opts) opts.classList.remove('show');
    }

    function showSettingsMenu() {
        settingsMenu.classList.add('show');
        updateSettingsMenu();
        updateSpeedUI();
        hideSpeedOptions();
    }

    function hideSettingsMenu() {
        settingsMenu.classList.remove('show');
        hideSpeedOptions();
    }

    function toggleMute() {
        activeVideo.muted = !activeVideo.muted;
        globalMuted = activeVideo.muted;
        updateSettingsMenu();
    }

    btnSettings.addEventListener('click', function(e) {
        e.stopPropagation();
        resetControlsTimer();
        if (settingsMenu.classList.contains('show')) {
            hideSettingsMenu();
        } else {
            showSettingsMenu();
        }
    });

    document.addEventListener('click', function(e) {
        if (!e.target.closest('#settingsWrap')) {
            hideSettingsMenu();
        }
    });

    buildSettingsMenu();
    setSpeed(1);

    // ==================== 进度条拖动 ====================
    progressWrap.addEventListener('pointerdown', function(e) {
        isDragging = true;
        seekTo(e);
        resetControlsTimer();
        e.preventDefault();
    });
    document.addEventListener('pointermove', function(e) {
        if (!isDragging) return;
        seekTo(e);
    });
    document.addEventListener('pointerup', function() {
        isDragging = false;
    });

    function seekTo(e) {
        const rect = progressWrap.getBoundingClientRect();
        const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        const pct = x / rect.width;
        if (activeVideo.duration) {
            activeVideo.currentTime = pct * activeVideo.duration;
        }
        updateProgress();
    }

    // ==================== 视频切换 ====================
    function playVideo(videoData, direction) {
        if (!videoData || isTransitioning) return;
        currentVideo = videoData;
        isTransitioning = true;

        var url = window.ROUTES.mediaServe + encodeURIComponent(videoData.relative_path);
        var name = videoData.name || decodeURIComponent(videoData.relative_path.split('/').pop());
        if (infoName) infoName.textContent = name;
        if (fileName) fileName.textContent = name;
        if (hint) hint.style.opacity = '0';
        if (endEl) endEl.classList.remove('active');

        if (!direction) {
            activeVideo.src = url;
            activeVideo.muted = globalMuted;
            activeVideo.playbackRate = selectedSpeed;
            updatePlayBtn();
            updateSettingsMenu();
            activeVideo.play().catch(function(){});
            isTransitioning = false;
            activeVideo.style.zIndex = '2';
            inactiveVideo.style.zIndex = '1';
            // loading remains visible, hidden by canplay event callback
        } else {
            var canplayFired = false;
            inactiveVideo.addEventListener('canplay', function onCanplay() {
                canplayFired = true;
                inactiveVideo.removeEventListener('canplay', onCanplay);
                if (transitionTimer) {
                    clearTimeout(transitionTimer);
                    transitionTimer = null;
                }
                animateSlideIn(direction);
            }, { once: false });

            inactiveVideo.muted = globalMuted;
            inactiveVideo.playbackRate = selectedSpeed;
            inactiveVideo.src = url;
            hideLoading();

            transitionTimer = setTimeout(function() {
                transitionTimer = null;
                if (isTransitioning && !canplayFired) animateSlideIn(direction);
            }, 500);
        }
    }

    function animateSlideIn(direction) {
        if (animatingSlide || !isTransitioning) return;
        animatingSlide = true;
        var fromY = direction === 'next' ? 'translateY(100%)' : 'translateY(-100%)';
        var outY = direction === 'next' ? 'translateY(-100%)' : 'translateY(100%)';

        activeVideo.muted = true;

        inactiveVideo.style.zIndex = '2';
        activeVideo.style.zIndex = '1';

        inactiveVideo.style.transition = 'none';
        activeVideo.style.transition = 'none';
        inactiveVideo.style.transform = fromY;
        activeVideo.style.transform = 'translateY(0)';

        inactiveVideo.offsetHeight;

        inactiveVideo.style.transition = 'transform 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
        activeVideo.style.transition = 'transform 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
        inactiveVideo.style.transform = 'translateY(0)';
        activeVideo.style.transform = outY;

        setTimeout(function() {
            finishVideoSwitch();
        }, 360);

        if (safetyTimer) clearTimeout(safetyTimer);
        safetyTimer = setTimeout(function() {
            safetyTimer = null;
            if (isTransitioning || animatingSlide) {
                inactiveVideo.style.transition = '';
                inactiveVideo.style.transform = '';
                activeVideo.style.transition = '';
                activeVideo.style.transform = '';
                swapVideoRefs();
                inactiveVideo.src = '';
                activeVideo.classList.remove('slide-in-from-bottom', 'slide-in-from-top', 'slide-out-up', 'slide-out-down');
                inactiveVideo.classList.remove('slide-in-from-bottom', 'slide-in-from-top', 'slide-out-up', 'slide-out-down');
                activeVideo.muted = globalMuted;
                activeVideo.style.zIndex = '2';
                inactiveVideo.style.zIndex = '1';
                updatePlayBtn();
                updateSettingsMenu();
                isTransitioning = false;
                animatingSlide = false;
            }
        }, 1500);
    }

    function finishVideoSwitch() {
        if (safetyTimer) {
            clearTimeout(safetyTimer);
            safetyTimer = null;
        }
        if (inactiveVideo._slideTimeout) {
            clearTimeout(inactiveVideo._slideTimeout);
        }
        inactiveVideo.style.transition = '';
        inactiveVideo.style.transform = '';
        activeVideo.style.transition = '';
        activeVideo.style.transform = '';

        activeVideo.pause();
        swapVideoRefs();
        inactiveVideo.src = '';
        activeVideo.classList.remove('slide-in-from-bottom', 'slide-in-from-top', 'slide-out-up', 'slide-out-down');
        inactiveVideo.classList.remove('slide-in-from-bottom', 'slide-in-from-top', 'slide-out-up', 'slide-out-down');
        activeVideo.muted = globalMuted;
        activeVideo.style.zIndex = '2';
        inactiveVideo.style.zIndex = '1';
        updatePlayBtn();
        updateSettingsMenu();
        updateSpeedUI();
        activeVideo.play().catch(function(){});
        isTransitioning = false;
        animatingSlide = false;

        if (!isGrid) preloadNextVideo();
    }

    // ==================== 网格模式导航 ====================
    if (isGrid) {
        function initGrid() {
            gridCurrentPath = window.DOUYIN_CONFIG.mediaPath;
            gridIsVideo = window.DOUYIN_CONFIG.isVideo;
            if (fileName) {
                fileName.textContent = decodeURIComponent(gridCurrentPath.split('/').pop());
            }

            if (gridIsVideo) {
                if (videoWrap) videoWrap.style.display = 'block';
                if (playerImage) playerImage.style.display = 'none';
                controls.style.display = '';
                showLoading();
                playVideo({ relative_path: gridCurrentPath }, null);
            } else {
                if (videoWrap) videoWrap.style.display = 'none';
                controls.style.display = 'none';
                var url = window.ROUTES.mediaServe + encodeURIComponent(gridCurrentPath);
                playerImage.onload = function() { hideLoading(); };
                playerImage.onerror = function() { hideLoading(); showError('图片加载失败'); };
                playerImage.src = url;
                playerImage.style.display = 'block';
            }
            updateGridNavButtons();
        }

        function loadGridImage(path) {
            if (activeVideo) {
                activeVideo.pause();
                inactiveVideo.src = '';
                activeVideo.src = '';
            }
            if (videoWrap) videoWrap.style.display = 'none';
            controls.style.display = 'none';
            var url = window.ROUTES.mediaServe + encodeURIComponent(path);
            playerImage.onload = function() { hideLoading(); };
            playerImage.onerror = function() { hideLoading(); showError('图片加载失败'); };
            playerImage.src = url;
            playerImage.style.display = 'block';
        }

        function navigateGrid(direction) {
            if (isLoading || isTransitioning) return;
            isLoading = true;
            showLoading();

            fetch(window.ROUTES.mediaNavigate + '?current_path=' + encodeURIComponent(gridCurrentPath) + '&direction=' + direction)
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    isLoading = false;
                    if (data.code === 0 && data.data) {
                        var newPath = data.data.relative_path;
                        var isVid = data.data.is_video;
                        var name = data.data.name || decodeURIComponent(newPath.split('/').pop());

                        if (fileName) fileName.textContent = name;

                        // 切换媒体类型
                        if (gridIsVideo !== isVid) {
                            gridIsVideo = isVid;
                            if (isVid) {
                                if (playerImage) playerImage.style.display = 'none';
                                if (videoWrap) videoWrap.style.display = 'block';
                                controls.style.display = '';
                            } else {
                                if (videoWrap) videoWrap.style.display = 'none';
                                controls.style.display = 'none';
                            }
                        }

                        if (isVid) {
                            playVideo({ relative_path: newPath, name: name }, direction);
                        } else {
                            loadGridImage(newPath);
                        }

                        gridCurrentPath = newPath;
                        updateGridNavButtons();
                    } else if (data.code === 2) {
                        hideLoading();
                        showError(direction === 'next' ? '没有更多了' : '已经是第一个了');
                    }
                })
                .catch(function(err) {
                    isLoading = false;
                    hideLoading();
                    showError('导航失败');
                });
        }

        function updateGridNavButtons() {
            if (!btnPrev || !btnNext) return;
            fetch(window.ROUTES.mediaNavigate + '?current_path=' + encodeURIComponent(gridCurrentPath) + '&direction=prev')
                .then(function(r) { return r.json(); })
                .then(function(d) { btnPrev.disabled = d.code !== 0; });
            fetch(window.ROUTES.mediaNavigate + '?current_path=' + encodeURIComponent(gridCurrentPath) + '&direction=next')
                .then(function(r) { return r.json(); })
                .then(function(d) { btnNext.disabled = d.code !== 0; });
        }
    }

    // 全局错误捕获（调试抖音模式问题用）
    window.onerror = function(msg, source, lineno, colno, error) {
        console.error('[LW_DEBUG] GLOBAL_ERROR:', msg, source, lineno, colno, error);
    };

    // 抖音模式异步函数（声明为 var 确保提升到 IIFE 作用域，async function 在 if 块内不会被提升）
    var fetchInitAsync, fetchNextAsync;

    // ==================== 抖音模式导航 ====================
    if (!isGrid) {
        function preloadNextVideo() {
            if (isEnded || isTransitioning || isPreloading) return;
            var nextIndex = historyIndex + 1;

            if (nextIndex < playHistory.length) {
                var data = playHistory[nextIndex];
                var url = window.ROUTES.mediaServe + encodeURIComponent(data.relative_path);
                inactiveVideo.src = url;
                inactiveVideo.muted = globalMuted;
                inactiveVideo.playbackRate = selectedSpeed;
                preloadedIndex = nextIndex;
                return;
            }

            isPreloading = true;
            fetch(window.ROUTES.douyinNext).then(function(resp) {
                return resp.json();
            }).then(function(result) {
                if (result.code === 0 && result.data) {
                    if (historyIndex < playHistory.length - 1) {
                        playHistory = playHistory.slice(0, historyIndex + 1);
                    }
                    playHistory.push(result.data);
                    if (playHistory.length > 100) playHistory.shift();
                    preloadedIndex = playHistory.length - 1;
                    var url = window.ROUTES.mediaServe + encodeURIComponent(result.data.relative_path);
                    inactiveVideo.src = url;
                    inactiveVideo.muted = globalMuted;
                    inactiveVideo.playbackRate = selectedSpeed;
                } else if (result.code === 2) {
                    isEnded = true;
                } else if (result.code !== 0) {
                    showError(result.msg || '预加载失败，请刷新页面');
                }
            }).catch(function(err){}).finally(function() {
                isPreloading = false;
            });
        }

        function fetchWithTimeout(url, timeoutMs) {
            var controller = new AbortController();
            var timer = setTimeout(function() { controller.abort(); }, timeoutMs);
            return fetch(url, { signal: controller.signal }).finally(function() {
                clearTimeout(timer);
            });
        }

        fetchInitAsync = async function() {
            console.log('[LW_DEBUG] fetchInit() STARTED');
            showLoading();
            try {
                var url = window.ROUTES.douyinInit;
                console.log('[LW_DEBUG] fetchInit fetching:', url);
                var resp = await fetchWithTimeout(url, 8000);
                console.log('[LW_DEBUG] fetchInit response status:', resp.status);
                var data = await resp.json();
                console.log('[LW_DEBUG] fetchInit data:', JSON.stringify(data));
                if (data.code === 0 && data.data) {
                    playHistory = [data.data];
                    historyIndex = 0;
                    playVideo(data.data, null);
                    preloadNextVideo();
                    return;
                }
            } catch (e) {
                console.error('[LW_DEBUG] fetchInit CAUGHT:', e.name, e.message, e);
            }
            // 降级: init 失败则用 next 代替（服务端已支持 auto-init）
            hideLoading();
            console.log('[LW_DEBUG] fetchInit fallback to fetchNext');
            fetchNextAsync();
        };

        fetchNextAsync = async function() {
            if (isLoading || isEnded || isTransitioning) return;
            showLoading();
            try {
                var resp = await fetchWithTimeout(window.ROUTES.douyinNext, 8000);
                var data = await resp.json();
                if (data.code === 0 && data.data) {
                    if (historyIndex < playHistory.length - 1) {
                        playHistory = playHistory.slice(0, historyIndex + 1);
                    }
                    playHistory.push(data.data);
                    if (playHistory.length > 100) playHistory.shift();
                    historyIndex = playHistory.length - 1;
                    playVideo(data.data, 'next');
                } else if (data.code === 2) {
                    hideLoading();
                    showEnd();
                } else {
                    hideLoading();
                    showError(data.msg || '获取失败');
                }
            } catch (e) {
                hideLoading();
                if (e.name === 'AbortError') {
                    showError('请求超时，请检查网络后刷新页面');
                } else {
                    showError('网络错误');
                }
            }
        };

        function goNext() {
            if (isLoading || isTransitioning) return;
            if (historyIndex < playHistory.length - 1) {
                historyIndex++;
                hideEnd();
                if (preloadedIndex === historyIndex) {
                    currentVideo = playHistory[historyIndex];
                    isTransitioning = true;
                    if (infoName) infoName.textContent = currentVideo.name || '';
                    if (hint) hint.style.opacity = '0';
                    animateSlideIn('next');
                } else {
                    playVideo(playHistory[historyIndex], 'next');
                }
            } else if (!isEnded) {
                fetchNextAsync();
            }
        }

        function playPrev() {
            if (isLoading || isTransitioning) return;
            if (historyIndex > 0) {
                historyIndex--;
                hideEnd();
                playVideo(playHistory[historyIndex], 'prev');
            }
        }
    }

    // ==================== 导航别名 ====================
    function navNext() {
        if (isGrid) {
            navigateGrid('next');
        } else {
            goNext();
        }
    }

    function navPrev() {
        if (isGrid) {
            navigateGrid('prev');
        } else {
            playPrev();
        }
    }

    // ==================== 视频事件 ====================
    [videoA, videoB].forEach(function(v) {
        v.addEventListener('loadedmetadata', updateProgress);
        v.addEventListener('timeupdate', function() {
            if (!isDragging && v === activeVideo) updateProgress();
        });
        v.addEventListener('play', function() {
            if (v === activeVideo) {
                updatePlayBtn();
                resetControlsTimer();
            }
        });
        v.addEventListener('pause', function() {
            if (v === activeVideo) {
                updatePlayBtn();
                showControls();
            }
        });
        v.addEventListener('ended', function() {
            if (v !== activeVideo) return;
            updatePlayBtn();
            showControls();
            if (AUTO_PLAY) {
                navNext();
            } else {
                activeVideo.currentTime = 0;
                activeVideo.play().catch(function(){});
            }
        });
        v.addEventListener('waiting', function() {
            if (v === activeVideo && !activeVideo.paused) showLoading();
        });
        v.addEventListener('canplay', function() {
            if (v === activeVideo) hideLoading();
        });
        v.addEventListener('error', function() {
            if (isGrid && !gridIsVideo) return; // 图片模式下忽略 video 元素的 error 事件
            if (v === activeVideo) {
                hideLoading();
                showError('视频加载失败');
            }
            if (v === inactiveVideo && isTransitioning) {
                hideLoading();
                showError('下一个视频加载失败');
                inactiveVideo.src = '';
                isTransitioning = false;
                animatingSlide = false;
            }
        });
    });

    // ==================== 按钮事件 ====================
    btnPlay.addEventListener('click', function(e) {
        e.stopPropagation();
        togglePlay();
        resetControlsTimer();
    });

    btnFullscreen.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleFullscreen();
        resetControlsTimer();
    });

    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('webkitfullscreenchange', onFullscreenChange);
    function onFullscreenChange() {
        updateFullscreenBtn();
        hideVolIndicator();
        hideBrightIndicator();
        adjustType = null;
        var fsEl = document.fullscreenElement || document.webkitFullscreenElement;
        if (!fsEl && orientationLocked) {
            unlockOrientation();
        }
    }

    if (btnSkipBack) {
        btnSkipBack.addEventListener('click', function(e) {
            e.stopPropagation();
            skipTime(-15);
            resetControlsTimer();
        });
    }

    if (btnSkipFwd) {
        btnSkipFwd.addEventListener('click', function(e) {
            e.stopPropagation();
            skipTime(15);
            resetControlsTimer();
        });
    }

    if (btnPrev) {
        btnPrev.addEventListener('click', function(e) {
            e.stopPropagation();
            navPrev();
        });
    }

    if (btnNext) {
        btnNext.addEventListener('click', function(e) {
            e.stopPropagation();
            navNext();
        });
    }

    if (btnBack) {
        btnBack.addEventListener('click', function() {
            history.back();
        });
    }

    // ==================== 双击控制切换 ====================
    [videoA, videoB].forEach(function(v) {
        v.addEventListener('click', function(e) {
            e.stopPropagation();
            hideSettingsMenu();
            if (clickTimer) {
                clearTimeout(clickTimer);
                clickTimer = null;
                togglePlay();
            } else {
                clickTimer = setTimeout(function() {
                    clickTimer = null;
                    if (controlsVisible) {
                        hideControls();
                    } else {
                        showControls();
                    }
                }, 300);
            }
        });
    });

    container.addEventListener('click', function(e) {
        if (e.target !== container) return;
        hideSettingsMenu();
        if (clickTimer) {
            clearTimeout(clickTimer);
            clickTimer = null;
            togglePlay();
        } else {
            clickTimer = setTimeout(function() {
                clickTimer = null;
                if (controlsVisible) {
                    hideControls();
                } else {
                    showControls();
                }
            }, 300);
        }
    });

    // ==================== 长按 3 倍速 ====================
    function startLongPress() {
        longPressTimer = setTimeout(function() {
            activeVideo.playbackRate = 3;
            speedIndicator.classList.add('active');
        }, 500);
    }

    function cancelLongPress() {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
        activeVideo.playbackRate = selectedSpeed;
        speedIndicator.classList.remove('active');
    }

    // ==================== 手势处理 ====================
    container.addEventListener('touchstart', function(e) {
        if (isGrid && !gridIsVideo) return;
        touchOnControls = !!e.target.closest('#controls');
        touchStartY = e.touches[0].clientY;
        touchStartX = e.touches[0].clientX;
        touchMoved = false;
        isSeeking = false;
        adjustType = null;
        seekStartTime = activeVideo.currentTime;
        if (!touchOnControls) startLongPress();
    }, { passive: true });

    container.addEventListener('touchmove', function(e) {
        if (isGrid && !gridIsVideo) return;
        touchMoved = true;
        cancelLongPress();
        if (touchOnControls) return;

        var currentX = e.touches[0].clientX;
        var currentY = e.touches[0].clientY;
        var dx = currentX - touchStartX;
        var dy = currentY - touchStartY;
        var absDx = Math.abs(dx);
        var absDy = Math.abs(dy);

        if (document.fullscreenElement) {
            if (!isSeeking && !adjustType && absDx > 15 && absDx > absDy) {
                isSeeking = true;
                seekIndicator.classList.add('active');
            }
            if (!isSeeking && !adjustType && absDy > 15 && absDy > absDx) {
                adjustType = currentX < container.clientWidth / 2 ? 'brightness' : 'volume';
                if (adjustType === 'volume') {
                    volIndicator.classList.add('active');
                } else {
                    brightIndicator.classList.add('active');
                }
            }

            if (isSeeking) {
                var seekSeconds = dx / SEEK_PX_PER_SEC;
                var targetTime = Math.max(0, Math.min(seekStartTime + seekSeconds, activeVideo.duration || 0));
                activeVideo.currentTime = targetTime;
                seekTime.textContent = formatTime(targetTime);
                updateProgress();
            } else if (adjustType === 'volume') {
                var newVol = Math.max(0, Math.min(1, activeVideo.volume - dy / ADJUST_SENSITIVITY));
                activeVideo.volume = newVol;
                var volPctVal = Math.round(newVol * 100);
                volFill.style.height = volPctVal + '%';
                volPct.textContent = volPctVal + '%';
            } else if (adjustType === 'brightness') {
                var curBright = parseFloat(brightnessOverlay.style.opacity) || 0;
                var newBright = Math.max(0.1, Math.min(1, (1 - curBright) - dy / ADJUST_SENSITIVITY));
                brightnessOverlay.style.opacity = (1 - newBright).toFixed(2);
                var brightPctVal = Math.round(newBright * 100);
                brightFill.style.height = brightPctVal + '%';
                brightPct.textContent = brightPctVal + '%';
            }
        } else {
            if (!isSeeking && absDx > absDy && absDx > 15) {
                isSeeking = true;
                seekIndicator.classList.add('active');
            }
            if (isSeeking) {
                var seekSeconds2 = dx / SEEK_PX_PER_SEC;
                var targetTime2 = Math.max(0, Math.min(seekStartTime + seekSeconds2, activeVideo.duration || 0));
                activeVideo.currentTime = targetTime2;
                seekTime.textContent = formatTime(targetTime2);
                updateProgress();
            }
        }
    }, { passive: true });

    container.addEventListener('touchend', function(e) {
        if (isGrid && !gridIsVideo) return;
        cancelLongPress();
        if (isSeeking) {
            seekIndicator.classList.remove('active');
            isSeeking = false;
            return;
        }
        if (adjustType) {
            volIndicator.classList.remove('active');
            brightIndicator.classList.remove('active');
            adjustType = null;
            return;
        }
        if (!touchMoved || touchOnControls) return;

        if (document.fullscreenElement) return;

        var dy = e.changedTouches[0].clientY - touchStartY;
        var dx = e.changedTouches[0].clientX - touchStartX;

        if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > SWIPE_THRESHOLD) {
            if (dy < 0) navNext();
            else navPrev();
        }
    });

    container.addEventListener('touchcancel', function() {
        if (isGrid && !gridIsVideo) return;
        cancelLongPress();
        seekIndicator.classList.remove('active');
        volIndicator.classList.remove('active');
        brightIndicator.classList.remove('active');
        adjustType = null;
    });

    // ==================== 鼠标支持 ====================
    container.addEventListener('mousedown', function(e) {
        if (isGrid && !gridIsVideo) return;
        if (!e.target.closest('#controls')) startLongPress();
    });
    document.addEventListener('mouseup', cancelLongPress);
    container.addEventListener('mouseleave', cancelLongPress);

    // ==================== 滚轮 ====================
    container.addEventListener('wheel', function(e) {
        e.preventDefault();
        if (isLoading) return;
        if (e.deltaY > 0) {
            navNext();
        } else {
            navPrev();
        }
    }, { passive: false });

    // ==================== 键盘 ====================
    document.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
            e.preventDefault();
            navPrev();
        } else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
            e.preventDefault();
            navNext();
        } else if (e.key === ' ') {
            e.preventDefault();
            togglePlay();
        } else if (e.key === 'f' || e.key === 'F') {
            toggleFullscreen();
        } else if (e.key === 'm' || e.key === 'M') {
            toggleMute();
        } else if (e.key === 'Escape' && isGrid) {
            history.back();
        }
    });

    // ==================== 音量/亮度指示器 ====================
    function hideVolIndicator() { volIndicator.classList.remove('active'); }
    function hideBrightIndicator() { brightIndicator.classList.remove('active'); }

    // ==================== 启动 ====================
    timeDisplay.textContent = '0:00 / 0:00';
    updateVolUI(activeVideo.volume);
    updateBrightUI(1);
    updateSettingsMenu();
    showControls();
    resetControlsTimer();

    console.log('[LW_DEBUG] isGrid:', isGrid, 'mode:', mode, 'DOUYIN_CONFIG:', JSON.stringify(window.DOUYIN_CONFIG));
    if (isGrid) {
        initGrid();
    } else {
        console.log('[LW_DEBUG] about to call fetchInitAsync(), douyinInit URL:', window.ROUTES.douyinInit);
        fetchInitAsync();
    }

    // ==================== 工具函数 ====================
    function updateVolUI(vol) {
        var pct = Math.round(vol * 100);
        volFill.style.height = pct + '%';
        volPct.textContent = pct + '%';
    }

    function updateBrightUI(brightness) {
        var pct = Math.round(brightness * 100);
        brightFill.style.height = pct + '%';
        brightPct.textContent = pct + '%';
        brightnessOverlay.style.opacity = (1 - brightness).toFixed(2);
    }
})();
