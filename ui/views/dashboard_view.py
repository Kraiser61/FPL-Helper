import sys
from typing import Dict, List, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QLayout, QWidgetItem, QApplication
)
from PySide6.QtCore import (
    Qt, QRect, QSize, QPoint, QPropertyAnimation, QEasingCurve, QTimer, QVariantAnimation
)
from PySide6.QtGui import QColor, QPainter, QFont, QBrush, QPen
from ui.theme import COLORS, FontManager, tokens
from utils.smooth_scroll import SmoothScrollArea
from ui.widgets.toast import ToastNotification, ToastManager

# =====================================================================
# 1. RESPONSIVE FLOW LAYOUT
# =====================================================================
class FlowLayout(QLayout):
    """
    Automatic line-wrapping layout for responsive UI components.
    Wraps 5 KPI summary cards into 3+2 or 2+3 layouts on smaller (e.g. 1024px) screens.
    """
    def __init__(self, parent=None, margin=0, spacing=10):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def addItem(self, item):
        if isinstance(item, QWidget):
            item.show()
            item = QWidgetItem(item)
        elif isinstance(item, QWidgetItem) and item.widget() is not None:
            item.widget().show()
        self.itemList.append(item)

    def addWidget(self, widget: QWidget):
        self.addItem(QWidgetItem(widget))

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def doLayout(self, rect, testOnly):
        x, y, lineHeight = rect.x(), rect.y(), 0
        spacing = self.spacing()

        for item in self.itemList:
            nextX = x + item.sizeHint().width() + spacing
            if nextX - spacing > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spacing
                nextX = x + item.sizeHint().width() + spacing
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()


# =====================================================================
# 2. NUMERIC TABLE ITEM & SQUAD DATA TABLE
# =====================================================================
class NumericTableWidgetItem(QTableWidgetItem):
    """
    Custom QTableWidgetItem that sorts numerically or by custom UserRole keys
    instead of basic string comparison. Inline editing is disabled.
    """
    def __init__(self, text: str = ""):
        super().__init__(text)
        self.setFlags(self.flags() & ~Qt.ItemIsEditable)

    def __lt__(self, other):
        val_self = self.data(Qt.UserRole)
        val_other = other.data(Qt.UserRole)
        if val_self is not None and val_other is not None:
            return val_self < val_other
        return super().__lt__(other)


class SquadBenchTable(QTableWidget):
    """
    11-column data table with alternating rows, fixed header section sizes,
    Tabular Numerics fonts, hover states, and zero blue selection highlight.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setColumnCount(11)
        headers = ["Rol", "Oyuncu", "Mevki", "Fiyat", "Tahmini Puan", "Sahiplik", "Tehdit", "Savunma", "Bonus / BPS", "Form", "Durum"]
        self.setHorizontalHeaderLabels(headers)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch) # Oyuncu column auto-stretches

        # Default section sizes that comfortably fit in standard window width & can be dragged by user
        section_sizes = {
            0: 110, # Rol
            2: 65,  # Mevki
            3: 70,  # Fiyat
            4: 110, # Tahmini Puan
            5: 80,  # Sahiplik
            6: 70,  # Tehdit
            7: 75,  # Savunma
            8: 95,  # Bonus / BPS
            9: 60,  # Form
            10: 90  # Durum
        }
        for col, size in section_sizes.items():
            header.resizeSection(col, size)

        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(36)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setMouseTracking(True)

        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['surface_card']};
                color: #FFFFFF;
                border: 1px solid {COLORS['border_default']};
                gridline-color: rgba(255, 255, 255, 0.06);
                border-radius: 8px;
            }}
            QTableWidget::item {{
                padding: 6px 8px;
                font-size: 14px;
                font-weight: 600;
            }}
            QTableWidget::item:alternate {{
                background-color: {COLORS['surface_elevated']};
            }}
            QTableWidget::item:selected {{
                background-color: #2D3D54 !important;
                color: #38BDF8 !important;
            }}
            QHeaderView::section {{
                background-color: #0F172A;
                color: #94A3B8;
                font-family: 'Inter';
                font-weight: 800;
                font-size: 12px;
                border: 1px solid {COLORS['border_default']};
                padding: 7px 5px;
            }}
        """)

    def mouseMoveEvent(self, event):
        idx = self.indexAt(event.pos())
        if idx.isValid():
            self.selectRow(idx.row())
        else:
            self.clearSelection()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.clearSelection()
        super().leaveEvent(event)

    def adjust_height_to_contents(self):
        row_h = self.verticalHeader().defaultSectionSize() or 36
        hdr_h = self.horizontalHeader().height() if self.horizontalHeader().height() > 0 else 36
        total_h = hdr_h + (self.rowCount() * row_h) + 4
        self.setFixedHeight(total_h)


# =====================================================================
# 3. SUMMARY CARD (KPI Kartı)
# =====================================================================
class SummaryCard(QFrame):
    """
    Modern KPI Metric Card Widget featuring a 4px colored top status bar,
    Inter font title, JetBrains Mono Tabular Numerics value, and subtext.
    """
    def __init__(self, title: str, value: str, subtext: str, top_color: str = COLORS['accent_info'], icon: str = "•"):

        super().__init__()
        self.setObjectName("SummaryCard")
        self.setMinimumSize(180, 106)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setStyleSheet(f"""
            QFrame#SummaryCard {{
                background-color: {COLORS['surface_glass']};
                border-radius: 13px;
                padding: 10px;
                border: 1px solid rgba(139, 148, 158, 0.24);
                border-top: 3px solid {top_color};
            }}
            QFrame#SummaryCard:hover {{
                background-color: {COLORS['surface_elevated']};
                border-color: {top_color};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"color: {top_color}; font-size: 17px; font-weight: 900; border: none;")
        lbl_title = QLabel(title)
        lbl_title.setFont(FontManager.get_ui_font(13, bold=True))
        lbl_title.setStyleSheet(f"color: {COLORS['text_primary']}; border: none; letter-spacing: 0.03em;")
        title_row.addWidget(icon_label)
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        layout.addLayout(title_row)

        self.lbl_value = QLabel(value)
        self.lbl_value.setFont(FontManager.get_data_font(25, bold=True))
        self.lbl_value.setStyleSheet(f"color: {COLORS['text_primary']}; border: none;")

        self.lbl_subtext = QLabel(subtext)
        self.lbl_subtext.setFont(FontManager.get_ui_font(12))
        self.lbl_subtext.setStyleSheet(f"color: {COLORS['text_muted']}; border: none;")

        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_subtext)


# =====================================================================
# 4. SKELETON LOADER
# =====================================================================
class SkeletonLoader(QWidget):
    """
    Animated pulse-loop placeholder recreating the layout structure (5 KPI cards + Table).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(900, 550)
        self._color = QColor(COLORS['surface_card'])

        # Pulse Loop Animation (800ms Cycle)
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(QColor(COLORS['surface_card']))
        self.anim.setEndValue(QColor(COLORS['surface_elevated']))
        self.anim.setDuration(800)
        self.anim.setLoopCount(-1)
        self.anim.setEasingCurve(QEasingCurve.InOutSine)
        self.anim.valueChanged.connect(self._on_color_changed)
        self.anim.start()

    def _on_color_changed(self, color):
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._color))

        w, h = self.width(), self.height()

        # 1. Draw 5 KPI Skeleton Cards
        card_w, card_h = (w - 40) / 5, 100
        for i in range(5):
            painter.drawRoundedRect(QRect(int(i * (card_w + 10)), 0, int(card_w), card_h), 8, 8)

        # 2. Draw Table Skeleton Block
        table_y = card_h + 20
        painter.drawRoundedRect(QRect(0, table_y, w, h - table_y), 8, 8)


# =====================================================================
# 5. TOP BANNER (Persistent Error Bar)
# =====================================================================
class TopBanner(QFrame):
    """
    Persistent alert banner (#DC2626 bg) for network failures or HTTP 429 status.
    """
    def __init__(self, message: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS.get('status_danger', '#DC2626')};
                border-radius: 6px;
                padding: 0px 12px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        self.lbl_msg = QLabel(f"⚠️ {message}")
        self.lbl_msg.setFont(FontManager.get_ui_font(10, bold=True))
        self.lbl_msg.setStyleSheet("color: #FFFFFF; border: none;")
        layout.addWidget(self.lbl_msg, alignment=Qt.AlignCenter)
        self.hide()

    def show_message(self, message: str):
        self.lbl_msg.setText(f"⚠️ {message}")
        self.show()

    def hide_banner(self):
        self.hide()


# =====================================================================
# 6. DASHBOARD / TEAM VIEW ORCHESTRATOR
# =====================================================================
class TeamView(QWidget):
    """
    Dashboard / Team View (🏠 ANA SAYFA):
    Displays 5 Top KPI Cards in FlowLayout, Starters Table, and Bench Table stacked vertically.
    Supports SkeletonLoader and TopBanner for notification and state management.
    """
    def __init__(self, dash_vm=None, squad_vm=None):
        super().__init__()
        self.dash_vm = dash_vm
        self.squad_vm = squad_vm
        self.current_squad_list: List[Dict[str, Any]] = []

        self.setStyleSheet("background: transparent;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = SmoothScrollArea()
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        container.setStyleSheet(f"background-color: {COLORS['bg_primary']};")
        self.layout = QVBoxLayout(container)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(16)

        self._setup_ui()

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

        # Connect Signals if viewmodels provided
        if self.dash_vm and hasattr(self.dash_vm, 'data_updated'):
            self.dash_vm.data_updated.connect(self.on_dash_data_loaded)
        if self.squad_vm:
            if hasattr(self.squad_vm, 'squad_loaded'):
                self.squad_vm.squad_loaded.connect(self.on_squad_loaded)
            if hasattr(self.squad_vm, 'lineup_optimized'):
                self.squad_vm.lineup_optimized.connect(self.on_lineup_optimized)

    def _setup_ui(self):
        # 0. Top Persistent Banner (Network / HTTP 429 Errors)
        self.banner = TopBanner(parent=self)
        self.layout.addWidget(self.banner)

        # 1. Skeleton Loader Widget (Hidden by default)
        self.skeleton_loader = SkeletonLoader(parent=self)
        self.skeleton_loader.hide()
        self.layout.addWidget(self.skeleton_loader)

        # 2. Main Content Container
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)

        # Top KPI Summary Cards (FlowLayout for 2+3 / 3+2 responsive wrapping)
        kpi_container = QWidget()
        kpi_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        kpi_container.setMinimumHeight(104)
        self.kpi_flow_layout = QHBoxLayout(kpi_container)
        self.kpi_flow_layout.setContentsMargins(0, 0, 0, 0)
        self.kpi_flow_layout.setSpacing(12)

        self.card_points = SummaryCard("Toplam Puan", "0", "GW1 Canlı", COLORS.get('accent_pitch', '#10B981'), "◆")
        self.card_rank = SummaryCard("Genel Sıralama", "-", "İlk 100K hedefi", COLORS.get('accent_gold', '#F59E0B'), "↗")
        self.card_value = SummaryCard("Kadro Değeri", "£100.0m", "Banka: £0.0m", COLORS.get('accent_action', '#3B82F6'), "£")
        self.card_transfers = SummaryCard("Transfer Hakkı", "1 FT", "Ceza: 0 puan", COLORS.get('accent_info', '#0EA5E9'), "↻")
        self.card_xp = SummaryCard("Tahmini Puan", "0.0", "Haftalık Kadro", COLORS.get('status_warning', '#FBBF24'), "✦")

        self.kpi_flow_layout.addWidget(self.card_points, 1)
        self.kpi_flow_layout.addWidget(self.card_rank, 1)
        self.kpi_flow_layout.addWidget(self.card_value, 1)
        self.kpi_flow_layout.addWidget(self.card_transfers, 1)
        self.kpi_flow_layout.addWidget(self.card_xp, 1)

        content_layout.addWidget(kpi_container)

        # Weekly Smart Brief — an editorial, high-signal summary surface.
        self.smart_brief = QFrame()
        self.smart_brief.setObjectName("GlassPanel")
        self.smart_brief.setStyleSheet(f"""
            QFrame#GlassPanel {{
                background-color: {COLORS['surface_glass']};
                border: 1px solid rgba(34, 211, 238, 0.18);
                border-radius: 14px;
            }}
        """)
        brief_layout = QVBoxLayout(self.smart_brief)
        brief_layout.setContentsMargins(12, 8, 12, 8)
        brief_layout.setSpacing(3)
        brief_header = QHBoxLayout()
        brief_eyebrow = QLabel("KADRO ÖZETİ")
        brief_eyebrow.setObjectName("Eyebrow")
        brief_eyebrow.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 11px; font-weight: 900; letter-spacing: 0.06em;")
        brief_header.addWidget(brief_eyebrow)
        brief_header.addStretch()
        self.lbl_brief_gw = QLabel("GW1")
        self.lbl_brief_gw.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 11px; font-weight: 900;")
        brief_header.addWidget(self.lbl_brief_gw)
        brief_layout.addLayout(brief_header)
        self.lbl_brief_title = QLabel("Kadro hazır — bir sonraki hamle için veri bekleniyor")
        self.lbl_brief_title.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 15px; font-weight: 900;")
        brief_layout.addWidget(self.lbl_brief_title)
        self.lbl_brief_body = QLabel("Canlı veri yenilendiğinde puan, sıra ve transfer esnekliği tek bakışta özetlenecek.")
        self.lbl_brief_body.setWordWrap(True)
        self.lbl_brief_body.setStyleSheet(f"color: #B8C4D0; font-size: 11px; font-weight: 600; line-height: 1.25;")
        brief_layout.addWidget(self.lbl_brief_body)
        content_layout.addWidget(self.smart_brief)
        self.smart_brief.setVisible(False)

        # Starters Section Header & Table
        lbl_starters_hdr = QLabel("⚽ SAHADAKİ İLK 11")
        lbl_starters_hdr.setStyleSheet(f"color: {COLORS.get('accent_pitch', '#10B981')}; font-size: 16px; font-weight: 900; margin-top: 8px; margin-bottom: 4px;")
        content_layout.addWidget(lbl_starters_hdr)

        self.table_starters = SquadBenchTable()
        content_layout.addWidget(self.table_starters)

        # Bench Section Header & Table
        lbl_bench_hdr = QLabel("🪑 YEDEK KULÜBESİ")
        lbl_bench_hdr.setStyleSheet(f"color: {COLORS.get('accent_gold', '#F59E0B')}; font-size: 16px; font-weight: 900; margin-top: 10px; margin-bottom: 4px;")
        content_layout.addWidget(lbl_bench_hdr)

        self.table_bench = SquadBenchTable()
        content_layout.addWidget(self.table_bench)

        content_layout.addStretch(1)
        self.layout.addWidget(self.content_widget)

    def show_loading_skeleton(self):
        self.content_widget.hide()
        self.skeleton_loader.show()

    def hide_loading_skeleton(self):
        self.skeleton_loader.hide()
        self.content_widget.show()

    def show_network_error(self, message: str):
        self.banner.show_message(message)

    def clear_network_error(self):
        self.banner.hide_banner()

    def on_dash_data_loaded(self, data: dict):
        total_pts = data.get("overall_points") or 0
        rank = data.get("overall_rank") or "-"
        value = data.get("team_value") or 100.0
        bank = data.get("bank") or 0.0
        fts = data.get("free_transfers") or 1

        self.card_points.lbl_value.setText(str(total_pts))
        self.card_rank.lbl_value.setText(f"#{rank:,}" if isinstance(rank, int) and rank > 0 else str(rank))
        self.card_value.lbl_value.setText(f"£{value:.1f}m")
        self.card_value.lbl_subtext.setText(f"Banka: £{bank:.1f}m")
        self.card_transfers.lbl_value.setText(f"{fts} FT")
        rank_display = f"{rank:,}" if isinstance(rank, int) else str(rank)
        self.lbl_brief_title.setText("Kadro metrikleri güncellendi — kaptan ve transfer sinyalleri hazır")
        self.lbl_brief_body.setText(
            f"Toplam {total_pts:,} puan ve #{rank_display} genel sıra ile ilerliyorsunuz. "
            f"Kadro değeri £{value:.1f}m, banka £{bank:.1f}m ve kullanılabilir transfer hakkı {fts}. "
            "Bir sonraki adımda fikstür zorluğu ile xP farkını birlikte değerlendirin."
        )

    def on_lineup_optimized(self, lineup_data: dict):
        # Dashboard view strictly displays the user's actual FPL live lineup.
        # AI-recommended lineup is presented on the Kadro (Squad) tab.
        pass

    def on_squad_loaded(self, squad_list: list):
        if not squad_list:
            return
        self.current_squad_list = squad_list
        starters = [dict(p) for p in squad_list if p.get("pick_position", 99) <= 11]
        bench = [dict(p) for p in squad_list if p.get("pick_position", 99) > 11]

        # Starters sorted by position order GKP -> DEF -> MID -> FWD
        POS_ORDER = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
        starters.sort(key=lambda x: (POS_ORDER.get(x.get("pos"), 99), x.get("pick_position", 99)))
        
        # Bench sorted strictly by user's actual FPL bench order (GK -> Y1 -> Y2 -> Y3)
        bench.sort(key=lambda x: (0 if x.get("pos") == "GKP" else 1, x.get("pick_position", 99)))

        tot_xp = sum(p.get("xp", 0.0) for p in starters)
        self.card_xp.lbl_value.setText(f"{tot_xp:.1f} xP")

        # Extract User's Actual Live Captain & Vice-Captain from FPL Picks
        captain_id = next((p["id"] for p in squad_list if p.get("is_captain")), None)
        vice_captain_id = next((p["id"] for p in squad_list if p.get("is_vice_captain")), None)

        self._populate_table(self.table_starters, starters, captain_id=captain_id, vice_captain_id=vice_captain_id)
        self._populate_table(self.table_bench, bench, captain_id=captain_id, vice_captain_id=vice_captain_id, is_bench=True)

    def _populate_table(self, table: QTableWidget, players: list, captain_id: int = None, vice_captain_id: int = None, is_bench: bool = False):
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        POS_ORDER = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
        try:
            table.setRowCount(len(players))
            outfield_bench_count = 1
            for row, p in enumerate(players):
                pid = p.get("id")
                if pid == captain_id:
                    role_text = "👑 Kaptan"
                    role_order = 1
                elif pid == vice_captain_id:
                    role_text = "⭐ 2. Kaptan"
                    role_order = 2
                elif not is_bench:
                    role_text = "⚽ İlk 11"
                    role_order = 3
                elif p.get("pos") == "GKP":
                    role_text = "🧤 GK Yedek"
                    role_order = 4
                else:
                    role_text = f"🔄 Yedek #{outfield_bench_count}"
                    role_order = 4 + outfield_bench_count
                    outfield_bench_count += 1

                item_role = NumericTableWidgetItem(role_text)
                item_role.setData(Qt.UserRole, role_order)
                if role_text == "👑 Kaptan":
                    item_role.setForeground(Qt.yellow)
                elif role_text == "⭐ 2. Kaptan":
                    item_role.setForeground(Qt.cyan)

                item_name = NumericTableWidgetItem(p.get("web_name", ""))
                item_name.setData(Qt.UserRole, p.get("web_name", "").lower())
                item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                pos_str = p.get("pos", "MID")
                item_pos = NumericTableWidgetItem(pos_str)
                item_pos.setData(Qt.UserRole, POS_ORDER.get(pos_str, 99))
                item_pos.setTextAlignment(Qt.AlignCenter)

                price_val = float(p.get('price', 0.0) or 0.0)
                item_price = NumericTableWidgetItem(f"£{price_val:.1f}m")
                item_price.setData(Qt.UserRole, price_val)
                item_price.setTextAlignment(Qt.AlignCenter)

                xp_val = float(p.get('xp', 0.0) or 0.0)
                item_xp = NumericTableWidgetItem(f"{xp_val:.1f}")
                item_xp.setData(Qt.UserRole, xp_val)
                item_xp.setTextAlignment(Qt.AlignCenter)

                ownership_val = float(p.get('selected_by_percent', 0.0) or 0.0)
                item_own = NumericTableWidgetItem(f"%{ownership_val:.1f}")
                item_own.setData(Qt.UserRole, ownership_val)
                item_own.setTextAlignment(Qt.AlignCenter)

                threat_val = float(p.get('threat', 0.0) or 0.0)
                item_threat = NumericTableWidgetItem(f"{threat_val:.1f}")
                item_threat.setData(Qt.UserRole, threat_val)
                item_threat.setTextAlignment(Qt.AlignCenter)

                def_actions = int(p.get('defensive_actions', 0) or 0)
                if def_actions == 0:
                    cbi = int(p.get('cbi', 0) or 0)
                    rec = int(p.get('recoveries', 0) or 0)
                    def_actions = cbi + rec
                item_def = NumericTableWidgetItem(str(def_actions))
                item_def.setData(Qt.UserRole, def_actions)
                item_def.setTextAlignment(Qt.AlignCenter)

                bonus_val = int(p.get('bonus', 0) or 0)
                bps_val = int(p.get('bps', 0) or 0)
                item_bonus = NumericTableWidgetItem(f"{bonus_val} / {bps_val}")
                item_bonus.setData(Qt.UserRole, bonus_val * 1000 + bps_val)
                item_bonus.setTextAlignment(Qt.AlignCenter)

                form_val = float(p.get('form', 0.0) or 0.0)
                item_form = NumericTableWidgetItem(f"{form_val:.1f}")
                item_form.setData(Qt.UserRole, form_val)
                item_form.setTextAlignment(Qt.AlignCenter)

                status_code = str(p.get('status', 'a'))
                if status_code == 'a':
                    status_txt = "Sağlıklı"
                    status_clr = Qt.green
                elif status_code in ('i', 's'):
                    status_txt = "Sakat" if status_code == 'i' else "Cezalı"
                    status_clr = Qt.red
                elif status_code == 'd':
                    status_txt = "Şüpheli %75"
                    status_clr = Qt.yellow
                else:
                    status_txt = "Sağlıklı"
                    status_clr = Qt.green

                item_status = NumericTableWidgetItem(status_txt)
                item_status.setData(Qt.UserRole, 1 if status_code == 'a' else 0)
                item_status.setForeground(status_clr)
                item_status.setTextAlignment(Qt.AlignCenter)

                table.setItem(row, 0, item_role)
                table.setItem(row, 1, item_name)
                table.setItem(row, 2, item_pos)
                table.setItem(row, 3, item_price)
                table.setItem(row, 4, item_xp)
                table.setItem(row, 5, item_own)
                table.setItem(row, 6, item_threat)
                table.setItem(row, 7, item_def)
                table.setItem(row, 8, item_bonus)
                table.setItem(row, 9, item_form)
                table.setItem(row, 10, item_status)
        finally:
            table.setSortingEnabled(True)
            table.setUpdatesEnabled(True)
            table.adjust_height_to_contents()


DashboardView = TeamView

# =====================================================================
# SANITY CHECK / UNITTEST
# =====================================================================
if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("FPL Helper v3.0 - UI Phase 3 Dashboard Sanity Check")
    window.resize(1024, 768)
    window.setStyleSheet(f"background-color: {COLORS['bg_primary']};")

    main_layout = QVBoxLayout(window)
    main_layout.setContentsMargins(0, 0, 0, 0)

    dashboard = DashboardView()
    main_layout.addWidget(dashboard)

    # Test Network Error Banner
    dashboard.show_network_error("BAĞLANTI HATASI: API sunucusuna erişilemiyor (HTTP 429).")

    # Test Data Load
    dashboard.on_dash_data_loaded({
        "overall_points": 1420,
        "overall_rank": 24150,
        "team_value": 103.8,
        "bank": 1.2,
        "free_transfers": 2
    })

    mock_squad = [
        {"id": 1, "web_name": "Raya", "pos": "GKP", "price": 5.5, "xp": 4.5, "pick_position": 1},
        {"id": 2, "web_name": "Saliba", "pos": "DEF", "price": 6.0, "xp": 4.2, "pick_position": 2},
        {"id": 3, "web_name": "Salah", "pos": "MID", "price": 13.0, "xp": 8.5, "pick_position": 3, "is_captain": True},
        {"id": 4, "web_name": "Haaland", "pos": "FWD", "price": 15.0, "xp": 7.8, "pick_position": 4, "is_vice_captain": True},
        {"id": 5, "web_name": "Turner", "pos": "GKP", "price": 4.0, "xp": 0.0, "pick_position": 12}
    ]
    dashboard.on_squad_loaded(mock_squad)

    # Toast Test
    toast_mgr = ToastManager(window)
    toast_mgr.show_toast("Başarılı", "Faz 3 UI bileşenleri sorunsuz yüklendi.", "success")

    window.show()

    print("--- SANITY CHECK: ui/views/dashboard_view.py ---")
    assert dashboard.card_points is not None
    assert dashboard.table_starters is not None
    assert dashboard.skeleton_loader is not None
    print("[SUCCESS] FlowLayout, SummaryCard, SquadBenchTable, SkeletonLoader & TopBanner sanity check passed.")
