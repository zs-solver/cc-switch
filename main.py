import sys
import os
import json
import subprocess
import webbrowser
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QAction)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt

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


class CCSwitch:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(create_icon("C"))
        self.tray.activated.connect(self.on_activated)

        self.current_name = None
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
