# Video/Image 模式数据库遍历逻辑（修订）

## 核心原则

- **用到才核实**：不预扫，遍历到哪个文件夹才 `sync_folder` 哪个
- **DB 驱动遍历**：文件夹列表和文件列表都从 DB 取，`sync_folder` 仅做校验修正
- **分组不混排**：文件夹之间不重排文件，一个文件夹的文件集中展示

## 启动流程

不做全量扫描。打开页面时只做两件事：

1. **确认祖先链**：`_ensure_node` 从盘符根到 MEDIA_DIR，逐级确认目录节点存在于 `nodes` 表
2. **同步根目录**：`sync_folder(MEDIA_DIR)` 核实 1 层内容（仅根目录的直接子项）

## 首页加载流程

1. 从 `nodes` 表查询 MEDIA_DIR 的直接子文件夹，按配置排序规则排序，得到有序文件夹列表：
   ```
   [sub1, sub2, sub3, sub4, sub5, ...]
   ```

2. 从 `media` 表查 MEDIA_DIR 根目录下的直接媒体文件，按规则排序，得到 `root_files`

3. 从 root_files 开始，然后逐个文件夹遍历：
   ```
   root_files: 3条 → 累计3，不够 PAGE_FIRST
   sub1: sync_folder(sub1) → 查 DB 直接子媒体文件 → 12条 → 累计15，不够
   sub2: sync_folder(sub2) → 查 DB 直接子媒体文件 → 40条 → 累计55，够了
   取 root_files(3) + sub1(12) + sub2前21条 = PAGE_FIRST 条
   记录断点: sub2, 已取21条
   ```

4. 返回给前端：文件列表 + next_offset + has_more

## 加载更多流程

前端请求 `offset=已取数量&limit=PAGE_LOAD`。

后端从断点位置继续遍历。步骤：

1. 如果断点在某个文件夹中间 → 从该文件夹剩余文件继续取
2. 不够则进入下一个文件夹 → `sync_folder` 核实 → 查 DB → 取文件
3. 凑满 `limit` 条后返回

例子（接上面首页）：
```
请求 offset=36, limit=36:
  sub2: 剩余19条 → 累计19，不够
  sub3: sync_folder(sub3) → 20条 → 累计39，够了
  取 sub2剩余19条 + sub3前17条 = 36条
  记录断点: sub3, 已取17条
```

## 随机模式

文件夹排序后，随机选一个起始下标，轮转文件夹列表：

```
排序后: [sub1, sub2, sub3, sub4, sub5]
随机起点=2 → 轮转后: [sub3, sub4, sub5, sub1, sub2]
```

随后遍历逻辑和顺序模式完全一致。文件夹内部文件不打乱，仍按排序规则取。

## 后端实现

### 新增函数

```python
def get_direct_media(conn, parent_id, media_type, sort_type, sort_order, limit, offset):
    """查某个文件夹的直接子媒体文件（不递归），返回 (rows, total)"""
    order_col = 'm.modify_time' if sort_type == 'time' else 'm.name'
    order_dir = 'DESC' if sort_order == 'desc' else 'ASC'
    total = conn.execute(
        "SELECT COUNT(*) FROM media m JOIN nodes n ON n.path = m.path "
        "WHERE m.media_type=? AND m.parent_id=? AND n.type=2",
        (media_type, parent_id)
    ).fetchone()[0]
    rows = conn.execute(
        f"SELECT m.* FROM media m JOIN nodes n ON n.path = m.path "
        f"WHERE m.media_type=? AND m.parent_id=? AND n.type=2 "
        f"ORDER BY {order_col} {order_dir} LIMIT ? OFFSET ?",
        (media_type, parent_id, limit, offset)
    ).fetchall()
    return [dict(r) for r in rows], total


def traverse_media(conn, root_folder_id, media_type, offset, limit, sort_type, sort_order, random_start=False):
    """文件夹遍历器：从 root_folder_id 开始，逐个文件夹取直接子媒体文件

    返回 (items, next_offset, has_more)
    """
    # 1. 获取有序子文件夹列表
    folders = get_subfolder_nodes(conn, root_folder_id, sort_type, sort_order)

    # 2. 随机模式：轮转子文件夹列表
    if random_start and folders:
        start_idx = random.randint(0, len(folders) - 1)
        folders = folders[start_idx:] + folders[:start_idx]

    # 3. 构建遍历序列：[root直接文件] + [folder1, folder2, ...]
    #    root直接文件视为一个"虚拟文件夹"

    # 4. 遍历，跳过 offset 个，收集 limit 个
    # ...
```

### 修改点

| 文件 | 改动 |
|------|------|
| `utils/db_utils.py` | 新增 `get_direct_media`、`traverse_media` |
| `app.py` | 删除启动时的 `sync_database` 调用，改为祖先链确认 |
| `blueprints/core.py` | Video/Image 首页改为调用 `traverse_media` |
| `blueprints/media_api.py` | `_db_load_more` 改为调用 `traverse_media` |
| `config.py` | 无改动 |

### API 不变

- `/media/load_more?offset=36&limit=36` — 接口签名不变，仅后端实现替换
- 首页渲染数据格式不变
