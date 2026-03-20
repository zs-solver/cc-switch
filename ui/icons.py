from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt


def create_tray_icon(letter="C", bg_color="#6B4C9A", fg_color="#FFFFFF"):
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


def create_check_icon():
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
