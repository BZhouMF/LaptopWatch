"""测试 file_utils.py — MIME/驱动器/图标/文件大小"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.file_utils import get_mime_type, get_drives, get_icon, sizeof_fmt


class TestGetMimeType:

    def test_known_video_types(self):
        """标准视频 MIME 类型"""
        assert get_mime_type('video.mp4') == 'video/mp4'
        assert get_mime_type('video.webm') == 'video/webm'
        assert get_mime_type('video.avi') == 'video/avi'

    def test_known_image_types(self):
        """标准图片 MIME 类型"""
        assert get_mime_type('photo.jpg') == 'image/jpeg'
        assert get_mime_type('photo.png') == 'image/png'
        assert get_mime_type('photo.gif') == 'image/gif'

    def test_supplement_mappings(self):
        """补充映射中的非标准格式"""
        assert get_mime_type('video.m4v') == 'video/mp4'
        assert get_mime_type('video.flv') == 'video/x-flv'
        assert get_mime_type('video.ts') == 'video/vnd.dlna.mpeg-tts'
        assert get_mime_type('video.rmvb') == 'application/vnd.rn-realmedia-vbr'

    def test_unknown_extension(self):
        """未知扩展名返回 octet-stream"""
        assert get_mime_type('file.xyzunknown') == 'application/octet-stream'


class TestGetDrives:

    def test_returns_list_with_C(self):
        """返回驱动器列表，至少包含 C:（Windows）"""
        drives = get_drives()
        assert isinstance(drives, list)
        if os.name == 'nt':
            assert 'C' in drives


class TestGetIcon:

    def test_image_icon(self):
        assert get_icon('photo.jpg') == '🖼️'
        assert get_icon('photo.png') == '🖼️'

    def test_video_icon(self):
        assert get_icon('video.mp4') == '🎬'
        assert get_icon('video.avi') == '🎬'

    def test_text_icon(self):
        assert get_icon('readme.txt') == '📝'
        assert get_icon('notes.md') == '📝'

    def test_code_icon(self):
        assert get_icon('script.py') == '🐍'
        assert get_icon('index.html') == '🌐'

    def test_archive_icon(self):
        assert get_icon('archive.zip') == '📦'

    def test_default_icon(self):
        assert get_icon('unknown.xyz') == '📄'


class TestSizeofFmt:

    def test_bytes(self):
        assert sizeof_fmt(0) == '0.0B'
        assert sizeof_fmt(500) == '500.0B'

    def test_kilobytes(self):
        assert sizeof_fmt(1024) == '1.0KB'
        assert sizeof_fmt(1536) == '1.5KB'

    def test_megabytes(self):
        assert sizeof_fmt(1024 * 1024) == '1.0MB'

    def test_gigabytes(self):
        assert sizeof_fmt(1024 * 1024 * 1024) == '1.0GB'
