from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QDialogButtonBox, QLabel, QMessageBox)
from urllib.parse import urlparse


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
