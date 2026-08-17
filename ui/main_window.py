import os
import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QStackedWidget, QLabel, QFrame, QSizePolicy,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QDateTime, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtGui import QIcon
from ui.theme import GLOBAL_STYLESHEET, COLORS

class MainWindow(QMainWindow):
    """
    Ultra-Premium 2026 Sports Analytics Desktop Main Window.
    Features:
    - 52px Sticky Top Navigation Bar with 5 Navigation Tabs (🏠 Ana Sayfa, 📋 Kadro, 💡 Öneriler, 📊 FDR, ⚙ Ayarlar)
    - 28px Bottom Status Bar with live API indicator
    - Clean Qt close event triggering graceful shutdown in main.py
    """
    refresh_requested = Signal()
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FPL Akıllı Kadro Yöneticisi")
        self.setMinimumSize(1024, 720)
        self.resize(1280, 800)
        self.setStyleSheet(GLOBAL_STYLESHEET)
        
        # Set App Icon
        icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "fpl_ts_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # --- 1. Top Navigation Bar (Distinctive Header Surface) ---
        self.top_nav = QFrame()
        self.top_nav.setFixedHeight(68)
        self.top_nav.setStyleSheet(f"""
            QFrame {{
                background-color: #0B1320;
                border-bottom: 2px solid #1E293B;
                border-radius: 0px;
            }}
        """)
        
        nav_layout = QHBoxLayout(self.top_nav)
        nav_layout.setContentsMargins(16, 0, 16, 0)
        nav_layout.setSpacing(10)
        
        # App Logo & Title (Branded Badge Panel)
        self.logo_frame = QFrame()
        self.logo_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 rgba(16, 185, 129, 0.18), stop: 1 rgba(59, 130, 246, 0.18));
                border: 1px solid rgba(16, 185, 129, 0.45);
                border-radius: 12px;
            }}
        """)
        logo_layout = QHBoxLayout(self.logo_frame)
        self.logo_frame.setFixedSize(168, 44)
        logo_layout.setContentsMargins(10, 4, 10, 4)
        logo_layout.setSpacing(6)
        
        self.lbl_logo = QLabel("⚽  <span style='color: #E11D48; font-weight: 900; font-size: 18px;'>F</span><span style='color: #38BDF8; font-weight: 900; font-size: 18px;'>P</span><span style='color: #FBBF24; font-weight: 900; font-size: 18px;'>L</span> <span style='color: #FFFFFF; font-weight: 900; font-size: 16px; letter-spacing: 0.05em;'>HELPER</span>")
        self.lbl_logo.setTextFormat(Qt.RichText)
        self.lbl_logo.setStyleSheet("background: transparent; border: none;")
        logo_layout.addWidget(self.lbl_logo)
        
        nav_layout.addWidget(self.logo_frame)
        
        # Vertical Separator Line between Logo and Tabs
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: #1E293B; max-width: 1px; min-height: 28px; margin: 0px 6px;")
        nav_layout.addWidget(sep)
        
        # 5 Navigation Buttons
        self.nav_buttons = []
        tab_names = [
            ("🏠 ANA SAYFA", 0),
            ("📋 KADRO", 1),
            ("💡 ÖNERİLER", 2),
            ("📊 FDR", 3),
            ("⚙ AYARLAR", 4)
        ]
        
        for text, index in tab_names:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(126, 42)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255, 255, 255, 0.04);
                    color: {COLORS['text_secondary']};
                    font-size: 13px;
                    font-weight: 800;
                    letter-spacing: 0.01em;
                    padding: 4px 6px;
                    border: 1px solid rgba(148, 163, 184, 0.14);
                    border-radius: 9px;
                    text-align: center;
                }}
                QPushButton:hover {{
                    color: #FFFFFF;
                    background-color: {COLORS['surface_elevated']};
                    border-color: {COLORS['accent_action']};
                }}
                QPushButton:checked {{
                    color: #FFFFFF;
                    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 {COLORS['accent_action']}, stop: 1 #2563EB);
                    border: 1px solid #93C5FD;
                    font-weight: 900;
                }}
            """)
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)
            
        self.nav_buttons[0].setChecked(True)
        nav_layout.addStretch()
        
        # Clean Text Status Indicator (Directly beside refresh button)
        self.lbl_status = QLabel("● Canlı Veri")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.lbl_status.setFixedHeight(36)
        self.lbl_status.setStyleSheet(f"""
            color: #10B981;
            font-size: 13px;
            font-weight: 800;
            background: transparent;
            border: none;
            padding: 0px 10px 0px 0px;
        """)
        nav_layout.addWidget(self.lbl_status, 0, Qt.AlignmentFlag.AlignVCenter)
        
        self.btn_refresh = QPushButton("↻ Yenile")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_refresh.setFixedHeight(36)
        self.btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['surface_elevated']};
                color: #F1F5F9;
                font-weight: 800;
                font-size: 13px;
                padding: 0px 16px;
                border-radius: 8px;
                border: 1px solid {COLORS['border_default']};
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {COLORS['surface_input']};
                border-color: {COLORS['accent_action']};
                color: #FFFFFF;
            }}
            QPushButton:disabled {{
                background-color: {COLORS['surface_input']};
                color: {COLORS['text_muted']};
            }}
        """)
        nav_layout.addWidget(self.btn_refresh, 0, Qt.AlignmentFlag.AlignVCenter)
        
        self.main_layout.addWidget(self.top_nav)

        # Animation timer for refreshing state
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._dot_count = 0
        
        # --- 2. Stacked Content Area (5 Pages) ---
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("PageStack")
        self.stacked_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._page_opacity = QGraphicsOpacityEffect(self.stacked_widget)
        self._page_opacity.setOpacity(1.0)
        self.stacked_widget.setGraphicsEffect(self._page_opacity)
        self._page_fade = QPropertyAnimation(self._page_opacity, b"opacity", self)
        self._page_fade.setDuration(180)
        self._page_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.main_layout.addWidget(self.stacked_widget, stretch=1)
        
        # --- 3. Bottom Status Bar (28px) ---
        self.status_bar = QFrame()
        self.status_bar.setFixedHeight(26)
        self.status_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_primary']};
                border-top: 1px solid {COLORS['border_subtle']};
            }}
        """)
        
        sb_layout = QHBoxLayout(self.status_bar)
        sb_layout.setContentsMargins(16, 0, 16, 0)
        
        self.lbl_sb_left = QLabel("Son güncelleme: --:--")
        self.lbl_sb_left.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px; font-weight: 600;")
        
        self.lbl_sb_center = QLabel("● FPL bağlantısı: Hazır  •  Motor çalışıyor")
        self.lbl_sb_center.setStyleSheet(f"color: {COLORS['status_success']}; font-size: 12px; font-weight: 700;")
        
        self.lbl_sb_right = QLabel("Sezon öncesi  •  Sınırsız transfer")
        self.lbl_sb_right.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px; font-weight: 600;")
        
        sb_layout.addWidget(self.lbl_sb_left)
        sb_layout.addStretch()
        sb_layout.addWidget(self.lbl_sb_center)
        sb_layout.addStretch()
        sb_layout.addWidget(self.lbl_sb_right)
        
        self.main_layout.addWidget(self.status_bar)

    def _connect_signals(self):
        for index, btn in enumerate(self.nav_buttons):
            btn.clicked.connect(lambda _, idx=index: self.switch_tab(idx))
            
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)

    def switch_tab(self, index: int):
        if 0 <= index < self.stacked_widget.count():
            if self.stacked_widget.currentIndex() == index:
                # Ensure the button remains checked
                for idx, btn in enumerate(self.nav_buttons):
                    btn.setChecked(idx == index)
                return
            
            self.stacked_widget.setCurrentIndex(index)
            for idx, btn in enumerate(self.nav_buttons):
                btn.setChecked(idx == index)
            self._page_fade.stop()
            self._page_opacity.setOpacity(0.72)
            self._page_fade.setStartValue(0.72)
            self._page_fade.setEndValue(1.0)
            self._page_fade.start()

    def _on_anim_tick(self):
        self._dot_count += 1
        dots = "." * ((self._dot_count % 3) + 1)
        self.lbl_status.setText(f"● Güncelleniyor{dots}")
        self.lbl_status.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: 800; background: transparent; border: none; padding-right: 8px;")

    def on_refresh_clicked(self):
        self.btn_refresh.setEnabled(False)
        self._dot_count = 0
        self._on_anim_tick()
        self._anim_timer.start(320)
        self.refresh_requested.emit()

    def set_refresh_completed(self, status_text: str = "● Canlı Veri"):
        if self._anim_timer.isActive():
            self._anim_timer.stop()
        self.lbl_status.setText("● Canlı Veri")
        self.lbl_status.setStyleSheet("color: #10B981; font-size: 13px; font-weight: 800; background: transparent; border: none; padding-right: 8px;")
        self.btn_refresh.setEnabled(True)
        now_str = QDateTime.currentDateTime().toString("hh:mm:ss")
        self.lbl_sb_left.setText(f"Son Güncelleme: {now_str}")

    def closeEvent(self, event):
        """
        Clean Qt close event allowing main.py to handle graceful shutdown.
        """
        event.accept()
        try:
            QApplication.quit()
        except Exception:
            pass
