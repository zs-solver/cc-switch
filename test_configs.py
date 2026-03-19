import sys
import os
import json
import time
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
                test_list.append((entry["name"], base_url, api_key, models))
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


class TestAllDialog(QDialog):
    """配置可用性测试对话框"""
    COLUMNS = ["名称", "状态", "模型", "路径", "首字耗时", "回复字数", "总耗时", "速度", "完整响应"]

    def __init__(self, test_configs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CC Switch - 配置可用性测试")
        self.setMinimumSize(900, 420)
        self.workers = []
        self._test_configs = test_configs

        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
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

    def start_tests(self):
        for w in self.workers:
            if w.isRunning():
                w.terminate()
        self.workers.clear()
        self.retest_btn.setEnabled(False)
        self._done_count = 0
        self._total = len(self._test_configs)

        self.table.setRowCount(self._total)
        for i, (name, base_url, api_key, model) in enumerate(self._test_configs):
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem("⏳"))
            for col in range(2, len(self.COLUMNS)):
                self.table.setItem(i, col, QTableWidgetItem(""))

            worker = _TestWorker(i, name, base_url, api_key, model)
            worker.finished.connect(self.on_test_done)
            self.workers.append(worker)

        for w in self.workers:
            w.start()

    def on_test_done(self, row, result):
        self.table.item(row, 1).setText(result["status"])
        self.table.item(row, 2).setText(result.get("model", "-"))
        self.table.item(row, 3).setText(result.get("path", "-"))
        self.table.item(row, 4).setText(result["ttft"])
        self.table.item(row, 5).setText(result["length"])
        self.table.item(row, 6).setText(result["total"])
        self.table.item(row, 7).setText(result["speed"])
        resp = result["response"]
        display = resp[:50] + "..." if len(resp) > 50 else resp
        self.table.item(row, 8).setText(display)
        self.table.item(row, 8).setToolTip(resp)

        self._done_count += 1
        if self._done_count >= self._total:
            self.retest_btn.setEnabled(True)

    def closeEvent(self, event):
        for w in self.workers:
            if w.isRunning():
                w.terminate()
                w.wait(1000)
        super().closeEvent(event)


# --------------- CLI 模式 ---------------

if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor, as_completed

    configs = load_test_configs()
    if not configs:
        print("未找到可测试的配置")
        sys.exit(1)

    print(f"开始测试 {len(configs)} 个配置...\n")

    with ThreadPoolExecutor(max_workers=len(configs)) as pool:
        futures = {
            pool.submit(test_single_config, *cfg): cfg[0]
            for cfg in configs
        }
        for future in as_completed(futures):
            r = future.result()
            print(f"{'='*60}")
            print(f"  {r['status']}  {r['name']}")
            print(f"  模型: {r.get('model', '-')}  |  路径: {r.get('path', '-')}")
            print(f"  首字耗时: {r['ttft']}  |  回复字数: {r['length']}  |  总耗时: {r['total']}  |  速度: {r['speed']}")
            print(f"  响应: {r['response']}")

    print(f"{'='*60}")
    print("测试完成")
