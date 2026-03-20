import sys
import os
import json
import subprocess
import webbrowser
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QAction,
                             QDialog)
from PyQt5.QtCore import Qt

from core.config_manager import ConfigManager, read_json
from ui.test_dialog import TestAllDialog
from ui.dialogs import AddConfigDialog
from ui.icons import create_tray_icon, create_check_icon

# 自动切换到脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)


class CCSwitch:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.cm = ConfigManager()
        self.cm.auto_discover()

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(create_tray_icon("C"))
        self.tray.activated.connect(self.on_activated)

        self.current_name = None
        self.build_menu()
        self.tray.show()

    def build_menu(self):
        """构建/重建托盘菜单"""
        self.current_name = self.cm.detect_current()

        menu = QMenu()

        # 配置切换区（子菜单）
        for entry in self.cm.configs:
            name = entry["name"]
            filename = entry["filename"]
            website = entry.get("website", "")
            cfg_path = self.cm.find_cfg_path(filename)
            if not cfg_path:
                continue

            submenu = menu.addMenu(name)
            if name == self.current_name:
                submenu.setIcon(create_check_icon())

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
            self.cm.switch(filename)
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
        dlg = TestAllDialog(self.cm)
        dlg.exec_()

    def on_add_config(self):
        """弹出对话框新增配置"""
        dlg = AddConfigDialog()
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.get_values()
        self.cm.add(**values)
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
