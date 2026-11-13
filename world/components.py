"""世界数据组件：按「位置 + 层」索引的可插拔纯数据存储。

方块定义（blocks.json 里的 id / 贴图 / 状态 schema）是静态的；组件记录的是
「世界里某一格上运行时的数据」——方块状态差异、箱子内容、熔炉燃料、红石
信号等。按组件类型分桶，既能按位置查，也能按类型批量遍历（例如以后每帧
更新全部熔炉），加功能方块时不用再往 VoxelWorld 里添新字典。

位置统一为 (x, y, z, layer)：layer 0 = 下层，1 = 上半砖层。
组件数据必须是 JSON 可序列化的 dict / list / 标量。
"""

BLOCK_STATE = 'state'   # 方块状态差异（axis / facing / half ...）

MAX_COMPONENT_TYPES = 64
MAX_ITEMS_PER_TYPE = 200000
MAX_DATA_ITEMS = 256
MAX_TYPE_NAME = 64


def valid_pos(pos):
    """位置必须是 (int, int, int, 0|1)。"""
    return (isinstance(pos, (tuple, list)) and len(pos) == 4
            and all(isinstance(v, int) and not isinstance(v, bool)
                    for v in pos[:3])
            and isinstance(pos[3], int) and pos[3] in (0, 1))


def _valid_data(data):
    """组件数据限制为可安全写入 JSON 的浅层结构，避免存档膨胀/注入。"""
    if isinstance(data, dict):
        return (len(data) <= MAX_DATA_ITEMS
                and all(isinstance(k, str) for k in data))
    if isinstance(data, (list, tuple)):
        return len(data) <= MAX_DATA_ITEMS
    return isinstance(data, (str, int, float, bool))


class ComponentStore:
    """ctype -> {(x, y, z, layer): data} 的稀疏存储。"""

    def __init__(self):
        self._stores = {}

    # ---------- 按位置读写 ----------
    def get(self, ctype, pos, default=None):
        return self._stores.get(ctype, {}).get(pos, default)

    def has(self, ctype, pos):
        return pos in self._stores.get(ctype, {})

    def set(self, ctype, pos, data):
        """设置组件；data 为空或 None 等价于删除。返回是否成功。"""
        if (not isinstance(ctype, str) or not ctype
                or len(ctype) > MAX_TYPE_NAME or not valid_pos(pos)):
            return False
        if data is None or data == {} or data == []:
            self.remove(ctype, pos)
            return True
        if not _valid_data(data):
            return False
        store = self._stores.get(ctype)
        if store is None:
            if len(self._stores) >= MAX_COMPONENT_TYPES:
                return False
            store = self._stores[ctype] = {}
        if pos not in store and len(store) >= MAX_ITEMS_PER_TYPE:
            return False
        store[pos] = data
        return True

    def remove(self, ctype, pos):
        store = self._stores.get(ctype)
        if store and pos in store:
            del store[pos]
            if not store:
                self._stores.pop(ctype, None)

    def remove_pos(self, pos):
        """清掉该位置的所有组件（挖掉方块时调用，避免残留运行时数据）。"""
        for ctype in list(self._stores):
            store = self._stores[ctype]
            store.pop(pos, None)
            if not store:
                self._stores.pop(ctype, None)

    # ---------- 按类型批量遍历（组件系统的主要价值） ----------
    def all(self, ctype):
        """迭代该类型的所有 (pos, data)。"""
        return self._stores.get(ctype, {}).items()

    def positions(self, ctype):
        return self._stores.get(ctype, {}).keys()

    def types(self):
        return tuple(self._stores)

    def count(self, ctype=None):
        if ctype is not None:
            return len(self._stores.get(ctype, {}))
        return sum(len(store) for store in self._stores.values())

    # ---------- 存档 ----------
    def at_pos(self, pos):
        """该位置的全部组件 {ctype: data}，用于写入存档。"""
        return {ctype: store[pos]
                for ctype, store in self._stores.items() if pos in store}

    def restore_pos(self, pos, raw):
        """从存档恢复某位置的组件；非法条目跳过。"""
        if not isinstance(raw, dict) or not valid_pos(pos):
            return
        for ctype, data in raw.items():
            self.set(ctype, pos, data)
