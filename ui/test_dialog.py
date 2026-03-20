from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QPushButton)
from PyQt5.QtCore import QThread, pyqtSignal

from core.test_runner import test_single_config, test_single_config_cli


class TestWorker(QThread):
    """QThread 包装，内部调用 test_single_config"""
    finished = pyqtSignal(int, dict)

    def __init__(self, row, name, base_url, api_key, model):
        super().__init__()
        self.row = row
        self.args = (name, base_url, api_key, model)

    def run(self):
        result = test_single_config(*self.args)
        self.finished.emit(self.row, result)


class CLITestWorker(QThread):
    """QThread 包装，内部调用 test_single_config_cli"""
    finished = pyqtSignal(int, dict)

    def __init__(self, row, name, settings_path):
        super().__init__()
        self.row = row
        self.name = name
        self.settings_path = settings_path

    def run(self):
        result = test_single_config_cli(self.name, self.settings_path)
        self.finished.emit(self.row, result)


class TestAllDialog(QDialog):
    """配置可用性测试对话框 — 每个配置占两行（HTTP + CLI）"""
    COLUMNS = ["名称", "测试", "状态", "模型", "路径", "首字耗时",
               "字数", "总耗时", "速度", "响应"]
    COL = {name: i for i, name in enumerate(COLUMNS)}

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CC Switch - 配置可用性测试")
        self.workers = []
        self.cli_workers = []
        self._cm = config_manager

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.82), int(screen.height() * 0.55))

        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.retest_btn = QPushButton("重新测试")
        self.retest_btn.clicked.connect(self.start_tests)
        btn_layout.addWidget(self.retest_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.start_tests()

    def _row_for(self, cfg_index, is_cli=False):
        """配置索引 → 表格行号。每个配置占 2 行：偶数=HTTP，奇数=CLI"""
        return cfg_index * 2 + (1 if is_cli else 0)

    def start_tests(self):
        for w in self.workers + self.cli_workers:
            if w.isRunning():
                w.terminate()
        self.workers.clear()
        self.cli_workers.clear()
        self.retest_btn.setEnabled(False)

        test_configs = self._cm.get_test_list()
        self._test_configs = test_configs
        self._done_count = 0
        self._total = len(test_configs) * 2

        n = len(test_configs)
        self.table.setRowCount(n * 2)
        C = self.COL

        for i, cfg in enumerate(test_configs):
            name, base_url, api_key, models, settings_path = cfg
            r_http = self._row_for(i, False)
            r_cli = self._row_for(i, True)

            for col in range(len(self.COLUMNS)):
                self.table.setItem(r_http, col, QTableWidgetItem(""))
                self.table.setItem(r_cli, col, QTableWidgetItem(""))

            self.table.setItem(r_http, C["名称"], QTableWidgetItem(name))
            self.table.setSpan(r_http, C["名称"], 2, 1)
            self.table.setItem(r_http, C["测试"], QTableWidgetItem("HTTP"))
            self.table.setItem(r_http, C["状态"], QTableWidgetItem("⏳"))
            self.table.setItem(r_cli, C["测试"], QTableWidgetItem("CLI"))
            self.table.setItem(r_cli, C["状态"], QTableWidgetItem("⏳"))

            worker = TestWorker(i, name, base_url, api_key, models)
            worker.finished.connect(self._on_http_done)
            self.workers.append(worker)

            cli_worker = CLITestWorker(i, name, settings_path)
            cli_worker.finished.connect(self._on_cli_done)
            self.cli_workers.append(cli_worker)

        self._apply_column_widths()

        for w in self.workers:
            w.start()
        for w in self.cli_workers:
            w.start()

    def _on_http_done(self, cfg_index, result):
        row = self._row_for(cfg_index, False)
        C = self.COL
        self.table.item(row, C["状态"]).setText(result["status"])
        self.table.item(row, C["模型"]).setText(result.get("model", "-"))
        self.table.item(row, C["路径"]).setText(result.get("path", "-"))
        self.table.item(row, C["首字耗时"]).setText(result["ttft"])
        self.table.item(row, C["字数"]).setText(result["length"])
        self.table.item(row, C["总耗时"]).setText(result["total"])
        self.table.item(row, C["速度"]).setText(result["speed"])
        resp = result["response"]
        display = resp[:60] + "..." if len(resp) > 60 else resp
        self.table.item(row, C["响应"]).setText(display)
        self.table.item(row, C["响应"]).setToolTip(resp)
        self._fit_columns()
        self._check_done()

    def _on_cli_done(self, cfg_index, result):
        row = self._row_for(cfg_index, True)
        C = self.COL
        self.table.item(row, C["状态"]).setText(result["cli_status"])
        self.table.item(row, C["总耗时"]).setText(result["cli_total"])
        resp = result["cli_response"]
        display = resp[:60] + "..." if len(resp) > 60 else resp
        self.table.item(row, C["响应"]).setText(display)
        self.table.item(row, C["响应"]).setToolTip(resp)
        self._fit_columns()
        self._check_done()

    def _apply_column_widths(self):
        from PyQt5.QtWidgets import QHeaderView
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL["响应"], QHeaderView.Stretch)
        self._fit_columns()

    def _fit_columns(self):
        """让每列宽度 = max(表头宽度, 内容宽度)"""
        header = self.table.horizontalHeader()
        fm = header.fontMetrics()
        for col in range(len(self.COLUMNS)):
            if col == self.COL["响应"]:
                continue
            header_w = fm.horizontalAdvance(self.COLUMNS[col]) + 24
            self.table.resizeColumnToContents(col)
            if self.table.columnWidth(col) < header_w:
                self.table.setColumnWidth(col, header_w)

    def _check_done(self):
        self._done_count += 1
        if self._done_count >= self._total:
            self.retest_btn.setEnabled(True)

    def closeEvent(self, event):
        for w in self.workers + self.cli_workers:
            if w.isRunning():
                w.terminate()
                w.wait(1000)
        super().closeEvent(event)
