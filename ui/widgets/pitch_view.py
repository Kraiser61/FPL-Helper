from __future__ import annotations

import sys
from typing import Any, Dict, List

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.theme import COLORS, FontManager
from ui.widgets.modern_ui import QuickStatsDialog


class PlayerWidget(QFrame):
    """Modern compact player card used on the pitch and bench."""

    clicked = Signal(dict)

    def __init__(
        self,
        data_or_name: Any = None,
        position: str = "MID",
        xp: float = 0.0,
        fdr: int = 3,
        is_captain: bool = False,
        is_vice: bool = False,
        is_locked: bool = False,
        status_flag: str = "OK",
        opponent: str = "",
        parent=None,
        **kwargs,
    ):
        super().__init__(parent)
        self.setObjectName("PlayerCard")
        self.setFixedSize(136, 104)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        if isinstance(data_or_name, dict):
            self.player_data = dict(data_or_name)
            d = self.player_data
            name = d.get("web_name") or d.get("name") or "Oyuncu"
            pos = str(d.get("pos") or d.get("position") or "MID").upper()
            if d.get("element_type") == 1 or pos in ("GK", "GKP"):
                pos = "GKP"
            xp_val = self._number(d.get("xp") or d.get("xp_next_gw") or d.get("xp_horizon"), 0.0)
            fdr_val = self._number(d.get("fdr") or d.get("avg_fdr"), 3)
            opp_val = str(d.get("opponent") or d.get("fixture") or d.get("next_fixture") or d.get("opp") or opponent or "").strip()
            cap = bool(d.get("is_captain") or d.get("is_cap"))
            vc = bool(d.get("is_vice_captain") or d.get("is_vice"))
            locked = bool(d.get("locked") or d.get("is_locked"))
            stat = str(d.get("status") or d.get("status_flag") or "OK")
        else:
            self.player_data = {
                "web_name": str(data_or_name or "Oyuncu"),
                "pos": str(position).upper(),
                "xp": xp,
                "fdr": fdr,
                "is_captain": is_captain,
                "is_vice_captain": is_vice,
                "locked": is_locked,
                "status": status_flag,
                "opponent": opponent,
            }
            name = self.player_data["web_name"]
            pos = self.player_data["pos"]
            xp_val = self._number(xp, 0.0)
            fdr_val = self._number(fdr, 3)
            opp_val = str(opponent).strip()
            cap = is_captain
            vc = is_vice
            locked = is_locked
            stat = status_flag

        # Parse suggestion flags
        suggestion = str(d.get("suggestion") or "").upper() if isinstance(data_or_name, dict) else ""
        is_cap_changed = bool(d.get("is_cap_changed")) if isinstance(data_or_name, dict) else False
        is_vc_changed = bool(d.get("is_vc_changed")) if isinstance(data_or_name, dict) else False

        self._name = str(name)
        self._pos = pos
        self._xp = float(xp_val)
        self._fdr = max(1, min(5, int(fdr_val)))
        self._opponent = opp_val
        self._status = stat
        self._locked = locked
        self._captain = cap
        self._vice = vc
        self._suggestion = suggestion

        # Exact Position Themes:
        # Kaleci: Açık Turuncu (#FB923C)
        # Defans: Açık Mavi (#38BDF8)
        # Ortasaha: Açık Mor (#C084FC)
        # Forvet: Kırmızı (#EF4444)
        pos_code = self._pos.upper()
        if pos_code in ("GK", "GKP", "1"):
            card_border = "#FB923C"       # Açık Turuncu
            card_bg = "#1C130A"
            card_hover_bg = "#2D1C0E"
            pos_pill_style = "background-color: #7C2D12; color: #FFEDD5; border: 1.5px solid #FB923C; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 900;"
            pos_accent = "#FB923C"
        elif pos_code in ("DEF", "2"):
            card_border = "#38BDF8"       # Açık Mavi
            card_bg = "#071524"
            card_hover_bg = "#0E2338"
            pos_pill_style = "background-color: #0369A1; color: #E0F2FE; border: 1.5px solid #38BDF8; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 900;"
            pos_accent = "#38BDF8"
        elif pos_code in ("MID", "3"):
            card_border = "#C084FC"       # Açık Mor
            card_bg = "#180D26"
            card_hover_bg = "#26153B"
            pos_pill_style = "background-color: #6B21A8; color: #F3E8FF; border: 1.5px solid #C084FC; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 900;"
            pos_accent = "#C084FC"
        elif pos_code in ("FWD", "4"):
            card_border = "#EF4444"       # Kırmızı
            card_bg = "#22090F"
            card_hover_bg = "#330E17"
            pos_pill_style = "background-color: #991B1B; color: #FEE2E2; border: 1.5px solid #EF4444; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 900;"
            pos_accent = "#EF4444"
        else:
            card_border = "#94A3B8"
            card_bg = "#1E293B"
            card_hover_bg = "#334155"
            pos_pill_style = "background-color: #334155; color: #F1F5F9; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 900;"
            pos_accent = "#94A3B8"

        bench_role = str(d.get("bench_role") or "") if isinstance(data_or_name, dict) else ""
        is_bench = bool(d.get("is_bench")) if isinstance(data_or_name, dict) else False

        if locked:
            self._accent = COLORS["text_secondary"]
            self._badge = "⌁"
            self._role = "KİLİTLİ"
        elif stat not in ("OK", "a", ""):
            self._accent = COLORS["status_danger"] if stat in ("d", "i", "s", "INJURED") else COLORS["status_warning"]
            self._badge = "!"
            self._role = "RİSKLİ"
        elif cap:
            self._accent = COLORS["accent_gold"]
            self._badge = "♛"
            self._role = "KAPTAN"
        elif vc:
            self._accent = "#38BDF8"
            self._badge = "★"
            self._role = "2. KAPTAN"
        elif bench_role:
            self._accent = COLORS["accent_gold"]
            self._badge = ""
            self._role = bench_role
        elif is_bench:
            self._accent = COLORS["accent_gold"]
            self._badge = ""
            self._role = "YEDEK"
        else:
            self._accent = pos_accent
            self._badge = ""
            self._role = "İLK 11"

        fdr_color = COLORS.get(f"fdr_{self._fdr}", COLORS["fdr_3"])
        
        # Single Uniform Border Color matching player position theme
        self.setStyleSheet(
            f"""
            QFrame#PlayerCard {{
                background-color: {card_bg};
                border: 2px solid {card_border};
                border-radius: 11px;
            }}
            QFrame#PlayerCard:hover {{
                background-color: {card_hover_bg};
                border: 2px solid #FFFFFF;
            }}
            QLabel {{ background: transparent; border: none; }}
            QLabel#PlayerName {{ color: #FFFFFF; font-size: 14px; font-weight: 900; }}
            QLabel#PlayerRole {{ color: {self._accent}; font-size: 11px; font-weight: 900; letter-spacing: 0.06em; }}
            QLabel#PlayerPosition {{ {pos_pill_style} }}
            QLabel#PlayerXP {{ color: #FFFFFF; font-family: 'JetBrains Mono'; font-size: 20px; font-weight: 900; }}
            QLabel#PlayerMeta {{ color: #94A3B8; font-size: 11px; font-weight: 700; }}
            QLabel#FdrBadge {{ color: #0D1117; background-color: {fdr_color}; border-radius: 5px; padding: 3px 6px; font-size: 11px; font-weight: 900; }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 6, 9, 7)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(4)
        name_label = QLabel()
        name_label.setObjectName("PlayerName")
        name_label.setFont(FontManager.get_ui_font(11, bold=True))
        name_label.setText(QFontMetrics(name_label.font()).elidedText(self._name, Qt.TextElideMode.ElideRight, 74))
        header.addWidget(name_label, 1)
        
        # Suggestion / Change Icon (if AI suggests change)
        if suggestion == "PROMOTED":
            sugg_badge = QLabel("🔺")
            sugg_badge.setToolTip("💡 Öneri: FPL'de yedektesiniz ➔ İlk 11'e almanız öneriliyor")
            sugg_badge.setStyleSheet("font-size: 13px;")
            header.addWidget(sugg_badge)
        elif suggestion == "DEMOTED":
            sugg_badge = QLabel("🔻")
            sugg_badge.setToolTip("⚠️ Öneri: FPL'de ilk 11'desiniz ➔ Yedeğe çekmeniz öneriliyor")
            sugg_badge.setStyleSheet("font-size: 13px;")
            header.addWidget(sugg_badge)
        elif is_cap_changed and cap:
            sugg_badge = QLabel("⚡")
            sugg_badge.setToolTip("👑 Öneri: FPL kaptanınızdan farklı ➔ Yeni Kaptan önerisi")
            sugg_badge.setStyleSheet("font-size: 13px;")
            header.addWidget(sugg_badge)
        elif is_vc_changed and vc:
            sugg_badge = QLabel("⭐")
            sugg_badge.setToolTip("⭐ Öneri: FPL 2. kaptanınızdan farklı ➔ Yeni 2. Kaptan önerisi")
            sugg_badge.setStyleSheet("font-size: 13px;")
            header.addWidget(sugg_badge)

        badge = QLabel(self._badge)
        badge.setStyleSheet(f"color: {self._accent}; font-size: 17px; font-weight: 900;")
        header.addWidget(badge, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)

        role_row = QHBoxLayout()
        role_row.setSpacing(4)
        role_label = QLabel(self._role)
        role_label.setObjectName("PlayerRole")
        role_row.addWidget(role_label)
        role_row.addStretch()
        pos_label = QLabel(self._pos)
        pos_label.setObjectName("PlayerPosition")
        role_row.addWidget(pos_label)
        layout.addLayout(role_row)

        score_row = QHBoxLayout()
        score_row.setSpacing(4)
        xp_label = QLabel(f"{self._xp:.1f}")
        xp_label.setObjectName("PlayerXP")
        score_row.addWidget(xp_label)
        xp_suffix = QLabel("xP")
        xp_suffix.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px; font-weight: 800;")
        score_row.addWidget(xp_suffix, alignment=Qt.AlignmentFlag.AlignBottom)
        score_row.addStretch()
        fdr_label = QLabel(self._opponent or f"FDR {self._fdr}")
        fdr_label.setObjectName("FdrBadge")
        score_row.addWidget(fdr_label, alignment=Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(score_row)

        footer = QHBoxLayout()
        footer.setSpacing(4)
        status_label = QLabel("Hazır" if stat in ("OK", "a", "") else "Durum riskli")
        status_label.setObjectName("PlayerMeta")
        status_label.setStyleSheet(
            f"color: {COLORS['status_success'] if stat in ('OK', 'a', '') else COLORS['status_warning']}; font-size: 12px; font-weight: 800;"
        )
        footer.addWidget(status_label)
        footer.addStretch()
        layout.addLayout(footer)

        tooltip_text = f"{self._name} ({self._pos}) · {self._xp:.1f} xP"
        if suggestion == "PROMOTED":
            tooltip_text += " · 💡 Öneri: İlk 11'e Al"
        elif suggestion == "DEMOTED":
            tooltip_text += " · ⚠️ Öneri: Yedeğe Çek"
        self.setToolTip(tooltip_text)

    @staticmethod
    def _number(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(fallback)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(dict(self.player_data))
        super().mousePressEvent(event)


class TacticalPitchField(QWidget):
    """Modern 2D pitch canvas with responsive normalized formation placement."""

    player_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TacticalPitchField")
        self.setMinimumSize(400, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.formation_data: Dict[str, List[Dict[str, Any]]] = {}

        self.lbl_pitch_badge = QLabel("⚽ OPTİMUM İLK 11", self)
        self.lbl_pitch_badge.setStyleSheet("""
            background-color: rgba(15, 23, 42, 0.75);
            color: #38BDF8;
            font-size: 13px;
            font-weight: 900;
            letter-spacing: 0.05em;
            padding: 5px 12px;
            border-radius: 8px;
            border: 1px solid rgba(56, 189, 248, 0.4);
        """)
        self.lbl_pitch_badge.move(18, 16)
        self.lbl_pitch_badge.show()

    def set_formation(self, formation_dict: Dict[str, List[Dict[str, Any]]]):
        self.formation_data = formation_dict
        self._clear_player_widgets()
        self.update_player_positions()
        self.update()

    def _clear_player_widgets(self):
        for child in self.findChildren(PlayerWidget):
            child.setParent(None)
            child.deleteLater()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'lbl_pitch_badge'):
            self.lbl_pitch_badge.move(18, 16)
            self.lbl_pitch_badge.raise_()
        self.update_player_positions()

    def update_player_positions(self):
        if not self.formation_data:
            return
        self._clear_player_widgets()
        w, h = self.width(), self.height()
        card_w, card_h = 136, 102
        y_ratios = {"GKP": 0.11, "DEF": 0.36, "MID": 0.62, "FWD": 0.86}
        for role, player_list in self.formation_data.items():
            if not player_list or role == "BENCH":
                continue
            y_pos = int(h * y_ratios.get(role, 0.5)) - card_h // 2
            for i, p_data in enumerate(player_list):
                x_pos = int(((i + 1) / (len(player_list) + 1)) * w) - card_w // 2
                widget = PlayerWidget(p_data, parent=self)
                widget.clicked.connect(self.player_clicked.emit)
                widget.move(max(8, min(w - card_w - 8, x_pos)), max(8, min(h - card_h - 8, y_pos)))
                widget.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 1. Lush Green Grass Gradient
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor("#15803D"))
        gradient.setColorAt(0.5, QColor("#16A34A"))
        gradient.setColorAt(1.0, QColor("#15803D"))
        painter.fillRect(self.rect(), QBrush(gradient))

        # 2. Alternating Grass Mowing Stripes
        stripe_count = 8
        stripe_h = h / stripe_count
        for i in range(stripe_count):
            if i % 2 == 0:
                painter.fillRect(QRectF(0, i * stripe_h, w, stripe_h), QColor(255, 255, 255, 12))

        # 3. Outer Field Boundary
        margin = 16
        painter.setPen(QPen(QColor(255, 255, 255, 210), 1.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        field_rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)
        painter.drawRoundedRect(field_rect, 10, 10)

        # 4. Top Goal Structure (Kale & File Çizimi)
        goal_w = min(140.0, w * 0.28)
        goal_h = 14.0
        goal_x = (w - goal_w) / 2.0
        painter.setPen(QPen(QColor(255, 255, 255, 220), 2.0))
        painter.drawRect(QRectF(goal_x, margin - goal_h + 2, goal_w, goal_h))
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
        for net_x in range(int(goal_x + 8), int(goal_x + goal_w), 10):
            painter.drawLine(QPointF(net_x, margin - goal_h + 2), QPointF(net_x, margin + 2))

        # 5. Goal Area (6-Yard Box / Altıpas)
        six_w = min(220.0, w * 0.38)
        six_h = h * 0.08
        six_x = (w - six_w) / 2.0
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1.6))
        painter.drawRect(QRectF(six_x, margin, six_w, six_h))

        # 6. Penalty Area (18-Yard Box / Ceza Sahası)
        pen_w = min(420.0, w * 0.68)
        pen_h = h * 0.22
        pen_x = (w - pen_w) / 2.0
        painter.drawRect(QRectF(pen_x, margin, pen_w, pen_h))

        # 7. Penalty Spot & Penalty Arc (D-Box)
        pen_spot_y = margin + pen_h * 0.65
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawEllipse(QPointF(w / 2.0, pen_spot_y), 3.0, 3.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        arc_radius = min(80.0, w * 0.14)
        arc_rect = QRectF(w / 2.0 - arc_radius, pen_spot_y - arc_radius, arc_radius * 2, arc_radius * 2)
        painter.drawArc(arc_rect, 215 * 16, 110 * 16)

        # 8. Bottom Halfway Line & Center Circle (Orta Saha Çizgisi & Çemberi)
        bot_y = h - margin
        painter.drawLine(QPointF(margin, bot_y), QPointF(w - margin, bot_y))
        center_r = min(110.0, w * 0.20)
        center_rect = QRectF(w / 2.0 - center_r, bot_y - center_r, center_r * 2, center_r * 2)
        painter.drawArc(center_rect, 0 * 16, 180 * 16)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawEllipse(QPointF(w / 2.0, bot_y), 3.0, 3.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # 9. Top Corner Arcs
        corner_r = 16.0
        painter.drawArc(QRectF(margin, margin, corner_r * 2, corner_r * 2), 270 * 16, 90 * 16)
        painter.drawArc(QRectF(w - margin - corner_r * 2, margin, corner_r * 2, corner_r * 2), 180 * 16, 90 * 16)


class PitchView(QWidget):
    """Squad screen surface containing the pitch and the bench rail."""

    player_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PitchView")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(10)

        self.pitch_field = TacticalPitchField()
        self.pitch_field.player_clicked.connect(self._on_player_clicked)
        main_layout.addWidget(self.pitch_field, stretch=1)

        self.bench_frame = QFrame()
        self.bench_frame.setObjectName("BenchCard")
        self.bench_frame.setStyleSheet(
            f"""
            QFrame#BenchCard {{
                background-color: {COLORS['surface_glass']};
                border: 1px solid rgba(245, 158, 11, 0.2); /* Subtle gold accent */
                border-top: 3px solid {COLORS['accent_gold']};
                border-radius: 12px;
            }}
            """
        )
        bench_layout = QVBoxLayout(self.bench_frame)
        bench_layout.setContentsMargins(14, 10, 14, 12)
        bench_layout.setSpacing(12)
        header = QHBoxLayout()
        self.bench_title = QLabel("YEDEK KULÜBESİ")
        self.bench_title.setStyleSheet(f"color: {COLORS['accent_gold']}; font-size: 14px; font-weight: 900; letter-spacing: 0.10em;")
        header.addWidget(self.bench_title)
        header.addStretch()
        bench_hint = QLabel("Sıralı değişiklik öncelikleri")
        bench_hint.setStyleSheet(f"color: {COLORS['text_secondary']}; background-color: rgba(255,255,255,0.05); border-radius: 6px; padding: 4px 10px; font-size: 12px; font-weight: 600;")
        header.addWidget(bench_hint, alignment=Qt.AlignmentFlag.AlignRight)
        bench_layout.addLayout(header)
        
        # Center the player widgets horizontally
        self.bench_cards_layout = QHBoxLayout()
        self.bench_cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bench_cards_layout.setSpacing(20)
        bench_layout.addLayout(self.bench_cards_layout)
        
        main_layout.addWidget(self.bench_frame)

    def set_formation(self, formation_dict: Dict[str, List[Dict[str, Any]]]):
        pitch_formation = {role: formation_dict.get(role, []) for role in ("GKP", "DEF", "MID", "FWD")}
        self.pitch_field.set_formation(pitch_formation)
        self._clear_bench()
        
        bench_list = formation_dict.get("BENCH", [])
        outfield_idx = 1
        for idx, p_data in enumerate(bench_list):
            p = dict(p_data)
            p["is_bench"] = True
            pos_str = str(p.get("pos") or p.get("position") or "MID").upper()
            if pos_str in ("GK", "GKP") or p.get("element_type") == 1:
                p["bench_role"] = "GK YEDEK"
            else:
                p["bench_role"] = f"{outfield_idx}. YEDEK"
                outfield_idx += 1

            card = PlayerWidget(p)
            card.clicked.connect(self._on_player_clicked)
            self.bench_cards_layout.addWidget(card)

    def set_squad(self, starting_11: List[Dict[str, Any]], bench_order: List[Dict[str, Any]]):
        formation_dict: Dict[str, List[Dict[str, Any]]] = {"GKP": [], "DEF": [], "MID": [], "FWD": [], "BENCH": list(bench_order)}
        for p in starting_11:
            pos = str(p.get("pos") or p.get("position") or "MID").upper()
            elem_type = p.get("element_type")
            if elem_type == 1 or pos in ("GK", "GKP"):
                formation_dict["GKP"].append(p)
            elif elem_type == 2 or pos == "DEF":
                formation_dict["DEF"].append(p)
            elif elem_type == 3 or pos == "MID":
                formation_dict["MID"].append(p)
            elif elem_type == 4 or pos == "FWD":
                formation_dict["FWD"].append(p)
            else:
                formation_dict["MID"].append(p)
        self.set_formation(formation_dict)

    def _on_player_clicked(self, player: dict):
        self.player_clicked.emit(player)
        dialog = QuickStatsDialog(player, self)
        dialog.exec()

    def _clear_bench(self):
        while self.bench_cards_layout.count():
            item = self.bench_cards_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("FPL Helper · Tactical Pitch Preview")
    window.resize(650, 850)
    layout = QVBoxLayout(window)
    pitch = PitchView()
    pitch.set_formation(
        {
            "GKP": [{"web_name": "Raya", "pos": "GKP", "xp": 4.5, "fdr": 2}],
            "DEF": [{"web_name": "Saliba", "pos": "DEF", "xp": 4.1, "fdr": 2}, {"web_name": "Porro", "pos": "DEF", "xp": 3.9, "fdr": 4}],
            "MID": [{"web_name": "Salah", "pos": "MID", "xp": 8.5, "fdr": 2, "is_captain": True}],
            "FWD": [{"web_name": "Haaland", "pos": "FWD", "xp": 7.1, "fdr": 5}],
            "BENCH": [{"web_name": "Turner", "pos": "GKP", "xp": 1.0, "fdr": 4}],
        }
    )
    layout.addWidget(pitch)
    window.show()
    sys.exit(app.exec())
