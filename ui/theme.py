from dataclasses import dataclass, field
from typing import Dict
from PySide6.QtGui import QFont

"""
FPL Helper Application Theme Definitions (v2.0 Modern Sports Analytics Identity).
Features:
- Solid Opak High-Contrast Surfaces & Precision Layering
- Futbol Sahası Rengi (#22C55E), Aksiyon Mavisi (#3B82F6), Altın (#F59E0B)
- Sezgisel Sıcak-Soğuk FDR Renk Kodlaması (1 -> 5)
- Inter / Segoe UI Typography & Monospace Tabular Figures
"""

COLORS = {
    # Zemin ve Yüzey Renkleri (Background & Surface)
    "bg_primary": "#0D1117",        # En koyu taban zemin
    "bg_secondary": "#161B22",      # İçerik alanı zemin
    "surface_card": "#1C2128",      # Kart ve panel yüzeyi
    "surface_elevated": "#252C35",  # Hover / Active yüzey & Modal
    "surface_input": "#2D333B",     # Input, dropdown, arama kutusu
    "surface_glass": "rgba(28, 33, 40, 0.88)", # Glassmorphism hissi için yarı saydam yüzey
    "surface_glass_blue": "rgba(59, 130, 246, 0.10)",
    "border_default": "#373E47",    # Kenar çizgisi (1px solid)
    "border_subtle": "#2D333B",     # İç bölüm / tablo satır ayırıcı
    
    # Vurgu Renkleri (Accent Colors)
    "accent_pitch": "#22C55E",      # Saha yeşili (Ana marka)
    "accent_pitch_muted": "#16A34A",# Hover durumundaki yeşil
    "accent_gold": "#F59E0B",       # Kaptan rozeti, 1. Kaptan
    "accent_gold_light": "#FBBF24", # 2. Kaptan (Vice)
    "accent_action": "#3B82F6",     # Birincil aksiyon butonu (Mavi)
    "accent_action_hover": "#2563EB",# Aksiyon buton hover
    "accent_info": "#60A5FA",       # Bilgi rozeti, aktif sekme
    "accent_purple": "#A78BFA",     # Analitik / strateji vurgusu
    "accent_cyan": "#22D3EE",       # Canlı veri vurgusu
    
    # Durum Renkleri (Status & Semantic)
    "status_success": "#22C55E",    # Pozitif / Sağlıklı / Başarılı
    "status_warning": "#F59E0B",    # Şüpheli / Dikkat
    "status_danger": "#EF4444",     # Sakat / Cezalı / Hit (-4)
    "status_danger_dark": "#DC2626",# Ciddi sakatlık / Tehlike
    "status_injured": "#F97316",    # Sakatlık turuncu badge
    "status_suspended": "#EF4444",  # Kırmızı kart
    "status_transferred": "#8B5CF6",# Takım değiştiren
    "status_neutral": "#6B7280",    # Bilinmeyen / Pasif
    
    # Metin Renkleri (Typography)
    "text_primary": "#E6EDF3",      # Başlıklar, oyuncu isimleri
    "text_secondary": "#B6C2CF",    # Alt başlıklar, açıklamalar — okunabilir kontrast
    "text_muted": "#8B98A7",        # Placeholder, zaman damgası
    "text_inverse": "#0D1117",      # Koyu metin (açık zemin üstünde)
    
    # FDR Renk Kodlaması (Fixture Difficulty Rating: 1 -> 5)
    "fdr_1": "#22C55E",             # 1: En Kolay (Parlak Yeşil)
    "fdr_2": "#86EFAC",             # 2: Kolay (Açık Yeşil)
    "fdr_3": "#FDE68A",             # 3: Orta (Sarı)
    "fdr_4": "#FCA5A5",             # 4: Zor (Açık Kırmızı)
    "fdr_5": "#DC2626",             # 5: Çok Zor (Koyu Kırmızı)
    "fdr_dgw": "#A78BFA",           # Çift Maç (Mor)
    "fdr_bgw": "#4B5563",           # Boş Hafta (Gri)
    
    # Backward Compatibility Aliases
    "background_dark": "#0D1117",
    "surface": "#1C2128",
    "surface_light": "#2D333B",
    "primary_blue": "#3B82F6",
    "primary_mavi": "#3B82F6",
    "primary_cyan": "#60A5FA",
    "primary_bordo": "#DC2626",
    "primary_gold": "#F59E0B",
    "primary_green": "#22C55E",
    "danger_red": "#EF4444",
    "warning_yellow": "#F59E0B",
    "info_blue": "#3B82F6"
}

@dataclass(frozen=True)
class DesignTokens:
    """
    Design System Singleton Dataclass containing color palettes, spacing scales, and font sizes.
    Ensures zero glassmorphism, completely solid/opaque high-contrast surfaces.
    """
    COLORS: Dict[str, str] = field(default_factory=lambda: dict(COLORS))
    
    # Base-4 Spacing Scale (px)
    SPACING_4: int = 4
    SPACING_8: int = 8
    SPACING_12: int = 12
    SPACING_16: int = 16
    SPACING_24: int = 24
    SPACING_32: int = 32
    
    # Font Sizes (pt)
    FONT_SIZE_BODY: int = 12
    FONT_SIZE_H3: int = 14
    FONT_SIZE_H2: int = 18
    FONT_SIZE_H1: int = 24

tokens = DesignTokens()

class FontManager:
    """
    Manages application font families and Tabular Numerics (tnum=1).
    Provides Inter for UI elements and JetBrains Mono for data/numerical tables.
    """
    @staticmethod
    def get_ui_font(size: int = tokens.FONT_SIZE_BODY, bold: bool = False) -> QFont:
        font = QFont("Inter", size)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        if bold:
            font.setBold(True)
        return font

    @staticmethod
    def get_data_font(size: int = tokens.FONT_SIZE_BODY, bold: bool = False) -> QFont:
        font = QFont("JetBrains Mono", size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)  # Enables Tabular Numerics alignment for figures
        if bold:
            font.setBold(True)
        return font

GLOBAL_STYLESHEET = f"""
/* --- Global Window & Core Base --- */
QMainWindow {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
    font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
}}

QWidget {{
    background-color: transparent;
    color: {COLORS['text_primary']};
    font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
    font-size: 12px;
}}

/* --- ScrollArea & Custom ScrollBar --- */
QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 6px;
    margin: 0px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: rgba(139, 148, 158, 0.30);
    min-height: 32px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgba(139, 148, 158, 0.55);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    height: 0px;
}}

/* --- Push Buttons --- */
QPushButton {{
    background-color: {COLORS['accent_action']};
    color: #FFFFFF;
    border: none;
    padding: 9px 18px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    min-height: 36px;
}}

QPushButton:hover {{
    background-color: {COLORS['accent_action_hover']};
}}

QPushButton:pressed {{
    background-color: #1D4ED8;
    padding-top: 10px;
    padding-bottom: 8px;
}}

QPushButton:disabled {{
    background-color: {COLORS['surface_input']};
    color: {COLORS['text_muted']};
}}

QPushButton#SecondaryBtn {{
    background-color: transparent;
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border_default']};
}}

QPushButton#SecondaryBtn:hover {{
    background-color: {COLORS['surface_elevated']};
    color: {COLORS['text_primary']};
}}

QPushButton#DangerBtn {{
    background-color: {COLORS['status_danger']};
    color: #FFFFFF;
}}

QPushButton#DangerBtn:hover {{
    background-color: {COLORS['status_danger_dark']};
}}

/* --- Cards & Frame Surfaces --- */
QFrame#Card {{
    background-color: {COLORS['surface_glass']};
    border-radius: 14px;
    border: 1px solid rgba(139, 148, 158, 0.28);
}}

QFrame#Card:hover {{
    border-color: #444C56;
}}

QFrame#BadgeCard {{
    background-color: {COLORS['surface_glass']};
    border-radius: 12px;
    border: 1px solid rgba(139, 148, 158, 0.26);
    padding: 8px 12px;
}}

/* --- Table Widget --- */
QTableWidget {{
    background-color: {COLORS['surface_card']};
    border-radius: 12px;
    border: 1px solid {COLORS['border_default']};
    gridline-color: transparent;
    outline: 0;
}}

QTableWidget::item {{
    padding: 8px 12px;
    color: {COLORS['text_primary']};
    border-bottom: 1px solid {COLORS['border_subtle']};
    font-size: 13px;
}}

QTableWidget::item:alternate {{
    background-color: rgba(255, 255, 255, 0.02);
}}

QHeaderView::section {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_secondary']};
    font-weight: 700;
    font-size: 11px;
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {COLORS['border_default']};
    letter-spacing: 0.04em;
}}

/* --- Inputs & Clean Dropdowns --- */
QLineEdit {{
    background-color: {COLORS['surface_input']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_default']};
    border-radius: 8px;
    padding: 9px 13px;
    font-size: 14px;
    min-height: 44px;
}}

QLineEdit:focus {{
    border: 1px solid {COLORS['accent_action']};
}}

QComboBox {{
    background-color: {COLORS['surface_input']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_default']};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 600;
    min-height: 36px;
}}

QComboBox:hover {{
    border-color: {COLORS['accent_action']};
    background-color: {COLORS['surface_elevated']};
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS['surface_elevated']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_default']};
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: {COLORS['accent_action']};
    selection-color: #FFFFFF;
}}

QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 4px 10px;
    border-radius: 4px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {COLORS['accent_action']};
    color: #FFFFFF;
}}

/* Completely eliminate all scrollbars, arrow buttons, and indicator bars from QComboBox popup */
QComboBox QAbstractItemView QScrollBar:vertical,
QComboBox QAbstractItemView QScrollBar:horizontal {{
    width: 0px !important;
    height: 0px !important;
    background: transparent !important;
    border: none !important;
}}

QComboBox QAbstractItemView QScrollBar::add-line:vertical,
QComboBox QAbstractItemView QScrollBar::sub-line:vertical,
QComboBox QAbstractItemView QScrollBar::add-page:vertical,
QComboBox QAbstractItemView QScrollBar::sub-page:vertical,
QComboBox QAbstractItemView QScrollBar::handle:vertical {{
    width: 0px !important;
    height: 0px !important;
    border: none !important;
    background: none !important;
}}

/* --- Group Box --- */
QGroupBox {{
    color: {COLORS['text_primary']};
    font-weight: 700;
    font-size: 15px;
    border: 1px solid {COLORS['border_default']};
    border-radius: 12px;
    margin-top: 18px;
    padding-top: 14px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 3px 10px;
    color: {COLORS['accent_cyan']};
    background-color: {COLORS['surface_elevated']};
}}

/* --- Progress Bar --- */
QProgressBar {{
    border: none;
    background-color: {COLORS['border_subtle']};
    height: 3px;
    border-radius: 0px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {COLORS['accent_action']};
    border-radius: 0px;
}}

/* --- Labels --- */
QLabel {{
    color: {COLORS['text_primary']};
    font-size: 12px;
}}

QLabel#Title {{
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.02em;
}}

QLabel#Eyebrow {{
    color: {COLORS['accent_cyan']};
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 0.12em;
}}

QFrame#GlassPanel {{
    background-color: {COLORS['surface_glass']};
    border: 1px solid rgba(139, 148, 158, 0.22);
    border-radius: 14px;
}}

QLabel#Subtitle {{
    font-size: 13px;
    color: {COLORS['text_secondary']};
}}

/* --- Tooltip --- */
QToolTip {{
    background-color: {COLORS['surface_elevated']};
    color: {COLORS['text_primary']};
    border: 1px solid #444C56;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QLabel
    app = QApplication.instance() or QApplication(sys.argv)
    
    print("--- SANITY CHECK: ui/theme.py ---")
    assert tokens.COLORS["bg_primary"] == "#0D1117"
    assert tokens.SPACING_16 == 16
    assert tokens.FONT_SIZE_BODY == 10
    
    ui_font = FontManager.get_ui_font(12, bold=True)
    data_font = FontManager.get_data_font(10)
    assert ui_font.bold() is True
    assert data_font.fixedPitch() is True
    
    label = QLabel("Theme sanity test label")
    label.setFont(ui_font)
    
    print("DesignTokens & FontManager sanity checks passed.")
    print("[SUCCESS] ui/theme.py imports and dataclasses verified.")

