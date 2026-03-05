#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HATA - Hierarchical Arc Type Analysis
統一入口：無命令列參數啟動 GUI，有參數走 CLI 模式

Usage:
    python run_hata.py                           # Launch GUI
    python run_hata.py analyze -i leader.net      # CLI: analyze single directed network
    python run_hata.py suite --name DEMO --run    # CLI: run suite experiment
"""

import sys


def main():
    if len(sys.argv) > 1:
        # CLI 模式
        from hata.cli import main as cli_main
        cli_main()
    else:
        # GUI 模式
        from hata.gui.main_window import launch_gui
        launch_gui()


if __name__ == '__main__':
    main()
