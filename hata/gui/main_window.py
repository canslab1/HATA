# -*- coding: utf-8 -*-
"""
PySide6 主視窗：包含連結分析和批次實驗兩個分頁
"""

import sys

import matplotlib
matplotlib.use('QtAgg')

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QProgressBar,
    QMessageBox,
)
from PySide6.QtGui import QAction

from hata.gui.link_analysis_tab import LinkAnalysisTab
from hata.gui.suite_experiment_tab import SuiteExperimentTab


class HATAMainWindow(QMainWindow):
    """HATA 主視窗"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HATA - Hierarchical Arc Type Analysis")
        self.setMinimumSize(1200, 800)

        # 分頁
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.link_tab = LinkAnalysisTab(main_window=self)
        self.tabs.addTab(self.link_tab, "Arc Analysis")

        self.suite_tab = SuiteExperimentTab(main_window=self)
        self.tabs.addTab(self.suite_tab, "Suite Experiment")

        # 進度列
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.statusBar().addPermanentWidget(self.progress_bar)

        # 選單列
        self._build_menu()

        self.statusBar().showMessage("Ready")

    def _build_menu(self):
        menubar = self.menuBar()

        # File 選單
        file_menu = menubar.addMenu("&File")

        action_quit = QAction("&Quit", self)
        action_quit.setShortcut("Ctrl+Q")
        action_quit.triggered.connect(self.close)
        file_menu.addAction(action_quit)

        # Help 選單
        help_menu = menubar.addMenu("&Help")

        action_about = QAction("&About", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About HATA",
            "<h3>HATA - Hierarchical Arc Type Analysis</h3>"
            "<p>Version 2.0 (Python 3)</p>"
            "<p>Classifies directed arcs in complex networks into four types:</p>"
            "<ul>"
            "<li><b>BOND</b> - Strong connections (high redundancy)</li>"
            "<li><b>Silk</b> - Pendant arcs (degree-1 endpoint)</li>"
            "<li><b>Local Bridge</b> - Inter-cluster connections</li>"
            "<li><b>Global Bridge</b> - Long-range connections</li>"
            "</ul>"
            "<p>Authors: Chung-Yuan Huang (gscott@mail.cgu.edu.tw)<br>"
            "Wei-Chien-Benny Chin (wcchin.88@gmail.com)</p>"
        )

    def show_progress(self, visible, maximum=0):
        """顯示或隱藏進度列"""
        self.progress_bar.setVisible(visible)
        if visible:
            self.progress_bar.setMaximum(maximum)
            self.progress_bar.setValue(0)

    def update_progress(self, current, total, message):
        """更新進度列"""
        if total > 0:
            self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.statusBar().showMessage(message)


def launch_gui():
    """啟動 GUI 應用程式"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = HATAMainWindow()
    window.show()
    sys.exit(app.exec())
