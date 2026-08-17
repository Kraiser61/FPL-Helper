from PySide6.QtWidgets import QScrollArea, QComboBox, QTabWidget
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QEvent, QObject, QCoreApplication
from PySide6.QtGui import QWheelEvent
from ui.theme import COLORS, tokens, FontManager

class TabWheelForwardFilter(QObject):
    """
    Event filter for QTabWidget & QTabBar.
    Prevents changing tabs via mouse wheel, while forwarding the wheel event 
    up to the parent QScrollArea so the page scrolls naturally.
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            parent_scroll = obj.parent()
            while parent_scroll and not isinstance(parent_scroll, QScrollArea):
                parent_scroll = parent_scroll.parent()
                
            if parent_scroll:
                QCoreApplication.sendEvent(parent_scroll.viewport(), event)
            return True
        return super().eventFilter(obj, event)


class SmoothScrollArea(QScrollArea):
    """
    High-FPS Smooth Scroll Area for 144Hz displays.
    Pixel-based scrolling with instant, crisp responsiveness using design tokens.
    Uses QPropertyAnimation with OutCubic easing (120ms duration) and target accumulation.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea { border: none; }")
        
        self.verticalScrollBar().setSingleStep(20)
        self._target_value = 0
        
        if self.viewport():
            self.viewport().setAttribute(Qt.WA_OpaquePaintEvent, False)
            self.viewport().setAutoFillBackground(True)
            self.viewport().setStyleSheet(f"background-color: {tokens.COLORS['bg_primary']};")

        self._anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setDuration(120)

    def wheelEvent(self, event: QWheelEvent):
        if not self.verticalScrollBar().isVisible():
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta != 0:
            v_bar = self.verticalScrollBar()
            if self._anim.state() != QPropertyAnimation.Running:
                self._target_value = v_bar.value()
                
            scroll_step = 60
            if delta > 0:
                self._target_value -= scroll_step
            else:
                self._target_value += scroll_step
                
            self._target_value = max(v_bar.minimum(), min(v_bar.maximum(), self._target_value))
            
            self._anim.stop()
            self._anim.setStartValue(v_bar.value())
            self._anim.setEndValue(self._target_value)
            self._anim.start()
            event.accept()
        else:
            super().wheelEvent(event)


class NoWheelComboBox(QComboBox):
    """
    Sleek QComboBox displaying options without accidental scroll-wheel triggers.
    Hides popup scrollbars and forwards scroll wheel events to parent scroll containers when closed.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(8)
        
        v = self.view()
        if v:
            v.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            v.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def showPopup(self):
        v = self.view()
        if v:
            v.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            v.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        super().showPopup()

    def wheelEvent(self, event: QWheelEvent):
        if self.view() and self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoWheelTabWidget(QTabWidget):
    """QTabWidget that prevents wheel tab switching while smoothly scrolling the page."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter = TabWheelForwardFilter(self)
        self.tabBar().installEventFilter(self._filter)

    def wheelEvent(self, event: QWheelEvent):
        event.ignore()


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
    
    app = QApplication.instance() or QApplication(sys.argv)
    
    print("--- SANITY CHECK: utils/smooth_scroll.py ---")
    
    area = SmoothScrollArea()
    content = QWidget()
    layout = QVBoxLayout(content)
    
    combo = NoWheelComboBox()
    combo.addItems(["Option 1", "Option 2"])
    layout.addWidget(combo)
    
    tab_widget = NoWheelTabWidget()
    tab_widget.addTab(QWidget(), "Tab 1")
    tab_widget.addTab(QWidget(), "Tab 2")
    layout.addWidget(tab_widget)
    
    for i in range(20):
        lbl = QLabel(f"Test Row {i}")
        lbl.setFont(FontManager.get_data_font())
        layout.addWidget(lbl)
        
    area.setWidget(content)
    assert area.widget() is not None
    assert combo.maxVisibleItems() == 8
    
    print("[SUCCESS] utils/smooth_scroll.py sanity checks passed.")

