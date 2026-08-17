from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QProgressBar, QSizePolicy, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from ui.theme import COLORS
from core.strategy_engine import DecisionBundle
from utils.smooth_scroll import SmoothScrollArea

class StatBadge(QFrame):
    """Uniform Metric Badge Widget for Top Summary Bar."""
    def __init__(self, icon: str, title: str, value: str, color: str = COLORS['accent_info']):
        super().__init__()
        self.setObjectName("BadgeCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(62)
        self.setMinimumWidth(120)
        
        self.setStyleSheet(f"""
            QFrame#BadgeCard {{
                background-color: {COLORS['surface_card']};
                border-radius: 10px;
                padding: 6px 12px;
                border: 1px solid {COLORS['border_default']};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        
        lbl_title = QLabel(f"{icon} {title}")
        lbl_title.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; font-weight: 800;")
        lbl_title.setWordWrap(False)
        
        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 900;")
        self.lbl_value.setWordWrap(False)
        
        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_value)


class SectionPanel(QFrame):
    """Clean Container Card with Accent Border for Strategy Sections."""
    def __init__(self, title: str, icon: str = "📌", accent_color: str = COLORS['accent_action']):
        super().__init__()
        self.setObjectName("SectionPanel")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.setStyleSheet(f"""
            QFrame#SectionPanel {{
                background-color: {COLORS['surface_card']};
                border-radius: 10px;
                padding: 12px 16px;
                border: 1px solid {COLORS['border_default']};
                border-left: 5px solid {accent_color};
            }}
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 10, 14, 12)
        self.main_layout.setSpacing(8)
        
        # Header Row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        self.lbl_title = QLabel(f"{icon} {title}")
        self.lbl_title.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 15px; font-weight: 900; letter-spacing: 0.02em;")
        header_layout.addWidget(self.lbl_title)
        
        header_layout.addStretch()
        
        self.lbl_badge = QLabel("")
        self.lbl_badge.setStyleSheet(f"""
            background-color: {COLORS['surface_elevated']};
            color: {COLORS['accent_info']};
            font-size: 12px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid {COLORS['border_default']};
        """)
        self.lbl_badge.setVisible(False)
        header_layout.addWidget(self.lbl_badge)
        
        self.main_layout.addLayout(header_layout)

    def set_badge(self, text: str, bg_color: str = None, text_color: str = None):
        if text:
            self.lbl_badge.setText(text)
            bg = bg_color or COLORS['surface_elevated']
            tc = text_color or COLORS['accent_info']
            self.lbl_badge.setStyleSheet(f"""
                background-color: {bg};
                color: {tc};
                font-size: 12px;
                font-weight: 800;
                padding: 3px 8px;
                border-radius: 6px;
                border: 1px solid {COLORS['border_default']};
            """)
            self.lbl_badge.setVisible(True)
        else:
            self.lbl_badge.setVisible(False)


class TransferView(QWidget):
    """
    Weekly Strategy & Recommendations View (💡 Öneriler):
    - HAFTALIK ÖNERİLEN TRANSFER HAMLESİ
    - TRANSFER HAKKINI DEVRETME / SAKLAMA DEĞERLENDİRMESİ
    - KAPTAN & CHIP STRATEJİSİ
    - 3-5 HAFTALIK STRATEJİK YOL HARİTASI
    """
    def __init__(self, viewmodel):
        super().__init__()
        self.viewmodel = viewmodel
        self.setStyleSheet("background: transparent;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._is_optimizing = False
        
        container = QWidget()
        container.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        container.setStyleSheet(f"background-color: {COLORS['bg_primary']};")
        self.content_layout = QVBoxLayout(container)
        self.content_layout.setContentsMargins(14, 10, 14, 10)
        self.content_layout.setSpacing(10)
        
        self._setup_ui()
        
        self.content_layout.addStretch(1)
        
        self.scroll_area.setWidget(container)
        main_layout.addWidget(self.scroll_area)
        
        # Connect signals
        self.viewmodel.bundle_ready.connect(self.on_bundle_ready)
        self.viewmodel.optimization_started.connect(self.on_optimization_started)
        self.viewmodel.error_occurred.connect(self.on_error)

    def _setup_ui(self):
        # 1. Top Header Row with Title and Small Refresh Button
        top_header = QHBoxLayout()
        lbl_page_title = QLabel("💡 HAFTALIK AKILLI STRATEJİ & TRANSFER ÖNERİLERİ")
        lbl_page_title.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 17px; font-weight: 900; letter-spacing: 0.03em;")
        top_header.addWidget(lbl_page_title)
        top_header.addStretch()
        
        self.btn_refresh = QPushButton("↻ Analizi Yenile")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent_action']};
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                padding: 3px 14px;
                border-radius: 6px;
                border: 1px solid rgba(147, 197, 253, 0.4);
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_action_hover']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['surface_elevated']};
                color: {COLORS['text_muted']};
            }}
        """)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        top_header.addWidget(self.btn_refresh)
        self.content_layout.addLayout(top_header)

        # 2. Top Summary Badges Grid (6 KPI cards)
        top_bar_widget = QWidget()
        top_bar_layout = QGridLayout(top_bar_widget)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(6)
        
        self.badge_gw = StatBadge("📅", "Hafta", "GW1", COLORS['text_primary'])
        self.badge_ft = StatBadge("🔄", "Transfer Hakkı", "1 FT", COLORS['accent_pitch'])
        self.badge_bank = StatBadge("💰", "Banka", "£0.0m", COLORS['accent_gold'])
        self.badge_cap = StatBadge("👑", "1. Kaptan", "-", COLORS['accent_gold'])
        self.badge_vcap = StatBadge("⭐", "2. Kaptan", "-", COLORS['accent_info'])
        self.badge_chip = StatBadge("🃏", "Chip Durumu", "4/4 Hazır", COLORS['text_secondary'])
        
        for b in [self.badge_gw, self.badge_ft, self.badge_bank, self.badge_cap, self.badge_vcap, self.badge_chip]:
            b.setFixedHeight(62)
            
        top_bar_layout.addWidget(self.badge_gw, 0, 0)
        top_bar_layout.addWidget(self.badge_ft, 0, 1)
        top_bar_layout.addWidget(self.badge_bank, 0, 2)
        top_bar_layout.addWidget(self.badge_cap, 0, 3)
        top_bar_layout.addWidget(self.badge_vcap, 0, 4)
        top_bar_layout.addWidget(self.badge_chip, 0, 5)
        
        self.content_layout.addWidget(top_bar_widget)

        # 3. Kadro Sağlık Paneli
        self.health_card = QFrame()
        self.health_card.setObjectName("HealthCard")
        self.health_card.setStyleSheet(f"""
            QFrame#HealthCard {{
                background-color: {COLORS['surface_card']};
                border: 1px solid {COLORS['border_default']};
                border-left: 4px solid {COLORS['status_success']};
                border-radius: 10px;
                padding: 8px 14px;
            }}
        """)
        health_layout = QVBoxLayout(self.health_card)
        health_layout.setContentsMargins(10, 8, 10, 8)
        health_layout.setSpacing(6)
        
        self.lbl_health_header = QLabel("🏥 KADRO SAĞLIK VE OYNAMA DURUMU: Kontrol ediliyor...")
        self.lbl_health_header.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 15px; font-weight: 900;")
        health_layout.addWidget(self.lbl_health_header)
        
        self.health_pills_frame = QWidget()
        self.health_pills_layout = QVBoxLayout(self.health_pills_frame)
        self.health_pills_layout.setContentsMargins(0, 0, 0, 0)
        self.health_pills_layout.setSpacing(6)
        self.health_pills_frame.setVisible(False)
        health_layout.addWidget(self.health_pills_frame)
        
        self.content_layout.addWidget(self.health_card)

        # -------------------------------------------------------------
        # 🟢 BÖLÜM 1: HAFTALIK ÖNERİLEN TRANSFER HAMLESİ
        # -------------------------------------------------------------
        self.panel_transfer = SectionPanel("HAFTALIK ÖNERİLEN TRANSFER HAMLESİ", "🟢", COLORS['accent_pitch'])
        c1_layout = QVBoxLayout()
        c1_layout.setSpacing(8)
        
        self.c1_box = QFrame()
        self.c1_box.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(34, 197, 94, 0.04);
                border-radius: 10px;
                padding: 12px 16px;
                border: 1px solid rgba(34, 197, 94, 0.25);
            }}
        """)
        c1_box_layout = QVBoxLayout(self.c1_box)
        c1_box_layout.setContentsMargins(12, 10, 12, 10)
        c1_box_layout.setSpacing(8)
        
        self.lbl_c1_action = QLabel("Optimal hamle hesaplanıyor...")
        self.lbl_c1_action.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 17px; font-weight: 900;")
        self.lbl_c1_action.setWordWrap(True)
        c1_box_layout.addWidget(self.lbl_c1_action)
        
        self.lbl_c1_stats = QLabel("")
        self.lbl_c1_stats.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px; font-weight: 700;")
        c1_box_layout.addWidget(self.lbl_c1_stats)
        
        # 3-4 Concise Reason Bullets Container
        self.c1_reasons_frame = QWidget()
        self.c1_reasons_frame.setStyleSheet("background: transparent; border: none;")
        self.c1_reasons_layout = QVBoxLayout(self.c1_reasons_frame)
        self.c1_reasons_layout.setContentsMargins(0, 4, 0, 0)
        self.c1_reasons_layout.setSpacing(6)
        c1_box_layout.addWidget(self.c1_reasons_frame)
        
        c1_layout.addWidget(self.c1_box)
        self.panel_transfer.main_layout.addLayout(c1_layout)
        self.content_layout.addWidget(self.panel_transfer)

        # -------------------------------------------------------------
        # 🔵 BÖLÜM 2: KAPTAN & CHIP STRATEJİSİ
        # -------------------------------------------------------------
        self.panel_captain = SectionPanel("KAPTAN & CHIP STRATEJİSİ", "🔵", COLORS['accent_info'])
        c3_layout = QVBoxLayout()
        c3_layout.setSpacing(8)
        
        # Captains Sub-Grid
        self.c3_cap_frame = QWidget()
        c3_cap_layout = QHBoxLayout(self.c3_cap_frame)
        c3_cap_layout.setContentsMargins(0, 0, 0, 0)
        c3_cap_layout.setSpacing(8)
        
        # Cap 1 Box
        self.cap1_box = QFrame()
        self.cap1_box.setStyleSheet(f"background-color: {COLORS['surface_elevated']}; border: 1px solid {COLORS['border_default']}; border-radius: 8px; padding: 8px 12px;")
        cap1_layout = QVBoxLayout(self.cap1_box)
        cap1_layout.setContentsMargins(8, 6, 8, 6)
        cap1_layout.setSpacing(3)
        self.lbl_cap1_header = QLabel("👑 1. KAPTAN (Güvenli / Yüksek Tavan)")
        self.lbl_cap1_header.setStyleSheet(f"color: {COLORS['accent_gold']}; font-size: 13px; font-weight: 900;")
        self.lbl_cap1_body = QLabel("Belirleniyor...")
        self.lbl_cap1_body.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px; font-weight: 700;")
        cap1_layout.addWidget(self.lbl_cap1_header)
        cap1_layout.addWidget(self.lbl_cap1_body)
        c3_cap_layout.addWidget(self.cap1_box, 1)
        
        # Cap 2 Box
        self.cap2_box = QFrame()
        self.cap2_box.setStyleSheet(f"background-color: {COLORS['surface_elevated']}; border: 1px solid {COLORS['border_default']}; border-radius: 8px; padding: 8px 12px;")
        cap2_layout = QVBoxLayout(self.cap2_box)
        cap2_layout.setContentsMargins(8, 6, 8, 6)
        cap2_layout.setSpacing(3)
        self.lbl_cap2_header = QLabel("⭐ 2. KAPTAN (Diferansiyel Tavan)")
        self.lbl_cap2_header.setStyleSheet(f"color: {COLORS['accent_info']}; font-size: 13px; font-weight: 900;")
        self.lbl_cap2_body = QLabel("Belirleniyor...")
        self.lbl_cap2_body.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px; font-weight: 700;")
        cap2_layout.addWidget(self.lbl_cap2_header)
        cap2_layout.addWidget(self.lbl_cap2_body)
        c3_cap_layout.addWidget(self.cap2_box, 1)
        
        c3_layout.addWidget(self.c3_cap_frame)
        
        # Detailed 4-Chip Status & Strategy Container
        self.c3_chip_box = QFrame()
        self.c3_chip_box.setStyleSheet(f"background-color: rgba(56, 189, 248, 0.04); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 10px 14px;")
        self.c3_chip_layout = QVBoxLayout(self.c3_chip_box)
        self.c3_chip_layout.setContentsMargins(4, 4, 4, 4)
        self.c3_chip_layout.setSpacing(6)
        
        self.lbl_chip_sec_title = QLabel("🃏 TÜM CHIPLERİN DURUMU & ZAMANLAMA REHBERİ")
        self.lbl_chip_sec_title.setStyleSheet(f"color: {COLORS['accent_info']}; font-size: 13px; font-weight: 900;")
        self.c3_chip_layout.addWidget(self.lbl_chip_sec_title)
        
        self.lbl_c3_chips = QLabel("Chipler analiz ediliyor...")
        self.lbl_c3_chips.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px; font-weight: 500; line-height: 1.5;")
        self.lbl_c3_chips.setWordWrap(True)
        self.c3_chip_layout.addWidget(self.lbl_c3_chips)
        
        c3_layout.addWidget(self.c3_chip_box)
        self.panel_captain.main_layout.addLayout(c3_layout)
        self.content_layout.addWidget(self.panel_captain)

        # -------------------------------------------------------------
        # 🟣 BÖLÜM 3: ÇOK HAFTALIK STRATEJİK YOL HARİTASI (Open-FPL-Solver)
        # -------------------------------------------------------------
        self.panel_roadmap = SectionPanel("ÇOK HAFTALIK STRATEJİK YOL HARİTASI (Open-FPL-Solver)", "🟣", "#8B5CF6")
        c4_layout = QVBoxLayout()
        c4_layout.setSpacing(6)
        
        self.golden_table = QTableWidget()
        self.golden_table.setColumnCount(4)
        self.golden_table.setHorizontalHeaderLabels(["Hafta", "Önerilen Aksiyon", "Haftalık Hedef", "Stratejik Gerekçe & Fikstür Notu"])
        self.golden_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.golden_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.golden_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.golden_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.golden_table.verticalHeader().setVisible(False)
        self.golden_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.golden_table.setSelectionMode(QTableWidget.NoSelection)
        self.golden_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['surface_elevated']};
                border: 1px solid {COLORS['border_default']};
                border-radius: 8px;
                gridline-color: #1E293B;
                font-size: 13px;
            }}
            QHeaderView::section {{
                background-color: #0F172A;
                color: #94A3B8;
                font-weight: 800;
                font-size: 12px;
                border: none;
                border-bottom: 1px solid {COLORS['border_default']};
                padding: 6px 10px;
            }}
            QTableWidget::item {{
                padding: 6px 10px;
                color: #F1F5F9;
            }}
        """)
        c4_layout.addWidget(self.golden_table)
        
        self.panel_roadmap.main_layout.addLayout(c4_layout)
        self.content_layout.addWidget(self.panel_roadmap)

    def _on_refresh_clicked(self):
        if getattr(self, '_is_optimizing', False):
            return
        self._is_optimizing = True
        self.btn_refresh.setText("⏳ Analiz Ediliyor...")
        self.viewmodel.run_optimization()

    def on_optimization_started(self):
        self._is_optimizing = True
        self.btn_refresh.setText("⏳ Analiz Ediliyor...")

    def on_bundle_ready(self, bundle: DecisionBundle):
        self._is_optimizing = False
        self.btn_refresh.setText("↻ Analizi Yenile")

        # 1. Top Badges
        gw_text = f"GW{bundle.current_gw}" + (" (Sezon Öncesi)" if bundle.is_preseason else "")
        self.badge_gw.lbl_value.setText(gw_text)
        
        ft_text = f"{bundle.free_transfers_count} FT" if not bundle.is_preseason else "∞ Sınırsız"
        self.badge_ft.lbl_value.setText(ft_text)
        
        self.badge_bank.lbl_value.setText(f"£{bundle.bank_amount:.1f}m")

        # 2. Health Panel
        healthy = getattr(bundle, 'total_healthy_count', 15)
        total = getattr(bundle, 'total_squad_count', 15)
        issues = getattr(bundle, 'squad_health_issues', [])
        
        while self.health_pills_layout.count() > 0:
            item = self.health_pills_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if len(issues) == 0:
            self.lbl_health_header.setText(f"🟢 KADRO SAĞLIK DURUMU: Tam Kadro Hazır ({total}/{total} Oyuncu)")
            self.health_card.setStyleSheet(f"""
                QFrame#HealthCard {{
                    background-color: {COLORS['surface_card']};
                    border: 1px solid {COLORS['border_default']};
                    border-left: 4px solid {COLORS['status_success']};
                    border-radius: 10px;
                    padding: 8px 14px;
                }}
            """)
            self.health_pills_frame.setVisible(False)
        else:
            self.lbl_health_header.setText(f"⚠️ KADRO SAĞLIK DURUMU: {len(issues)} Riskli Oyuncu Bulunuyor")
            self.health_card.setStyleSheet(f"""
                QFrame#HealthCard {{
                    background-color: {COLORS['surface_card']};
                    border: 1px solid {COLORS['border_default']};
                    border-left: 4px solid {COLORS['status_warning']};
                    border-radius: 10px;
                    padding: 8px 14px;
                }}
            """)
            for iss in issues:
                chance = int(iss.get('chance', 0) or 0)
                color = "#EF4444" if chance < 50 else "#F59E0B"
                p_name = iss.get('web_name', 'Oyuncu')
                news = str(iss.get('news', '')).strip()
                reason_str = f" &nbsp;•&nbsp; <span style='color: #CBD5E1; font-weight: 500;'>{news}</span>" if news else ""
                lbl_pill = QLabel(
                    f"● <span style='color: #FFFFFF; font-weight: 900;'>{p_name}</span> &nbsp;"
                    f"<span style='color: {color}; font-weight: 900;'>%{chance}</span>"
                    f"{reason_str}"
                )
                lbl_pill.setTextFormat(Qt.RichText)
                lbl_pill.setWordWrap(True)
                lbl_pill.setStyleSheet("background: rgba(255, 255, 255, 0.04); border: none; border-radius: 6px; padding: 5px 12px; font-size: 13px;")
                self.health_pills_layout.addWidget(lbl_pill)
            self.health_pills_frame.setVisible(True)

        # -------------------------------------------------------------
        # 3. BÖLÜM 1: HAFTALIK ÖNERİLEN TRANSFER HAMLESİ
        # -------------------------------------------------------------
        prim = getattr(bundle, 'primary_action', {})
        while self.c1_reasons_layout.count() > 0:
            it = self.c1_reasons_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        if prim.get('type') == 'transfer' and prim.get('transfers_in') and prim.get('transfers_out'):
            self.panel_transfer.set_badge("⭐ AKTİF TRANSFER ÖNERİSİ", COLORS['surface_elevated'], COLORS['accent_pitch'])
            ins = prim['transfers_in']
            outs = prim['transfers_out']
            
            action_text = []
            for i in range(min(len(ins), len(outs))):
                p_in = ins[i]
                p_out = outs[i]
                
                in_name = getattr(p_in, 'web_name', str(p_in))
                in_cost = getattr(p_in, 'now_cost', 0) / 10.0
                out_name = getattr(p_out, 'web_name', str(p_out))
                out_cost = getattr(p_out, 'now_cost', 0) / 10.0
                
                action_text.append(
                    f"<span style='color: {COLORS['status_danger']}; font-weight: 900;'>❌ SAT:</span> <b>{out_name}</b> (£{out_cost:.1f}m) "
                    f"&nbsp;&nbsp;──►&nbsp;&nbsp;"
                    f"<span style='color: {COLORS['accent_pitch']}; font-weight: 900;'>✅ AL:</span> <b>{in_name}</b> (£{in_cost:.1f}m)"
                )
            
            self.lbl_c1_action.setText("<br>".join(action_text))
            
            net_gain = prim.get('net_xp_gain', 0.0)
            hit = prim.get('hit_cost', 0)
            rem_bank = prim.get('budget_remaining', bundle.bank_amount)
            
            self.lbl_c1_stats.setText(
                f"<b>Net Kazanç:</b> <span style='color: {COLORS['accent_pitch']}; font-weight: 900;'>+{net_gain:.1f} Puan</span> &nbsp;|&nbsp; "
                f"<b>Maliyet:</b> {'0 FT (Ücretsiz)' if hit == 0 else f'-{hit} Puan Ceza (Hit)'} &nbsp;|&nbsp; "
                f"<b>Kalan Banka:</b> £{rem_bank:.1f}m"
            )

            # Populate concise, readable bullet points (Max 3-4 bullets)
            reasons_list = prim.get('reasons', [])
            for r in reasons_list:
                lbl_r = QLabel(f"<span style='color: {COLORS['accent_pitch']}; font-weight: 900;'>•</span> &nbsp;{r}")
                lbl_r.setTextFormat(Qt.RichText)
                lbl_r.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px; font-weight: 500; background: transparent; border: none; padding: 2px 0px;")
                lbl_r.setWordWrap(True)
                self.c1_reasons_layout.addWidget(lbl_r)

            # Roll evaluation note inside transfer box
            lbl_roll = QLabel(f"<span style='color: {COLORS['accent_gold']}; font-weight: 900;'>•</span> &nbsp;<b>Transfer Hakkı Kararı:</b> Bu transfer hamlesi net +{net_gain:.1f} xP kazandırdığı için hakkı devretmek yerine bu hafta transfer yapmak daha karlı.")
            lbl_roll.setTextFormat(Qt.RichText)
            lbl_roll.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px; font-weight: 500; background: transparent; border: none; padding: 2px 0px;")
            lbl_roll.setWordWrap(True)
            self.c1_reasons_layout.addWidget(lbl_roll)
        else:
            self.panel_transfer.set_badge("🛡️ TRANSFER HAKKINI SAKLA (DEVRET)", COLORS['surface_elevated'], COLORS['accent_info'])
            self.lbl_c1_action.setText(f"<span style='color: {COLORS['accent_pitch']}; font-weight: 900;'>✓ Kadronuz Dengeli ve Hazır:</span> Bu hafta transfer hakkınızı saklamanız (devretmeniz) önerilir.")
            self.lbl_c1_stats.setText(f"<b>Kadro Durumu:</b> Optimum & Dengeli &nbsp;|&nbsp; <b>Gelecek Hafta:</b> 2 Transfer Hakkı (2 FT) &nbsp;|&nbsp; <b>Banka:</b> £{bundle.bank_amount:.1f}m")
            
            reasons_list = prim.get('reasons', [
                "Kadronuzdaki ilk 11 oyuncularının fikstürleri ve puan potansiyelleri bu hafta için yeterli.",
                "Zorunlu bir sakatlık veya acil transfer gerektiren bir durum bulunmuyor.",
                "Hakkınızı saklayarak sonraki haftaya 2 serbest transfer hakkı devredebilirsiniz."
            ])
            for r in reasons_list:
                lbl_r = QLabel(f"<span style='color: {COLORS['accent_pitch']}; font-weight: 900;'>•</span> &nbsp;{r}")
                lbl_r.setTextFormat(Qt.RichText)
                lbl_r.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px; font-weight: 500; background: transparent; border: none; padding: 2px 0px;")
                lbl_r.setWordWrap(True)
                self.c1_reasons_layout.addWidget(lbl_r)

        # -------------------------------------------------------------
        # 4. BÖLÜM 2: KAPTAN & CHIP STRATEJİSİ
        # -------------------------------------------------------------
        cap_picks = getattr(bundle, 'captain_picks', [])
        if len(cap_picks) >= 1:
            c1 = cap_picks[0]
            c1_p = c1.player
            c1_name = getattr(c1_p, 'web_name', str(c1_p))
            c1_xp = getattr(c1_p, 'xp_next_gw', 0.0)
            c1_boom = getattr(c1_p, 'boom_index', c1.boom_index)
            c1_prob = int(getattr(c1_p, 'boom_prob', c1.boom_prob) * 100)
            self.lbl_cap1_body.setText(f"<b>{c1_name}</b> &nbsp;|&nbsp; {c1_xp:.1f} xP &nbsp;|&nbsp; <span style='color: {COLORS['accent_gold']}; font-weight: 900;'>Boom: {c1_boom:.1f} (%{c1_prob} Tavan İhtimali)</span>")
            self.badge_cap.lbl_value.setText(f"{c1_name} ({c1_xp:.1f} xP)")
        else:
            self.lbl_cap1_body.setText("—")
            self.badge_cap.lbl_value.setText("—")

        if len(cap_picks) >= 2:
            c2 = cap_picks[1]
            c2_p = c2.player
            c2_name = getattr(c2_p, 'web_name', str(c2_p))
            c2_xp = getattr(c2_p, 'xp_next_gw', 0.0)
            c2_boom = getattr(c2_p, 'boom_index', c2.boom_index)
            c2_eo = getattr(c2_p, 'ownership', 10.0)
            self.lbl_cap2_body.setText(f"<b>{c2_name}</b> &nbsp;|&nbsp; {c2_xp:.1f} xP &nbsp;|&nbsp; <span style='color: {COLORS['accent_info']}; font-weight: 900;'>Boom: {c2_boom:.1f} (Sahiplik: %{c2_eo:.1f})</span>")
            self.badge_vcap.lbl_value.setText(f"{c2_name} ({c2_xp:.1f} xP)")
        else:
            self.lbl_cap2_body.setText("—")
            self.badge_vcap.lbl_value.setText("—")

        # Chip status badge & detailed chip guide
        active_chip = getattr(bundle, 'active_chip', None)
        avail_chips = getattr(bundle, 'available_chips', [])
        
        if active_chip:
            self.badge_chip.lbl_value.setText(f"Aktif: {active_chip}")
            self.badge_chip.lbl_value.setStyleSheet(f"color: {COLORS['accent_pitch']}; font-size: 14px; font-weight: 800;")
        elif avail_chips:
            self.badge_chip.lbl_value.setText(f"{len(avail_chips)}/4 Hazır")
            self.badge_chip.setToolTip(f"Kullanılabilir Chipler: {', '.join(avail_chips)}")
        else:
            self.badge_chip.lbl_value.setText("4/4 Hazır")

        # Specific timing & condition catalog for available chips
        chip_catalog = {
            "Wildcard": {
                "icon": "🎴",
                "timing": "GW 6 (Milli ara / fikstür kırılması) veya GW 19/34 (Büyük Çift Maç öncesi)",
                "condition": "Kadroda 3+ sakat/rotasyon olduğunda veya fikstürler kökten değiştiğinde"
            },
            "Free Hit": {
                "icon": "🃏",
                "timing": "GW 18 veya GW 29 / 34 (Geniş Boş Hafta - BGW)",
                "condition": "Birçok takımın maç yapmadığı eksik haftalarda geçici 11 kurmak için"
            },
            "Bench Boost": {
                "icon": "🪑",
                "timing": "GW 34 veya GW 37 (Çift Maç Haftası - DGW)",
                "condition": "15 oyuncunun tamamının aktif ve çift maç oynayacağı haftada"
            },
            "Triple Captain": {
                "icon": "👑",
                "timing": "GW 25 veya GW 34 / 37 (Çift Maç Haftası - DGW)",
                "condition": "Haaland veya Salah gibi süperstarların zayıf rakiplere karşı çift maçı olduğunda"
            }
        }

        chip_lines = []
        if active_chip:
            chip_lines.append(f"• <b>⚡ {active_chip}:</b> <span style='color: {COLORS['status_success']}; font-weight: 900;'>BU HAFTA AKTİF</span>")

        for chip_name, info in chip_catalog.items():
            if chip_name in avail_chips and chip_name != active_chip:
                chip_lines.append(
                    f"• <b>{info['icon']} {chip_name}:</b> "
                    f"<span style='color: {COLORS['accent_gold']}; font-weight: 800;'>Bu Hafta Kullanma (Sakla)</span> ➔ "
                    f"<b>Önerilen Zaman:</b> <span style='color: {COLORS['accent_info']}; font-weight: 700;'>{info['timing']}</span> "
                    f"<span style='color: {COLORS['text_secondary']};'>({info['condition']})</span>"
                )

        if not chip_lines:
            chip_lines.append("• <span style='color: #94A3B8;'>Bu hafta için önerilen veya bekleyen kullanılabilir chip bulunmuyor.</span>")

        self.lbl_c3_chips.setText("<br/>".join(chip_lines))

        # -------------------------------------------------------------
        # 5. BÖLÜM 3: ÇOK HAFTALIK STRATEJİK YOL HARİTASI (Golden Path)
        # -------------------------------------------------------------
        path = getattr(bundle, 'golden_path', [])
        self.golden_table.setRowCount(len(path))
        hdr_height = self.golden_table.horizontalHeader().sizeHint().height() or 30
        row_height = 34
        num_rows = max(1, len(path))
        calc_height = (num_rows * row_height) + hdr_height + 6
        self.golden_table.setFixedHeight(calc_height)
        
        for row_idx, item in enumerate(path):
            gw_str = f"GW {item.get('gw', '')}"
            act_str = item.get('action', '')
            tgt_str = item.get('target', '')
            rsn_str = item.get('reason', '')
            
            i_gw = QTableWidgetItem(gw_str)
            i_gw.setTextAlignment(Qt.AlignCenter)
            i_gw.setForeground(Qt.white)
            
            i_act = QTableWidgetItem(act_str)
            i_act.setForeground(Qt.white)
            
            i_tgt = QTableWidgetItem(tgt_str)
            i_tgt.setTextAlignment(Qt.AlignCenter)
            i_tgt.setForeground(Qt.white)
            
            i_rsn = QTableWidgetItem(rsn_str)
            i_rsn.setForeground(Qt.white)
            
            self.golden_table.setItem(row_idx, 0, i_gw)
            self.golden_table.setItem(row_idx, 1, i_act)
            self.golden_table.setItem(row_idx, 2, i_tgt)
            self.golden_table.setItem(row_idx, 3, i_rsn)

    def on_error(self, err_msg: str):
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setVisible(False)
        self._is_optimizing = False
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("↻ Analizi Yenile")
        self.lbl_c1_action.setText(f"<span style='color: {COLORS['status_danger']}; font-weight: 800;'>❌ Analiz Hatası:</span> {err_msg}")
