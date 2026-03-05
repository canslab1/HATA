# -*- coding: utf-8 -*-
"""
CLI 命令列入口：使用 argparse 取代原始 getopt
"""

import os
import sys
import warnings

import matplotlib
matplotlib.use('Agg')  # CLI 模式下使用非互動式後端
import matplotlib.pyplot as plt

from hata.engine import run_link_analysis, run_suite_experiment
from hata.excel_writer import write_link_analysis_excel, write_suite_experiment_excel, write_edge_classification_csv
from hata.plotting import (
    create_network_figure,
    create_detail_layer_figure,
    create_betweenness_figure,
    create_pagerank_figure,
    create_degree_distribution_figure,
    create_clustering_figure,
    create_fingerprint_chart,
    create_correlation_heatmap,
    create_dendrogram_figure,
)


def _cli_progress(current, total, message):
    """CLI 模式下的進度顯示"""
    bar_len = 40
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = '=' * filled + '-' * (bar_len - filled)
    pct = 100.0 * current / total if total > 0 else 0
    sys.stdout.write(f'\r[{bar}] {pct:.1f}% {message}')
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write('\n')


def cmd_analyze(args):
    """執行單一有向網絡分析"""
    path = args.input
    if not os.path.exists(path):
        print(f"Error: file not found: {path}")
        sys.exit(1)

    quick = args.quick is not None
    separation = args.quick if args.quick else 1

    print(f"Analyzing directed network: {path}")
    print(f"Random networks: {args.times}")
    if quick:
        print(f"Quick mode: separation = {separation}")
    if args.parallel:
        print(f"Parallel mode: {args.workers or 'auto'} workers")

    results = run_link_analysis(
        path=path,
        times=args.times,
        quick=quick,
        separation=separation,
        debug=args.debug,
        parallel=args.parallel,
        workers=args.workers,
        progress_callback=_cli_progress,
    )

    root, ext = os.path.splitext(path)

    for result in results:
        cid = result.component_id
        print(f"\n--- Component {cid} ---")
        print(f"Nodes: {result.num_nodes}, Arcs: {result.num_edges}")
        print(f"BOND: {result.bond_count}, Silk: {result.silk_count}, "
              f"Local Bridge: {result.local_bridge_count}, Global Bridge: {result.global_bridge_count}")
        print(f"Entropy: {result.graph_entropy:.4f}")

        # 輸出 Excel
        excel_path = f'{root}_{cid}_result.xlsx'
        write_link_analysis_excel(result, excel_path)
        print(f"Excel saved: {excel_path}")

        # 輸出 CSV 邊分類表
        if args.export_csv:
            csv_path = f'{root}_{cid}_edges.csv'
            write_edge_classification_csv(result, csv_path)
            print(f"Arc classification CSV saved: {csv_path}")

        # 儲存主要結果圖
        fig = create_network_figure(result)
        png_path = f'{root}_{cid}_result.png'
        fig.savefig(png_path, dpi=600)
        print(f"Network plot saved: {png_path}")

        if args.show_detail:
            for layer in range(1, result.layers + 1):
                fig = create_detail_layer_figure(result, layer)
                layer_path = f'{root}_{cid}_result_layer_{layer}.png'
                fig.savefig(layer_path)
                print(f"Detail layer {layer} saved: {layer_path}")

        if args.show_betweenness:
            fig = create_betweenness_figure(result)
            bet_path = f'{root}_{cid}_result_betweenness.png'
            fig.savefig(bet_path)
            print(f"Betweenness plot saved: {bet_path}")

        if args.show_pagerank:
            fig = create_pagerank_figure(result)
            pr_path = f'{root}_{cid}_result_pagerank.png'
            fig.savefig(pr_path)
            print(f"PageRank plot saved: {pr_path}")

        if args.show_clustering:
            fig = create_clustering_figure(result)
            cl_path = f'{root}_{cid}_result_clustering.png'
            fig.savefig(cl_path)
            print(f"Clustering plot saved: {cl_path}")

        if args.show_degree:
            fig = create_degree_distribution_figure(result)
            deg_path = f'{root}_{cid}_result_degree.png'
            fig.savefig(deg_path)
            print(f"Degree distribution plot saved: {deg_path}")

    plt.close('all')


def cmd_suite(args):
    """執行批次實驗"""
    data_dir = args.dir if args.dir else '.'

    print(f"Suite experiment: {args.name}")
    print(f"Data directory: {data_dir}")

    suite_result = run_suite_experiment(
        suite=args.name,
        data_dir=data_dir,
        run_analysis=args.run,
        times=args.times,
        debug=args.debug,
        progress_callback=_cli_progress,
    )

    if not suite_result.labels:
        print("No fingerprint data found. Run with --run to generate data first.")
        return

    # 儲存指紋長條圖
    fig = create_fingerprint_chart(suite_result, args.name)
    fig.savefig(f'fingerprints_{args.name}.png')
    print(f"Fingerprint chart saved: fingerprints_{args.name}.png")

    # 儲存相關矩陣
    fig = create_correlation_heatmap(suite_result, args.name)
    fig.savefig(f'correlation_{args.name}.png')
    print(f"Correlation heatmap saved: correlation_{args.name}.png")

    # 儲存樹狀圖
    fig = create_dendrogram_figure(suite_result, args.name)
    fig.savefig(f'hierarchy_{args.name}.png')
    print(f"Dendrogram saved: hierarchy_{args.name}.png")

    # 儲存 Excel
    excel_path = f'suite_result_{args.name}.xlsx'
    write_suite_experiment_excel(suite_result, excel_path)
    print(f"Excel saved: {excel_path}")

    plt.close('all')


def main(argv=None):
    """CLI 主入口"""
    import argparse

    warnings.filterwarnings("ignore")

    parser = argparse.ArgumentParser(
        description='HATA - Hierarchical Arc Type Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s analyze -i leader.net
  %(prog)s analyze -i leader.net -t 100 -d
  %(prog)s analyze -i leader.net -q 2
  %(prog)s analyze -i leader.net -p          (parallel mode)
  %(prog)s analyze -i leader.net -p -w 8     (parallel with 8 workers)
  %(prog)s suite --name DEMO --run
        """,
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # analyze 子命令
    p_analyze = subparsers.add_parser('analyze', help='Analyze a single directed network')
    p_analyze.add_argument('-i', '--input', required=True,
                           help='Path to network file (.net, .gml, .graphml, .edgelist, .edges, .adjlist)')
    p_analyze.add_argument('-t', '--times', type=int, default=1000,
                           help='Number of random networks (default: 1000)')
    p_analyze.add_argument('-q', '--quick', type=int, default=None, metavar='LAYERS',
                           help='Quick mode: limit analysis to N layers')
    p_analyze.add_argument('-d', '--debug', action='store_true', help='Enable debug output')
    p_analyze.add_argument('-p', '--parallel', action='store_true',
                           help='Enable parallel random network generation')
    p_analyze.add_argument('-w', '--workers', type=int, default=None,
                           help='Number of parallel workers (default: CPU cores - 1)')
    p_analyze.add_argument('--show-detail', action='store_true', help='Save detail layer plots')
    p_analyze.add_argument('--show-betweenness', action='store_true', help='Save betweenness plot')
    p_analyze.add_argument('--show-pagerank', action='store_true', help='Save PageRank plot')
    p_analyze.add_argument('--show-clustering', action='store_true', help='Save clustering plot')
    p_analyze.add_argument('--show-degree', action='store_true', help='Save degree distribution plot')
    p_analyze.add_argument('--export-csv', action='store_true',
                           help='Export arc classification as CSV (for Gephi/Cytoscape)')

    # suite 子命令
    p_suite = subparsers.add_parser('suite', help='Run suite experiment')
    p_suite.add_argument('--name', choices=['DEMO'], default='DEMO',
                         help='Suite name (default: DEMO)')
    p_suite.add_argument('--run', action='store_true',
                         help='Run analysis first (otherwise show existing results)')
    p_suite.add_argument('--dir', default='.', help='Directory containing network files')
    p_suite.add_argument('-t', '--times', type=int, default=1000,
                         help='Number of random networks (default: 1000)')
    p_suite.add_argument('-d', '--debug', action='store_true', help='Enable debug output')

    args = parser.parse_args(argv)

    if args.command == 'analyze':
        cmd_analyze(args)
    elif args.command == 'suite':
        cmd_suite(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
