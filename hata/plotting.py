# -*- coding: utf-8 -*-
"""
繪圖模組：使用 matplotlib 物件導向 API，每個函數回傳 Figure 物件

有向圖版本：使用 arrows=True 繪製有向弧，SILK 取代 SINK。
所有函數使用 Figure() 而非 plt.figure()，確保執行緒安全且可嵌入 GUI。
"""

import numpy as np
import networkx as nx
import scipy.cluster.hierarchy as hc
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from hata.constants import *
from hata.engine import network_clustering


def create_network_figure(result):
    """
    繪製目標有向網絡的連結分類結果
    """
    g = result.graph
    pos = result.pos

    fig = Figure(figsize=(6, 6), dpi=200, facecolor='white')
    ax = fig.add_subplot(111)

    bb_width = [g[s][t][EDGE_KEY_WIDTH] for (s, t) in g.edges()]
    bb_color = [g[s][t][EDGE_KEY_COLOR] for (s, t) in g.edges()]
    nc = result.node_colors
    ns = result.node_sizes

    ax.set_title(f'target network = {result.network_name}')
    ax.axis('off')

    node_label_switch = result.num_nodes < 50
    real_node_size = ns if node_label_switch else [max(1, int(300.0 / result.num_nodes))] * result.num_nodes

    nx.draw_networkx(g, pos=pos, linewidths=0, width=bb_width,
                     node_size=real_node_size, node_color=nc, font_size=6,
                     edge_color=bb_color, arrows=True, arrowsize=10,
                     with_labels=node_label_switch, ax=ax)

    # 邊類型圖例
    legend_items = [
        Line2D([0], [0], color=BOND_COLOR, lw=2, label=BOND),
        Line2D([0], [0], color=LOCAL_BRIDGE_COLOR, lw=2, label=LOCAL_BRIDGE),
        Line2D([0], [0], color=GLOBAL_BRIDGE_COLOR, lw=2, label=GLOBAL_BRIDGE),
        Line2D([0], [0], color=SILK_COLOR, lw=2, label=SILK),
    ]
    ax.legend(handles=legend_items, loc='lower center', ncol=4,
              fontsize=7, framealpha=0.8, fancybox=True)

    fig.set_tight_layout(True)
    return fig


def create_detail_layer_figure(result, layer_num):
    """
    繪製特定層級的詳細分析圖（含邊權重標籤）
    """
    g = result.graph
    pos = result.pos

    sub_edge_label = {}
    for s, t in g.edges():
        sub_edge_label[(s, t)] = round(g[s][t][-layer_num], 3)

    bb_width = [g[s][t][EDGE_KEY_WIDTH] for (s, t) in g.edges()]
    bb_color = [g[s][t][EDGE_KEY_COLOR] for (s, t) in g.edges()]

    fig = Figure(figsize=(12, 8), facecolor='white')
    ax = fig.add_subplot(111)

    r1 = round(result.thresholds_r1.get(str(layer_num), 0), 4)
    r2 = round(result.thresholds_r2.get(str(layer_num), 0), 4)
    ax.set_title(f'target network = {result.network_name} (layer {layer_num}, R1 = {r1}, R2 = {r2})')

    node_label_switch = result.num_nodes < 50
    real_node_size = result.node_sizes if node_label_switch else [max(1, int(300.0 / result.num_nodes))] * result.num_nodes

    nx.draw_networkx(g, pos=pos, linewidths=0, width=bb_width,
                     node_size=real_node_size, node_color=result.node_colors,
                     font_size=6, edge_color=bb_color,
                     arrows=True, arrowsize=8,
                     with_labels=node_label_switch, ax=ax)
    nx.draw_networkx_edge_labels(g, pos=pos, edge_labels=sub_edge_label,
                                 font_size=5, ax=ax)

    fig.set_tight_layout(True)
    return fig


def create_betweenness_figure(result):
    """
    繪製邊介數中心性圖（有向圖版本）
    """
    g = result.graph
    pos = result.pos

    eb = nx.edge_betweenness_centrality(g)
    for key in list(eb.keys()):
        eb[key] = round(eb[key], 3)

    eb_values = [eb.get((s, t), 0) for s, t in g.edges()]
    min_eb = min(eb_values) if eb_values else 0
    std_eb = np.std(eb_values) if eb_values else 1.0
    if std_eb == 0:
        std_eb = 1.0

    bn_width = [0.5 + ((eb.get((s, t), 0) - min_eb) / std_eb) for (s, t) in g.edges()]

    fig = Figure(figsize=(12, 8), facecolor='white')
    ax = fig.add_subplot(111)
    ax.set_title(f'Target network = {result.network_name} (betweenness centrality for arcs)')

    node_label_switch = result.num_nodes < 50
    real_node_size = result.node_sizes if node_label_switch else [max(1, int(300.0 / result.num_nodes))] * result.num_nodes

    nx.draw_networkx(g, pos=pos, linewidths=0, width=bn_width,
                     node_size=real_node_size, node_color=result.node_colors,
                     font_size=6, arrows=True, arrowsize=8,
                     with_labels=node_label_switch, ax=ax)
    eb_labels = {(s, t): eb.get((s, t), 0) for s, t in g.edges()}
    nx.draw_networkx_edge_labels(g, pos=pos, edge_labels=eb_labels, font_size=5, ax=ax)

    fig.set_tight_layout(True)
    return fig


def create_pagerank_figure(result):
    """
    繪製 PageRank 權重圖（有向圖版本）

    直接在有向圖上計算 PageRank，而非像 HETA 那樣先建立 line graph。
    有向圖的 PageRank 直接反映節點的重要性。
    以每條弧的 source 和 target 的 PageRank 平均值作為弧的權重。
    """
    g = result.graph
    pos = result.pos

    try:
        pr = nx.pagerank(g, max_iter=2000)
    except nx.PowerIterationFailedConvergence:
        pr = {key: 1.0 / len(g) for key in g.nodes()}
    for key in list(pr.keys()):
        pr[key] = round(pr[key], 4)

    # 以弧兩端 PageRank 的平均值作為弧權重
    edge_pr = {}
    for s, t in g.edges():
        edge_pr[(s, t)] = round((pr[s] + pr[t]) / 2, 4)

    pr_values = list(edge_pr.values())
    min_pr = min(pr_values) if pr_values else 0
    std_pr = np.std(pr_values) if pr_values else 1.0
    if std_pr == 0:
        std_pr = 1.0

    pg_width = [(edge_pr[(s, t)] - min_pr) / std_pr for (s, t) in g.edges()]

    fig = Figure(figsize=(12, 8), facecolor='white')
    ax = fig.add_subplot(111)
    ax.set_title(f'Target network = {result.network_name} (PageRank-based weighting for arcs)')

    node_label_switch = result.num_nodes < 50
    real_node_size = result.node_sizes if node_label_switch else [max(1, int(300.0 / result.num_nodes))] * result.num_nodes

    nx.draw_networkx(g, pos=pos, linewidths=0, width=pg_width,
                     node_size=real_node_size, node_color=result.node_colors,
                     font_size=6, arrows=True, arrowsize=8,
                     with_labels=node_label_switch, ax=ax)
    nx.draw_networkx_edge_labels(g, pos=pos, edge_labels=edge_pr, font_size=5, ax=ax)

    fig.set_tight_layout(True)
    return fig


def create_degree_distribution_figure(result):
    """
    繪製度分佈圖：入度與出度分開呈現（四面板）

    左上：入度直方圖    右上：出度直方圖
    左下：入度 log-log   右下：出度 log-log
    """
    g = result.graph
    in_degrees = [d for _, d in g.in_degree()]
    out_degrees = [d for _, d in g.out_degree()]

    from collections import Counter

    fig = Figure(figsize=(12, 10), facecolor='white')

    # 入度直方圖
    ax1 = fig.add_subplot(221)
    max_in = max(in_degrees) if in_degrees else 1
    bins_in = range(0, max_in + 2)
    ax1.hist(in_degrees, bins=bins_in, color='steelblue', edgecolor='white', align='left')
    ax1.set_xlabel('In-Degree (k)')
    ax1.set_ylabel('Count')
    ax1.set_title(f'{result.network_name} — In-Degree Distribution')

    # 出度直方圖
    ax2 = fig.add_subplot(222)
    max_out = max(out_degrees) if out_degrees else 1
    bins_out = range(0, max_out + 2)
    ax2.hist(out_degrees, bins=bins_out, color='coral', edgecolor='white', align='left')
    ax2.set_xlabel('Out-Degree (k)')
    ax2.set_ylabel('Count')
    ax2.set_title(f'{result.network_name} — Out-Degree Distribution')

    # 入度 log-log
    in_count = Counter(in_degrees)
    ks_in = sorted(k for k in in_count.keys() if k > 0)
    pk_in = [in_count[k] / len(in_degrees) for k in ks_in]

    ax3 = fig.add_subplot(223)
    if ks_in:
        ax3.scatter(ks_in, pk_in, s=30, color='steelblue', edgecolors='navy', zorder=3)
        ax3.set_xscale('log')
        ax3.set_yscale('log')
    ax3.set_xlabel('In-Degree k (log)')
    ax3.set_ylabel('P(k) (log)')
    ax3.set_title(f'{result.network_name} — Log-Log In-Degree')
    ax3.grid(True, which='both', ls='--', alpha=0.4)

    # 出度 log-log
    out_count = Counter(out_degrees)
    ks_out = sorted(k for k in out_count.keys() if k > 0)
    pk_out = [out_count[k] / len(out_degrees) for k in ks_out]

    ax4 = fig.add_subplot(224)
    if ks_out:
        ax4.scatter(ks_out, pk_out, s=30, color='coral', edgecolors='darkred', zorder=3)
        ax4.set_xscale('log')
        ax4.set_yscale('log')
    ax4.set_xlabel('Out-Degree k (log)')
    ax4.set_ylabel('P(k) (log)')
    ax4.set_title(f'{result.network_name} — Log-Log Out-Degree')
    ax4.grid(True, which='both', ls='--', alpha=0.4)

    fig.set_tight_layout(True)
    return fig


def create_clustering_figure(result):
    """
    繪製階層式社群分割結果（有向圖版本）
    """
    g = result.graph
    pos = result.pos

    network_clustering(g, result.layers)

    ncc_map = {}
    color_count = 1
    for v in g.nodes():
        if g.nodes[v][NODE_KEY_GROUP_NUMBER] not in ncc_map:
            ncc_map[g.nodes[v][NODE_KEY_GROUP_NUMBER]] = color_count
            color_count += 1
    ncc = [ncc_map[g.nodes[v][NODE_KEY_GROUP_NUMBER]] for v in g.nodes()]

    bb_width = [g[s][t][EDGE_KEY_WIDTH] for (s, t) in g.edges()]
    bb_color = [g[s][t][EDGE_KEY_COLOR] for (s, t) in g.edges()]

    fig = Figure(figsize=(12, 8), facecolor='white')
    ax = fig.add_subplot(111)
    ax.set_title(f'Target network = {result.network_name} (clustering result)')

    import matplotlib.pyplot as plt
    nx.draw_networkx(g, pos=pos, linewidths=0, width=bb_width,
                     node_color=ncc, vmin=min(ncc), vmax=max(ncc),
                     cmap=plt.cm.Dark2, font_size=6, edge_color=bb_color,
                     arrows=True, arrowsize=8, ax=ax)

    fig.set_tight_layout(True)
    return fig


def create_fingerprint_chart(suite_result, suite_name=''):
    """
    繪製網絡指紋堆疊長條圖
    """
    if suite_result.corr_index and len(suite_result.corr_index) == len(suite_result.labels):
        order = suite_result.corr_index
        labels = [suite_result.labels[i] for i in order]
        bar = {
            k: v[order] if hasattr(v, '__getitem__') and hasattr(v, 'dtype') else v
            for k, v in suite_result.bar_data.items()
        }
    else:
        labels = suite_result.labels
        bar = suite_result.bar_data
    index = np.arange(len(labels))
    width = 0.5

    fig = Figure(figsize=(12, 8), facecolor='white')
    ax = fig.add_subplot(111)

    if suite_name:
        ax.set_title(f'Network Fingerprints — {suite_name}', pad=40)

    p1 = ax.bar(index, bar[BOND], width, color=BOND_COLOR, edgecolor=BOND_COLOR)
    p2 = ax.bar(index, bar[LOCAL_BRIDGE], width, color=LOCAL_BRIDGE_COLOR,
                edgecolor=LOCAL_BRIDGE_COLOR, bottom=bar[BOND])
    p3 = ax.bar(index, bar[GLOBAL_BRIDGE], width, color=GLOBAL_BRIDGE_COLOR,
                edgecolor=GLOBAL_BRIDGE_COLOR, bottom=bar[BOND] + bar[LOCAL_BRIDGE])
    p4 = ax.bar(index, bar[SILK], width, color=SILK_COLOR,
                edgecolor=SILK_COLOR, bottom=bar[BOND] + bar[LOCAL_BRIDGE] + bar[GLOBAL_BRIDGE])

    ax.xaxis.tick_top()
    ax.set_xticks(index)
    ax.set_xticklabels(labels, rotation=90)
    ax.set_ylabel('Percentage')
    ax.set_yticks(np.arange(0, 1.01, 0.1))
    ax.set_ylim(0, 1.)
    ax.legend((p1[0], p2[0], p3[0], p4[0]),
              (BOND, LOCAL_BRIDGE, GLOBAL_BRIDGE, SILK),
              loc='lower center', fancybox=True, shadow=True, ncol=4)

    for t in ax.xaxis.get_major_ticks():
        t.tick1line.set_visible(False)
        t.tick2line.set_visible(False)
    for t in ax.yaxis.get_major_ticks():
        t.tick1line.set_visible(False)
        t.tick2line.set_visible(False)

    fig.set_tight_layout(True)
    return fig


def create_correlation_heatmap(suite_result, suite_name=''):
    """
    繪製相關係數矩陣熱力圖
    """
    corr_coef = np.array(suite_result.corr_matrix)
    corr_labels = suite_result.corr_labels

    fig = Figure(figsize=(11, 11))
    ax = fig.add_subplot(111)

    if suite_name:
        ax.set_title(f'Fingerprint Correlation — {suite_name}', pad=40)

    import matplotlib.pyplot as plt
    ccmap = ax.pcolor(corr_coef, vmin=-1.0, vmax=1.0, cmap=plt.cm.RdBu, alpha=0.8)
    fig.colorbar(ccmap, ax=ax)

    ax.set_frame_on(False)
    ax.set_xticks(np.arange(corr_coef.shape[0]) + 0.5, minor=False)
    ax.set_yticks(np.arange(corr_coef.shape[1]) + 0.5, minor=False)
    ax.invert_yaxis()
    ax.xaxis.tick_top()
    ax.set_xticklabels(corr_labels, minor=False, rotation=90)
    ax.set_yticklabels(corr_labels, minor=False)
    ax.grid(False)

    for t in ax.xaxis.get_major_ticks():
        t.tick1line.set_visible(False)
        t.tick2line.set_visible(False)
    for t in ax.yaxis.get_major_ticks():
        t.tick1line.set_visible(False)
        t.tick2line.set_visible(False)

    fig.set_tight_layout(True)
    return fig


def create_dendrogram_figure(suite_result, suite_name=''):
    """
    繪製階層聚類樹狀圖
    """
    labels = suite_result.labels
    n = len(labels)

    if n < 2:
        fig = Figure(figsize=(12, 8), facecolor='white')
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, 'Need at least 2 networks for dendrogram',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        ax.set_axis_off()
        fig.set_tight_layout(True)
        return fig

    fingerprint_vectors = []
    for i in range(n):
        vec = [
            float(suite_result.bar_data[BOND][i]),
            float(suite_result.bar_data[LOCAL_BRIDGE][i]),
            float(suite_result.bar_data[GLOBAL_BRIDGE][i]),
            float(suite_result.bar_data[SILK][i]),
        ]
        fingerprint_vectors.append(vec)

    import warnings as _warnings
    corr_mat = []
    for i in range(n):
        row = []
        for j in range(n):
            with _warnings.catch_warnings():
                _warnings.simplefilter('ignore', RuntimeWarning)
                c = np.corrcoef(fingerprint_vectors[i], fingerprint_vectors[j])[0, 1]
            row.append(0.0 if np.isnan(c) else c)
        corr_mat.append(row)

    from scipy.spatial.distance import squareform
    dist_mat = np.array([[1.0 - corr_mat[i][j] for j in range(n)] for i in range(n)])
    dist_mat = (dist_mat + dist_mat.T) / 2
    np.fill_diagonal(dist_mat, 0)
    dist_condensed = squareform(dist_mat)

    fig = Figure(figsize=(12, 8), facecolor='white')
    ax = fig.add_subplot(111)

    if suite_name:
        ax.set_title(f'Hierarchical Clustering — {suite_name}')

    hc.dendrogram(hc.linkage(dist_condensed, method='centroid'),
                  no_plot=False, labels=labels, ax=ax)

    ax.tick_params(axis='x', rotation=90)
    ax.set_yticks([])

    fig.set_tight_layout(True)
    return fig
