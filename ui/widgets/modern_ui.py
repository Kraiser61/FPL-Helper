from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, FontManager


class PillBadge(QFrame):
    """Compact, readable status badge for dense recommendation summaries."""

    def __init__(self, text: str, color: str = COLORS['accent_info'], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PillBadge")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"""
            QFrame#PillBadge {{
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid {color};
                border-radius: 9px;
            }}
            QLabel#PillBadgeText {{
                color: {COLORS['text_primary']};
                font-size: 13px;
                font-weight: 800;
                padding: 4px 9px;
            }}
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        label = QLabel(text)
        label.setObjectName("PillBadgeText")
        layout.addWidget(label)


class CollapsiblePanel(QFrame):
    """Accordion panel that keeps content mounted while toggling visibility."""

    def __init__(self, title: str, icon: str, accent: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CollapsiblePanel")
        self._accent = accent
        self._expanded = True
        self.setStyleSheet(
            f"""
            QFrame#CollapsiblePanel {{
                background-color: {COLORS['surface_elevated']};
                border: 1px solid {COLORS['border_subtle']};
                border-left: 3px solid {accent};
                border-radius: 10px;
            }}
            QPushButton#AccordionHeader {{
                background: transparent;
                color: {COLORS['text_primary']};
                border: none;
                text-align: left;
                padding: 13px 14px;
                font-size: 15px;
                font-weight: 900;
            }}
            QPushButton#AccordionHeader:hover {{
                background-color: rgba(255, 255, 255, 0.045);
                border-radius: 8px;
            }}
            """
        )
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 6)
        self.main_layout.setSpacing(2)

        self.header = QPushButton(f"{icon}  {title}   ˅")
        self.header.setObjectName("AccordionHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.clicked.connect(self.toggle)
        self.main_layout.addWidget(self.header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 2, 12, 8)
        self.body_layout.setSpacing(4)
        self.main_layout.addWidget(self.body)

    def add_content(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget)

    def set_content_layout(self, layout: QVBoxLayout | QGridLayout) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.body_layout.addLayout(layout)

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self.body.setVisible(self._expanded)
        arrow = "˅" if self._expanded else "›"
        current = self.header.text()
        self.header.setText(current.rsplit("   ", 1)[0] + f"   {arrow}")

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded != expanded:
            self.toggle()


class TransferVersusCard(QFrame):
    """Compact in/out comparison card for recommendation scenarios."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TransferVersusCard")
        self.setStyleSheet(
            f"""
            QFrame#TransferVersusCard {{
                background-color: {COLORS['bg_secondary']};
                border: 1px solid {COLORS['border_default']};
                border-radius: 12px;
            }}
            QFrame#TransferSide {{
                background-color: {COLORS['surface_card']};
                border: 1px solid {COLORS['border_subtle']};
                border-radius: 9px;
            }}
            QLabel#TransferKicker {{
                color: {COLORS['text_muted']};
                font-size: 12px;
                font-weight: 800;
            }}
            QLabel#TransferName {{
                color: {COLORS['text_primary']};
                font-size: 17px;
                font-weight: 900;
            }}
            QLabel#TransferMeta {{
                color: {COLORS['text_secondary']};
                font-size: 13px;
                font-weight: 600;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        comparison_row = QHBoxLayout()
        comparison_row.setSpacing(10)
        self.out_frame, out_layout = self._side("ÇIKAR", COLORS['status_danger'])
        self.in_frame, in_layout = self._side("AL", COLORS['accent_pitch'])
        self.out_name = self._label("—", "TransferName")
        self.out_meta = self._label("Mevcut oyuncu", "TransferMeta")
        self.in_name = self._label("—", "TransferName")
        self.in_meta = self._label("Önerilen oyuncu", "TransferMeta")
        out_layout.addWidget(self.out_name)
        out_layout.addWidget(self.out_meta)
        in_layout.addWidget(self.in_name)
        in_layout.addWidget(self.in_meta)

        arrow = QLabel("→")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setStyleSheet(
            f"color: {COLORS['accent_info']}; font-size: 26px; font-weight: 900; padding: 0 4px;"
        )
        comparison_row.addWidget(self.out_frame, 1)
        comparison_row.addWidget(arrow)
        comparison_row.addWidget(self.in_frame, 1)
        layout.addLayout(comparison_row)

        self.stats = QLabel("Net kazanç —  |  Hit —  |  Banka —")
        self.stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats.setMinimumHeight(34)
        self.stats.setStyleSheet(
            f"color: {COLORS['text_primary']}; background-color: {COLORS['surface_elevated']}; border: 1px solid {COLORS['border_subtle']}; border-radius: 8px; padding: 7px 10px; font-size: 13px; font-weight: 800;"
        )
        layout.addWidget(self.stats)

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _side(kicker: str, accent: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("TransferSide")
        frame.setStyleSheet(
            f"QFrame#TransferSide {{ border-top: 3px solid {accent}; background-color: {COLORS['surface_card']}; border-radius: 9px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(3)
        kicker_label = QLabel(kicker)
        kicker_label.setObjectName("TransferKicker")
        kicker_label.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: 900;")
        layout.addWidget(kicker_label)
        return frame, layout

    def set_transfer(self, out_name: str, out_price: float, in_name: str, in_price: float, net_gain: float, hit: int, bank: float) -> None:
        self.out_name.setText(out_name or "—")
        self.out_meta.setText(f"£{out_price:.1f}m  •  Transfer out")
        self.in_name.setText(in_name or "—")
        self.in_meta.setText(f"£{in_price:.1f}m  •  Transfer in")
        gain_prefix = "+" if net_gain >= 0 else ""
        self.stats.setText(
            f"Net kazanç <b style='color:{COLORS['accent_pitch']}'>{gain_prefix}{net_gain:.1f} xP</b>"
            f"  •  Hit <b style='color:{COLORS['status_warning']}'>{hit}</b>"
            f"  •  Kalan banka <b>£{bank:.1f}m</b>"
        )


class QuickStatsDialog(QDialog):
    """Animated player quick-stats modal, fed only by the existing player dictionary."""

    def __init__(self, player: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.player = player
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("")
        self.setMinimumWidth(480)
        self.setObjectName("QuickStatsDialog")
        
        # Dynamic Position Color Theme
        pos_code = str(player.get("pos") or player.get("position") or "MID").upper()
        if player.get("element_type") == 1 or pos_code in ("GK", "GKP", "1"):
            pos_theme = {
                "border": "#FB923C",        # Açık Turuncu
                "accent": "#FDBA74",
                "bg": "#150E07",
                "tile_bg": "#24140B",
                "pill_bg": "#7C2D12",
                "pill_text": "#FFEDD5"
            }
        elif player.get("element_type") == 2 or pos_code in ("DEF", "2"):
            pos_theme = {
                "border": "#38BDF8",        # Açık Mavi
                "accent": "#7DD3FC",
                "bg": "#061322",
                "tile_bg": "#0B1D33",
                "pill_bg": "#0369A1",
                "pill_text": "#E0F2FE"
            }
        elif player.get("element_type") == 3 or pos_code in ("MID", "3"):
            pos_theme = {
                "border": "#C084FC",        # Açık Mor
                "accent": "#D8B4FE",
                "bg": "#130821",
                "tile_bg": "#200E36",
                "pill_bg": "#6B21A8",
                "pill_text": "#F3E8FF"
            }
        elif player.get("element_type") == 4 or pos_code in ("FWD", "4"):
            pos_theme = {
                "border": "#EF4444",        # Kırmızı
                "accent": "#FCA5A5",
                "bg": "#1D060C",
                "tile_bg": "#2E0A13",
                "pill_bg": "#991B1B",
                "pill_text": "#FEE2E2"
            }
        else:
            pos_theme = {
                "border": "#334155",
                "accent": "#94A3B8",
                "bg": "#0F172A",
                "tile_bg": "#1E293B",
                "pill_bg": "#334155",
                "pill_text": "#F1F5F9"
            }

        # Root layout for dialog
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(0)
        
        # Solid Container Card with Position Themed Border
        self.modal_card = QFrame(self)
        self.modal_card.setObjectName("ModalCard")
        self.modal_card.setStyleSheet(f"""
            QFrame#ModalCard {{
                background-color: {pos_theme['bg']};
                border: 2px solid {pos_theme['border']};
                border-radius: 16px;
            }}
            QLabel#ModalTitle {{ color: #FFFFFF; font-size: 21px; font-weight: 900; }}
            QLabel#ModalSubtitle {{ color: {pos_theme['accent']}; font-size: 13px; font-weight: 700; }}
            QFrame#StatTile {{
                background-color: {pos_theme['tile_bg']};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top: 2px solid {pos_theme['border']};
                border-radius: 10px;
            }}
            QLabel#StatLabel {{ color: #94A3B8; font-size: 11px; font-weight: 800; }}
            QLabel#StatValue {{ color: #FFFFFF; font-size: 18px; font-weight: 900; }}
            QPushButton#ModalX {{
                background-color: rgba(255, 255, 255, 0.06);
                color: #94A3B8;
                border: 1px solid transparent;
                border-radius: 8px;
                font-size: 20px;
                font-weight: 900;
                padding: 0px;
            }}
            QPushButton#ModalX:hover {{
                background-color: #EF4444;
                color: #FFFFFF;
            }}
        """)
        
        layout = QVBoxLayout(self.modal_card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel(str(player.get("web_name") or player.get("name") or "Oyuncu"))
        title.setObjectName("ModalTitle")
        subtitle = QLabel(
            f"{str(player.get('pos') or player.get('position') or 'MID').upper()}  •  "
            f"{player.get('opponent') or player.get('fixture') or 'Sonraki fikstür bekleniyor'}"
        )
        subtitle.setObjectName("ModalSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block, 1)

        status = self._status_text(player)
        status_label = QLabel(status)
        status_label.setStyleSheet(
            f"color: {COLORS['status_success'] if status == 'Hazır' else COLORS['status_warning']}; font-weight: 900; font-size: 13px; padding-top: 4px;"
        )
        header.addWidget(status_label, alignment=Qt.AlignmentFlag.AlignTop)
        
        close_button = QPushButton("✕")
        close_button.setObjectName("ModalX")
        close_button.setFixedSize(32, 32)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.setToolTip("Kapat")
        close_button.clicked.connect(self.reject)
        header.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(8)
        stats = [
            ("Beklenen Puan", self._number(player.get("xp") or player.get("xp_next_gw"), "—")),
            ("xG (Beklenen Gol)", self._number(player.get("xg") or player.get("expected_goals"), "—")),
            ("xA (Beklenen Asist)", self._number(player.get("xa") or player.get("expected_assists"), "—")),
            ("FDR (Zorluk)", self._number(player.get("fdr") or player.get("avg_fdr"), "3")),
            ("Form", self._number(player.get("form"), "—")),
            ("Sahiplik", self._percent(player.get("selected_by_percent"))),
            ("Fiyat", self._price(player.get("price") or player.get("now_cost"))),
            ("Bonus / BPS", f"{player.get('bonus', 0)} / {player.get('bps', 0)}"),
        ]
        for idx, (label, value) in enumerate(stats):
            tile = self._stat_tile(label, value)
            grid.addWidget(tile, idx // 2, idx % 2)
        layout.addLayout(grid)

        news = str(player.get("news") or "").strip()
        if news:
            news_label = QLabel(f"⚠️ {news}")
            news_label.setWordWrap(True)
            news_label.setStyleSheet(
                f"color: #FBBF24; background-color: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.3); border-radius: 8px; padding: 10px; font-size: 12px; font-weight: 600;"
            )
            layout.addWidget(news_label)

        root_layout.addWidget(self.modal_card)


        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade.setDuration(220)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade.start()

    @staticmethod
    def _stat_tile(label: str, value: str) -> QFrame:
        tile = QFrame()
        tile.setObjectName("StatTile")
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(10, 8, 10, 8)
        tile_layout.setSpacing(2)
        lbl = QLabel(label.upper())
        lbl.setObjectName("StatLabel")
        val = QLabel(value)
        val.setObjectName("StatValue")
        tile_layout.addWidget(lbl)
        tile_layout.addWidget(val)
        return tile

    @staticmethod
    def _number(value: Any, fallback: str) -> str:
        if value in (None, ""):
            return fallback
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _percent(value: Any) -> str:
        if value in (None, ""):
            return "—"
        try:
            return f"{float(value):.1f}%"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _price(value: Any) -> str:
        if value in (None, ""):
            return "—"
        try:
            amount = float(value)
            if amount > 20:
                amount /= 10
            return f"£{amount:.1f}m"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _status_text(player: dict[str, Any]) -> str:
        status = str(player.get("status") or "a").lower()
        return "Hazır" if status in ("a", "ok", "") else "Riskli"
