"""
文件操作API蓝图
包含文件下载、预览、文本查看等接口
"""
import os
import time
import tempfile
import zipfile
import urllib.parse
from flask import Blueprint, request, jsonify, render_template, send_file, after_this_request
from config import config
from utils.logging_utils import log_access, log_exception, logger
from utils.file_utils import safe_send_file, sizeof_fmt
from blueprints.auth import login_required, require_mode

file_bp = Blueprint('file_api', __name__, url_prefix='/file')

@file_bp.route('/raw/<path:filepath>')
@login_required
@require_mode('normal')
def _resolve_file_path(raw_path):
    """解析并校验文件路径，返回 (规范路径, None) 或 (None, 错误响应)"""
    decoded = urllib.parse.unquote(raw_path)
    real_path = os.path.realpath(decoded)
    if not os.path.exists(real_path):
        return None, "文件不存在", 404
    return real_path, None, None


def serve_raw(filepath):
    """原始文件预览"""
    start_time = time.time()
    try:
        abs_path, error, code = _resolve_file_path(filepath)
        if error:
            return error, code

        log_access(request, 'RAW_PREVIEW_ABS', abs_path, details=f"原始路径: {filepath}")

        return safe_send_file(abs_path, as_attachment=False)
    except Exception as e:
        log_exception(request, 'RAW_PREVIEW', filepath, e)
        return "预览失败", 500
    finally:
        # 使用绝对路径记录耗时
        abs_path = os.path.abspath(urllib.parse.unquote(filepath)) if 'filepath' in locals() else filepath
        log_access(request, 'RAW_PREVIEW_ABS', abs_path, duration=time.time() - start_time)

@file_bp.route('/view/<path:filepath>')
@login_required
@require_mode('normal')
def view_file(filepath):
    """文件下载"""
    start_time = time.time()
    try:
        abs_path, error, code = _resolve_file_path(filepath)
        if error:
            return error, code

        log_access(request, 'DOWNLOAD_ABS', abs_path, details=f"原始路径: {filepath}")

        return safe_send_file(abs_path, as_attachment=True)
    except Exception as e:
        log_exception(request, 'DOWNLOAD', filepath, e)
        return "下载失败", 500
    finally:
        # 使用绝对路径记录耗时
        abs_path = os.path.abspath(urllib.parse.unquote(filepath)) if 'filepath' in locals() else filepath
        log_access(request, 'DOWNLOAD_ABS', abs_path, duration=time.time() - start_time)

@file_bp.route('/text/<path:filepath>')
@login_required
@require_mode('normal')
def view_text_file(filepath):
    """文本文件查看"""
    start_time = time.time()
    try:
        abs_path, error, code = _resolve_file_path(filepath)
        if error:
            return error, code
        if os.path.getsize(abs_path) > 1024 * 1024:
            return "文件过大", 400
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        content = None
        used_encoding = None
        for enc in encodings:
            try:
                with open(abs_path, 'r', encoding=enc) as f:
                    content = f.read()
                    used_encoding = enc
                    break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                return f"读取失败: {e}", 500
        if content is None:
            return "无法识别编码", 400

        # 记录查看文本文件的绝对路径
        log_access(request, 'VIEW_TEXT_ABS', abs_path, details=f"原始路径: {filepath}")

        return render_template('text_viewer.html',
                               filename=os.path.basename(abs_path),
                               content=content,
                               encoding=used_encoding,
                               filepath=urllib.parse.quote(decoded_filepath.replace(os.sep, '/')),
                               file_size=sizeof_fmt(os.path.getsize(abs_path)))
    except Exception as e:
        log_exception(request, 'VIEW_TEXT', filepath, e)
        return "文本查看失败", 500
    finally:
        # 使用绝对路径记录耗时
        abs_path = os.path.abspath(urllib.parse.unquote(filepath)) if 'filepath' in locals() else filepath
        log_access(request, 'VIEW_TEXT_ABS', abs_path, duration=time.time() - start_time)

@file_bp.route('/download_folder')
@login_required
@require_mode('normal')
def download_folder():
    """文件夹下载（ZIP压缩）"""
    start_time = time.time()
    try:
        folder_path = request.args.get('path')
        if not folder_path:
            return '缺少路径参数', 400
        # 解码URL路径
        decoded_folder_path = urllib.parse.unquote(folder_path)
        abs_path = os.path.abspath(decoded_folder_path)
        if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            return '路径不存在或不是文件夹', 404
        total_size = 0
        file_count = 0
        file_list = []
        try:
            for root, dirs, files in os.walk(abs_path):
                for file in files:
                    full = os.path.join(root, file)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        continue
                    total_size += size
                    file_count += 1
                    if total_size > config.MAX_FOLDER_SIZE or file_count > config.MAX_FOLDER_FILES:
                        return f'文件夹过大（超过 {config.MAX_FOLDER_SIZE//1024//1024}MB 或 {config.MAX_FOLDER_FILES} 个文件），无法下载', 400
                    rel = os.path.relpath(full, abs_path)
                    file_list.append((full, rel))
        except Exception as e:
            from utils.logging_utils import logger
            logger.error(f"扫描文件夹失败 {abs_path}: {e}", exc_info=True)
            return f'扫描文件夹失败: {str(e)}', 500
        if not file_list:
            return '文件夹为空', 400
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        tmp.close()
        zip_path = tmp.name
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for full, rel in file_list:
                    zf.write(full, rel)
        except Exception as e:
            from utils.logging_utils import logger
            logger.error(f"压缩文件夹失败 {abs_path}: {e}", exc_info=True)
            os.unlink(zip_path)
            return f'压缩失败: {str(e)}', 500
        @after_this_request
        def cleanup(response):
            try:
                os.unlink(zip_path)
            except Exception as e:
                logger.debug(f"清理临时文件失败 {zip_path}: {e}")
            return response

        folder_name = os.path.basename(abs_path)
        try:
            return send_file(zip_path, as_attachment=True,
                             download_name=f'{folder_name}.zip',
                             mimetype='application/zip')
        except Exception:
            # send_file 失败（如客户端断连），立即清理，防止临时文件残留
            try:
                os.unlink(zip_path)
            except Exception:
                pass
            raise
    except Exception as e:
        log_exception(request, 'DOWNLOAD_FOLDER', folder_path, e)
        return "文件夹下载失败", 500
    finally:
        log_access(request, 'DOWNLOAD_FOLDER', folder_path or '', duration=time.time() - start_time)

@file_bp.route('/download_selected', methods=['POST'])
@login_required
@require_mode('normal')
def download_selected():
    """批量文件下载"""
    start_time = time.time()
    try:
        data = request.get_json()
        base = data.get('base') if data else ''
        count = len(data.get('paths', [])) if data else 0
        if not data:
            return '无效的请求数据', 400
        base = data.get('base')
        paths = data.get('paths', [])
        if not base or not paths:
            return '缺少参数', 400

        # 解码基准路径
        decoded_base = urllib.parse.unquote(base)
        base_abs = os.path.abspath(decoded_base)
        if not os.path.isdir(base_abs):
            return '基准路径不存在或不是文件夹', 400

        file_list = []
        total_size = 0
        total_files = 0
        try:
            for p in paths:
                # 解码路径
                decoded_p = urllib.parse.unquote(p)
                abs_p = os.path.abspath(decoded_p)
                if not abs_p.startswith(base_abs + os.sep) and abs_p != base_abs:
                    return f'路径 {p} 不在基准目录内', 400
                if not os.path.exists(abs_p):
                    return f'路径不存在: {p}', 400
                if os.path.isfile(abs_p):
                    file_size = os.path.getsize(abs_p)
                    total_size += file_size
                    total_files += 1
                    rel_path = os.path.relpath(abs_p, base_abs)
                    file_list.append((abs_p, rel_path))
                else:
                    for root, dirs, files in os.walk(abs_p):
                        for file in files:
                            full = os.path.join(root, file)
                            try:
                                size = os.path.getsize(full)
                            except OSError:
                                continue
                            total_size += size
                            total_files += 1
                            if total_size > config.MAX_FOLDER_SIZE or total_files > config.MAX_FOLDER_FILES:
                                return f'总大小超过 {config.MAX_FOLDER_SIZE//1024//1024}MB 或文件数超过 {config.MAX_FOLDER_FILES}，无法下载', 400
                            rel = os.path.relpath(full, base_abs)
                            file_list.append((full, rel))
        except Exception as e:
            return f'扫描文件失败: {str(e)}', 500
        if not file_list:
            return '没有可下载的文件', 400
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        tmp.close()
        zip_path = tmp.name
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for full, rel in file_list:
                    zf.write(full, rel)
        except Exception as e:
            os.unlink(zip_path)
            return f'压缩失败: {str(e)}', 500
        @after_this_request
        def cleanup(response):
            try:
                os.unlink(zip_path)
            except Exception as e:
                logger.debug(f"清理临时文件失败 {zip_path}: {e}")
            return response
        folder_name = os.path.basename(base_abs) + '_下载' if base_abs else '下载'
        try:
            return send_file(zip_path, as_attachment=True,
                             download_name=f'{folder_name}.zip',
                             mimetype='application/zip')
        except Exception:
            try:
                os.unlink(zip_path)
            except Exception:
                pass
            raise
    except Exception as e:
        log_exception(request, 'DOWNLOAD_SELECTED', base, e)
        return "批量下载失败", 500
    finally:
        log_access(request, 'DOWNLOAD_SELECTED', base, f'count={count}', duration=time.time() - start_time)