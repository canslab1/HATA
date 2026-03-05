# -*- coding: utf-8 -*-
"""
HATA 核心分析引擎 — 階層式有向弧類型分析
(Hierarchical Arc Type Analysis)

論文參考
=======
Huang, C.-Y. & Chin, W.-C.-B.,
"Distinguishing Arc Types to Understand Complex Network Strength
 Structures and Hierarchical Connectivity Patterns"

移植自 HATA.py (Python 2.7)，修正所有 Python 3 與現代函式庫 API 不相容問題。
所有函數以明確參數傳遞，無全域變數，支援 progress_callback 供 GUI 顯示進度。

方法論概覽
=========
本模組實現一種純拓撲、無參數假設的有向弧分類方法，將有向網絡 G = (V, A)
中的每一條有向弧（directed arc）歸入以下四種類型之一：

    BOND（鍵結弧）          — 論文 Definition 5
        嵌入於緊密社群內部的冗餘連結；移除後，弧兩端節點仍可透過
        多條替代路徑相互到達，不改變社群的連通結構。

    SILK（絲絮弧）          — 論文 Definition 6
        一端節點的（全域）分支度為 1 的懸掛連結；移除後，該端點即
        成為孤立節點。結構上不具橋接功能。

    LOCAL_BRIDGE（區域橋接弧） — 論文 Definition 7
        連接鄰近社群的跨群連結；移除後使得局部連通性下降，但不致
        造成全域斷裂。

    GLOBAL_BRIDGE（全域橋接弧） — 論文 Definition 8
        連接遠距社群的長程連結；移除後可能使網路斷裂為不連通的
        分量。

HATA 與 HETA 的核心差異（論文 Section 3.1）
-------------------------------------------
HETA 處理無向圖，使用「共同朋友」概念：邊兩端的鄰域重疊度反映共享鄰居的多寡。
HATA 處理有向圖，使用「路徑」概念（論文 Eq. 3–6）：
  - 對於有向弧 s→t，s 的「朋友」是 s 可經由出邊到達的節點（出向 ego network）
  - t 的「朋友」是可經由入邊到達 t 的節點（入向 ego network）
  - 兩者的交集代表 s 到 t 之間存在的替代路徑結構

整體演算法流程（對應論文 Algorithm 1 / Figure 2 流程圖）
----------------------------------------------------
    Step 0 : 讀取有向網絡 G = (V, A)，分離弱連通分量
    Step 1 : 對每個分量計算分析層數 k_max = ⌊avg_SP / 2⌋（Eq. 3–4）
    Step 2 : 建立出向/入向多層 ego network，計算弧兩端鄰域重疊度（Eq. 5–8）
    Step 3 : 生成 |RG| 個度序列保持的隨機有向網絡（null model），導出 R1 門檻（Eq. 9）
    Step 4 : 五階段弧分類
             Phase 1 — SILK 識別（degree-1 端點）
             Phase 2 — BOND vs LOCAL_BRIDGE（R1 外部門檻 + R2 內部門檻，逐層精煉）
             Phase 3 — GLOBAL_BRIDGE（殘留未分類弧全數歸入）
             Phase 4 — 節點結構資訊熵與重要性量化（Eq. 10–11）
             Phase 5 — 網絡指紋（四類弧比例向量）輸出

整體時間複雜度：O(|RG| × |A| × k_max)
整體空間複雜度：O(|A| × k_max)
"""

import math
import multiprocessing as mp
import os
import pickle
import random
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed

import networkx as nx
import numpy as np
import scipy.cluster.hierarchy as hc
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

from hata.constants import *


# ═══════════════════════════════════════════════════════════════════════
# 資料結構定義
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LinkAnalysisResult:
    """
    單一弱連通分量的完整分析結果。

    由 run_link_analysis() 針對每個足夠大的弱連通分量產生一個實例，
    封裝所有後續繪圖、Excel 輸出與指紋比較所需的資料。
    """
    # --- 核心分析產物 ---
    graph: Any                      # nx.DiGraph，每條弧已標註 layer/color/width/type
    component_id: int               # 該分量在原始網絡中的序號（按節點數降序編號）
    network_name: str               # 來源檔案名稱（不含副檔名與路徑）

    # --- 網絡拓撲統計量 ---
    num_nodes: int                  # |V|
    num_edges: int                  # |A|
    avg_in_degree: float            # 平均入度
    avg_out_degree: float           # 平均出度
    diameter: int                   # 直徑（弱連通圖可能回退至無向圖計算）
    avg_shortest_path: float        # 平均最短路徑長度（隨機抽樣估計）
    avg_clustering_coeff: float     # 平均群聚係數
    degree_assortativity: float     # 度相關係數

    # --- 弧分類計數（Phase 1–3 結果）---
    bond_count: int                 # BOND 弧數量
    silk_count: int                 # SILK 弧數量
    local_bridge_count: int         # LOCAL_BRIDGE 弧數量
    global_bridge_count: int        # GLOBAL_BRIDGE 弧數量

    # --- 結構資訊量（Phase 4 結果）---
    graph_entropy: float            # 全域弧類型 Shannon 熵 H(G)（Eq. 10）
    layers: int                     # 實際分析層數 k_max

    # --- 門檻值（供 Excel / 圖表顯示）---
    thresholds_r1: Dict[str, float] = field(default_factory=dict)  # 各層 R1（外部門檻）
    thresholds_r2: Dict[str, float] = field(default_factory=dict)  # 各層 R2（內部門檻）

    # --- 視覺化輔助 ---
    node_sizes: List[float] = field(default_factory=list)          # 依 information gain 縮放
    node_colors: List[str] = field(default_factory=list)           # 依重要性分色
    node_info_avg: float = 0.0                                     # 節點 information gain 平均值

    # --- Null Model 統計（供 Excel Sheet 2 輸出）---
    random_network_stats: List[Dict] = field(default_factory=list)

    # --- 網絡指紋（Phase 5 結果）---
    fingerprint: Dict[int, float] = field(default_factory=dict)    # {0:BOND%, 1:LB%, 2:GB%, 3:SILK%}

    # --- 佈局與來源 ---
    pos: Optional[Dict] = None      # spring_layout 座標
    path: str = ''                   # 來源檔案完整路徑


@dataclass
class SuiteExperimentResult:
    """
    批次實驗結果：多個有向網絡的指紋比較與階層聚類。

    由 run_suite_experiment() 產生，封裝指紋長條圖、Pearson 相關係數
    熱力圖、以及 centroid linkage 樹狀圖所需的全部資料。
    """
    fingerprints: Dict[str, Dict[int, float]] = field(default_factory=dict)  # 各網絡指紋
    corr_table: Dict[str, Dict[str, float]] = field(default_factory=dict)    # 兩兩相關係數
    labels: List[str] = field(default_factory=list)                          # 網絡標籤
    bar_data: Dict[str, Any] = field(default_factory=dict)                   # 堆疊長條圖資料
    corr_matrix: Any = None                                                  # 聚類後相關矩陣
    corr_index: List[int] = field(default_factory=list)                      # 聚類排序索引
    corr_labels: List[str] = field(default_factory=list)                     # 聚類後標籤順序
    network_stats: Dict[str, Dict[str, float]] = field(default_factory=dict) # 各網絡拓撲統計


# ═══════════════════════════════════════════════════════════════════════
# 輔助函數
# ═══════════════════════════════════════════════════════════════════════

def debugmsg(s, debug=False):
    """在除錯模式下顯示訊息"""
    if debug:
        print(s)


def _safe_degree_assortativity(g):
    """
    安全版本的 degree assortativity coefficient。

    當所有節點的 degree 完全相同（例如正則圖）時，degree 序列的
    variance = 0，導致 NetworkX 內部除以零而回傳 NaN。
    此函數攔截此情況並以 0.0（無相關）取代。
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            r = nx.degree_assortativity_coefficient(g)
        return 0.0 if (r is None or np.isnan(r)) else r
    except (ValueError, ZeroDivisionError):
        return 0.0


def _safe_diameter(g):
    """
    安全版本的 diameter 計算。

    有向圖的弱連通分量不一定是強連通的，因此 nx.diameter()
    可能因找不到全域最短路徑而拋出例外。
    回退策略：先嘗試有向圖 → 再嘗試底層無向圖 → 最終回傳 0。
    """
    try:
        return nx.diameter(g)
    except (nx.NetworkXError, nx.NetworkXUnfeasible):
        try:
            return nx.diameter(g.to_undirected())
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            return 0


def average_shortest_path_length(g, pairs=1000):
    """
    以隨機抽樣估計有向圖的平均最短路徑長度。
    （對應論文 Algorithm 1, Step 0 之 avg_SP 計算）

    有向圖中並非所有節點對 (s, t) 都存在 s→…→t 的可達路徑，
    因此無法直接使用 nx.average_shortest_path_length()。
    本函數隨機抽取 pairs 組節點對，僅對有路徑可達者計算平均值。

    此估計值將被用於決定分析層數：
        k_max = ⌊avg_SP / 2⌋  （論文 Eq. 3–4）

    原始：HATA.py:192-201
    """
    nlist = list(g.nodes())
    if len(nlist) < 2:
        return 1.0
    total = 0
    count = 0
    for _ in range(pairs):
        s, t = random.sample(nlist, k=2)
        if nx.has_path(g, source=s, target=t):
            total += nx.shortest_path_length(g, source=s, target=t)
            count += 1
    if count == 0:
        return 1.0
    return total / float(count)


# ═══════════════════════════════════════════════════════════════════════
# 核心演算法：多層 Ego Network 建構與鄰域重疊度計算
# （對應論文 Algorithm 1, Step 1–2 / Section 3.1）
# ═══════════════════════════════════════════════════════════════════════

def generate_ego_graph(g, sp):
    """
    為每個節點預先建立出向與入向的多層 ego network。
    （對應論文 Eq. 5–6：k-hop 累積鄰域的遞迴定義）

    有向圖中需要兩套 ego network（與無向 HETA 只需一套不同）：
      - 出向（outgoing）：N_out^k(n) = 節點 n 沿出邊方向 k 步可達的所有節點
      - 入向（incoming）：N_in^k(n)  = 沿入邊方向 k 步可到達節點 n 的所有節點

    遞迴建構方式（BFS 式逐層擴展）：
      - r = 0（基底）：ego_out[0] = {n},  ego_in[0] = {n}
      - r > 0（遞迴）：
            ego_out[r](n) = ego_out[r-1](n) ∪ ⋃_{ng ∈ successors(n)} ego_out[r-1](ng)
            ego_in[r](n)  = ego_in[r-1](n)  ∪ ⋃_{ng ∈ predecessors(n)} ego_in[r-1](ng)

    以 node attribute 形式存放，key 格式為 'ego_O_{r}' 與 'ego_I_{r}'。

    原始：HATA.py:94-112
    時間複雜度：O(sp × |V| × avg_degree)
    """
    for r in range(sp):
        if r == 0:
            # 基底：每個節點的 0-hop ego network 就是自己
            for n in g.nodes():
                g.nodes[n][EGO_NETWORK_OUT + str(r)] = {n}
                g.nodes[n][EGO_NETWORK_IN + str(r)] = {n}
        else:
            # 遞迴：由 r-1 層擴展至 r 層
            for n in g.nodes():
                # 先複製前一層作為基底
                g.nodes[n][EGO_NETWORK_OUT + str(r)] = set(g.nodes[n][EGO_NETWORK_OUT + str(r - 1)])
                g.nodes[n][EGO_NETWORK_IN + str(r)] = set(g.nodes[n][EGO_NETWORK_IN + str(r - 1)])
                # 出向擴展：聯集所有出鄰居的 r-1 層 ego
                for ng in g.successors(n):
                    g.nodes[n][EGO_NETWORK_OUT + str(r)] = (
                        g.nodes[n][EGO_NETWORK_OUT + str(r)] | g.nodes[ng][EGO_NETWORK_OUT + str(r - 1)]
                    )
                # 入向擴展：聯集所有入鄰居的 r-1 層 ego
                for ng in g.predecessors(n):
                    g.nodes[n][EGO_NETWORK_IN + str(r)] = (
                        g.nodes[n][EGO_NETWORK_IN + str(r)] | g.nodes[ng][EGO_NETWORK_IN + str(r - 1)]
                    )


def get_outgoing_ego_graph(g, s, t, l):
    """
    取得節點 s 的出向第 l 層「排除 t」鄰域。
    （對應論文 Eq. 7 左半部：source 端的替代出向結構）

    對有向弧 s→t，計算 s 不經由 s→t 直接弧所能到達的出向鄰域：
      ring_out(s, t, l) = ⋃_{ng ∈ successors(s), ng ≠ t} ego_out[l-1](ng) - {s}

    直覺：如果移除 s→t 這條弧，s 還能透過哪些替代路徑向外延伸？

    原始：HATA.py:115-130
    """
    index = EGO_NETWORK_OUT + str(l - 1)
    node_list = set()
    for ng in g.successors(s):
        if ng != t:
            node_list = node_list | g.nodes[ng][index]
    return node_list - {s}


def get_incoming_ego_graph(g, t, s, l):
    """
    取得節點 t 的入向第 l 層「排除 s」鄰域。
    （對應論文 Eq. 7 右半部：target 端的替代入向結構）

    對有向弧 s→t，計算不經由 s→t 直接弧即可到達 t 的入向鄰域：
      ring_in(t, s, l) = ⋃_{ng ∈ predecessors(t), ng ≠ s} ego_in[l-1](ng) - {t}

    直覺：如果移除 s→t 這條弧，還有哪些替代路徑可以抵達 t？

    原始：HATA.py:133-140
    """
    index = EGO_NETWORK_IN + str(l - 1)
    node_list = set()
    for ng in g.predecessors(t):
        if ng != s:
            node_list = node_list | g.nodes[ng][index]
    return node_list - {t}


def compute_link_property(g, sp):
    """
    核心演算法：計算有向網絡中每一條弧的多層鄰域重疊度。
    （對應論文 Algorithm 1, Step 1 / Eq. 5–8）

    對每條有向弧 s→t，在每個半徑 l = 1, 2, ..., k_max 下：

    1. 計算「環」（ring）— 該層新增的鄰域節點：
       s 端出向環：ring_out(s, l) = ego_out(s, l) - ego_out(s, l-1) - {s, t}
       t 端入向環：ring_in(t, l)  = ego_in(t, l)  - ego_in(t, l-1)  - {s, t}

    2. 計算「交叉層共同節點」（cross-layer common nodes, Eq. 8）：
       CN(s→t, l) = (ring_out(s,l) ∩ ring_in(t,l))       ← 同層交集
                   ∪ (ring_out(s,l) ∩ ring_in(t,l-1))     ← 交叉層交集
                   ∪ (ring_out(s,l-1) ∩ ring_in(t,l))     ← 交叉層交集

       三項交叉層交集的目的：捕捉「s 到 t 之間經由 ±1 層中間節點的
       替代路徑」，避免因層邊界而遺漏。

    3. Union 正規化（Eq. 8 分母）：
       denom = |ring_out(s,l) ∪ ring_in(t,l)|
             + |ring_out(s,l) ∪ ring_in(t,l-1)|
             + |ring_out(s,l-1) ∪ ring_in(t,l)|

       w(s→t, l) = |CN(s→t, l)| / denom

       值域 [0, 1]。越接近 1 代表替代路徑越多，弧越可能是 BOND；
       越接近 0 代表弧越可能是 bridge。

    計算結果存放於 edge attribute: g[s][t][-l] = w(s→t, l)
    （使用負整數 key -1, -2, ... 對應 layer 1, 2, ...）

    原始：HATA.py:143-189
    時間複雜度：O(|A| × k_max × avg_degree)
    空間複雜度：O(|A| × k_max)
    """
    # 使用副本 c 進行 ego network 建構，避免汙染原始圖的 edge attributes
    c = g.copy()

    # 初始化各層的 common nodes 收集列表（用於後續計算全域 avg / std）
    for i in range(sp):
        c.graph[GRAPH_KEY_COMMON_NODES_LIST + str(i + 1)] = []

    # Step 1a: 預建所有節點的多層 ego network
    generate_ego_graph(c, sp)

    # Step 1b: 對每條弧計算各層的鄰域重疊度 w(s→t, l)
    for s, t in g.edges():
        base_st_nodes = {s, t}   # 始終排除弧的兩個端點本身
        c.nodes[s][0] = set()    # 累積已處理的出向環節點（layer 0 ~ l-1）
        c.nodes[t][0] = set()    # 累積已處理的入向環節點（layer 0 ~ l-1）

        for i in range(sp):
            l = i + 1

            # --- 計算該層的「環」（新增鄰域） ---
            # s 端：出向 l-hop 鄰域 - 前幾層已算過的 - {s, t}
            c.nodes[s][l] = get_outgoing_ego_graph(c, s, t, l) - c.nodes[s][0] - base_st_nodes
            # t 端：入向 l-hop 鄰域 - 前幾層已算過的 - {s, t}
            c.nodes[t][l] = get_incoming_ego_graph(c, t, s, l) - c.nodes[t][0] - base_st_nodes

            # --- 交叉層共同節點（Eq. 8 分子）---
            common_nodes = (
                (c.nodes[s][l] & c.nodes[t][l]) |          # 同層 l ∩ l
                (c.nodes[s][l] & c.nodes[t][l - 1]) |      # 交叉 l ∩ (l-1)
                (c.nodes[s][l - 1] & c.nodes[t][l])         # 交叉 (l-1) ∩ l
            )

            # --- Union 正規化（Eq. 8 分母）---
            denominator = 1.0
            if len(common_nodes) != 0:
                denominator = (
                    len(c.nodes[s][l] | c.nodes[t][l]) +
                    len(c.nodes[s][l] | c.nodes[t][l - 1]) +
                    len(c.nodes[s][l - 1] | c.nodes[t][l])
                )

            # 寫入該弧在第 l 層的重疊度權重 w(s→t, l)
            g[s][t][-l] = float(len(common_nodes)) / denominator

            # 收集全域統計（供後續計算 R1 門檻使用）
            c.graph[GRAPH_KEY_COMMON_NODES_LIST + str(l)].append(g[s][t][-l])

            # 將本層環節點納入「已處理」集合，下一層才能正確計算差集
            c.nodes[s][0] |= c.nodes[s][l]
            c.nodes[t][0] |= c.nodes[t][l]

    # 計算各層 w 值的全域平均與標準差（供 null model 比較）
    for i in range(sp):
        l = str(i + 1)
        g.graph[GRAPH_KEY_AVG_COMMON_NODES + l] = np.mean(c.graph[GRAPH_KEY_COMMON_NODES_LIST + l])
        g.graph[GRAPH_KEY_STD_COMMON_NODES + l] = np.std(c.graph[GRAPH_KEY_COMMON_NODES_LIST + l])

    return g


def entropy(p):
    """
    計算 Shannon 資訊熵 H = -Σ p_i × log₂(p_i)。
    （對應論文 Eq. 10）

    參數 p 為各類別的計數（非比例），函數內部自動正規化為機率分佈。
    用於量化弧類型分佈的不確定性：
      - H 越高 → 各類型弧的分佈越均勻（網絡結構越多樣）
      - H = 0  → 所有弧屬於同一類型
    """
    e = 0
    t = sum(p)
    if t == 0:
        return 0
    for v in p:
        if v != 0:
            pi = float(v) / t
            e += -(pi * math.log(pi, 2))
    return e


# ═══════════════════════════════════════════════════════════════════════
# 階層式社群切割（視覺化輔助）
# ═══════════════════════════════════════════════════════════════════════

def network_clustering(g, layer):
    """
    階層式社群切割：透過逐步移除橋接弧來揭示社群結構。
    （對應論文 Section 4.2 之社群分割應用）

    演算法步驟：
      1. 移除所有 GLOBAL_BRIDGE 弧（長程連結），使遠距社群分離
      2. 移除所有 SILK 弧並孤立其 degree-1 端點（不屬於任何社群核心）
      3. 對剩餘的弱連通分量，遞迴呼叫 component_clustering()
         逐層移除 LOCAL_BRIDGE，由最高層向下逐層精煉
      4. 最終每個節點被分配一個階層式群組編號（如 "0.01", "0.0102"）

    有向圖版本使用弱連通分量（weakly connected components）進行分割
    （而非 HETA 的連通分量）。

    回傳：snapshot_g 字典，包含各層級移除橋接後的子圖快照（供繪圖使用）
    """
    snapshot_g = {GLOBAL_BRIDGE: [], EDGE_KEY_LAYER + str(layer): []}
    c = g.copy()

    for s, t in g.edges():
        if g[s][t][EDGE_KEY_LAYER + str(layer)].startswith(GLOBAL_BRIDGE):
            if c.has_edge(s, t):
                c.remove_edge(s, t)
        if g[s][t][EDGE_KEY_LAYER + str(layer)].startswith(SILK):
            if c.has_edge(s, t):
                c.remove_edge(s, t)
            tmpG = nx.DiGraph()
            if g.degree(s) == 1:
                if c.has_node(s):
                    c.remove_node(s)
                g.nodes[s][NODE_KEY_GROUP_NUMBER] = "-0.01"
                tmpG.add_node(s)
            elif g.degree(t) == 1:
                if c.has_node(t):
                    c.remove_node(t)
                g.nodes[t][NODE_KEY_GROUP_NUMBER] = "-0.01"
                tmpG.add_node(t)
            else:
                if c.has_node(t):
                    c.remove_node(t)
                g.nodes[t][NODE_KEY_GROUP_NUMBER] = "-0.01"
                tmpG.add_node(t)
            snapshot_g[GLOBAL_BRIDGE].append(tmpG)
            snapshot_g[EDGE_KEY_LAYER + str(layer)].append(tmpG)

    snapshot_g[GLOBAL_BRIDGE].append(c)
    no = 1
    for comp_nodes in nx.weakly_connected_components(c):
        sc = c.subgraph(comp_nodes).copy()
        component_clustering(g, snapshot_g, sc, layer, "0." + ("%02d" % no))
        no += 1
    return snapshot_g


def component_clustering(bigG, sg, g, layer, cno):
    """
    遞迴式社群切割：逐層移除 local bridge（有向圖版本）。

    從最高層（k_max）向下，每層移除該層標記為 local bridge 的弧，
    再以弱連通分量分割出新的子社群，遞迴至 layer=0 或無法再分割為止。
    每個節點最終被標記一個由層級編碼組成的群組編號（cno），
    例如 "0.01" → "0.0102" → "0.010201"，層數越深編碼越長。

    參數：
        bigG  : 原始完整圖（用於寫入節點 group number）
        sg    : snapshot 字典（收集各層子圖快照）
        g     : 當前待切割的子圖
        layer : 當前處理層級（由高向低遞減）
        cno   : 當前群組編號前綴

    終止條件（任一成立即停止遞迴）：
      - g 只剩 1 個節點（無法再分割）
      - g 沒有邊（所有弧已移除）
      - layer 已遞減至 0（已達最細粒度）
    """
    if g.order() == 1 or g.size() == 0 or layer == 0:
        for v in g.nodes():
            bigG.nodes[v][NODE_KEY_GROUP_NUMBER] = cno
        if layer != 0:
            sg[EDGE_KEY_LAYER + str(layer)].append(g)
        return

    c = g.copy()
    for s, t in g.edges():
        if g[s][t][EDGE_KEY_LAYER + str(layer)] == LOCAL_BRIDGE + ' of layer ' + str(layer):
            if c.has_edge(s, t):
                c.remove_edge(s, t)

    sg[EDGE_KEY_LAYER + str(layer)].append(c)
    if layer > 1:
        sg[EDGE_KEY_LAYER + str(layer - 1)] = []

    no = 1
    for comp_nodes in nx.weakly_connected_components(c):
        sc = c.subgraph(comp_nodes).copy()
        component_clustering(bigG, sg, sc, layer - 1, cno + ("%02d" % no))
        no += 1


# ═══════════════════════════════════════════════════════════════════════
# Null Model：隨機有向網絡生成
# （對應論文 Algorithm 1, Step 2 / Section 3.2）
# ═══════════════════════════════════════════════════════════════════════

def _generate_random_network(g, layers, cache_path=None):
    """
    產生單一隨機有向網絡（null model）並計算其鄰域重疊度統計。
    （對應論文 Algorithm 1, Step 2：生成 |RG| 個隨機有向網絡）

    使用 directed_configuration_model 產生具有相同入度/出度序列的
    隨機有向圖。此方法保持每個節點的入度和出度不變，但隨機重新配線，
    藉此保留度序列特徵但破壞社群結構。

    與 HETA 的差異：
      - HETA 使用 connected_double_edge_swap（無向，保持連通性）
      - HATA 使用 directed_configuration_model（有向，保持度序列）

    生成後立即計算 compute_link_property()，僅保留各層的 avg/std 統計，
    其餘圖結構即丟棄以節省記憶體。

    此函數為頂層函數（非巢狀），以支援 multiprocessing 的 pickle 序列化。
    結果可選擇性地快取至磁碟，加速後續相同參數的重複分析。
    """
    in_degree_seq = [d for _, d in g.in_degree()]
    out_degree_seq = [d for _, d in g.out_degree()]

    try:
        rg = nx.directed_configuration_model(in_degree_seq, out_degree_seq)
        rg = nx.DiGraph(rg)  # MultiDiGraph → DiGraph（移除多重邊，保留自迴圈）
    except (nx.NetworkXError, nx.NetworkXUnfeasible):
        warnings.warn(
            f"Random directed network generation failed "
            f"(edges={g.number_of_edges()}). "
            f"Using original graph structure.",
            RuntimeWarning,
            stacklevel=2,
        )
        rg = g.copy()

    if rg.number_of_edges() == 0:
        rg = g.copy()

    compute_link_property(rg, layers)

    rg_data = {'graph': {}}
    for i in range(layers):
        l = str(i + 1)
        rg_data['graph'][GRAPH_KEY_AVG_COMMON_NODES + l] = rg.graph[GRAPH_KEY_AVG_COMMON_NODES + l]
        rg_data['graph'][GRAPH_KEY_STD_COMMON_NODES + l] = rg.graph[GRAPH_KEY_STD_COMMON_NODES + l]

    if cache_path:
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(rg_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError:
            pass

    return rg_data


# ═══════════════════════════════════════════════════════════════════════
# 網絡檔案 I/O
# ═══════════════════════════════════════════════════════════════════════

# 支援的網絡檔案格式
SUPPORTED_FORMATS = {
    '.net': 'Pajek',
    '.gml': 'GML',
    '.graphml': 'GraphML',
    '.edgelist': 'Edge List',
    '.edges': 'Edge List',
    '.adjlist': 'Adjacency List',
}


def _read_network(path):
    """
    讀取有向網絡檔案，根據副檔名自動選擇對應的讀取器。
    一律以 DiGraph 讀入。
    """
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='.*is not processed.*Non-string attribute.*',
                                category=UserWarning)
        if ext == '.net':
            G = nx.DiGraph(nx.read_pajek(path))
        elif ext == '.gml':
            G = nx.DiGraph(nx.read_gml(path))
        elif ext == '.graphml':
            G = nx.DiGraph(nx.read_graphml(path))
        elif ext in ('.edgelist', '.edges'):
            G = nx.read_edgelist(path, create_using=nx.DiGraph())
        elif ext == '.adjlist':
            G = nx.read_adjlist(path, create_using=nx.DiGraph())
        else:
            supported = ', '.join(SUPPORTED_FORMATS.keys())
            raise ValueError(
                f"Unsupported network file format: '{ext}'\n"
                f"Supported formats: {supported}"
            )

    return G


# ═══════════════════════════════════════════════════════════════════════
# 主分析管線
# （對應論文 Algorithm 1 / Figure 2 完整流程）
# ═══════════════════════════════════════════════════════════════════════

def run_link_analysis(
    path,
    times=1000,
    quick=False,
    separation=1,
    debug=False,
    parallel=False,
    workers=None,
    progress_callback=None,
):
    """
    HATA 主分析管線：讀取有向網絡 → 建立 null model → 分類所有弧 → 計算結構資訊量。
    （對應論文 Algorithm 1 完整流程）

    分析管線概覽：
        Step 0 : 讀取有向網絡 G=(V,A)，分離弱連通分量（跳過 |V|<3 或 |A|<3 的平凡分量）
        Step 1 : 估計平均最短路徑 avg_SP，決定分析層數 k_max = ⌊avg_SP/2⌋（Eq. 3–4）
                 計算每條弧在各層的鄰域重疊度 w(s→t, l)（Eq. 5–8）
        Step 2 : 生成 |RG| 個度序列保持的隨機有向網絡，導出 R1 外部門檻（Eq. 9）
        Step 3 : 五階段弧分類（Phase 1–5）
                 Phase 1 — SILK 識別
                 Phase 2 — BOND vs LOCAL_BRIDGE（R1 + R2 門檻，逐層精煉）
                 Phase 3 — GLOBAL_BRIDGE 收網
                 Phase 4 — 節點資訊熵與重要性（Eq. 10–11）
                 Phase 5 — 網絡指紋（四類弧比例向量）

    參數：
        path              : 有向網絡檔案路徑（.net / .gml / .graphml / .edgelist / .edges / .adjlist）
        times             : 隨機網絡數量 |RG|（預設 1000）
        quick             : 是否啟用快速模式（限制最大層數）
        separation        : 快速模式下的最大層數
        debug             : 是否在 console 輸出除錯訊息
        parallel          : 是否平行生成隨機網絡
        workers           : 平行 worker 數量（None=自動偵測）
        progress_callback : 進度回報函數 callback(current, total, message)

    回傳：List[LinkAnalysisResult]，每個弱連通分量一個結果。

    原始：HATA.py:212-391（link_analysis 函數）
    整體時間複雜度：O(|RG| × |A| × k_max)
    """
    root, ext = os.path.splitext(path)
    head, tail = os.path.split(root)

    if not (os.path.exists(path) and os.path.isfile(path)):
        raise FileNotFoundError(f"Network file not found: {path}")

    results = []

    # ---------------------------------------------------------------
    # Step 0: 讀取有向網絡 G = (V, A)
    # （對應論文 Algorithm 1, Line 1: Input G = (V, A)）
    # ---------------------------------------------------------------
    debugmsg('read and analyse the target directed network...', debug)
    G = _read_network(path)
    compNo = 0

    # 分離弱連通分量（有向圖使用 weakly connected components），
    # 按節點數降序處理，跳過過小的平凡分量（|V|<3 或 |A|<3）。
    for comp_nodes in sorted(nx.weakly_connected_components(G), key=len, reverse=True):
        g = G.subgraph(comp_nodes).copy()

        if g.order() < 3 or g.size() < 3:
            debugmsg(f'Skip a very tiny component: {g.order()} node(s) & {g.size()} edge(s)', debug)
            continue

        # ---------------------------------------------------------------
        # Step 1: 估計平均最短路徑 → 決定分析層數 k_max
        # （對應論文 Eq. 3–4: k_max = ⌊avg_SP / 2⌋）
        #
        # 有向圖不保證所有節點對都可達，因此以隨機抽樣法估計 avg_SP。
        # k_max 代表鄰域重疊度的最大分析深度：層數越多，越能區分
        # 近距橋接（local bridge）與遠距橋接（global bridge）。
        # ---------------------------------------------------------------
        avg_sp = average_shortest_path_length(g)
        g.graph[GRAPH_KEY_SHORTEST_PATH] = avg_sp
        g.name = compNo
        compNo += 1

        if quick:
            layers = max(1, int(min(avg_sp / 2.0, separation)))
        else:
            layers = max(1, int(math.floor(avg_sp / 2.0)))

        debugmsg(f'Component {compNo}, {g.order()} nodes, {g.size()} edges, '
                 f'avg. SP length = {avg_sp:.4f}, k_max = {layers}', debug)

        # ---------------------------------------------------------------
        # Step 1 (續): 計算每條弧在各層的鄰域重疊度 w(s→t, l)
        # （對應論文 Eq. 5–8 / Algorithm 1, Line 3–6）
        #
        # 時間複雜度：O(|A| × k_max × avg_degree)
        # 結果存放於 edge attribute: g[s][t][-l] = w(s→t, l)
        # ---------------------------------------------------------------
        compute_link_property(g, layers)

        t_start = time.time()

        if progress_callback:
            progress_callback(0, times, f"Component {compNo}: generating random networks...")

        # ---------------------------------------------------------------
        # Step 2: 生成 |RG| 個度序列保持的隨機有向網絡（null model）
        # （對應論文 Algorithm 1, Line 7–9 / Section 3.2）
        #
        # 目的：建立「隨機期望值」基線，用以區分 BOND 與 bridge。
        # 隨機網絡保留原始圖的入度/出度序列但破壞社群結構，
        # 因此其鄰域重疊度 w 的平均值代表「純粹由度序列產生的
        # 背景值」。真實網絡中 w 顯著高於此背景值的弧 → BOND。
        #
        # 快取機制：結果以 .pkl 檔案快取於 .hata_cache/ 目錄，
        # 避免重複分析時重新生成。
        # ---------------------------------------------------------------
        cache_dir = os.path.join(head, '.hata_cache') if head else '.hata_cache'
        os.makedirs(cache_dir, exist_ok=True)

        # Phase 1: 載入已快取的隨機網絡
        rgs = [None] * times
        uncached_tasks = []
        cached_count = 0

        for c in range(times):
            cp = os.path.join(cache_dir, f'{tail}_{compNo}_{c}.pkl')
            if os.path.exists(cp):
                debugmsg(f'read random network #{c} from cache...', debug)
                try:
                    with open(cp, 'rb') as f:
                        rgs[c] = pickle.load(f)
                    cached_count += 1
                except (pickle.UnpicklingError, EOFError, OSError, Exception):
                    debugmsg(f'cache file #{c} corrupted, will regenerate', debug)
                    uncached_tasks.append((c, cp))
            else:
                uncached_tasks.append((c, cp))

        if cached_count > 0:
            debugmsg(f'loaded {cached_count} random networks from cache', debug)
            if progress_callback:
                progress_callback(cached_count, times,
                    f"Component {compNo}: loaded {cached_count} from cache")

        # Phase 2: 生成未快取的隨機有向網絡
        if uncached_tasks:
            if parallel and len(uncached_tasks) > 1:
                # === 平行模式 ===
                cpu_count = os.cpu_count() or 4
                actual_workers = workers or max(1, cpu_count - 1)
                actual_workers = min(actual_workers, len(uncached_tasks))
                debugmsg(f'generating {len(uncached_tasks)} random networks '
                         f'in parallel ({actual_workers} workers)...', debug)

                # 建立輕量級圖形副本（只保留結構，去除 ego network 屬性）
                g_for_workers = nx.DiGraph()
                g_for_workers.add_nodes_from(g.nodes())
                g_for_workers.add_edges_from(g.edges())

                try:
                    mp_ctx = mp.get_context('spawn')
                except ValueError:
                    mp_ctx = None
                with ProcessPoolExecutor(max_workers=actual_workers,
                                         mp_context=mp_ctx) as executor:
                    future_to_idx = {}
                    for idx, cp in uncached_tasks:
                        future = executor.submit(
                            _generate_random_network, g_for_workers,
                            layers, cp)
                        future_to_idx[future] = idx

                    done_count = 0
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            rgs[idx] = future.result()
                        except Exception as e:
                            debugmsg(f'parallel worker error #{idx}: {e}, '
                                     f'falling back to serial...', debug)
                            cp = os.path.join(cache_dir,
                                f'{tail}_{compNo}_{idx}.pkl')
                            try:
                                rgs[idx] = _generate_random_network(
                                    g, layers, cp)
                            except Exception as e2:
                                debugmsg(f'serial fallback also failed #{idx}: {e2}', debug)
                                rgs[idx] = None

                        done_count += 1
                        if progress_callback:
                            progress_callback(
                                cached_count + done_count, times,
                                f"Component {compNo}: network "
                                f"{cached_count + done_count}/{times} "
                                f"(parallel, {actual_workers} workers)")

                t_elapsed = time.time() - t_start
                debugmsg(f'parallel generation done in {t_elapsed:.2f}s '
                         f'({actual_workers} workers)', debug)
            else:
                # === 序列模式 ===
                for i, (idx, cp) in enumerate(uncached_tasks):
                    debugmsg(f'create and analyse random network #{idx}...',
                             debug)
                    rgs[idx] = _generate_random_network(g, layers, cp)

                    if progress_callback:
                        progress_callback(
                            cached_count + i + 1, times,
                            f"Component {compNo}: random network "
                            f"{cached_count + i + 1}/{times}")

                    debugmsg(f'+--- * Time spent: '
                             f'{time.time() - t_start:.4f}s', debug)
                    t_start = time.time()

        rgs = [r for r in rgs if r is not None]
        actual_times = len(rgs)
        if actual_times == 0:
            raise RuntimeError(
                f"Component {compNo}: all random network generations failed, "
                f"cannot compute thresholds"
            )

        # ---------------------------------------------------------------
        # Step 2 (續): 計算 R1 外部門檻
        # （對應論文 Eq. 9 / Algorithm 1, Line 10–12）
        #
        # R1(l) = mean_over_RG{ avg_w(l) } + mean_over_RG{ std_w(l) }
        #
        # 直覺：R1 是「隨機網絡中預期的鄰域重疊度上界」。
        # 真實弧的 w(s→t, l) ≥ R1(l) → 該弧的重疊度顯著高於隨機期望
        # → 判定為 BOND（弧兩端有足夠的替代路徑支撐）。
        #
        # 注意：HATA 使用 mean + mean（而非 HETA 的 mean + 2σ），
        #        因為有向圖的 w 分佈通常比無向圖更偏斜。
        # R1 上界限制為 1.0（正規化後的最大值）。
        # ---------------------------------------------------------------
        debugmsg('generate a threshold for BOND/bridge link analysis...', debug)
        thresholds_r1 = {}
        thresholds_r2 = {}
        for i in range(layers):
            l = str(i + 1)
            # 收集所有隨機網絡在第 l 層的 avg(w) 與 std(w)
            g.graph[GRAPH_KEY_AVG_LIST + l] = []
            g.graph[GRAPH_KEY_STD_LIST + l] = []
            for j in range(actual_times):
                g.graph[GRAPH_KEY_AVG_LIST + l].append(rgs[j]['graph'][GRAPH_KEY_AVG_COMMON_NODES + l])
                g.graph[GRAPH_KEY_STD_LIST + l].append(rgs[j]['graph'][GRAPH_KEY_STD_COMMON_NODES + l])
            # R1(l) = E[avg] + E[std]
            g.graph[GRAPH_KEY_THRESHOLD_R1 + l] = (
                np.mean(g.graph[GRAPH_KEY_AVG_LIST + l]) +
                np.mean(g.graph[GRAPH_KEY_STD_LIST + l])
            )
            if g.graph[GRAPH_KEY_THRESHOLD_R1 + l] > 1:
                g.graph[GRAPH_KEY_THRESHOLD_R1 + l] = 1.0
            thresholds_r1[l] = g.graph[GRAPH_KEY_THRESHOLD_R1 + l]

        # ===============================================================
        # Step 3: 五階段弧分類
        # （對應論文 Algorithm 1, Line 13–30 / Figure 2 流程圖右半部）
        #
        # 每條弧攜帶一個 EDGE_KEY_NEXT_STEP 狀態旗標：
        #   PASS = 尚未確定類型，繼續下一層判斷
        #   STOP = 類型已確定，後續層直接繼承
        #
        # 分類順序嚴格遵循：SILK → BOND → LOCAL_BRIDGE → GLOBAL_BRIDGE
        # ===============================================================
        debugmsg('assess the arc property of every edge...', debug)

        # --- Phase 1: SILK 識別 ---
        # （對應論文 Definition 6 / Algorithm 1, Line 13–16）
        #
        # 判定準則：弧 s→t 的任一端點之全域分支度（in+out）= 1
        # → 該端點僅有此一條弧，移除後即成孤立節點 → SILK
        #
        # SILK 弧不參與後續 BOND/bridge 判定（標記 STOP），
        # 其分類結果記錄在 layer '0'（零層，意即無需進入逐層分析）。
        # 時間複雜度：O(|A|)
        g.graph[SILK] = 0
        g.graph[BOND] = 0
        g.graph[LOCAL_BRIDGE] = 0
        g.graph[GLOBAL_BRIDGE] = 0

        for s, t in g.edges():
            if (g.degree(s) == 1) or (g.degree(t) == 1):
                g[s][t][EDGE_KEY_LAYER + '0'] = SILK
                g[s][t][EDGE_KEY_NEXT_STEP] = STOP
                g[s][t][EDGE_KEY_WIDTH] = SILK_BASIC_WIDTH
                g[s][t][EDGE_KEY_COLOR] = SILK_COLOR
                g.graph[SILK] += 1
            else:
                g[s][t][EDGE_KEY_NEXT_STEP] = PASS  # 待後續判定

        # --- Phase 2: BOND vs LOCAL_BRIDGE — 逐層精煉分類 ---
        # （對應論文 Algorithm 1, Line 17–26 / Figure 2 中央迴圈）
        #
        # 對每一層 l = 1, 2, ..., k_max 依序執行：
        #
        # Phase 2a（外部門檻 R1）：
        #   若 w(s→t, l) ≥ R1(l) → BOND（該弧在第 l 層有足夠的替代路徑）
        #   標記 STOP，後續層不再重新判定。
        #   否則 → 暫時歸為 LOCAL_BRIDGE 候選。
        #
        # Phase 2b（內部門檻 R2）：
        #   R2(l) = mean(候選弧的 w) - std(候選弧的 w)
        #   若候選弧的 w(s→t, l) > R2(l) → 確認為 LOCAL_BRIDGE
        #   標記 STOP。否則保持 PASS，繼續下一層判定。
        #
        #   直覺：R2 從候選弧中「撈回」那些重疊度相對較高者，
        #   確認其為區域橋接而非全域橋接。
        #
        # 時間複雜度：O(|A| × k_max)
        n = '1'
        for i in range(layers):
            l = -(i + 1)   # edge attribute 中的 key（-1, -2, ...）
            n = str(i + 1)  # 層號字串（'1', '2', ...）
            g.graph[GRAPH_KEY_PASS_TO_NEXT_LAYER + n] = []  # 收集候選弧的 w 值

            # Phase 2a: 以 R1 外部門檻區分 BOND vs 候選 bridge
            for s, t in g.edges():
                if g[s][t][EDGE_KEY_NEXT_STEP] == STOP:
                    # 已確定類型 → 繼承前一層的分類結果
                    g[s][t][EDGE_KEY_LAYER + n] = g[s][t][EDGE_KEY_LAYER + str(i)]
                elif g[s][t][l] >= g.graph[GRAPH_KEY_THRESHOLD_R1 + n]:
                    # w ≥ R1 → BOND（替代路徑充足）
                    g[s][t][EDGE_KEY_LAYER + n] = BOND
                    g[s][t][EDGE_KEY_NEXT_STEP] = STOP
                    g[s][t][EDGE_KEY_WIDTH] = (layers - i + 1) * BOND_BASIC_WIDTH
                    g[s][t][EDGE_KEY_COLOR] = BOND_COLOR
                    g.graph[BOND] += 1
                else:
                    # w < R1 → 暫歸為 LOCAL_BRIDGE 候選
                    g[s][t][EDGE_KEY_LAYER + n] = LOCAL_BRIDGE + ' of layer ' + n
                    g[s][t][EDGE_KEY_WIDTH] = (layers - i + 1) * BRIDGE_BASIC_WIDTH
                    g[s][t][EDGE_KEY_COLOR] = LOCAL_BRIDGE_COLOR
                    g.graph[GRAPH_KEY_PASS_TO_NEXT_LAYER + n].append(g[s][t][l])

            # Phase 2b: 以 R2 內部門檻從候選弧中確認 LOCAL_BRIDGE
            if len(g.graph[GRAPH_KEY_PASS_TO_NEXT_LAYER + n]) == 0:
                g.graph[GRAPH_KEY_THRESHOLD_R2 + n] = 0
            else:
                # R2(l) = mean(候選 w) - std(候選 w)，下界為 0
                g.graph[GRAPH_KEY_THRESHOLD_R2 + n] = (
                    np.mean(g.graph[GRAPH_KEY_PASS_TO_NEXT_LAYER + n]) -
                    np.std(g.graph[GRAPH_KEY_PASS_TO_NEXT_LAYER + n])
                )
                if g.graph[GRAPH_KEY_THRESHOLD_R2 + n] < 0:
                    g.graph[GRAPH_KEY_THRESHOLD_R2 + n] = 0.0
                # 候選弧中 w > R2 者 → 確認為 LOCAL_BRIDGE，標記 STOP
                for s, t in g.edges():
                    if g[s][t][EDGE_KEY_NEXT_STEP] == PASS:
                        if g[s][t][l] > g.graph[GRAPH_KEY_THRESHOLD_R2 + n]:
                            g[s][t][EDGE_KEY_NEXT_STEP] = STOP
                            g.graph[LOCAL_BRIDGE] += 1

            thresholds_r2[n] = g.graph[GRAPH_KEY_THRESHOLD_R2 + n]

        # --- Phase 3: GLOBAL_BRIDGE 收網 ---
        # （對應論文 Definition 8 / Algorithm 1, Line 27–29）
        #
        # 經過所有層的 R1 + R2 篩選後，仍標記為 PASS 的弧
        # 代表「在任何層級都找不到足夠的替代路徑」→ GLOBAL_BRIDGE。
        # 這些弧是網絡中最脆弱的長程連結。
        # 時間複雜度：O(|A|)
        for s, t in g.edges():
            if g[s][t][EDGE_KEY_NEXT_STEP] == PASS:
                g[s][t][EDGE_KEY_LAYER + n] = GLOBAL_BRIDGE
                g[s][t][EDGE_KEY_WIDTH] = BRIDGE_BASIC_WIDTH
                g[s][t][EDGE_KEY_COLOR] = GLOBAL_BRIDGE_COLOR
                g.graph[GLOBAL_BRIDGE] += 1

        # --- Phase 4: 節點結構資訊熵與重要性量化 ---
        # （對應論文 Eq. 10–11 / Section 3.3）
        #
        # 核心概念：
        #   H(G) = 全域弧類型分佈的 Shannon 熵（衡量網絡整體的結構多樣性）
        #   H(G\s) = 移除節點 s 所有相鄰弧後的弧類型分佈熵
        #   IG(s) = H(G) - H(G\s) = 節點 s 的 information gain
        #
        # IG(s) 越高 → s 的鄰弧類型分佈與全域分佈差異越大
        # → s 在結構上越「特殊」（例如橋接節點）。
        #
        # 實作方式：
        #   1. 以全域計數 {BOND:n₁, LB:n₂, GB:n₃} 為基底
        #   2. 對每個節點 s，扣除 s 所有相鄰弧的類型計數
        #   3. 以扣除後的計數計算 H(G\s)，再求 IG(s) = H(G) - H(G\s)
        #
        # 注意：SILK 弧不納入此計算（SILK 是端點結構特徵，非橋接類型）。
        #
        # 有向圖特殊處理：同一對節點可能同時存在 s→t 與 t→s（互惠邊），
        # 必須分別檢查兩個方向，避免 set 去重後只處理到一個方向。
        ns = []
        nc = []
        g.graph[GRAPH_KEY_EDGE_CLASS] = {
            BOND: g.graph[BOND],
            LOCAL_BRIDGE: g.graph[LOCAL_BRIDGE],
            GLOBAL_BRIDGE: g.graph[GLOBAL_BRIDGE],
        }
        g.graph[GRAPH_KEY_ENTROPY] = entropy(list(g.graph[GRAPH_KEY_EDGE_CLASS].values()))

        for s in g.nodes():
            # 以全域計數為基底，逐一扣除 s 的鄰弧
            g.nodes[s][NODE_KEY_EDGE_CLASS] = g.graph[GRAPH_KEY_EDGE_CLASS].copy()
            all_neighbors = set(g.successors(s)) | set(g.predecessors(s))
            for t in all_neighbors:
                # 出向弧 s→t
                if g.has_edge(s, t):
                    edge_data = g[s][t]
                    for key in list(g.nodes[s][NODE_KEY_EDGE_CLASS].keys()):
                        if edge_data[EDGE_KEY_LAYER + str(layers)].startswith(key):
                            g.nodes[s][NODE_KEY_EDGE_CLASS][key] -= 1
                # 入向弧 t→s（互惠邊時兩個方向都要處理）
                if g.has_edge(t, s):
                    edge_data = g[t][s]
                    for key in list(g.nodes[s][NODE_KEY_EDGE_CLASS].keys()):
                        if edge_data[EDGE_KEY_LAYER + str(layers)].startswith(key):
                            g.nodes[s][NODE_KEY_EDGE_CLASS][key] -= 1
            # H(G\s) 與 IG(s)
            g.nodes[s][NODE_KEY_NEW_ENTROPY] = entropy(list(g.nodes[s][NODE_KEY_EDGE_CLASS].values()))
            g.nodes[s][NODE_KEY_INFORMATION_GAIN] = max(0, g.graph[GRAPH_KEY_ENTROPY] - g.nodes[s][NODE_KEY_NEW_ENTROPY])
            ns.append(g.nodes[s][NODE_KEY_INFORMATION_GAIN])
            # 依 IG(s) 大小決定節點顏色（用於視覺化）
            _node_colors = [REGULAR_NODE_COLOR, IMPORTANT_NODE_COLOR, SUPER_NODE_COLOR]
            _color_idx = max(0, min(len(_node_colors) - 1,
                                    int(math.ceil(g.nodes[s][NODE_KEY_INFORMATION_GAIN]))))
            nc.append(_node_colors[_color_idx])

        # 節點大小依 IG(s) 正規化（以平均值為基準縮放）
        ns_avg = np.mean(ns)
        if ns_avg != 0:
            ns = [NODE_SIZE_BASE + NODE_SIZE * (value / ns_avg) for value in ns]
        else:
            ns = [NODE_SIZE_BASE] * len(ns)

        # --- Phase 5: 網絡指紋 ---
        # （對應論文 Section 4.1 / Figure 3）
        #
        # 將四類弧的計數轉換為比例向量 [BOND%, LB%, GB%, SILK%]，
        # 此向量即為該網絡的「指紋」。不同網絡的指紋可透過 Pearson
        # 相關係數進行比較，藉此揭示網絡之間的結構相似性。
        d = float(g.graph[BOND] + g.graph[LOCAL_BRIDGE] + g.graph[GLOBAL_BRIDGE] + g.graph[SILK])
        if d == 0:
            fingerprint = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
        else:
            fingerprint = {
                0: round(g.graph[BOND] / d, 4),          # BOND 比例
                1: round(g.graph[LOCAL_BRIDGE] / d, 4),   # LOCAL_BRIDGE 比例
                2: round(g.graph[GLOBAL_BRIDGE] / d, 4),  # GLOBAL_BRIDGE 比例
                3: round(g.graph[SILK] / d, 4),            # SILK 比例
            }

        # ---------------------------------------------------------------
        # Step 4: 統計量計算與結果封裝
        # （對應論文 Table 1 的網絡特徵統計）
        #
        # 計算並儲存該分量的全域拓撲特徵，包括：
        #   - 直徑（最長最短路徑）
        #   - 平均聚類係數（局部三角結構密度）
        #   - 度關聯性（同/異配性）
        #   - 弧類型分佈熵 H(G)
        # 這些統計量與指紋一起寫入 JSON 快取檔案，
        # 供後續批次實驗（Suite Experiment）比較使用。
        # ---------------------------------------------------------------
        diameter = _safe_diameter(g)
        clustering_coeff = round(nx.average_clustering(g), 4)

        # 將指紋與統計量持久化至 network_fingerprints.json
        _save_fingerprint(root + '_' + str(compNo), fingerprint, stats={
            'nodes': g.number_of_nodes(),
            'edges': g.number_of_edges(),
            'avg_in_degree': round(sum(d for _, d in g.in_degree()) / g.number_of_nodes(), 4),
            'avg_out_degree': round(sum(d for _, d in g.out_degree()) / g.number_of_nodes(), 4),
            'diameter': diameter,
            'avg_shortest_path': round(avg_sp, 4),
            'avg_clustering_coeff': clustering_coeff,
            'degree_assortativity': round(_safe_degree_assortativity(g), 4),
            'entropy': round(g.graph[GRAPH_KEY_ENTROPY], 4),
        })

        # 計算視覺化佈局：
        # 先以 Kamada-Kawai（基於圖論距離的能量最小化）產生初始位置，
        # 再以 Spring Layout（Fruchterman-Reingold 力導引）微調，
        # 兼顧全域結構和局部均勻性。
        pos = nx.spring_layout(g, pos=nx.kamada_kawai_layout(g))

        # 收集所有隨機網絡的逐層統計（avg_w, std_w），
        # 供 GUI 或報告中展示 null model 的分佈特徵。
        rn_stats = []
        for j in range(actual_times):
            stat = {}
            for i in range(layers):
                l = str(i + 1)
                stat[GRAPH_KEY_AVG_COMMON_NODES + l] = rgs[j]['graph'][GRAPH_KEY_AVG_COMMON_NODES + l]
                stat[GRAPH_KEY_STD_COMMON_NODES + l] = rgs[j]['graph'][GRAPH_KEY_STD_COMMON_NODES + l]
            rn_stats.append(stat)

        # 封裝所有分析結果至 LinkAnalysisResult dataclass，
        # 包含：圖物件、拓撲統計、弧計數、門檻值、節點視覺屬性、
        # 隨機網絡統計、指紋、佈局座標、原始檔案路徑。
        result = LinkAnalysisResult(
            graph=g,
            component_id=compNo,
            network_name=tail,
            num_nodes=g.number_of_nodes(),
            num_edges=g.number_of_edges(),
            avg_in_degree=round(sum(d for _, d in g.in_degree()) / g.number_of_nodes(), 4),
            avg_out_degree=round(sum(d for _, d in g.out_degree()) / g.number_of_nodes(), 4),
            diameter=diameter,
            avg_shortest_path=round(avg_sp, 4),
            avg_clustering_coeff=clustering_coeff,
            degree_assortativity=round(_safe_degree_assortativity(g), 4),
            bond_count=g.graph[BOND],
            silk_count=g.graph[SILK],
            local_bridge_count=g.graph[LOCAL_BRIDGE],
            global_bridge_count=g.graph[GLOBAL_BRIDGE],
            graph_entropy=g.graph[GRAPH_KEY_ENTROPY],
            layers=layers,
            thresholds_r1=thresholds_r1,
            thresholds_r2=thresholds_r2,
            node_sizes=ns,
            node_colors=nc,
            node_info_avg=float(ns_avg),
            random_network_stats=rn_stats,
            fingerprint=fingerprint,
            pos=pos,
            path=path,
        )
        results.append(result)

    return results


# ===================================================================
# 指紋持久化與批次實驗
# （對應論文 Section 4.1–4.2 / Figure 3–5）
#
# 每個分析完成的網絡會將其指紋（4-element 比例向量）持久化至
# network_fingerprints.json。批次實驗（Suite Experiment）則從此
# 檔案載入多個網絡的指紋，計算 Pearson 相關矩陣並進行階層聚類，
# 藉此揭示不同網絡之間的結構相似性。
# ===================================================================


def _save_fingerprint(network_name, fingerprint, stats=None):
    """
    儲存網絡指紋與基本統計量到 JSON 快取。
    （對應論文 Section 4.1 — 指紋向量定義與儲存）

    此函數在每次單一網絡分析完成後被呼叫，負責：
    1. 讀取現有的 JSON 快取（若存在）
    2. 新增/更新該網絡的指紋與統計量
    3. 重新計算所有已知網絡之間的 Pearson 相關係數矩陣
    4. 寫回 JSON 快取

    JSON 結構：
      {
        "finger_prints": { "network_name": {"0": bond%, "1": lb%, "2": gb%, "3": silk%} },
        "corr_table":    { "net1": { "net2": pearson_r } },
        "network_stats": { "network_name": { nodes, edges, diameter, ... } }
      }

    指紋向量的 key 對應：
      "0" → BOND 比例, "1" → LOCAL_BRIDGE 比例,
      "2" → GLOBAL_BRIDGE 比例, "3" → SILK 比例

    相關係數計算：
      對每一對網絡 (A, B)，以其 4-element 指紋向量計算 Pearson r。
      r ≈ 1 代表兩網絡的弧類型分佈高度相似（結構近似）；
      r ≈ 0 代表無線性關聯；r < 0 代表互補型結構。

    參數:
        network_name: 網絡識別名稱（通常為 "filename_componentId"）
        fingerprint:  {0: bond%, 1: lb%, 2: gb%, 3: silk%} 指紋字典
        stats:        可選的拓撲統計量字典（nodes, edges, diameter, ...）
    """
    fp_path = 'network_fingerprints.json'
    finger_prints = {}
    corr_table = {}
    network_stats = {}

    # 載入現有快取（增量更新模式：保留先前分析的其他網絡資料）
    if os.path.exists(fp_path):
        try:
            import json
            with open(fp_path, 'r') as f:
                data = json.load(f)
                finger_prints = data.get('finger_prints', {})
                network_stats = data.get('network_stats', {})
        except (json.JSONDecodeError, KeyError):
            pass

    # 新增/更新當前網絡的指紋（key 統一轉為字串以相容 JSON）
    finger_prints[network_name] = {str(k): v for k, v in fingerprint.items()}

    if stats:
        network_stats[network_name] = stats

    # 重建全量 Pearson 相關矩陣（O(N²)，N = 已知網絡數量）
    # 每次新增網絡後都須重算，因為新網絡與所有既有網絡的相關都需更新。
    for net_name1, net_series1 in finger_prints.items():
        corr_table[net_name1] = {}
        vals1 = list(net_series1.values())
        for net_name2, net_series2 in finger_prints.items():
            vals2 = list(net_series2.values())
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                c = np.corrcoef(vals1, vals2)[0, 1]
            # NaN 處理：當某網絡指紋為全零向量時 corrcoef 產生 NaN
            corr_table[net_name1][net_name2] = 0.0 if np.isnan(c) else float(c)

    # 寫回 JSON（OSError 靜默處理：唯讀檔案系統或權限不足時不中斷分析）
    import json
    try:
        with open(fp_path, 'w') as f:
            json.dump({
                'finger_prints': finger_prints,
                'corr_table': corr_table,
                'network_stats': network_stats,
            }, f, indent=2)
    except OSError:
        pass


def _load_fingerprints():
    """
    載入已儲存的網絡指紋、相關矩陣與統計量。

    從 network_fingerprints.json 讀取由 _save_fingerprint() 累積的
    所有網絡分析結果。此函數被 run_suite_experiment() 呼叫，用於
    批次實驗中的跨網絡比較。

    回傳:
        (finger_prints, corr_table, network_stats) 三元組：
        - finger_prints: {name: {0: bond%, 1: lb%, 2: gb%, 3: silk%}}
        - corr_table:    {name1: {name2: pearson_r}}
        - network_stats: {name: {nodes, edges, diameter, ...}}
        若檔案不存在或解析失敗，回傳三個空字典。
    """
    fp_path = 'network_fingerprints.json'
    if os.path.exists(fp_path):
        import json
        try:
            with open(fp_path, 'r') as f:
                data = json.load(f)
            return (data.get('finger_prints', {}),
                    data.get('corr_table', {}),
                    data.get('network_stats', {}))
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return {}, {}, {}


def run_suite_experiment(
    suite='DEMO',
    data_dir='.',
    run_analysis=False,
    times=1000,
    debug=False,
    progress_callback=None,
):
    """
    批次實驗：對一組有向網絡執行 HATA 分析並進行跨網絡指紋比較。
    （對應論文 Section 4 — Experiments / Figure 3–5）

    此函數實現論文中「不同網絡的結構指紋比較」流程：
      1. 對套件中的每個網絡依序執行 run_link_analysis()（可選）
      2. 從 JSON 快取載入所有已分析網絡的指紋
      3. 建構指紋堆疊長條圖所需的資料結構
      4. 計算 Pearson 相關矩陣
      5. 以階層聚類（centroid method）重排矩陣，揭示結構相似群組

    論文 Figure 3：指紋堆疊長條圖 — 直觀顯示各網絡的弧類型組成
    論文 Figure 4：相關矩陣熱力圖 — 量化網絡間的結構相似度
    論文 Figure 5：樹狀圖         — 以階層聚類展示網絡群組關係

    參數:
        suite:    套件名稱（目前支援 'DEMO'），對應 constants.SUITE_DATASETS
        data_dir: 網絡檔案所在目錄（.net Pajek 格式）
        run_analysis: True = 先對所有網絡執行完整分析（耗時），
                      False = 僅讀取已存在的指紋結果
        times:    每個網絡的隨機網絡生成數量（null model 樣本數）
        debug:    是否輸出除錯訊息
        progress_callback: 進度回報函數 (current, total, message)

    回傳:
        SuiteExperimentResult dataclass，包含指紋、相關矩陣、
        聚類排序等，供 GUI 繪圖函數直接使用。
    """
    dataset = SUITE_DATASETS.get(suite, SUITE_DATASETS['DEMO'])
    total = len(dataset)

    # Phase 1: 依序對套件中每個網絡執行完整 HATA 分析（可選）
    # 每次分析完成後，run_link_analysis 內部會自動呼叫
    # _save_fingerprint() 將結果寫入 JSON 快取。
    if run_analysis:
        for idx, data_file in enumerate(dataset):
            file_path = os.path.join(data_dir, data_file)

            if progress_callback:
                progress_callback(idx, total, f"Processing {data_file}...")

            print(f"Processing {data_file}...")
            run_link_analysis(
                path=file_path,
                times=times,
                debug=debug,
                progress_callback=None,
            )

        if progress_callback:
            progress_callback(total, total, "Analysis complete.")

    # Phase 2: 載入指紋資料
    # 從 network_fingerprints.json 讀取所有已分析網絡的指紋與相關矩陣。
    finger_prints, corr_table, network_stats = _load_fingerprints()

    if not finger_prints:
        return SuiteExperimentResult()

    # Phase 3: 建構指紋堆疊長條圖資料
    # （對應論文 Figure 3）
    # 對套件中每個網絡，從快取中擷取其指紋向量，
    # 分解為四個類型的比例陣列。
    #
    # 命名約定：快取中的 key 為 "filename_componentId"（例如 "leader_1"），
    # 因此需要將資料檔名去掉 .net 副檔名後加上 "_1"。
    # 若直接比對失敗，則以後綴匹配方式搜尋（容許路徑前綴差異）。
    bar = {SILK: [], GLOBAL_BRIDGE: [], LOCAL_BRIDGE: [], BOND: []}
    labels = []

    for net_name in dataset:
        # 嘗試以 "filename_1" 為 key 查詢（取第一個弱連通分量）
        name_key = net_name[:-4] + '_1'
        if name_key not in finger_prints:
            # 後綴匹配：快取 key 可能帶有完整路徑前綴
            found = False
            for fp_key in finger_prints:
                if fp_key.endswith(net_name[:-4] + '_1'):
                    name_key = fp_key
                    found = True
                    break
            if not found:
                continue

        net_series = finger_prints[name_key]
        labels.append(net_name[:-4])
        # 指紋向量 key 可能是字串 '0' 或整數 0（相容兩種格式）
        bar[BOND].append(float(net_series.get('0', net_series.get(0, 0))))
        bar[LOCAL_BRIDGE].append(float(net_series.get('1', net_series.get(1, 0))))
        bar[GLOBAL_BRIDGE].append(float(net_series.get('2', net_series.get(2, 0))))
        bar[SILK].append(float(net_series.get('3', net_series.get(3, 0))))

    if not labels:
        return SuiteExperimentResult()

    # 轉換為 numpy 陣列（供 matplotlib stacked bar chart 使用）
    bar[BOND] = np.array(bar[BOND])
    bar[LOCAL_BRIDGE] = np.array(bar[LOCAL_BRIDGE])
    bar[GLOBAL_BRIDGE] = np.array(bar[GLOBAL_BRIDGE])
    bar[SILK] = np.array(bar[SILK])

    # 單一網絡無法計算相關矩陣，直接回傳
    if len(labels) < 2:
        return SuiteExperimentResult(
            fingerprints=finger_prints,
            corr_table=corr_table,
            labels=labels,
            bar_data=bar,
            corr_matrix=np.array([[1.0]]),
            corr_index=[0],
            corr_labels=labels[:],
            network_stats=network_stats,
        )

    # Phase 4: 建構相關矩陣
    # （對應論文 Figure 4 — Pearson 相關係數熱力圖）
    #
    # 從 corr_table（由 _save_fingerprint 預先計算）中擷取
    # 套件內所有網絡對的相關係數，組成 N×N 矩陣。
    corr_matrix_list = []
    for net_name1 in labels:
        row = []
        key1 = net_name1 + '_1'
        actual_key1 = _find_fingerprint_key(corr_table, key1)
        for net_name2 in labels:
            key2 = net_name2 + '_1'
            actual_key2 = _find_fingerprint_key(
                corr_table.get(actual_key1, {}) if actual_key1 else {}, key2)
            if actual_key1 and actual_key2:
                row.append(corr_table[actual_key1][actual_key2])
            else:
                row.append(0.0)
        corr_matrix_list.append(row)

    # Phase 5: 階層聚類與矩陣重排
    # （對應論文 Figure 5 — 樹狀圖 / Section 4.2 聚類分析）
    #
    # 步驟：
    #   1. 相關矩陣 → 距離矩陣：d(A,B) = 1 - r(A,B)
    #   2. 對稱化距離矩陣（消除浮點誤差）
    #   3. 壓縮為上三角形式（scipy squareform）
    #   4. 以 centroid 方法執行階層聚類
    #   5. 依聚類結果的葉節點順序重排相關矩陣
    #
    # centroid 方法：合併兩群時，以兩群重心的距離為合併依據，
    # 適合處理大小不均的群組（論文選用此方法）。
    from scipy.spatial.distance import squareform
    dist_matrix = np.array([[1.0 - corr_matrix_list[i][j] for j in range(len(labels))]
                            for i in range(len(labels))])
    # 對稱化：確保 d(A,B) == d(B,A)（消除浮點運算不對稱誤差）
    dist_matrix = (dist_matrix + dist_matrix.T) / 2
    np.fill_diagonal(dist_matrix, 0)
    # 轉為 condensed form（上三角一維陣列），供 scipy linkage 使用
    dist_condensed = squareform(dist_matrix)
    # 執行階層聚類（no_plot=True：僅計算，不繪圖）
    corr_cluster = hc.dendrogram(hc.linkage(dist_condensed, method='centroid'), no_plot=True)
    corr_index = corr_cluster['leaves']  # 聚類後的葉節點排列順序

    # 以聚類順序重排相關矩陣（使結構相似的網絡相鄰排列）
    corr_result = np.zeros([len(labels), len(labels)])
    for i in range(len(labels)):
        for j in range(len(labels)):
            corr_result[i, j] = corr_matrix_list[i][j]
    corr_result = corr_result[corr_index, :]   # 行重排
    corr_result = corr_result[:, corr_index]    # 列重排
    corr_labels = [labels[i] for i in corr_index]  # 對應的標籤順序

    return SuiteExperimentResult(
        fingerprints=finger_prints,
        corr_table=corr_table,
        labels=labels,
        bar_data=bar,
        corr_matrix=corr_result,
        corr_index=corr_index,
        corr_labels=corr_labels,
        network_stats=network_stats,
    )


def _find_fingerprint_key(d, suffix):
    """
    在字典 d 中搜尋以 suffix 結尾的 key。

    用於處理指紋快取中 key 帶有路徑前綴的情況。
    例如：suffix = "leader_1"，但快取中的 key 可能是
    "/data/networks/leader_1"。

    參數:
        d:      待搜尋的字典
        suffix: 目標後綴字串

    回傳:
        匹配的完整 key，或 None（找不到時）
    """
    if suffix in d:
        return suffix
    for k in d:
        if k.endswith(suffix):
            return k
    return None
