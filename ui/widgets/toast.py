from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QWidget
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve
from ui.theme import COLORS

class ToastNotification(QFrame):
    """
    Sleek Toast Notification Card (320px wide, top-right overlay).
    Types: success (green), info (blue), warning (yellow), error (red).
    Auto-dismisses after duration_ms (default 4000ms).
    """
    def __init__(self, parent: QWidget, title: str, message: str, toast_type: str = "info", duration_ms: int = 4000):
        super().__init__(parent)
        self.toast_type = toast_type
        self.setFixedWidth(320)
        self.setFrameShape(QFrame.NoFrame)
        
        type_configs = {
            "success": {"border": COLORS['status_success'], "icon": "✅"},
            "info": {"border": COLORS['accent_action'], "icon": "ℹ️"},
            "warning": {"border": COLORS['status_warning'], "icon": "⚠️"},
            "error": {"border": COLORS['status_danger'], "icon": "❌"},
        }
        config = type_configs.get(toast_type, type_configs["info"])
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface_card']};
                border-left: 4px solid {config['border']};
                border-top: 1px solid {COLORS['border_default']};
                border-right: 1px solid {COLORS['border_default']};
                border-bottom: 1px solid {COLORS['border_default']};
                border-radius: 8px;
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)
        
        # Icon Label
        lbl_icon = QLabel(config["icon"])
        lbl_icon.setStyleSheet("font-size: 16px; background: transparent; border: none;")
        layout.addWidget(lbl_icon, alignment=Qt.AlignTop)
        
        # Text Content (Title + Message)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {COLORS['text_primary']}; font-weight: 700; font-size: 13px; background: transparent; border: none;")
        lbl_title.setWordWrap(True)
        
        lbl_msg = QLabel(message)
        lbl_msg.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; background: transparent; border: none;")
        lbl_msg.setWordWrap(True)
        
        text_layout.addWidget(lbl_title)
        text_layout.addWidget(lbl_msg)
        layout.addLayout(text_layout, stretch=1)
        
        # Close Button
        btn_close = QPushButton("✕")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['text_muted']};
                font-weight: 800;
                font-size: 12px;
                border: none;
                padding: 0px;
                min-height: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['text_primary']};
            }}
        """)
        btn_close.clicked.connect(self.dismiss)
        layout.addWidget(btn_close, alignment=Qt.AlignTop)
        
        # Timer for Auto-Dismiss
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        if duration_ms > 0:
            self.timer.start(duration_ms)

    def dismiss(self):
        self.timer.stop()
        self.hide()
        self.deleteLater()


class ToastManager:
    """
    Manager for stacking and displaying Toast notifications in top-right of window.
    """
    def __init__(self, parent_window: QWidget):
        self.parent = parent_window
        self.toasts = []

    def show_toast(self, title: str, message: str, toast_type: str = "info", duration_ms: int = 4000):
        # Create Toast Widget
        toast = ToastNotification(self.parent, title, message, toast_type, duration_ms)
        self.toasts.append(toast)
        
        # Reposition all active toasts
        self._reposition_toasts()
        toast.show()
        toast.raise_()

    def _reposition_toasts(self):
        # Filter out destroyed toasts
        self.toasts = [t for t in self.toasts if t.isVisible()]
        
        parent_rect = self.parent.rect()
        margin_right = 16
        margin_top = 64  # Below TopNav bar
        spacing = 8
        
        current_y = margin_top
        for toast in reversed(self.toasts[-3:]):  # Max 3 visible at once
            x = parent_rect.width() - toast.width() - margin_right
            toast.move(x, current_y)
            current_y += toast.sizeHint().height() + spacing
