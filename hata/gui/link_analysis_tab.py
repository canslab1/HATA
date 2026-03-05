# -*- coding: utf-8 -*-
"""
連結分析分頁：檔案選擇、參數設定、執行分析、顯示結果
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFileDialog, QSpinBox,
    QCheckBox, QSplitter, QTabWidget, QMessageBox,
)
from PySide6.QtCore import Qt

from hata.gui.plot_canvas import PlotWidget
from hata.gui.worker import LinkAnalysisWorker
from hata.excel_writer import write_link_analysis_excel, write_edge_classification_csv
from hata.plotting import (
    create_network_figure,
    create_detail_layer_figure,
    create_betweenness_figure,
    create_pagerank_figure,
    create_degree_distribution_figure,
    create_clustering_figure,
)


class LinkAnalysisTab(QWidget):
    """
    連結分析分頁：單一有向網絡的完整分析介面。

    左側面板：檔案瀏覽、參數設定（隨機網絡數量、Quick 模式、平行計算）、
              額外圖表選項、執行/匯出按鈕。
    右側面板：以分頁式顯示分析結果圖表（主網絡圖、各層詳情、Betweenness、
              PageRank、Clustering、Degree Distribution）。

    分析在 LinkAnalysisWorker（QThread）中執行，避免 GUI 凍結。
    """

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.worker = None
        self.results = None
        self.net_file = None
        self._build_ui()

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # === 左側：參數面板 ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # 檔案選擇
        file_group = QGroupBox("Directed Network File")
        file_layout = QVBoxLayout(file_group)
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(btn_browse)
        left_layout.addWidget(file_group)

        # 參數設定
        param_group = QGroupBox("Parameters")
        param_layout = QVBoxLayout(param_group)

        # 隨機網絡數量
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Random Networks:"))
        self.spin_times = QSpinBox()
        self.spin_times.setRange(1, 100000)
        self.spin_times.setValue(1000)
        self.spin_times.setToolTip("Number of random directed networks for comparison (default: 1000)")
        row1.addWidget(self.spin_times)
        param_layout.addLayout(row1)

        # Quick 模式
        self.chk_quick = QCheckBox("Quick Mode")
        self.chk_quick.setToolTip("Limit the number of analysis layers")
        self.chk_quick.toggled.connect(self._on_quick_toggled)
        param_layout.addWidget(self.chk_quick)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Separation Layers:"))
        self.spin_separation = QSpinBox()
        self.spin_separation.setRange(1, 20)
        self.spin_separation.setValue(1)
        self.spin_separation.setEnabled(False)
        self.spin_separation.setToolTip("Maximum number of layers in quick mode")
        row2.addWidget(self.spin_separation)
        param_layout.addLayout(row2)

        # 平行計算
        self.chk_parallel = QCheckBox("Parallel Mode")
        self.chk_parallel.setChecked(True)
        self.chk_parallel.setToolTip("Use multiple CPU cores for random network generation")
        self.chk_parallel.toggled.connect(self._on_parallel_toggled)
        param_layout.addWidget(self.chk_parallel)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Workers:"))
        self.spin_workers = QSpinBox()
        cpu_count = os.cpu_count() or 4
        self.spin_workers.setRange(1, cpu_count)
        self.spin_workers.setValue(max(1, cpu_count - 1))
        self.spin_workers.setToolTip(f"Number of parallel workers (detected {cpu_count} CPU cores)")
        row3.addWidget(self.spin_workers)
        param_layout.addLayout(row3)

        # Debug 模式
        self.chk_debug = QCheckBox("Debug Mode")
        self.chk_debug.setToolTip("Show detailed debug output in console")
        param_layout.addWidget(self.chk_debug)

        left_layout.addWidget(param_group)

        # 額外顯示選項
        show_group = QGroupBox("Additional Plots")
        show_layout = QVBoxLayout(show_group)
        self.chk_detail = QCheckBox("Layer Detail Plots")
        self.chk_betweenness = QCheckBox("Arc Betweenness Centrality")
        self.chk_pagerank = QCheckBox("PageRank-based Weighting")
        self.chk_clustering = QCheckBox("Network Clustering")
        self.chk_degree = QCheckBox("Degree Distribution (In/Out)")
        show_layout.addWidget(self.chk_detail)
        show_layout.addWidget(self.chk_betweenness)
        show_layout.addWidget(self.chk_pagerank)
        show_layout.addWidget(self.chk_clustering)
        show_layout.addWidget(self.chk_degree)
        left_layout.addWidget(show_group)

        # 執行按鈕
        self.btn_run = QPushButton("Run Analysis")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_run.clicked.connect(self._run_analysis)
        left_layout.addWidget(self.btn_run)

        # 匯出按鈕
        self.btn_export = QPushButton("Export Excel (.xlsx)")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_excel)
        left_layout.addWidget(self.btn_export)

        # CSV 匯出按鈕
        self.btn_export_csv = QPushButton("Export Arc CSV")
        self.btn_export_csv.setEnabled(False)
        self.btn_export_csv.setToolTip("Export arc classification as CSV (for Gephi/Cytoscape)")
        self.btn_export_csv.clicked.connect(self._export_csv)
        left_layout.addWidget(self.btn_export_csv)

        # 儲存圖表按鈕
        self.btn_save_plot = QPushButton("Save Current Plot (.png)")
        self.btn_save_plot.setEnabled(False)
        self.btn_save_plot.clicked.connect(self._save_plot)
        left_layout.addWidget(self.btn_save_plot)

        left_layout.addStretch()

        # === 右側：結果面板 ===
        self.result_tabs = QTabWidget()
        self.plot_network = PlotWidget()
        self.result_tabs.addTab(self.plot_network, "Network")

        splitter.addWidget(left_panel)
        splitter.addWidget(self.result_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def _on_quick_toggled(self, checked):
        self.spin_separation.setEnabled(checked)

    def _on_parallel_toggled(self, checked):
        self.spin_workers.setEnabled(checked)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Directed Network File", "",
            "All Supported (*.net *.gml *.graphml *.edgelist *.edges *.adjlist);;"
            "Pajek (*.net);;GML (*.gml);;GraphML (*.graphml);;"
            "Edge List (*.edgelist *.edges);;Adjacency List (*.adjlist);;"
            "All Files (*)"
        )
        if path:
            self.net_file = path
            self.file_label.setText(path)

    def _run_analysis(self):
        if not self.net_file:
            QMessageBox.warning(self, "Warning", "Please select a directed network file first.")
            return

        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_export_csv.setEnabled(False)
        self.btn_save_plot.setEnabled(False)

        # 清除舊的結果分頁
        while self.result_tabs.count() > 1:
            w = self.result_tabs.widget(1)
            self.result_tabs.removeTab(1)
            w.deleteLater()
        self.plot_network = PlotWidget()
        self.result_tabs.removeTab(0)
        self.result_tabs.insertTab(0, self.plot_network, "Network")

        if self.main_window:
            self.main_window.show_progress(True, self.spin_times.value())

        self.worker = LinkAnalysisWorker(
            path=self.net_file,
            times=self.spin_times.value(),
            quick=self.chk_quick.isChecked(),
            separation=self.spin_separation.value(),
            debug=self.chk_debug.isChecked(),
            parallel=self.chk_parallel.isChecked(),
            workers=self.spin_workers.value() if self.chk_parallel.isChecked() else None,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current, total, message):
        if self.main_window:
            self.main_window.update_progress(current, total, message)

    def _on_finished(self, results):
        self.results = results
        self.worker = None

        if self.main_window:
            self.main_window.show_progress(False)

        if not results:
            QMessageBox.information(self, "Result", "No components found in the network.")
            self.btn_run.setEnabled(True)
            return

        result = results[0]

        # 主網絡圖
        fig = create_network_figure(result)
        self.plot_network.update_figure(fig)

        # 額外圖表
        if self.chk_detail.isChecked():
            for layer in range(1, result.layers + 1):
                fig = create_detail_layer_figure(result, layer)
                pw = PlotWidget()
                pw.update_figure(fig)
                self.result_tabs.addTab(pw, f"Layer {layer}")

        if self.chk_betweenness.isChecked():
            fig = create_betweenness_figure(result)
            pw = PlotWidget()
            pw.update_figure(fig)
            self.result_tabs.addTab(pw, "Betweenness")

        if self.chk_pagerank.isChecked():
            fig = create_pagerank_figure(result)
            pw = PlotWidget()
            pw.update_figure(fig)
            self.result_tabs.addTab(pw, "PageRank")

        if self.chk_clustering.isChecked():
            fig = create_clustering_figure(result)
            pw = PlotWidget()
            pw.update_figure(fig)
            self.result_tabs.addTab(pw, "Clustering")

        if self.chk_degree.isChecked():
            fig = create_degree_distribution_figure(result)
            pw = PlotWidget()
            pw.update_figure(fig)
            self.result_tabs.addTab(pw, "Degree Dist.")

        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_export_csv.setEnabled(True)
        self.btn_save_plot.setEnabled(True)

        # 顯示摘要
        if self.main_window:
            self.main_window.statusBar().showMessage(
                f"Done: {result.num_nodes} nodes, {result.num_edges} arcs | "
                f"BOND={result.bond_count}, Silk={result.silk_count}, "
                f"LB={result.local_bridge_count}, GB={result.global_bridge_count}"
            )

    def _on_error(self, message):
        self.worker = None
        self.btn_run.setEnabled(True)
        if self.main_window:
            self.main_window.show_progress(False)
        QMessageBox.critical(self, "Error", f"Analysis failed:\n{message}")

    def _export_excel(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel File", "", "Excel Files (*.xlsx);;All Files (*)"
        )
        if path:
            if not path.endswith('.xlsx'):
                path += '.xlsx'
            write_link_analysis_excel(self.results[0], path)
            QMessageBox.information(self, "Saved", f"Excel file saved:\n{path}")

    def _export_csv(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Arc Classification CSV", "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            if not path.endswith('.csv'):
                path += '.csv'
            write_edge_classification_csv(self.results[0], path)
            QMessageBox.information(self, "Saved", f"Arc classification CSV saved:\n{path}")

    def _save_plot(self):
        current_widget = self.result_tabs.currentWidget()
        if not isinstance(current_widget, PlotWidget):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Plot", "", "PNG Files (*.png);;PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            current_widget.canvas.fig.savefig(path, dpi=300, bbox_inches='tight')
            QMessageBox.information(self, "Saved", f"Plot saved:\n{path}")
