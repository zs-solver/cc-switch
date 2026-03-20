import sys
import os
import json
import time
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# 每个配置尝试的路径列表
API_PATHS = ["/v1/messages", "/messages"]
# 无明确模型时尝试的模型列表
FALLBACK_MODELS = ["claude-opus-4-6-thinking", "claude-opus-4-6", "opus"]


def _test_url(url, headers, body):
    """对指定 URL 发送流式请求，返回指标字典，失败则抛异常"""
    t_start = time.time()
    t_first = None
    text = ""

    resp = requests.post(url, headers=headers, json=body,
                         stream=True, timeout=30)
    resp.raise_for_status()

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        try:
            data = json.loads(data_str)
        except Exception:
            continue
        if data.get("type") == "content_block_delta":
            if t_first is None:
                t_first = time.time()
            text += data.get("delta", {}).get("text", "")

    t_end = time.time()
    if t_first is None or not text:
        raise ValueError("无响应内容")

    ttft = t_first - t_start
    total = t_end - t_start
    length = len(text)
    speed = length / total if total > 0 else 0
    return {
        "ttft": f"{ttft:.2f}s",
        "length": str(length),
        "total": f"{total:.2f}s",
        "speed": f"{speed:.1f} 字/秒",
        "response": text,
    }


def test_single_config(name, base_url, api_key, models):
    """同时测试多条路径 × 多个模型，返回首个成功的结果"""
    base = base_url.rstrip("/")
    headers = {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    result = {"name": name, "status": "❌", "ttft": "-", "length": "-",
              "total": "-", "speed": "-", "response": "",
              "path": "-", "model": "-"}

    combos = [(m, p) for m in models for p in API_PATHS]

    def try_combo(model, path):
        body = {
            "model": model,
            "max_tokens": 200,
            "stream": True,
            "messages": [{"role": "user", "content": "Hi"}],
        }
        r = _test_url(base + path, headers, body)
        r["path"] = path
        r["model"] = model
        return r

    with ThreadPoolExecutor(max_workers=len(combos)) as pool:
        futures = {pool.submit(try_combo, m, p): f"{m} {p}"
                   for m, p in combos}
        errors = []
        for future in as_completed(futures):
            label = futures[future]
            try:
                r = future.result()
                result.update(r)
                result["status"] = "✅"
                return result
            except Exception as e:
                errors.append(f"{label}: {e}")

    result["response"] = " | ".join(errors)
    return result


def test_single_config_cli(name, settings_path):
    """通过 claude --settings <path> -p "Hi" 测试配置"""
    result = {"name": name, "cli_status": "❌", "cli_total": "-",
              "cli_response": ""}
    t_start = time.time()
    try:
        proc = subprocess.run(
            ["claude", "--settings", settings_path, "-p", "Hi"],
            capture_output=True, text=True, timeout=120,
            shell=True, encoding="utf-8", errors="replace",
        )
        total = time.time() - t_start
        result["cli_total"] = f"{total:.2f}s"
        output = proc.stdout.strip()
        if proc.returncode == 0 and output:
            result["cli_status"] = "✅"
            result["cli_response"] = output
        else:
            result["cli_response"] = proc.stderr.strip() or "无输出"
    except subprocess.TimeoutExpired:
        result["cli_total"] = f"{time.time() - t_start:.2f}s"
        result["cli_response"] = "超时(120s)"
    except Exception as e:
        result["cli_total"] = f"{time.time() - t_start:.2f}s"
        result["cli_response"] = str(e)
    return result


def load_test_configs():
    """从 config.json 和 settings 文件中加载测试配置列表"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(script_dir, "config.json")
    settings_dir = os.path.join(script_dir, "settings")
    home_dir = os.path.expanduser("~\\.claude")

    with open(config_file, "r", encoding="utf-8") as f:
        app_config = json.load(f)

    test_list = []
    for entry in app_config["configs"]:
        filename = entry["filename"]
        path = os.path.join(settings_dir, filename)
        if not os.path.exists(path):
            path = os.path.join(home_dir, filename)
            if not os.path.exists(path):
                continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            base_url = cfg.get("env", {}).get("ANTHROPIC_BASE_URL", "")
            api_key = cfg.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
            cfg_model = (cfg.get("model")
                         or cfg.get("env", {}).get("ANTHROPIC_MODEL"))
            # 有明确的非标模型就只测那个，否则测三种常见模型
            if cfg_model and cfg_model not in FALLBACK_MODELS:
                models = [cfg_model]
            else:
                models = FALLBACK_MODELS
            if base_url and api_key:
                test_list.append((entry["name"], base_url, api_key, models, path))
        except Exception:
            continue
    return test_list


# --------------- GUI 部分（被 main.py 导入时使用） ---------------

from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QPushButton)
from PyQt5.QtCore import QThread, pyqtSignal


class _TestWorker(QThread):
    """QThread 包装，内部调用 test_single_config"""
    finished = pyqtSignal(int, dict)

    def __init__(self, row, name, base_url, api_key, model):
        super().__init__()
        self.row = row
        self.args = (name, base_url, api_key, model)

    def run(self):
        result = test_single_config(*self.args)
        self.finished.emit(self.row, result)


class _CLITestWorker(QThread):
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

    def __init__(self, test_configs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CC Switch - 配置可用性测试")
        self.workers = []
        self.cli_workers = []
        self._test_configs = test_configs

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
        self._done_count = 0
        self._total = len(self._test_configs) * 2

        n = len(self._test_configs)
        self.table.setRowCount(n * 2)
        C = self.COL

        for i, cfg in enumerate(self._test_configs):
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

            worker = _TestWorker(i, name, base_url, api_key, models)
            worker.finished.connect(self._on_http_done)
            self.workers.append(worker)

            cli_worker = _CLITestWorker(i, name, settings_path)
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


# --------------- CLI 模式 ---------------

if __name__ == "__main__":
    configs = load_test_configs()
    if not configs:
        print("未找到可测试的配置")
        sys.exit(1)

    print(f"开始测试 {len(configs)} 个配置 (HTTP + CLI)...\n")

    # 并发跑 HTTP 测试
    http_results = {}
    with ThreadPoolExecutor(max_workers=len(configs)) as pool:
        futures = {
            pool.submit(test_single_config, c[0], c[1], c[2], c[3]): c[0]
            for c in configs
        }
        for future in as_completed(futures):
            name = futures[future]
            http_results[name] = future.result()

    # 并发跑 CLI 测试
    cli_results = {}
    with ThreadPoolExecutor(max_workers=min(len(configs), 4)) as pool:
        futures = {
            pool.submit(test_single_config_cli, c[0], c[4]): c[0]
            for c in configs
        }
        for future in as_completed(futures):
            name = futures[future]
            cli_results[name] = future.result()

    # 按原始顺序输出
    for c in configs:
        name = c[0]
        h = http_results[name]
        cl = cli_results[name]
        print(f"{'='*60}")
        print(f"  {name}")
        print(f"  [HTTP] {h['status']}  模型: {h.get('model','-')}  路径: {h.get('path','-')}")
        print(f"         首字: {h['ttft']}  字数: {h['length']}  总耗时: {h['total']}  速度: {h['speed']}")
        print(f"         响应: {h['response'][:80]}")
        print(f"  [CLI]  {cl['cli_status']}  耗时: {cl['cli_total']}")
        print(f"         响应: {cl['cli_response'][:80]}")

    print(f"{'='*60}")
    print("测试完成")
