"""核心遍历算法正确性测试"""
import os
import time
import random
from pathlib import Path
from unittest.mock import patch


# ==================== 测试辅助 ====================

def make_subfolder(name, parent="/root"):
    """创建一个子文件夹条目（_get_sorted_subfolders 返回格式）"""
    return {'name': name, 'path': str(Path(parent) / name), 'mtime': 1000000000}


def make_file(name, parent="/root"):
    """创建一个文件条目（get_files_in_folder 返回格式）"""
    parent_str = str(Path(parent))
    root_str = str(Path("/root"))
    rel = Path(parent_str.replace(root_str, "", 1).lstrip(os.sep)) / name
    return {
        'name': name,
        'path': str(Path(parent_str) / name),
        'rel_path': str(rel).replace("\\", "/"),
        'mtime': 1000000000,
        'size': 1024,
    }


def folder_name(path):
    """从路径字符串中提取文件夹名（跨平台）"""
    return Path(str(path)).name


FOLDERS_ABC = [
    make_subfolder('A'), make_subfolder('B'), make_subfolder('C'),
]

FOLDERS_AB = [
    make_subfolder('A'), make_subfolder('B'),
]

A_SUBS = [
    make_subfolder('A1', '/root/A'), make_subfolder('A2', '/root/A'),
]

SINGLE_LEVEL_MOCK = {
    '/root': FOLDERS_ABC,
    '/root/A': [],
    '/root/B': [],
    '/root/C': [],
}

DRILL_MOCK = {
    '/root': FOLDERS_AB,
    '/root/A': A_SUBS,
    '/root/A/A1': [],
    '/root/A/A2': [],
    '/root/B': [],
}

TWO_LEVEL_MOCK = {
    '/root': [make_subfolder('A'), make_subfolder('B'), make_subfolder('C')],
    '/root/A': A_SUBS,
    '/root/A/A1': [],
    '/root/A/A2': [],
    '/root/B': [],
    '/root/C': [],
}


def make_subfolder_side_effect(mapping: dict):
    """创建 _get_sorted_subfolders 的 side_effect"""
    def side_effect(path):
        key = str(Path(str(path)).as_posix())
        return mapping.get(key, [])
    return side_effect


# ==================== _get_next_folder 测试 ====================

class TestGetNextFolder:
    """_get_next_folder 文件夹推进与回绕逻辑"""

    def test_empty_stack_marks_finished(self):
        """空栈返回 (None, False) 并标记 finished"""
        from utils.media_utils import _get_next_folder
        traversal = {'folder_stack': [], 'finished': False}
        folder, has_more = _get_next_folder(traversal)
        assert folder is None
        assert has_more is False
        assert traversal['finished'] is True

    def test_single_level_wrap_around(self):
        """单层 [A(start), B, C] → A→B→C→A→B→C→pop"""
        from utils.media_utils import _get_next_folder

        stack = [{
            'folder_path': '/root',
            'sibling_folders': FOLDERS_ABC,
            'current_sibling_idx': 0,
            'start_sibling_idx': 0,
            'visited_all_siblings': False,
        }]

        with patch('utils.media_utils._get_sorted_subfolders',
                   side_effect=make_subfolder_side_effect(SINGLE_LEVEL_MOCK)):
            traversal = {'folder_stack': stack, 'finished': False}

            # 第一轮：B(1), C(2)
            assert folder_name(_get_next_folder(traversal)[0]) == 'B'
            assert folder_name(_get_next_folder(traversal)[0]) == 'C'

            # C → wraps to 0 == start_idx, not visited → mark visited, return A
            folder, has_more = _get_next_folder(traversal)
            assert folder_name(folder) == 'A'
            assert stack[0]['visited_all_siblings'] is True

            # 第二轮：B, C
            assert folder_name(_get_next_folder(traversal)[0]) == 'B'
            assert folder_name(_get_next_folder(traversal)[0]) == 'C'

            # C → wraps to 0 == start, visited_all → pop
            folder, has_more = _get_next_folder(traversal)
            assert folder is None
            assert has_more is False
            assert traversal['finished'] is True
            assert len(stack) == 0

    def test_drill_into_subfolder(self):
        """从 C 回绕到 A，A 有 A1/A2，应下钻到 A1"""
        from utils.media_utils import _get_next_folder

        f3 = [make_subfolder('A'), make_subfolder('B'), make_subfolder('C')]
        stack = [{
            'folder_path': '/root',
            'sibling_folders': f3,
            'current_sibling_idx': 2,
            'start_sibling_idx': 2,
            'visited_all_siblings': False,
        }]

        with patch('utils.media_utils._get_sorted_subfolders',
                   side_effect=make_subfolder_side_effect(DRILL_MOCK)):
            traversal = {'folder_stack': stack, 'finished': False}
            # C(idx=2) → next=3≥3→wrap to 0, != start(2), return A, drill to A1
            folder, has_more = _get_next_folder(traversal)

            assert has_more is True
            assert folder_name(folder) == 'A1'
            assert len(stack) == 2
            assert Path(stack[1]['folder_path']).name == 'A'

    def test_two_level_up_on_parent_exhausted(self):
        """子层耗尽后上钻父层"""
        from utils.media_utils import _get_next_folder

        root_frame = {
            'folder_path': '/root',
            'sibling_folders': TWO_LEVEL_MOCK['/root'],
            'current_sibling_idx': 2,
            'start_sibling_idx': 2,
            'visited_all_siblings': False,
        }
        sub_frame = {
            'folder_path': '/root/A',
            'sibling_folders': A_SUBS,
            'current_sibling_idx': 0,
            'start_sibling_idx': 0,
            'visited_all_siblings': False,
        }
        stack = [root_frame, sub_frame]

        with patch('utils.media_utils._get_sorted_subfolders',
                   side_effect=make_subfolder_side_effect(TWO_LEVEL_MOCK)):
            traversal = {'folder_stack': stack, 'finished': False}

            # 子层：A1(start=0)→A2, A2→wraps to A1(not visited, mark visited)
            assert folder_name(_get_next_folder(traversal)[0]) == 'A2'
            assert sub_frame['visited_all_siblings'] is False

            folder, has_more = _get_next_folder(traversal)
            assert folder_name(folder) == 'A1'
            assert sub_frame['visited_all_siblings'] is True

            # A1→A2
            assert folder_name(_get_next_folder(traversal)[0]) == 'A2'

            # A2→wraps to A1, visited_all → pop sub_frame
            # 回到 root_frame: idx=2, next=3≥3→wrap to 0 != start(2) → A, drill to A1
            folder, has_more = _get_next_folder(traversal)
            assert folder_name(folder) == 'A1'
            assert len(stack) == 2

    def test_start_not_at_zero(self):
        """起始索引 B(start=1) [A, B, C] → B→C→A→B→C→A→pop"""
        from utils.media_utils import _get_next_folder

        stack = [{
            'folder_path': '/root',
            'sibling_folders': FOLDERS_ABC,
            'current_sibling_idx': 1,
            'start_sibling_idx': 1,
            'visited_all_siblings': False,
        }]

        with patch('utils.media_utils._get_sorted_subfolders',
                   side_effect=make_subfolder_side_effect(SINGLE_LEVEL_MOCK)):
            traversal = {'folder_stack': stack, 'finished': False}

            # B(start=1) → C(2)
            assert folder_name(_get_next_folder(traversal)[0]) == 'C'
            # C → wraps to 0 != start(1) → A
            assert folder_name(_get_next_folder(traversal)[0]) == 'A'
            # A → next=1 == start(1), not visited → mark visited, return B
            folder, has_more = _get_next_folder(traversal)
            assert folder_name(folder) == 'B'
            assert stack[0]['visited_all_siblings'] is True
            # B → C
            assert folder_name(_get_next_folder(traversal)[0]) == 'C'
            # C → wraps to 0 → 1 == start(1), visited_all → first pop pass...
            # actually: C(2) → next=3≥3→wrap to 0 != start(1) → A returned
            assert folder_name(_get_next_folder(traversal)[0]) == 'A'
            # A(0) → next=1 == start(1), visited_all → pop, empty
            folder, has_more = _get_next_folder(traversal)
            assert folder is None
            assert not has_more
            assert traversal['finished'] is True


# ==================== init_traversal 测试 ====================

class TestInitTraversal:
    """init_traversal 初始化逻辑"""

    def test_no_subfolders_uses_root(self):
        """根目录无子文件夹时直接返回根目录"""
        from utils.media_utils import init_traversal, _traversal_store

        with patch('utils.media_utils._get_sorted_subfolders', return_value=[]):
            tid = init_traversal(Path('/root'), 'video')
            entry = _traversal_store.get(tid)
            assert entry is not None
            assert str(entry['current_folder']) == str(Path('/root'))
            assert entry['folder_stack'] == []
            assert entry['finished'] is False
            assert entry['run_mode'] == 'video'
            _traversal_store.pop(tid, None)

    def test_selects_subfolder_as_start(self):
        """有子文件夹时随机选起点并下钻到叶子"""
        from utils.media_utils import init_traversal, _traversal_store

        with patch('utils.media_utils._get_sorted_subfolders',
                   side_effect=make_subfolder_side_effect(DRILL_MOCK)), \
             patch('random.randint', return_value=0):
            tid = init_traversal(Path('/root'), 'video')
            entry = _traversal_store.get(tid)
            assert entry is not None
            # randint=0 选 A, 然后 while 循环 A 有 A1/A2, randint=0 选 A1
            assert folder_name(entry['current_folder']) == 'A1'
            assert len(entry['folder_stack']) == 2
            assert entry['finished'] is False
            _traversal_store.pop(tid, None)

    def test_selects_second_subfolder(self):
        """random.randint 返回 1 时选 B 为起点"""
        from utils.media_utils import init_traversal, _traversal_store

        with patch('utils.media_utils._get_sorted_subfolders',
                   side_effect=make_subfolder_side_effect(SINGLE_LEVEL_MOCK)), \
             patch('random.randint', return_value=1):
            tid = init_traversal(Path('/root'), 'video')
            entry = _traversal_store.get(tid)
            assert entry is not None
            assert folder_name(entry['current_folder']) == 'B'
            assert entry['folder_stack'][0]['start_sibling_idx'] == 1
            _traversal_store.pop(tid, None)


# ==================== get_next_media_files 测试 ====================

class TestGetNextMediaFiles:
    """get_next_media_files 文件分页与文件夹切换"""

    def test_unknown_traversal_id(self):
        """不存在的 traversal_id 返回空"""
        from utils.media_utils import get_next_media_files
        files, has_more = get_next_media_files('nonexistent', 10)
        assert files == []
        assert has_more is False

    def test_return_files_from_current_folder(self):
        """从当前文件夹返回文件直到达到 limit"""
        from utils.media_utils import get_next_media_files, _traversal_store

        folder_a = str(Path('/root/videos'))
        files_in_folder = [make_file(f'clip{i}.mp4', folder_a) for i in range(5)]
        tid = 'test_return_files'

        with patch('utils.media_utils.get_files_in_folder', return_value=files_in_folder):
            _traversal_store[tid] = {
                'current_folder': folder_a,
                'current_file_idx': 0,
                'folder_stack': [],
                'finished': False,
                'root_path': '/root',
                'run_mode': 'video',
                'last_activity_time': time.time(),
            }
            result, has_more = get_next_media_files(tid, 3)

        assert len(result) == 3
        assert result[0]['name'] == 'clip0.mp4'
        assert result[2]['name'] == 'clip2.mp4'
        assert has_more is True
        assert _traversal_store[tid]['current_file_idx'] == 3
        _traversal_store.pop(tid, None)

    def test_switch_folder_when_current_exhausted(self):
        """当前文件夹耗尽后自动切换到下一个文件夹"""
        from utils.media_utils import get_next_media_files, _traversal_store

        folder_a = str(Path('/root/A'))
        folder_b = str(Path('/root/B'))
        a_files = [make_file(f'a{i}.mp4', folder_a) for i in range(2)]

        tid = 'test_switch_folder'
        stack = [{
            'folder_path': str(Path('/root')),
            'sibling_folders': [make_subfolder('A'), make_subfolder('B')],
            'current_sibling_idx': 0,
            'start_sibling_idx': 0,
            'visited_all_siblings': False,
        }]
        _traversal_store[tid] = {
            'current_folder': folder_a,
            'current_file_idx': 0,
            'folder_stack': stack,
            'finished': False,
            'root_path': '/root',
            'run_mode': 'video',
            'last_activity_time': time.time(),
        }

        def mock_files(path):
            if str(path) == folder_a:
                return a_files
            return []

        with patch('utils.media_utils.get_files_in_folder', side_effect=mock_files), \
             patch('utils.media_utils._get_sorted_subfolders',
                   side_effect=make_subfolder_side_effect(SINGLE_LEVEL_MOCK)):
            # 拉取 2 个文件（消耗完 A）
            result1, has_more1 = get_next_media_files(tid, 2)
            assert len(result1) == 2
            assert result1[0]['name'] == 'a0.mp4'

            # 再拉取 → 切换到 B，但 B 没有文件（mock_files 返回 []）
            # → 继续 _get_next_folder → wraps to A → A 有文件
            result2, has_more2 = get_next_media_files(tid, 2)
            # A 又返回了 2 个文件（a0, a1 again）
            assert len(result2) == 2

        _traversal_store.pop(tid, None)

    def test_exhaust_all_folders(self):
        """所有文件夹耗尽后返回空"""
        from utils.media_utils import get_next_media_files, _traversal_store

        folder_a = str(Path('/root/A'))
        a_files = [make_file('a.mp4', folder_a)]

        tid = 'test_exhausted'
        stack = [{
            'folder_path': str(Path('/root')),
            'sibling_folders': [make_subfolder('A')],
            'current_sibling_idx': 0,
            'start_sibling_idx': 0,
            'visited_all_siblings': False,
        }]
        _traversal_store[tid] = {
            'current_folder': folder_a,
            'current_file_idx': 0,
            'folder_stack': stack,
            'finished': False,
            'root_path': '/root',
            'run_mode': 'video',
            'last_activity_time': time.time(),
        }

        def mock_files(path):
            if str(path) == folder_a:
                return a_files
            return []

        with patch('utils.media_utils.get_files_in_folder', side_effect=mock_files), \
             patch('utils.media_utils._get_sorted_subfolders',
                   side_effect=make_subfolder_side_effect(SINGLE_LEVEL_MOCK)):
            # 第一次：消耗 a.mp4
            result1, h1 = get_next_media_files(tid, 1)
            assert len(result1) == 1
            assert h1 is True

            # 第二次：A 空了 → 推进到下一文件夹
            # 只有 A 一个，推进→wrap→mark visited→返回 A（a.mp4 again）
            result2, h2 = get_next_media_files(tid, 1)
            assert len(result2) == 1

            # 第三次：A 空 → wrap again → pop → finished
            result3, h3 = get_next_media_files(tid, 1)
            assert result3 == []
            assert h3 is False

        _traversal_store.pop(tid, None)

    def test_finished_removes_store_entry(self):
        """标记 finished 后 _traversal_store 应删除条目"""
        from utils.media_utils import get_next_media_files, _traversal_store

        tid = 'test_finished_removal'
        _traversal_store[tid] = {
            'current_folder': '/root',
            'current_file_idx': 0,
            'folder_stack': [],
            'finished': True,
            'root_path': '/root',
            'run_mode': 'video',
            'last_activity_time': time.time(),
        }
        get_next_media_files(tid, 1)
        assert tid not in _traversal_store


# ==================== init_sequential_traversal 测试 ====================

class TestInitSequentialTraversal:
    """init_sequential_traversal DFS 初始化逻辑"""

    def test_no_subfolders_single_frame(self):
        """无子文件夹时只有一个栈帧"""
        from utils.media_utils import init_sequential_traversal, _traversal_store

        with patch('utils.media_utils._get_sorted_subfolders', return_value=[]), \
             patch('utils.media_utils._get_sorted_media_files', return_value=[]):
            tid = init_sequential_traversal(Path('/root'), 'video')
            entry = _traversal_store.get(tid)
            assert entry is not None
            assert len(entry['folder_stack']) == 1
            assert entry['folder_stack'][0]['folder_path'] == str(Path('/root'))
            assert entry['finished'] is False
            _traversal_store.pop(tid, None)

    def test_drills_down_to_leaf(self):
        """沿第一个子文件夹下钻到叶子，每层包含 media_files"""
        from utils.media_utils import init_sequential_traversal, _traversal_store

        def mock_subfolders(path):
            key = str(Path(str(path)).as_posix())
            m = {
                '/root': [make_subfolder('A'), make_subfolder('B')],
                '/root/A': [make_subfolder('A1', '/root/A')],
                '/root/A/A1': [],
                '/root/B': [],
            }
            return m.get(key, [])

        def mock_media(path, target_ext):
            dir_name = Path(str(path)).name
            return [make_file(f'{dir_name}.mp4', str(path))]

        with patch('utils.media_utils._get_sorted_subfolders', side_effect=mock_subfolders), \
             patch('utils.media_utils._get_sorted_media_files', side_effect=mock_media):
            tid = init_sequential_traversal(Path('/root'), 'video')
            entry = _traversal_store.get(tid)

        assert entry is not None
        assert len(entry['folder_stack']) == 3
        assert Path(entry['folder_stack'][1]['folder_path']).name == 'A'
        assert Path(entry['folder_stack'][2]['folder_path']).name == 'A1'
        # 每层应有 media_files
        assert len(entry['folder_stack'][0]['media_files']) == 1
        assert entry['folder_stack'][0]['media_files'][0]['name'] == 'root.mp4'
        assert len(entry['folder_stack'][1]['media_files']) == 1
        assert entry['folder_stack'][1]['media_files'][0]['name'] == 'A.mp4'
        # 根层已消耗 A，故 subfolder_idx=1
        assert entry['folder_stack'][0]['current_subfolder_idx'] == 1
        assert entry['folder_stack'][1]['current_subfolder_idx'] == 1
        assert entry['folder_stack'][2]['current_subfolder_idx'] == 0
        _traversal_store.pop(tid, None)


# ==================== get_next_sequential_files 测试 ====================

class TestGetNextSequentialFiles:
    """get_next_sequential_files DFS 深度优先遍历"""

    def test_subfolder_files_before_self(self):
        """子文件夹的文件先于自身文件返回"""
        from utils.media_utils import get_next_sequential_files, _traversal_store

        tid = 'test_seq_sub_first'
        stack = [
            {
                'folder_path': str(Path('/root')),
                'subfolders': [make_subfolder('A')],
                'current_subfolder_idx': 1,
                'media_files': [make_file('root.mp4', str(Path('/root')))],
                'media_file_idx': 0,
            },
            {
                'folder_path': str(Path('/root/A')),
                'subfolders': [],
                'current_subfolder_idx': 0,
                'media_files': [make_file('a.mp4', str(Path('/root/A')))],
                'media_file_idx': 0,
            },
        ]
        _traversal_store[tid] = {
            'folder_stack': stack,
            'finished': False,
            'root_path': '/root',
            'run_mode': 'video',
            'last_activity_time': time.time(),
        }

        result, has_more = get_next_sequential_files(tid, 1)
        assert len(result) == 1
        assert result[0]['name'] == 'a.mp4'
        assert has_more is True

        result, has_more = get_next_sequential_files(tid, 1)
        assert len(result) == 1
        assert result[0]['name'] == 'root.mp4'
        assert has_more is False
        _traversal_store.pop(tid, None)

    def test_sequential_depth_first_traversal(self):
        """完整 DFS：A1 → A → B1 → B → root"""
        from utils.media_utils import get_next_sequential_files, _traversal_store

        def mock_subfolders(path):
            key = str(Path(str(path)).as_posix())
            m = {
                '/root': [make_subfolder('A'), make_subfolder('B')],
                '/root/A': [make_subfolder('A1', '/root/A')],
                '/root/A/A1': [],
                '/root/B': [make_subfolder('B1', '/root/B')],
                '/root/B/B1': [],
            }
            return m.get(key, [])

        def mock_media_dfs(path, target_ext):
            dir_name = Path(str(path)).name
            return [make_file(f'{dir_name}.mp4', str(path))]

        with patch('utils.media_utils._get_sorted_subfolders', side_effect=mock_subfolders), \
             patch('utils.media_utils._get_sorted_media_files', side_effect=mock_media_dfs):

            from utils.media_utils import init_sequential_traversal
            tid = init_sequential_traversal(Path('/root'), 'video')

            expected = ['A1.mp4', 'A.mp4', 'B1.mp4', 'B.mp4', 'root.mp4']
            for exp_name in expected:
                result, has_more = get_next_sequential_files(tid, 1)
                assert len(result) == 1
                assert result[0]['name'] == exp_name, f"期望 {exp_name}, 得到 {result[0]['name']}"

            result, has_more = get_next_sequential_files(tid, 1)
            assert result == []
            assert has_more is False
            assert tid not in _traversal_store
