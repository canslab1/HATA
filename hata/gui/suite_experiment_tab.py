# -*- coding: utf-8 -*-
"""
批次實驗分頁：套件選擇、執行分析/顯示結果、三種圖表、匯出 Excel
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFileDialog, QSpinBox,
    QCheckBox, QComboBox, QSplitter, QTabWidget,
    QMessageBox,
)
from PySide6.QtCore import Qt

from hata.gui.plot_canvas import PlotWidget
from hata.gui.worker import SuiteExperimentWorker
from hata.excel_writer import write_suite_experiment_excel
from hata.plotting import (
    create_fingerprint_chart,
    create_correlation_heatmap,
    create_dendrogram_figure,
)


class SuiteExperimentTab(QWidget):
    """
    批次實驗分頁：對一組有向網絡進行批次分析並比較指紋。

    左側面板：套件選擇（DEMO）、資料目錄、是否重新執行分析、參數設定。
    右側面板：三個固定分頁——指紋堆疊長條圖、相關係數熱力圖、階層聚類樹狀圖。

    分析在 SuiteExperimentWorker（QThread）中執行，避免 GUI 凍結。
    """

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.worker = None
        self.suite_result = None
        self._build_ui()

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # === 左側：參數面板 ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # 套件選擇
        suite_group = QGroupBox("Suite Selection")
        suite_layout = QVBoxLayout(suite_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Suite:"))
        self.combo_suite = QComboBox()
        self.combo_suite.addItems(['DEMO'])
        self.combo_suite.setToolTip(
            "DEMO: Directed network examples\n"
            "(leader, prisonInter, Ragusa16, s208, women)"
        )
        row1.addWidget(self.combo_suite)
        suite_layout.addLayout(row1)

        # 資料目錄
        dir_row = QHBoxLayout()
        self.dir_label = QLabel("Data directory: (current)")
        self.dir_label.setWordWrap(True)
        btn_dir = QPushButton("Change...")
        btn_dir.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_label)
        dir_row.addWidget(btn_dir)
        suite_layout.addLayout(dir_row)

        left_layout.addWidget(suite_group)

        # 分析參數
        param_group = QGroupBox("Analysis Parameters")
        param_layout = QVBoxLayout(param_group)

        self.chk_run_analysis = QCheckBox("Run Analysis (generate new data)")
        self.chk_run_analysis.setToolTip(
            "If checked, run arc analysis on all networks in the suite.\n"
            "If unchecked, only show existing results."
        )
        param_layout.addWidget(self.chk_run_analysis)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Random Networks:"))
        self.spin_times = QSpinBox()
        self.spin_times.setRange(1, 100000)
        self.spin_times.setValue(1000)
        row2.addWidget(self.spin_times)
        param_layout.addLayout(row2)

        self.chk_debug = QCheckBox("Debug Mode")
        param_layout.addWidget(self.chk_debug)

        left_layout.addWidget(param_group)

        # 執行按鈕
        self.btn_run = QPushButton("Run Suite Experiment")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_run.clicked.connect(self._run_experiment)
        left_layout.addWidget(self.btn_run)

        # 匯出按鈕
        self.btn_export = QPushButton("Export Excel (.xlsx)")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_excel)
        left_layout.addWidget(self.btn_export)

        # 儲存圖表按鈕
        self.btn_save_plot = QPushButton("Save Current Plot (.png)")
        self.btn_save_plot.setEnabled(False)
        self.btn_save_plot.clicked.connect(self._save_plot)
        left_layout.addWidget(self.btn_save_plot)

        left_layout.addStretch()

        # === 右側：結果面板 ===
        self.result_tabs = QTabWidget()
        self.plot_fingerprint = PlotWidget()
        self.plot_correlation = PlotWidget()
        self.plot_dendrogram = PlotWidget()
        self.result_tabs.addTab(self.plot_fingerprint, "Fingerprint")
        self.result_tabs.addTab(self.plot_correlation, "Correlation")
        self.result_tabs.addTab(self.plot_dendrogram, "Dendrogram")

        splitter.addWidget(left_panel)
        splitter.addWidget(self.result_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.data_dir = '.'

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Data Directory")
        if d:
            self.data_dir = d
            self.dir_label.setText(f"Data directory: {d}")

    def _run_experiment(self):
        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_save_plot.setEnabled(False)

        suite = self.combo_suite.currentText()

        if self.main_window:
            self.main_window.show_progress(True, 0)
            self.main_window.statusBar().showMessage(f"Running suite experiment: {suite}...")

        self.worker = SuiteExperimentWorker(
            suite=suite,
            data_dir=self.data_dir,
            run_analysis=self.chk_run_analysis.isChecked(),
            times=self.spin_times.value(),
            debug=self.chk_debug.isChecked(),
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, current, total, message):
        if self.main_window:
            self.main_window.update_progress(current, total, message)

    def _on_finished(self, suite_result):
        self.suite_result = suite_result
        self.worker = None

        if self.main_window:
            self.main_window.show_progress(False)

        if not suite_result.labels:
            QMessageBox.information(
                self, "Result",
                "No fingerprint data found.\n"
                "Check 'Run Analysis' to generate data first."
            )
            self.btn_run.setEnabled(True)
            return

        suite_name = self.combo_suite.currentText()

        # 更新指紋長條圖
        fig = create_fingerprint_chart(suite_result, suite_name)
        self.plot_fingerprint.update_figure(fig)

        # 更新相關矩陣
        fig = create_correlation_heatmap(suite_result, suite_name)
        self.plot_correlation.update_figure(fig)

        # 更新樹狀圖
        fig = create_dendrogram_figure(suite_result, suite_name)
        self.plot_dendrogram.update_figure(fig)

        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_save_plot.setEnabled(True)

        if self.main_window:
            self.main_window.statusBar().showMessage(
                f"Suite '{suite_name}': {len(suite_result.labels)} networks analyzed"
            )

    def _on_error(self, message):
        self.worker = None
        self.btn_run.setEnabled(True)
        if self.main_window:
            self.main_window.show_progress(False)
        QMessageBox.critical(self, "Error", f"Suite experiment failed:\n{message}")

    def _export_excel(self):
        if not self.suite_result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel File", "", "Excel Files (*.xlsx);;All Files (*)"
        )
        if path:
            if not path.endswith('.xlsx'):
                path += '.xlsx'
            write_suite_experiment_excel(self.suite_result, path)
            QMessageBox.information(self, "Saved", f"Excel file saved:\n{path}")

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
