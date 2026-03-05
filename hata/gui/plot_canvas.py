# -*- coding: utf-8 -*-
"""
matplotlib 嵌入 PySide6 的包裝器
"""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget


class PlotCanvas(FigureCanvasQTAgg):
    """可嵌入 PySide6 的 matplotlib 畫布"""

    def __init__(self, parent=None, width=8, height=6, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='white')
        super().__init__(self.fig)
        self.setParent(parent)

    def update_figure(self, new_figure):
        """用新的 Figure 物件取代目前的圖表"""
        if new_figure is not None:
            self.fig = new_figure
            self.figure = new_figure
            new_figure.set_canvas(self)

        self.draw()


class PlotWidget(QWidget):
    """包含 PlotCanvas 和導覽工具列的完整繪圖元件"""

    def __init__(self, parent=None, width=8, height=6, dpi=100):
        super().__init__(parent)
        self.canvas = PlotCanvas(self, width, height, dpi)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def update_figure(self, new_figure):
        """
        更新圖表並重新連結工具列。

        替換 canvas 的 Figure 後，必須銷毀並重建 NavigationToolbar，
        因為工具列內部快取了舊 Figure 的參考，直接復用會導致
        縮放/平移等操作失效。
        """
        if new_figure is not None:
            self.canvas.fig = new_figure
            self.canvas.figure = new_figure
            new_figure.set_canvas(self.canvas)
            self.canvas.draw()
            # 重建工具列（工具列內部快取舊 Figure 參考，無法直接復用）
            layout = self.layout()
            layout.removeWidget(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = NavigationToolbar2QT(self.canvas, self)
            layout.insertWidget(0, self.toolbar)
