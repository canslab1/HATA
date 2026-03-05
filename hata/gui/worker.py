# -*- coding: utf-8 -*-
"""
QThread 背景工作執行緒：在背景執行長時間分析，避免 GUI 凍結
"""

from PySide6.QtCore import QThread, Signal

from hata.engine import run_link_analysis, run_suite_experiment


class LinkAnalysisWorker(QThread):
    """連結分析背景工作"""
    progress = Signal(int, int, str)   # current, total, message
    finished = Signal(list)            # List[LinkAnalysisResult]
    error = Signal(str)                # error message

    def __init__(self, path, times=1000, quick=False, separation=1,
                 debug=False, parallel=False, workers=None):
        super().__init__()
        self.path = path
        self.times = times
        self.quick = quick
        self.separation = separation
        self.debug = debug
        self.parallel = parallel
        self.workers = workers

    def run(self):
        try:
            results = run_link_analysis(
                path=self.path,
                times=self.times,
                quick=self.quick,
                separation=self.separation,
                debug=self.debug,
                parallel=self.parallel,
                workers=self.workers,
                progress_callback=self._on_progress,
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, current, total, message):
        self.progress.emit(current, total, message)


class SuiteExperimentWorker(QThread):
    """批次實驗背景工作"""
    progress = Signal(int, int, str)
    finished = Signal(object)          # SuiteExperimentResult
    error = Signal(str)

    def __init__(self, suite='DEMO', data_dir='.', run_analysis=False,
                 times=1000, debug=False):
        super().__init__()
        self.suite = suite
        self.data_dir = data_dir
        self.run_analysis = run_analysis
        self.times = times
        self.debug = debug

    def run(self):
        try:
            result = run_suite_experiment(
                suite=self.suite,
                data_dir=self.data_dir,
                run_analysis=self.run_analysis,
                times=self.times,
                debug=self.debug,
                progress_callback=self._on_progress,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, current, total, message):
        self.progress.emit(current, total, message)
