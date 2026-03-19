import sys
import os
import json
import glob
import subprocess
import webbrowser
from urllib.parse import urlparse
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QAction,
                             QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QDialogButtonBox, QLabel, QMessageBox)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt
from test_configs import TestAllDialog

# 自动切换到脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


APP_CONFIG = load_config()
SETTINGS_DIR = os.path.expanduser(APP_CONFIG["settings_dir"])
LOCAL_SETTINGS_DIR = os.path.join(SCRIPT_DIR, "settings")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")
CONFIGS = APP_CONFIG["configs"]
KNOWN_ENV_KEYS = set(APP_CONFIG["known_env_keys"])


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find_cfg_path(filename):
    """查找配置文件路径，优先项目 settings/ 目录，其次家目录"""
    local_path = os.path.join(LOCAL_SETTINGS_DIR, filename)
    if os.path.exists(local_path):
        return local_path
    home_path = os.path.join(SETTINGS_DIR, filename)
    if os.path.exists(home_path):
        return home_path
    return None


def extract_website(base_url):
    """从 base_url 提取 scheme://host 作为 website"""
    parsed = urlparse(base_url)
    if parsed.scheme and parsed.hostname:
        port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}"
    return base_url


def derive_name(filename):
    """从文件名推导显示名称: settings-foo-bar.json -> foo-bar"""
    name = filename
    if name.startswith("settings-"):
        name = name[len("settings-"):]
    if name.endswith(".json"):
        name = name[:-len(".json")]
    return name or filename


def auto_discover_configs():
    """扫描 settings/ 和 ~/.claude/ 下的 settings-*.json，自动补充未登记的条目并回写 config.json"""
    known_filenames = {entry["filename"] for entry in CONFIGS}
    discovered = []

    # 扫描两个目录
    for scan_dir in [LOCAL_SETTINGS_DIR, SETTINGS_DIR]:
        if not os.path.isdir(scan_dir):
            continue
        for filepath in glob.glob(os.path.join(scan_dir, "settings-*.json")):
            filename = os.path.basename(filepath)
            if filename in known_filenames:
                continue
            # 避免两个目录重复发现同名文件
            known_filenames.add(filename)
            try:
                cfg = read_json(filepath)
                base_url = cfg.get("env", {}).get("ANTHROPIC_BASE_URL", "")
                entry = {
                    "name": derive_name(filename),
                    "filename": filename,
                    "website": extract_website(base_url) if base_url else "",
                    "base_url": base_url,
                }
                discovered.append(entry)
            except Exception:
                continue

    if discovered:
        CONFIGS.extend(discovered)
        # 回写 config.json 持久化
        APP_CONFIG["configs"] = CONFIGS
        write_json(CONFIG_FILE, APP_CONFIG)

    return discovered


def detect_current(settings):
    """根据当前 settings.json 的 env 匹配到哪个配置"""
    cur_url = settings.get("env", {}).get("ANTHROPIC_BASE_URL", "")
    cur_token = settings.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
    for entry in CONFIGS:
        cfg_path = find_cfg_path(entry["filename"])
        if not cfg_path:
            continue
        cfg = read_json(cfg_path)
        cfg_url = cfg.get("env", {}).get("ANTHROPIC_BASE_URL", "")
        cfg_token = cfg.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
        if cur_url == cfg_url and cur_token == cfg_token:
            return entry["name"]
    return None


def switch_config(target_filename):
    """将目标配置文件的 env 和 model 覆盖到 settings.json，清除多余 env 变量"""
    target_path = find_cfg_path(target_filename)
    if not target_path:
        raise FileNotFoundError(f"找不到配置文件: {target_filename}")
    target = read_json(target_path)
    current = read_json(SETTINGS_FILE)

    # 用目标的 env 完全替换，但只保留已知的 env 键
    new_env = {}
    for k, v in target.get("env", {}).items():
        if k in KNOWN_ENV_KEYS:
            new_env[k] = v
    current["env"] = new_env

    # 覆盖 model（如果目标有 model 字段就覆盖，没有就删除）
    if "model" in target:
        current["model"] = target["model"]
    elif "model" in current:
        del current["model"]

    write_json(SETTINGS_FILE, current)


def create_icon(letter="C", bg_color="#6B4C9A", fg_color="#FFFFFF"):
    """创建一个带字母的托盘图标"""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(bg_color))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 12, 12)
    painter.setPen(QColor(fg_color))
    font = QFont("Consolas", 36, QFont.Bold)
    painter.setFont(font)
    painter.drawText(0, 0, size, size, Qt.AlignCenter, letter)
    painter.end()
    return QIcon(pixmap)


class AddConfigDialog(QDialog):
    """新增配置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增 API 配置")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        # 说明
        tip = QLabel("Base URL 和 API Key 为必填项，其他字段可留空自动推导。")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 表单
        form = QFormLayout()

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.example.com")
        form.addRow("Base URL *", self.base_url_input)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-...")
        form.addRow("API Key *", self.api_key_input)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("留空则从 Base URL 域名推导")
        form.addRow("名称", self.name_input)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("留空则不指定，如 claude-sonnet-4-20250514")
        form.addRow("Model", self.model_input)

        layout.addLayout(form)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self):
        base_url = self.base_url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        if not base_url:
            QMessageBox.warning(self, "提示", "Base URL 不能为空")
            return
        if not api_key:
            QMessageBox.warning(self, "提示", "API Key 不能为空")
            return
        self.accept()

    def get_values(self):
        base_url = self.base_url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        name = self.name_input.text().strip()
        model = self.model_input.text().strip()

        # 自动推导 name
        if not name:
            parsed = urlparse(base_url)
            name = parsed.hostname or base_url

        return {
            "base_url": base_url,
            "api_key": api_key,
            "name": name,
            "model": model,
        }


class CCSwitch:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(create_icon("C"))
        self.tray.activated.connect(self.on_activated)

        self.current_name = None
        auto_discover_configs()
        self.build_menu()
        self.tray.show()

    def create_check_icon(self):
        """创建一个圆点图标用于标记当前配置"""
        size = 16
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#000000"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 8, 8)
        painter.end()
        return QIcon(pixmap)

    def build_menu(self):
        """构建/重建托盘菜单"""
        settings = read_json(SETTINGS_FILE)
        self.current_name = detect_current(settings)

        menu = QMenu()

        # 配置切换区（子菜单）
        for entry in CONFIGS:
            name = entry["name"]
            filename = entry["filename"]
            website = entry.get("website", "")
            cfg_path = find_cfg_path(filename)
            if not cfg_path:
                continue

            submenu = menu.addMenu(name)
            if name == self.current_name:
                submenu.setIcon(self.create_check_icon())

            # 切换到此配置
            switch_action = QAction("切换到此配置", submenu)
            switch_action.triggered.connect(
                lambda checked, fn=filename, n=name: self.on_switch(fn, n)
            )
            submenu.addAction(switch_action)

            # 复制启动参数
            copy_action = QAction("复制启动参数", submenu)
            copy_action.triggered.connect(
                lambda checked, p=cfg_path: self.copy_settings_arg(p)
            )
            submenu.addAction(copy_action)

            # 打开配置文件（悬浮预览路径和内容）
            open_action = QAction("打开配置文件", submenu)
            open_action.triggered.connect(
                lambda checked, p=cfg_path: os.startfile(p)
            )
            try:
                cfg_content = read_json(cfg_path)
                preview = json.dumps(cfg_content, indent=2, ensure_ascii=False)
                if len(preview) > 1500:
                    preview = preview[:1500] + "\n..."
                open_action.setToolTip(f"📁 {cfg_path}\n\n{preview}")
            except Exception:
                open_action.setToolTip(f"📁 {cfg_path}\n\n(无法读取文件内容)")
            submenu.setToolTipsVisible(True)
            submenu.addAction(open_action)

            # 访问官网
            if website:
                web_action = QAction("访问官网", submenu)
                web_action.triggered.connect(
                    lambda checked, url=website: webbrowser.open(url)
                )
                submenu.addAction(web_action)

        menu.addSeparator()

        # 测试所有配置
        test_action = QAction("测试所有配置(&T)...", menu)
        test_action.triggered.connect(self.on_test_all)
        menu.addAction(test_action)

        # 新增配置
        add_action = QAction("新增配置(&A)...", menu)
        add_action.triggered.connect(self.on_add_config)
        menu.addAction(add_action)

        menu.addSeparator()

        # 重启
        restart_action = QAction("重启程序(&R)", menu)
        restart_action.triggered.connect(self.restart)
        menu.addAction(restart_action)

        # 退出
        quit_action = QAction("退出(&E)", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.update_tooltip()

    def update_tooltip(self):
        tip = f"CC Switch - 当前: {self.current_name or '未知'}"
        self.tray.setToolTip(tip)

    def on_activated(self, reason):
        """左键单击也弹出菜单"""
        if reason == QSystemTrayIcon.Trigger:
            menu = self.tray.contextMenu()
            if menu:
                # 在鼠标位置显示菜单
                from PyQt5.QtGui import QCursor
                menu.popup(QCursor.pos())

    def copy_settings_arg(self, settings_path):
        """复制 --settings <path> 到剪贴板"""
        text = f"--settings {settings_path}"
        QApplication.clipboard().setText(text)
        self.tray.showMessage("CC Switch", f"已复制: {text}",
                              QSystemTrayIcon.Information, 2000)

    def on_switch(self, filename, name):
        if name == self.current_name:
            return
        try:
            switch_config(filename)
            self.current_name = name
            self.update_tooltip()
            self.build_menu()
            self.tray.showMessage("CC Switch", f"已切换到: {name}",
                                  QSystemTrayIcon.Information, 2000)
        except Exception as e:
            self.tray.showMessage("CC Switch 错误", str(e),
                                  QSystemTrayIcon.Critical, 3000)

    def on_test_all(self):
        """弹出测试对话框"""
        from test_configs import FALLBACK_MODELS
        test_list = []
        for entry in CONFIGS:
            cfg_path = find_cfg_path(entry["filename"])
            if not cfg_path:
                continue
            try:
                cfg = read_json(cfg_path)
                base_url = cfg.get("env", {}).get("ANTHROPIC_BASE_URL", "")
                api_key = cfg.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
                cfg_model = (cfg.get("model")
                             or cfg.get("env", {}).get("ANTHROPIC_MODEL"))
                if cfg_model and cfg_model not in FALLBACK_MODELS:
                    models = [cfg_model]
                else:
                    models = FALLBACK_MODELS
                if base_url and api_key:
                    test_list.append((entry["name"], base_url, api_key, models))
            except Exception:
                continue
        dlg = TestAllDialog(test_list)
        dlg.exec_()

    def on_add_config(self):
        """弹出对话框新增配置"""
        dlg = AddConfigDialog()
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.get_values()

        # 生成文件名 slug：取域名，替换特殊字符
        parsed = urlparse(values["base_url"])
        slug = (parsed.hostname or "custom").replace(".", "-")
        filename = f"settings-{slug}.json"

        # 避免文件名冲突，加数字后缀
        existing_filenames = {entry["filename"] for entry in CONFIGS}
        if filename in existing_filenames:
            i = 2
            while f"settings-{slug}-{i}.json" in existing_filenames:
                i += 1
            filename = f"settings-{slug}-{i}.json"

        # 生成 settings 文件内容
        settings_content = {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": values["api_key"],
                "ANTHROPIC_BASE_URL": values["base_url"],
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            }
        }
        if values["model"]:
            settings_content["model"] = values["model"]

        # 写入 settings/ 目录
        os.makedirs(LOCAL_SETTINGS_DIR, exist_ok=True)
        settings_path = os.path.join(LOCAL_SETTINGS_DIR, filename)
        write_json(settings_path, settings_content)

        # 追加到 config.json
        new_entry = {
            "name": values["name"],
            "filename": filename,
            "website": extract_website(values["base_url"]),
            "base_url": values["base_url"],
        }
        CONFIGS.append(new_entry)
        APP_CONFIG["configs"] = CONFIGS
        write_json(CONFIG_FILE, APP_CONFIG)

        # 刷新菜单
        self.build_menu()
        self.tray.showMessage("CC Switch", f"已新增配置: {values['name']}",
                              QSystemTrayIcon.Information, 2000)

    def restart(self):
        """重启程序"""
        python = sys.executable
        script = os.path.abspath(__file__)
        subprocess.Popen([python, script],
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        self.quit()

    def quit(self):
        self.tray.hide()
        QApplication.instance().quit()

    def run(self):
        sys.exit(self.app.exec_())


if __name__ == "__main__":
    switch = CCSwitch()
    switch.run()
