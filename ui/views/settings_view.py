import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QGroupBox, QMessageBox,
    QFrame, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QGuiApplication
from ui.theme import COLORS
from utils.smooth_scroll import SmoothScrollArea
from utils.logger import app_logger
from ingestion.local_sync_server import save_synced_team_to_disk, sync_signals
from core.solver.data_parser import validate_and_import_projection_csv, get_active_projection_metadata


class SettingsView(QWidget):
    """
    Sadeleştirilmiş Ayarlar & Kadro Senkronizasyonu Görünümü:
    - Tek Tıkla Tarayıcıdan Kadro Aktarma (Bookmarklet & Pano Aktarımı)
    - Çok Haftalı xP Projeksiyon CSV'si Yükleme (Open-FPL-Solver Entegrasyonu)
    - Veri Yönetimi & Yerel Önbellek (Cache) Sıfırlama
    """
    session_changed = Signal()
    projection_updated = Signal(dict)

    def __init__(self, auth_manager=None, cache_manager=None):
        super().__init__()
        self.auth_manager = auth_manager
        self.cache_manager = cache_manager
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_area = SmoothScrollArea()
        scroll_area.setWidgetResizable(True)
        
        container = QWidget()
        container.setStyleSheet(f"background-color: {COLORS['bg_primary']};")
        self.layout = QVBoxLayout(container)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.setSpacing(20)
        
        lbl_title = QLabel("⚙ AYARLAR & VERİ YÖNETİMİ")
        lbl_title.setStyleSheet(f"font-size: 22px; font-weight: 900; color: {COLORS['text_primary']}; margin-bottom: 2px;")
        lbl_title.setWordWrap(True)
        self.layout.addWidget(lbl_title)
        
        self._setup_sync_bookmarklet_group()
        self._setup_projection_csv_group()
        self._setup_cache_group()
        
        self.layout.addStretch()
        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

    def _setup_sync_bookmarklet_group(self):
        group_box = QGroupBox("🌐 Tarayıcıdan Tek Tıkla Kadro Aktarma (Yer İmi)")
        group_box.setObjectName("SettingsGroup")
        group_box.setStyleSheet(self._group_box_style(accent_color=COLORS['accent_pitch']))
        
        v_layout = QVBoxLayout(group_box)
        v_layout.setContentsMargins(18, 24, 18, 18)
        v_layout.setSpacing(12)
        
        lbl_info = QLabel(
            "FPL web sitesinde (<code>fantasy.premierleague.com</code>) takımınız açıkken tarayıcınızın yer imleri çubuğundaki "
            "<b>'FPL Kadromu Aktar'</b> butonuna 1 kez tıklamanız yeterlidir. "
            "15 kişilik güncel kadronuz, kalan bütçeniz ve transfer haklarınız hiçbir ek işlem yapmanıza gerek kalmadan bu uygulamaya anında aktarılır."
        )
        lbl_info.setTextFormat(Qt.RichText)
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13.5px; line-height: 1.5;")
        v_layout.addWidget(lbl_info)

        # Status Banner
        status_box = QFrame()
        status_box.setStyleSheet(f"background-color: {COLORS['surface_elevated']}; border: 1px solid {COLORS['border_default']}; border-radius: 8px; padding: 6px 12px;")
        sb_layout = QHBoxLayout(status_box)
        sb_layout.setContentsMargins(8, 4, 8, 4)
        lbl_status_icon = QLabel("🟢")
        lbl_status_text = QLabel("Yerel Senkronizasyon Sunucusu: <b>Aktif ve Dinliyor</b> (Port: 8765)")
        lbl_status_text.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px;")
        sb_layout.addWidget(lbl_status_icon)
        sb_layout.addWidget(lbl_status_text)
        sb_layout.addStretch()
        v_layout.addWidget(status_box)

        self.layout.addWidget(group_box)

    def _setup_projection_csv_group(self):
        """Çok Haftalı xP Projeksiyon CSV Dosyası Yükleme Grubu"""
        group_box = QGroupBox("📊 Çok Haftalı xP Projeksiyon Verisi (Open-FPL-Solver)")
        group_box.setObjectName("SettingsGroup")
        group_box.setStyleSheet(self._group_box_style(accent_color=COLORS['accent_action']))
        
        v_layout = QVBoxLayout(group_box)
        v_layout.setContentsMargins(18, 26, 18, 18)
        v_layout.setSpacing(14)
        
        lbl_info = QLabel(
            "Yeni matematiksel optimizasyon motoru (Open-FPL-Solver), çok haftalık kadro ve transfer planı yapabilmek için "
            "Solio, FPLReview veya Mikkel gibi kaynaklardan alınan beklenen puan (xP) ve süre (xMins) CSV dosyalarını kullanır."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; line-height: 1.5;")
        v_layout.addWidget(lbl_info)

        # Status Frame
        self.frame_csv_status = QFrame()
        self.frame_csv_status.setStyleSheet(f"background-color: {COLORS['surface_elevated']}; border: 1px solid {COLORS['border_default']}; border-radius: 8px; padding: 10px 14px;")
        status_layout = QVBoxLayout(self.frame_csv_status)
        status_layout.setContentsMargins(6, 6, 6, 6)
        status_layout.setSpacing(6)

        self.lbl_csv_status_title = QLabel()
        self.lbl_csv_status_title.setStyleSheet(f"font-size: 13.5px; font-weight: 800; color: {COLORS['text_primary']};")
        
        self.lbl_csv_status_detail = QLabel()
        self.lbl_csv_status_detail.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']}; line-height: 1.4;")
        
        status_layout.addWidget(self.lbl_csv_status_title)
        status_layout.addWidget(self.lbl_csv_status_detail)
        v_layout.addWidget(self.frame_csv_status)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_upload_csv = QPushButton("📂 Projeksiyon CSV'si Seç & Yükle")
        self.btn_upload_csv.setCursor(Qt.PointingHandCursor)
        self.btn_upload_csv.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent_action']};
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                padding: 10px 22px;
                border-radius: 8px;
                border: 1px solid #2563EB;
            }}
            QPushButton:hover {{
                background-color: #1D4ED8;
            }}
        """)
        self.btn_upload_csv.clicked.connect(self._on_select_csv_file)
        btn_row.addWidget(self.btn_upload_csv)

        btn_row.addStretch()
        v_layout.addLayout(btn_row)

        self._refresh_csv_status_ui()
        self.layout.addWidget(group_box)

    def _refresh_csv_status_ui(self):
        """Mevcut projeksiyon CSV'sinin durumunu arayüzde günceller."""
        meta = get_active_projection_metadata()
        if meta.get("is_valid"):
            self.lbl_csv_status_title.setText(f"🟢 Aktif Projeksiyon: <b>{meta.get('original_name', 'projections.csv')}</b>")
            self.lbl_csv_status_detail.setText(
                f"• <b>Oyuncu Sayısı:</b> {meta.get('player_count', 0)} oyuncu<br/>"
                f"• <b>Tespit Edilen Haftalar:</b> {meta.get('gw_range_str', 'Bilinmiyor')} ({len(meta.get('gameweeks', []))} hafta)<br/>"
                f"• <b>Son Güncellenme:</b> {meta.get('updated_at', 'Bilinmiyor')} ({meta.get('size_kb', 0)} KB)"
            )
            self.frame_csv_status.setStyleSheet(
                f"background-color: #052E16; border: 1px solid #16A34A; border-radius: 8px; padding: 10px 14px;"
            )
        else:
            self.lbl_csv_status_title.setText("🟡 Henüz Projeksiyon CSV Dosyası Yüklenmedi")
            self.lbl_csv_status_detail.setText(
                "Open-FPL-Solver motorunun çalışabilmesi için lütfen <i>'Projeksiyon CSV'si Seç & Yükle'</i> butonunu kullanarak "
                "Solio veya FPLReview'dan indirdiğiniz haftalık tahmin dosyasını yükleyin."
            )
            self.frame_csv_status.setStyleSheet(
                f"background-color: #2D1A05; border: 1px solid #D97706; border-radius: 8px; padding: 10px 14px;"
            )

    def _on_select_csv_file(self):
        """Kullanıcının dosya seçici ile CSV yüklemesini sağlar."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Projeksiyon CSV Dosyası Seç (Solio / FPLReview / Mikkel)",
            "",
            "CSV Dosyaları (*.csv);;Tüm Dosyalar (*.*)"
        )
        if not file_path:
            return

        try:
            meta = validate_and_import_projection_csv(file_path)
            self._refresh_csv_status_ui()
            self.projection_updated.emit(meta)
            self.session_changed.emit()

            QMessageBox.information(
                self,
                "CSV Başarıyla Yüklendi",
                f"✅ Projeksiyon dosyası başarıyla doğrulandı ve yüklendi!\n\n"
                f"• Dosya: {meta['original_name']}\n"
                f"• Oyuncu Sayısı: {meta['player_count']}\n"
                f"• Kapsanan Haftalar: {meta['gw_range_str']}\n\n"
                f"Optimizasyon motoru artık bu verileri kullanacaktır."
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "CSV Yükleme Hatası",
                f"Seçilen CSV dosyası doğrulanamadı veya okunamadı:\n\n{e}\n\n"
                f"Lütfen dosyanın geçerli bir Solio veya FPLReview formatında olduğundan emin olun."
            )

    def _on_copy_bookmarklet(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.bookmarklet_code)
        self.btn_copy_bm.setText("✓ Kopyalandı!")
        self.btn_copy_bm.setStyleSheet(f"""
            QPushButton {{
                background-color: #16A34A;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                padding: 9px 20px;
                border-radius: 8px;
            }}
        """)
        QTimer.singleShot(2500, lambda: self._reset_copy_btn())

    def _reset_copy_btn(self):
        self.btn_copy_bm.setText("📋 Kodu Panoya Kopyala")
        self.btn_copy_bm.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent_pitch']};
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                padding: 9px 20px;
                border-radius: 8px;
                border: 1px solid #16A34A;
            }}
            QPushButton:hover {{
                background-color: #16A34A;
            }}
        """)

    def _on_paste_squad_from_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text().strip()
        if not text:
            QMessageBox.warning(self, "Pano Boş", "Panoda herhangi bir metin bulunamadı.\nLütfen FPL sayfasındayken yer imine tıklayıp kopyalamayı yapın.")
            return

        try:
            data = json.loads(text)
            manager_id = data.get("manager_id", 3842372)
            team_data = data.get("team_data", data)
            
            if not isinstance(team_data, dict) or "picks" not in team_data:
                raise ValueError("JSON verisinde 'picks' listesi bulunamadı.")

            save_synced_team_to_disk({
                "manager_id": manager_id,
                "team_data": team_data
            })
            
            sync_signals.team_synced.emit({
                "manager_id": manager_id,
                "team_data": team_data
            })
            
            picks_count = len(team_data.get("picks", []))
            QMessageBox.information(
                self, 
                "Kadro Yüklendi", 
                f"✅ {picks_count} oyunculu kadronuz ve bütçeniz panodan başarıyla içeri aktarıldı!\nUygulamadaki tüm sekmeler güncellendi."
            )
        except Exception as e:
            QMessageBox.warning(
                self, 
                "Geçersiz Veri", 
                f"Panodaki veri geçerli bir FPL kadro verisi değil.\nHata detayı: {e}\n\nLütfen FPL sitesindeyken yer imine tıklayarak veriyi kopyaladığınızdan emin olun."
            )

    def _setup_cache_group(self):
        group_box = QGroupBox("🗑️ Veri Yönetimi & Yerel Önbellek (Cache)")
        group_box.setObjectName("SettingsGroup")
        group_box.setStyleSheet(self._group_box_style(accent_color=COLORS['status_danger']))
        
        v_layout = QVBoxLayout(group_box)
        v_layout.setContentsMargins(16, 24, 16, 16)
        v_layout.setSpacing(12)
        
        lbl_info = QLabel(
            "Uygulama API çağrılarını hızlandırmak ve gereksiz ağ trafiğini önlemek için genel lig verilerini "
            "(oyuncu fiyatları, sakatlıklar, xP projeksiyonları, fikstürler vb.) yerel veritabanında (SQLite) önbellekler. "
            "Önbelleği temizlediğinizde tüm lig verileri FPL resmi sunucularından en güncel haliyle baştan indirilir."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; line-height: 1.5;")
        
        btn_clear = QPushButton("🗑️ Önbelleği Temizle & Yeniden İndir")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['status_danger']};
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                padding: 10px 22px;
                border-radius: 8px;
                border: 1.5px solid #DC2626;
                min-height: 36px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['status_danger_dark']};
                border-color: #B91C1C;
            }}
        """)
        btn_clear.clicked.connect(self._on_clear_cache)
        
        v_layout.addWidget(lbl_info)
        v_layout.addWidget(btn_clear, alignment=Qt.AlignLeft)
        
        self.layout.addWidget(group_box)

    def _on_clear_cache(self):
        try:
            from data.database import db_manager
            with db_manager.get_connection() as conn:
                conn.execute("DELETE FROM api_cache_data")
                conn.execute("DELETE FROM api_cache_meta")
                conn.commit()
            QMessageBox.information(self, "Önbellek Temizlendi", "Tüm yerel API önbellekleri başarıyla temizlendi.\nUygulama verileri FPL sunucularından taze olarak çekecektir.")
            self.session_changed.emit()
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Önbellek temizlenirken hata oluştu: {e}")

    @staticmethod
    def _style_input(widget: QLineEdit) -> None:
        widget.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['surface_input']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border_default']};
                border-radius: 8px;
                padding: 9px 13px;
                font-size: 13px;
                selection-background-color: {COLORS['accent_action']};
            }}
            QLineEdit:focus {{ border: 2px solid {COLORS['accent_action']}; }}
        """)

    @staticmethod
    def _group_box_style(accent_color: str = COLORS['accent_cyan']) -> str:
        return f"""
            QGroupBox#SettingsGroup {{
                background-color: {COLORS['surface_card']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border_default']};
                border-left: 4px solid {accent_color};
                border-radius: 12px;
                margin-top: 22px;
                padding-top: 18px;
            }}
            QGroupBox#SettingsGroup::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 4px 10px;
                color: {COLORS['text_primary']};
                background-color: {COLORS['surface_elevated']};
                border: 1px solid {COLORS['border_default']};
                border-radius: 6px;
                font-size: 14px;
                font-weight: 900;
            }}
        """
