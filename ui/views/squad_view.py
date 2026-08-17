from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy
)
from PySide6.QtCore import Qt
from ui.widgets.pitch_view import PitchView
from ui.theme import COLORS
from utils.smooth_scroll import SmoothScrollArea

class SquadView(QWidget):
    """
    Kadro Analizi & Optimal Dizilim Görünümü (📋 Kadro):
    Mevcut 15 kişilik kadronuzun bu haftaki fikstür ve xP potansiyeline göre
    algoritmanın önerdiği OPTİMAL 11, YEDEK SIRASI ve KAPTANLIK tercihlerini taktiksel saha üzerinde gösterir.
    """
    def __init__(self, viewmodel):
        super().__init__()
        self.viewmodel = viewmodel
        self.squad_data_ref: List[Dict[str, Any]] = []
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_area = SmoothScrollArea()
        scroll_area.setWidgetResizable(True)
        
        container = QWidget()
        container.setStyleSheet(f"background-color: {COLORS['bg_primary']};")
        self.layout = QVBoxLayout(container)
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(10)
        
        # 1. Top Informative Header Card
        self._setup_header_card()
        
        # 2. Pure Pitch View Component
        self.pitch = PitchView()
        self.pitch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.pitch)
        
        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)
        
        # Connect Signals
        self.viewmodel.squad_loaded.connect(self.populate_squad)
        self.viewmodel.lineup_optimized.connect(self.populate_pitch)

    def _setup_header_card(self):
        self.header_card = QFrame()
        self.header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface_card']};
                border: 1px solid {COLORS['border_default']};
                border-left: 4px solid {COLORS['accent_cyan']};
                border-radius: 10px;
                padding: 4px;
            }}
        """)
        main_v_layout = QVBoxLayout(self.header_card)
        main_v_layout.setContentsMargins(14, 10, 14, 10)
        main_v_layout.setSpacing(8)

        # Top row: title & stat badges
        top_row = QHBoxLayout()
        top_row.setSpacing(14)
        
        lbl_title = QLabel("🎯 ALGORİTMA OPTİMAL DİZİLİMİ & KAPTAN SEÇİMİ")
        lbl_title.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 14px; font-weight: 900; letter-spacing: 0.04em;")
        top_row.addWidget(lbl_title, stretch=1)
        
        # Stats Badges
        self.badge_formation = QLabel("Formasyon: —")
        self.badge_formation.setStyleSheet(f"background: {COLORS['surface_elevated']}; color: {COLORS['text_primary']}; border-radius: 6px; padding: 5px 10px; font-size: 12px; font-weight: 800;")
        top_row.addWidget(self.badge_formation)

        self.badge_captain = QLabel("👑 Kaptan: —")
        self.badge_captain.setStyleSheet(f"background: rgba(245, 158, 11, 0.15); color: {COLORS['accent_gold']}; border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; padding: 5px 10px; font-size: 12px; font-weight: 800;")
        top_row.addWidget(self.badge_captain)

        self.badge_vice_captain = QLabel("⭐ 2. Kaptan: —")
        self.badge_vice_captain.setStyleSheet(f"background: rgba(56, 189, 248, 0.15); color: {COLORS['accent_cyan']}; border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; padding: 5px 10px; font-size: 12px; font-weight: 800;")
        top_row.addWidget(self.badge_vice_captain)

        self.badge_xp = QLabel("✦ Optimal xP: —")
        self.badge_xp.setStyleSheet(f"background: rgba(34, 197, 94, 0.15); color: {COLORS['accent_pitch']}; border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 6px; padding: 5px 10px; font-size: 12px; font-weight: 800;")
        top_row.addWidget(self.badge_xp)

        main_v_layout.addLayout(top_row)

        # Bottom row: Advice / Change summary pill
        self.advice_pill = QLabel("✓ Dizilim analiz ediliyor...")
        self.advice_pill.setWordWrap(True)
        self.advice_pill.setStyleSheet(f"""
            background-color: rgba(15, 23, 42, 0.7);
            color: #E2E8F0;
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 6px;
            padding: 5px 12px;
            font-size: 12px;
            font-weight: 600;
        """)
        main_v_layout.addWidget(self.advice_pill)

        self.layout.addWidget(self.header_card)

    def populate_squad(self, squad_data: list):
        if not squad_data:
            return
        self.squad_data_ref = squad_data

    def populate_pitch(self, lineup_data: dict):
        if not self.squad_data_ref: 
            return
        
        # Clone player dictionaries to avoid mutating squad_data_ref (which is shared with Ana Sayfa)
        id_to_dict = {p["id"]: dict(p) for p in self.squad_data_ref}
        
        cap_id = lineup_data.get("captain_id")
        vc_id = lineup_data.get("vice_captain_id")
        user_c_id = lineup_data.get("user_captain_id")
        user_vc_id = lineup_data.get("user_vice_id")
        formation = lineup_data.get("formation", "3-5-2")
        total_xp = lineup_data.get("total_xp", 0.0)
        
        promoted_ids = set(lineup_data.get("promoted_to_starters", []))
        demoted_ids = set(lineup_data.get("demoted_to_bench", []))
        
        starting_11 = []
        for pid in lineup_data.get("starting_11", []):
            if pid in id_to_dict:
                p = id_to_dict[pid]
                p["is_captain"] = (pid == cap_id)
                p["is_vice_captain"] = (pid == vc_id)
                
                # Check suggestions
                if pid in promoted_ids:
                    p["suggestion"] = "PROMOTED"
                else:
                    p["suggestion"] = ""
                    
                p["is_cap_changed"] = (pid == cap_id and cap_id != user_c_id)
                p["is_vc_changed"] = (pid == vc_id and vc_id != user_vc_id)
                starting_11.append(p)
                
        bench_order = []
        for pid in lineup_data.get("bench_order", []):
            if pid in id_to_dict:
                p = id_to_dict[pid]
                p["is_captain"] = False
                p["is_vice_captain"] = False
                if pid in demoted_ids:
                    p["suggestion"] = "DEMOTED"
                else:
                    p["suggestion"] = ""
                p["is_cap_changed"] = False
                p["is_vc_changed"] = False
                bench_order.append(p)
        
        # Update Header Badges
        self.badge_formation.setText(f"Formasyon: {formation}")
        cap_name = id_to_dict[cap_id]["web_name"] if (cap_id and cap_id in id_to_dict) else "—"
        vc_name = id_to_dict[vc_id]["web_name"] if (vc_id and vc_id in id_to_dict) else "—"
        self.badge_captain.setText(f"👑 Kaptan: {cap_name}")
        self.badge_vice_captain.setText(f"⭐ 2. Kaptan: {vc_name}")
        self.badge_xp.setText(f"✦ Optimal xP: {total_xp:.1f}")
        
        # Build human readable change advice
        advice_parts = []
        if promoted_ids:
            prom_names = [id_to_dict[pid]["web_name"] for pid in promoted_ids if pid in id_to_dict]
            advice_parts.append(f"🔺 <b>İlk 11'e Al:</b> {', '.join(prom_names)}")
        if demoted_ids:
            dem_names = [id_to_dict[pid]["web_name"] for pid in demoted_ids if pid in id_to_dict]
            advice_parts.append(f"🔻 <b>Yedeğe Çek:</b> {', '.join(dem_names)}")
        if cap_id and user_c_id and cap_id != user_c_id and cap_id in id_to_dict:
            advice_parts.append(f"👑 <b>Kaptan Önerisi:</b> {id_to_dict[cap_id]['web_name']}")
        if vc_id and user_vc_id and vc_id != user_vc_id and vc_id in id_to_dict:
            advice_parts.append(f"⭐ <b>2. Kaptan Önerisi:</b> {id_to_dict[vc_id]['web_name']}")

        # Compare user's actual FPL outfield bench order vs optimal bench order
        user_bench_outfield = [
            p["id"] for p in sorted(
                [p for p in self.squad_data_ref if p.get("pick_position", 99) > 11 and p.get("element_type") != 1],
                key=lambda x: x.get("pick_position", 99)
            )
        ]
        opt_bench_outfield = [
            pid for pid in lineup_data.get("bench_order", [])
            if pid in id_to_dict and id_to_dict[pid].get("element_type") != 1
        ]

        # Only display bench order recommendation if it differs from user's current FPL setup
        if user_bench_outfield != opt_bench_outfield and opt_bench_outfield:
            bench_names_ordered = [
                f"{idx + 1}. {id_to_dict[pid]['web_name']}"
                for idx, pid in enumerate(opt_bench_outfield)
                if pid in id_to_dict
            ]
            advice_parts.append("🪑 <b>Yedek Sırası Önerisi:</b> " + " ➔ ".join(bench_names_ordered))

        if advice_parts:
            self.advice_pill.setText(" &nbsp;|&nbsp; ".join(advice_parts))
            self.advice_pill.setStyleSheet(f"""
                background-color: rgba(245, 158, 11, 0.12);
                color: #FCD34D;
                border: 1px solid rgba(245, 158, 11, 0.35);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            """)
        else:
            self.advice_pill.setText("✓ <b>Diziliminiz ve Kaptanınız İdeal:</b> Mevcut sahadaki ilk 11, yedek sırası ve kaptan seçiminiz haftalık en yüksek puan getirisini sunuyor.")
            self.advice_pill.setStyleSheet(f"""
                background-color: rgba(34, 197, 94, 0.12);
                color: #86EFAC;
                border: 1px solid rgba(34, 197, 94, 0.3);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12.5px;
                font-weight: 600;
            """)
        
        # Starters sorted by position order GKP -> DEF -> MID -> FWD
        POS_ORDER = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
        starting_11.sort(key=lambda x: (POS_ORDER.get(x.get("pos"), 99), -x.get("xp", 0.0)))
        
        self.pitch.set_squad(starting_11, bench_order)
