"""
缩略图生成工具函数
"""
import os
import time
import base64
from io import BytesIO

from config import config
from utils.logging_utils import logger
from models.cache_models import cache_manager

# 尝试导入图像处理库
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# 兼容不同版本PIL的LANCZOS采样算法
try:
    # PIL 9.1.0+ 新版本
    LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    # 低版本PIL兼容
    LANCZOS = Image.LANCZOS if Image else None

def generate_thumbnail(filepath, size=config.THUMBNAIL_SIZE):
    """
    生成缩略图，支持图片和视频
    :param filepath: 文件路径
    :param size: 缩略图尺寸，默认为配置中的THUMBNAIL_SIZE
    :return: (mime_type, base64_data) 元组，或 None
    """
    # 缓存键：文件路径 + 文件修改时间 + 文件大小 + 缩略图尺寸
    try:
        stat = os.stat(filepath)
        cached_thumb = cache_manager.get_thumbnail_cache(filepath, stat.st_mtime, stat.st_size, size)
        if cached_thumb is not None:
            return ('image/jpeg', cached_thumb)
    except Exception as e:
        logger.error(f"获取文件状态失败 {filepath}: {e}", exc_info=True)
        print(f"[ERROR] 获取文件状态失败 {filepath}: {e}", flush=True)
        pass

    ext = os.path.splitext(filepath)[1].lower()
    is_image = ext in config.IMAGE_EXT
    is_video = ext in config.VIDEO_EXT

    # 图片大小校验
    if is_image:
        try:
            if os.path.getsize(filepath) > config.MAX_IMAGE_SIZE:
                return None
        except Exception as e:
            logger.error(f"获取图片大小失败 {filepath}: {e}", exc_info=True)
            print(f"[ERROR] 获取图片大小失败 {filepath}: {e}", flush=True)
            return None

    img = None
    try:
        if is_image and HAS_PIL:
            img = Image.open(filepath)
            img.thumbnail(size, LANCZOS)
        elif is_video and HAS_CV2:
            cap = cv2.VideoCapture(filepath)
            if cap.isOpened():
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    mid_frame = total_frames // 2
                    cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
                ret, frame = cap.read()
                if ret:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)
                    img.thumbnail(size, LANCZOS)
                else:
                    logger.error(f"OpenCV 无法从视频中截取帧: {filepath}")
                    print(f"[ERROR] OpenCV 无法从视频中截取帧: {filepath}", flush=True)
                cap.release()
            else:
                logger.error(f"OpenCV 无法打开视频文件: {filepath}")
                print(f"[ERROR] OpenCV 无法打开视频文件: {filepath}", flush=True)
        elif is_video and not HAS_CV2:
            logger.error(f"视频缩略图生成失败: OpenCV 未安装, 文件={filepath}")
            print(f"[ERROR] 视频缩略图生成失败: OpenCV 未安装, 文件={filepath}", flush=True)

        if img:
            if img.mode in ('RGBA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            buffered = BytesIO()
            quality = 100 if config.RUN_MODE == 'image' else 70
            img.save(buffered, format="JPEG", quality=quality)
            thumbnail_data = base64.b64encode(buffered.getvalue()).decode()

            # 存储到缓存
            try:
                stat = os.stat(filepath)
                cache_manager.set_thumbnail_cache(filepath, stat.st_mtime, stat.st_size, size, thumbnail_data)
            except Exception as e:
                logger.error(f"缓存缩略图失败 {filepath}: {e}", exc_info=True)
                print(f"[ERROR] 缓存缩略图失败 {filepath}: {e}", flush=True)
                pass

            return ('image/jpeg', thumbnail_data)
    except Exception as e:
        logger.error(f"生成缩略图失败 {filepath}: {e}", exc_info=True)
        print(f"[ERROR] 生成缩略图失败 {filepath}: {e}", flush=True)
    return None

def log_thumbnail_backend_status():
    """记录缩略图后端状态"""
    if HAS_CV2:
        logger.info('OpenCV 可用，视频缩略图将使用 OpenCV')
    else:
        logger.warning('[ERROR] OpenCV 不可用，视频缩略图功能不可用')

# 初始化时记录状态
log_thumbnail_backend_status()