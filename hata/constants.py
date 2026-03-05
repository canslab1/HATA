# -*- coding: utf-8 -*-
"""
常數項定義：保持程式高可讀性且易於修改及維護
"""

# 流程控制常數
STOP = 'stop'       # 停止下一階層的判斷
PASS = 'pass'       # 判斷尚未結束，下一階層繼續判斷

# 連結類型
BOND = 'bond link'               # 鍵結連結（強連結）
SILK = 'silk link'               # 絲絮連結（一端節點分支度為 1）
LOCAL_BRIDGE = 'local bridge'    # 區域橋接連結
GLOBAL_BRIDGE = 'global bridge'  # 全域橋接連結

# 連結顏色
SILK_COLOR = 'brown'
BOND_COLOR = 'lightblue'
LOCAL_BRIDGE_COLOR = 'red'
GLOBAL_BRIDGE_COLOR = 'green'

# 連結寬度
SILK_BASIC_WIDTH = 0.4
BOND_BASIC_WIDTH = 1.0
BRIDGE_BASIC_WIDTH = 0.7

# 節點大小
NODE_SIZE_BASE = 140
NODE_SIZE = 80

# 節點顏色
REGULAR_NODE_COLOR = 'pink'
IMPORTANT_NODE_COLOR = 'pink'
SUPER_NODE_COLOR = 'red'

# Ego 網絡鍵名（有向圖使用出入兩個方向）
EGO_NETWORK_OUT = 'ego_O_'
EGO_NETWORK_IN = 'ego_I_'

# 演算法內部 Graph 層級鍵名
GRAPH_KEY_COMMON_NODES_LIST = 'list_'
GRAPH_KEY_AVG_COMMON_NODES = 'avg'
GRAPH_KEY_STD_COMMON_NODES = 'std'
GRAPH_KEY_AVG_LIST = 'all.avg'
GRAPH_KEY_STD_LIST = 'all.std'
GRAPH_KEY_PASS_TO_NEXT_LAYER = 'partial.w'
GRAPH_KEY_SHORTEST_PATH = 'sp'
GRAPH_KEY_THRESHOLD_R1 = 'threshold.R1'
GRAPH_KEY_THRESHOLD_R2 = 'threshold.R2'
GRAPH_KEY_ENTROPY = 'entropy'
GRAPH_KEY_EDGE_CLASS = 'edge_class'
GRAPH_KEY_NUMBER_OF_LAYER = 'number_of_layer'

# 演算法內部 Edge 層級鍵名
EDGE_KEY_LAYER = 'layer'
EDGE_KEY_COLOR = 'color'
EDGE_KEY_WIDTH = 'width'
EDGE_KEY_NEXT_STEP = 'next step'

# 演算法內部 Node 層級鍵名
NODE_KEY_EDGE_CLASS = 'edge_class'
NODE_KEY_NEW_ENTROPY = 'new_entropy'
NODE_KEY_INFORMATION_GAIN = 'information_gain'
NODE_KEY_GROUP_NUMBER = 'group'

# 套件實驗資料集定義（有向網絡）
SUITE_DATASETS = {
    'DEMO': [
        'leader.net', 'prisonInter.net', 'Ragusa16.net',
        's208.net', 'women.net',
    ],
}
