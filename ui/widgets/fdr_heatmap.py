from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QAbstractAnimation
from PySide6.QtGui import QColor, QFont, QBrush, QPainter, QPen
from PySide6.QtWidgets import QHeaderView, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ui.theme import COLORS


TEAM_NAMES_FULL = {
    "ARS": "Arsenal",
    "AST": "Aston Villa",
    "AVL": "Aston Villa",
    "BOU": "Bournemouth",
    "BRE": "Brentford",
    "BHA": "Brighton",
    "CHE": "Chelsea",
    "CRY": "Crystal Palace",
    "EVE": "Everton",
    "FUL": "Fulham",
    "IPS": "Ipswich Town",
    "LEI": "Leicester City",
    "LIV": "Liverpool",
    "MCI": "Manchester City",
    "MUN": "Manchester United",
    "NEW": "Newcastle United",
    "NFO": "Nottingham Forest",
    "SOU": "Southampton",
    "TOT": "Tottenham",
    "WHU": "West Ham",
    "WOL": "Wolves"
}

class FdrCellDelegate(QStyledItemDelegate):
    """Paints rounded, softened FDR cells and a focused hover state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_row = -1
        self.hovered_col = -1

    def set_hovered(self, row: int, col: int) -> None:
        self.hovered_row = row
        self.hovered_col = col
        if self.parent():
            self.parent().viewport().update()

    def paint(self, painter, option, index):
        if index.column() == 0:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        bg_brush = index.data(Qt.ItemDataRole.BackgroundRole)
        fg_brush = index.data(Qt.ItemDataRole.ForegroundRole)
        rect = QRectF(option.rect).adjusted(2, 2, -2, -2)
        is_hovered = index.row() == self.hovered_row and index.column() == self.hovered_col

        base = bg_brush.color() if bg_brush else QColor(COLORS["surface_card"])
        if is_hovered:
            base = QColor(
                min(255, int(base.red() * 0.72 + 255 * 0.28)),
                min(255, int(base.green() * 0.72 + 255 * 0.28)),
                min(255, int(base.blue() * 0.72 + 255 * 0.28)),
            )
        painter.setBrush(QBrush(base))
        painter.setPen(QPen(QColor(255, 255, 255, 80 if is_hovered else 32), 1.2))
        painter.drawRoundedRect(rect, 7 if is_hovered else 5, 7 if is_hovered else 5)

        if fg_brush:
            painter.setPen(QPen(fg_brush.color()))
        else:
            painter.setPen(QPen(QColor(COLORS["text_primary"])))
        font = QFont("Inter", 10, QFont.Weight.Bold)
        if is_hovered:
            font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(text))
        painter.restore()


class FdrHeatmapWidget(QWidget):
    """Fixture Difficulty Rating matrix for all teams and selected gameweeks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setMouseTracking(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.viewport().setMouseTracking(True)
        self.delegate = FdrCellDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.cellEntered.connect(self._on_cell_entered)
        self.table.leaveEvent = self._leave_table
        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {COLORS['surface_card']};
                border-radius: 10px;
                border: 1px solid {COLORS['border_default']};
                padding: 2px;
            }}
            QTableWidget::item {{ padding: 2px 4px; border: none; }}
            QHeaderView::section {{
                background-color: #0F172A;
                color: #94A3B8;
                font-weight: 800;
                font-size: 11px;
                padding: 5px 6px;
                border: none;
                border-bottom: 1px solid {COLORS['border_default']};
            }}
            """
        )
        self.layout.addWidget(self.table)

    def _on_cell_entered(self, row: int, column: int) -> None:
        self.delegate.set_hovered(row, column)
        if column == 0:
            self.table.setToolTip("")
            return
        item = self.table.item(row, column)
        if item and item.toolTip():
            self.table.setToolTip(item.toolTip())
        else:
            self.table.setToolTip("")

    def _leave_table(self, event):
        self.delegate.set_hovered(-1, -1)
        self.table.setToolTip("")
        return QTableWidget.leaveEvent(self.table, event)

    @staticmethod
    def _format_opponent(opp_str: str) -> str:
        if not opp_str or opp_str in ("BYE", "BLANK"):
            return "—"
        # Format e.g. WOL(H) -> Wolves (E), AST(A) -> Aston Villa (D)
        opp = str(opp_str).strip()
        code = opp[:3].upper()
        full = TEAM_NAMES_FULL.get(code, code)
        if "(H)" in opp:
            return f"{full} (E)"
        elif "(A)" in opp:
            return f"{full} (D)"
        return full

    def populate_matrix(self, teams_data: list, gws: list):
        self.table.setRowCount(len(teams_data))
        self.table.setColumnCount(len(gws) + 1)
        self.table.setHorizontalHeaderLabels(["Kulüp / Takım"] + [f"GW{gw}" for gw in gws])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in range(1, len(gws) + 1):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        for row_idx, team_data in enumerate(teams_data):
            team_code = team_data.get("team", "")
            team_full = TEAM_NAMES_FULL.get(team_code, team_code)
            p_count = team_data.get("player_count", 0)
            display_team = f"  {team_full}  ({p_count} oyuncu)" if p_count > 0 else f"  {team_full}"
            team_item = QTableWidgetItem(display_team)
            team_item.setFont(self._bold_font())
            team_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            team_item.setToolTip("")
            if p_count > 0:
                team_item.setBackground(QBrush(QColor(59, 130, 246, 45)))
                team_item.setForeground(QBrush(QColor(COLORS["accent_info"])))
            else:
                team_item.setBackground(QBrush(QColor(COLORS["surface_card"])))
                team_item.setForeground(QBrush(QColor(COLORS["text_primary"])))
            self.table.setItem(row_idx, 0, team_item)

            fixtures = {f["gw"]: f for f in team_data.get("fixtures", [])}
            for col_idx, gw in enumerate(gws):
                data = fixtures.get(gw)
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if data:
                    if data.get("is_bgw"):
                        item.setText("BOŞ (BGW)")
                        bg = QColor(COLORS["fdr_bgw"])
                        fg = QColor(COLORS["text_secondary"])
                        tooltip = f"{team_full} — GW{gw}: Maç yok (Blank Gameweek)"
                    else:
                        raw_opp = data.get("opp", "")
                        fdr = int(data.get("fdr", 3) or 3)
                        formatted_opp = self._format_opponent(str(raw_opp))
                        item.setText(formatted_opp)
                        bg = QColor(COLORS.get(f"fdr_{fdr}", COLORS["fdr_3"]))
                        fg = QColor("#FFFFFF" if fdr >= 5 else COLORS["text_inverse"])
                        labels = {1: "Çok Kolay", 2: "Kolay", 3: "Dengeli", 4: "Zor", 5: "Çok Zor"}
                        tooltip = f"{team_full} vs {formatted_opp} (GW{gw}) — FDR {fdr}: {labels.get(fdr, 'Dengeli')}"
                    item.setBackground(QBrush(bg))
                    item.setForeground(QBrush(fg))
                    item.setFont(self._cell_font())
                    item.setToolTip(tooltip)
                else:
                    item.setText("—")
                    item.setBackground(QBrush(QColor(COLORS["surface_card"])))
                    item.setForeground(QBrush(QColor(COLORS["text_muted"])))
                self.table.setItem(row_idx, col_idx + 1, item)

        # Set exact table height to eliminate empty vertical space
        hdr_height = self.table.horizontalHeader().sizeHint().height() or 28
        self.table.setFixedHeight(len(teams_data) * 28 + hdr_height + 6)

    @staticmethod
    def _bold_font() -> QFont:
        return QFont("Inter", 11, QFont.Weight.Bold)

    @staticmethod
    def _cell_font() -> QFont:
        return QFont("Inter", 10, QFont.Weight.Bold)
