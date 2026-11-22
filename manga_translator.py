import sys
import time
import ctypes
import traceback
import threading
import easyocr
import keyboard
import numpy as np
from PIL import ImageGrab
from deep_translator import GoogleTranslator, MyMemoryTranslator

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QSystemTrayIcon, QMenu, QAction, QComboBox,
    QFrame, QSpinBox, QFontComboBox
)
from PyQt5.QtCore import Qt, QRect, pyqtSignal, QObject
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPixmap, QIcon


# سبک‌های ترجمه
STYLE_MANGA_CASUAL = "manga_casual"   # محاوره‌ای و روان مناسب مانگا/کمیک
STYLE_LITERARY = "literary"           # رسمی و ادبی
STYLE_DIRECT = "direct"               # مستقیم و سریع


class Signals(QObject):
    drag_start = pyqtSignal(int, int)
    drag_move = pyqtSignal(int, int)
    drag_end = pyqtSignal(QRect)
    result_ready = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)


def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(24, 26, 32))
    p.setPen(QPen(QColor(0, 230, 160), 4))
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(QColor(0, 230, 160))
    p.setFont(QFont("Arial", 24, QFont.Bold))
    p.drawText(pm.rect(), Qt.AlignCenter, "M")
    p.end()
    return QIcon(pm)


class SelectionOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.box = QRect()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

    def update_box(self, rect):
        self.box = rect.normalized()
        self.update()
        if not self.isVisible():
            self.show()

    def clear_box(self):
        self.box = QRect()
        self.hide()
        self.update()

    def paintEvent(self, event):
        if not self.box.isNull():
            qp = QPainter(self)
            qp.setRenderHint(QPainter.Antialiasing)
            qp.setPen(QPen(QColor(0, 240, 170), 2.5))
            qp.setBrush(QColor(0, 240, 170, 40))
            qp.drawRect(self.box)


class PopupCard(QWidget):
    def __init__(self, on_translate, get_font_config, on_font_size_quick_change):
        super().__init__()
        self.on_translate = on_translate
        self.get_font_config = get_font_config
        self.on_font_size_quick_change = on_font_size_quick_change
        self.target_rect = None
        self.last_translated_text = ""

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setStyleSheet("""
            QFrame {
                background-color: #181A20;
                border: 1.5px solid #00E6A0;
                border-radius: 10px;
            }
        """)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # نوار بالا: عنوان، کنترل سریع اندازه فونت و دکمه بستن
        top = QHBoxLayout()
        top.setSpacing(6)

        self.lbl_title = QLabel("ترجمه مانگا")
        self.lbl_title.setFont(QFont("Tahoma", 9, QFont.Bold))
        self.lbl_title.setStyleSheet("color: #00E6A0; border: none;")

        btn_minus = QPushButton("A-")
        btn_minus.setFixedSize(26, 22)
        btn_minus.setCursor(Qt.PointingHandCursor)
        btn_minus.setToolTip("کوچک‌تر کردن فونت")
        btn_minus.clicked.connect(lambda: self.on_font_size_quick_change(-1))
        btn_minus.setStyleSheet(
            "QPushButton { background: #242832; color: #DDD; border: 1px solid #3A4050; border-radius: 4px; font-size: 9pt; }"
            "QPushButton:hover { border-color: #00E6A0; color: #00E6A0; }"
        )

        btn_plus = QPushButton("A+")
        btn_plus.setFixedSize(26, 22)
        btn_plus.setCursor(Qt.PointingHandCursor)
        btn_plus.setToolTip("بزرگ‌تر کردن فونت")
        btn_plus.clicked.connect(lambda: self.on_font_size_quick_change(+1))
        btn_plus.setStyleSheet(
            "QPushButton { background: #242832; color: #DDD; border: 1px solid #3A4050; border-radius: 4px; font-size: 9pt; }"
            "QPushButton:hover { border-color: #00E6A0; color: #00E6A0; }"
        )

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.hide)
        btn_close.setStyleSheet(
            "QPushButton { color: #AAA; background: transparent; border: none; font-weight: bold; }"
            "QPushButton:hover { color: #FF5555; }"
        )

        top.addWidget(self.lbl_title)
        top.addStretch()
        top.addWidget(btn_minus)
        top.addWidget(btn_plus)
        top.addWidget(btn_close)
        lay.addLayout(top)

        # دکمه شروع ترجمه
        self.btn_do = QPushButton("🌐 ترجمه متن داخل کادر")
        self.btn_do.setCursor(Qt.PointingHandCursor)
        self.btn_do.setFont(QFont("Tahoma", 10, QFont.Bold))
        self.btn_do.clicked.connect(self._run_translate)
        self.btn_do.setStyleSheet("""
            QPushButton {
                background-color: #00E6A0;
                color: #111318;
                border: none;
                border-radius: 6px;
                padding: 7px 14px;
            }
            QPushButton:hover { background-color: #28F8B8; }
        """)
        lay.addWidget(self.btn_do)

        # متن اصلی (انگلیسی/ژاپنی)
        self.lbl_src = QLabel()
        self.lbl_src.setWordWrap(True)
        self.lbl_src.setFont(QFont("Segoe UI", 9))
        self.lbl_src.setStyleSheet("color: #9DA3B4; border: none;")
        self.lbl_src.hide()

        # ترجمه فارسی
        self.lbl_fa = QLabel()
        self.lbl_fa.setWordWrap(True)
        self.lbl_fa.setLayoutDirection(Qt.RightToLeft)
        self.lbl_fa.setAlignment(Qt.AlignRight)
        self.lbl_fa.setStyleSheet("color: #FFFFFF; border: none;")
        self.lbl_fa.hide()

        # نوار پایین برای کپی کردن ترجمه
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(6)

        self.btn_copy = QPushButton("📋 کپی ترجمه")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setFont(QFont("Tahoma", 9, QFont.Bold))
        self.btn_copy.clicked.connect(self.copy_translation)
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #232732;
                color: #00E6A0;
                border: 1px solid #00E6A0;
                border-radius: 6px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #00E6A0;
                color: #111318;
            }
        """)
        self.btn_copy.hide()

        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_copy)

        lay.addWidget(self.lbl_src)
        lay.addWidget(self.lbl_fa)
        lay.addLayout(bottom_bar)

        root.addWidget(self.card)
        self.setMaximumWidth(480)
        self.apply_font_style()

    def apply_font_style(self):
        family, size = self.get_font_config()
        self.lbl_fa.setFont(QFont(family, size))
        if self.isVisible():
            self.adjustSize()

    def show_choice(self, rect, pos):
        self.target_rect = rect
        self.lbl_title.setText("کادر آماده است")
        self.btn_do.setText("🌐 ترجمه به فارسی")
        self.btn_do.setEnabled(True)
        self.btn_do.show()
        self.lbl_src.hide()
        self.lbl_fa.hide()
        self.btn_copy.hide()
        self.adjustSize()
        self.move(pos.x() + 12, pos.y() + 12)
        self.show()

    def _run_translate(self):
        if self.target_rect:
            self.btn_do.setText("⏳ در حال ترجمه...")
            self.btn_do.setEnabled(False)
            self.adjustSize()
            self.on_translate(self.target_rect)

    def show_result(self, src, fa):
        self.last_translated_text = fa
        self.lbl_title.setText("ترجمه فارسی")
        self.btn_do.hide()
        self.lbl_src.setText(src)
        self.lbl_src.show()
        self.lbl_fa.setStyleSheet("color: #FFFFFF; border: none;")
        self.lbl_fa.setText(fa)
        self.lbl_fa.show()
        self.btn_copy.setText("📋 کپی ترجمه")
        self.btn_copy.show()
        self.apply_font_style()
        self.adjustSize()
        self.show()

    def show_err(self, msg):
        self.last_translated_text = ""
        self.lbl_title.setText("پیام / خطا")
        self.btn_do.hide()
        self.lbl_src.hide()
        self.btn_copy.hide()
        self.lbl_fa.setStyleSheet("color: #FF6B6B; border: none;")
        self.lbl_fa.setText(msg)
        self.lbl_fa.show()
        self.apply_font_style()
        self.adjustSize()
        self.show()

    def copy_translation(self):
        if not self.last_translated_text:
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_translated_text)
        self.btn_copy.setText("کپی شد ✓")


class SettingsWin(QWidget):
    def __init__(self, on_lang, on_style, on_font_change, initial_font_family, initial_font_size):
        super().__init__()
        self.on_lang = on_lang
        self.on_style = on_style
        self.on_font_change = on_font_change

        self.setWindowTitle("تنظیمات مترجم مانگا")
        self.setFixedSize(370, 310)
        self.setStyleSheet("""
            QWidget {
                background-color: #16181E;
                color: #E6E8EE;
                font-family: Tahoma;
            }
            QComboBox, QFontComboBox, QSpinBox {
                background-color: #222630;
                color: #FFFFFF;
                border: 1px solid #353B4B;
                border-radius: 6px;
                padding: 5px 8px;
            }
            QPushButton {
                background-color: #00E6A0;
                color: #111318;
                border: none;
                border-radius: 6px;
                padding: 7px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #26F7B7;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # زبان OCR
        lay.addWidget(QLabel("زبان متن مانگا / کمیک:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("انگلیسی (en)", ["en"])
        self.lang_combo.addItem("ژاپنی + انگلیسی (ja, en)", ["ja", "en"])
        self.lang_combo.currentIndexChanged.connect(
            lambda i: self.on_lang(self.lang_combo.itemData(i))
        )
        lay.addWidget(self.lang_combo)

        # سبک و لحن ترجمه
        lay.addWidget(QLabel("سبک و لحن ترجمه:"))
        self.style_combo = QComboBox()
        self.style_combo.addItem("محاوره‌ای مانگا / کمیک (روان و خودمانی)", STYLE_MANGA_CASUAL)
        self.style_combo.addItem("رسمی و ادبی (مناسب روایت و داستان)", STYLE_LITERARY)
        self.style_combo.addItem("مستقیم و سریع (بدون روان‌سازی اضافه)", STYLE_DIRECT)
        self.style_combo.currentIndexChanged.connect(
            lambda i: self.on_style(self.style_combo.itemData(i))
        )
        lay.addWidget(self.style_combo)

        # فونت و اندازه فونت
        font_row = QHBoxLayout()
        font_col = QVBoxLayout()
        font_col.addWidget(QLabel("نوع فونت:"))
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(initial_font_family))
        self.font_combo.currentFontChanged.connect(self._emit_font)
        font_col.addWidget(self.font_combo)

        size_col = QVBoxLayout()
        size_col.addWidget(QLabel("اندازه:"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(9, 24)
        self.size_spin.setValue(initial_font_size)
        self.size_spin.valueChanged.connect(self._emit_font)
        size_col.addWidget(self.size_spin)

        font_row.addLayout(font_col, 3)
        font_row.addLayout(size_col, 1)
        lay.addLayout(font_row)

        info = QLabel("Alt + کلیک چپ و درگ → کادر ترجمه | با Exit از تسک‌بار ببندید.")
        info.setStyleSheet("color: #9DA3B4; font-size: 8.5pt;")
        lay.addWidget(info)

        btn_hide = QPushButton("مخفی کردن به تسک‌بار")
        btn_hide.clicked.connect(self.hide)
        lay.addWidget(btn_hide)

    def _emit_font(self):
        self.on_font_change(self.font_combo.currentFont().family(), self.size_spin.value())

    def sync_font_size_ui(self, size):
        self.size_spin.blockSignals(True)
        self.size_spin.setValue(size)
        self.size_spin.blockSignals(False)


class AppController:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.signals = Signals()
        self.langs = ['en']
        self.translation_style = STYLE_MANGA_CASUAL
        self.font_family = "Tahoma"
        self.font_size = 12

        print("در حال بارگذاری EasyOCR...")
        self.reader = easyocr.Reader(self.langs, gpu=False)
        print("EasyOCR آماده است.")

        self.dragging = False
        self.start_pos = None

        self.overlay = SelectionOverlay()
        self.popup = PopupCard(
            on_translate=self.process_rect,
            get_font_config=lambda: (self.font_family, self.font_size),
            on_font_size_quick_change=self.change_font_size_delta
        )
        self.settings = SettingsWin(
            on_lang=self.set_lang,
            on_style=self.set_style,
            on_font_change=self.set_font,
            initial_font_family=self.font_family,
            initial_font_size=self.font_size
        )

        self.signals.drag_start.connect(self._on_start)
        self.signals.drag_move.connect(self._on_move)
        self.signals.drag_end.connect(self._on_end)
        self.signals.result_ready.connect(self.popup.show_result)
        self.signals.error_occurred.connect(self.popup.show_err)

        self._setup_tray()
        self._hook_mouse_alt_drag()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self.app)
        self.tray.setToolTip("مترجم مانگا و کمیک")
        menu = QMenu()
        menu.setLayoutDirection(Qt.RightToLeft)

        act_set = QAction("تنظیمات (سبک، فونت، زبان)", self.app)
        act_set.triggered.connect(self.settings.show)

        act_exit = QAction("بستن برنامه (Exit)", self.app)
        act_exit.triggered.connect(self.exit_app)

        menu.addAction(act_set)
        menu.addSeparator()
        menu.addAction(act_exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.settings.show() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def set_lang(self, langs):
        if langs != self.langs:
            self.langs = langs
            threading.Thread(
                target=lambda: setattr(self, "reader", easyocr.Reader(self.langs, gpu=False)),
                daemon=True
            ).start()

    def set_style(self, style_key):
        self.translation_style = style_key

    def set_font(self, family, size):
        self.font_family = family
        self.font_size = size
        self.popup.apply_font_style()

    def change_font_size_delta(self, delta):
        new_size = max(9, min(24, self.font_size + delta))
        self.font_size = new_size
        self.settings.sync_font_size_ui(new_size)
        self.popup.apply_font_style()

    def _hook_mouse_alt_drag(self):
        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        def get_pos():
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y

        def poll():
            was_down = False
            while True:
                alt_down = bool(keyboard.is_pressed('alt'))
                left_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)

                if alt_down and left_down and not was_down:
                    x, y = get_pos()
                    self.start_pos = (x, y)
                    self.dragging = True
                    self.signals.drag_start.emit(x, y)
                elif self.dragging and left_down:
                    x, y = get_pos()
                    self.signals.drag_move.emit(x, y)
                elif self.dragging and not left_down:
                    x, y = get_pos()
                    self.dragging = False
                    if self.start_pos:
                        rect = QRect(
                            min(self.start_pos[0], x),
                            min(self.start_pos[1], y),
                            abs(x - self.start_pos[0]),
                            abs(y - self.start_pos[1])
                        )
                        self.signals.drag_end.emit(rect)
                    self.start_pos = None
                elif not alt_down and self.dragging:
                    self.dragging = False
                    self.start_pos = None
                    self.overlay.clear_box()

                was_down = left_down
                threading.Event().wait(0.02)

        threading.Thread(target=poll, daemon=True).start()

    def _on_start(self, x, y):
        self.popup.hide()
        self.overlay.update_box(QRect(x, y, 1, 1))

    def _on_move(self, x, y):
        if self.start_pos:
            rect = QRect(
                min(self.start_pos[0], x),
                min(self.start_pos[1], y),
                abs(x - self.start_pos[0]),
                abs(y - self.start_pos[1])
            )
            self.overlay.update_box(rect)

    def _on_end(self, rect):
        self.overlay.clear_box()
        if rect.width() > 10 and rect.height() > 10:
            self.popup.show_choice(rect, self.app.desktop().cursor().pos())

    def _make_casual_manga_fa(self, fa_text: str) -> str:
        """روان‌سازی محاوره‌ای ترجمه برای دیالوگ‌های مانگا و کمیک"""
        replacements = [
            ("من هستم", "منم"),
            ("تو هستی", "تویی"),
            ("او است", "اونِ"),
            ("آن است", "اونِ"),
            ("می‌خواهم", "می‌خوام"),
            ("می‌خواهی", "می‌خوای"),
            ("می‌خواهد", "می‌خواد"),
            ("می‌توانم", "می‌تونم"),
            ("می‌توانی", "می‌تونی"),
            ("می‌تواند", "می‌تونه"),
            ("نمی‌توانم", "نمی‌تونم"),
            ("نمی‌توانی", "نمی‌تونی"),
            ("نمی‌تواند", "نمی‌تونه"),
            ("نیستم", "نیستم"),
            ("نیستی", "نیستی"),
            ("نیست", "نیست"),
            ("چرا که", "چون"),
            ("زیرا", "چون"),
            ("بسیار", "خیلی"),
            ("اکنون", "الان"),
            ("این‌گونه", "این‌جوری"),
            ("آن‌گونه", "اون‌جوری"),
            ("چگونه", "چطور"),
            ("بیایید", "بیاین"),
            ("برویم", "بریم"),
            ("بگویید", "بگین"),
        ]
        out = fa_text
        for formal, casual in replacements:
            out = out.replace(formal, casual)
        return out.strip()

    def _translate_text(self, text: str) -> str:
        src_code = 'ja-JP' if 'ja' in self.langs else 'en-US'
        raw_fa = None

        try:
            res = MyMemoryTranslator(source=src_code, target='fa-IR').translate(text)
            if res and "MYMEMORY WARNING" not in res.upper():
                raw_fa = res
        except Exception:
            pass

        if not raw_fa:
            time.sleep(0.4)
            last_err = None
            for _ in range(2):
                try:
                    raw_fa = GoogleTranslator(source='auto', target='fa').translate(text)
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(0.8)
            if not raw_fa:
                raise RuntimeError(f"خطا در ترجمه ({last_err}). اینترنت یا VPN را بررسی کن.")

        if self.translation_style == STYLE_MANGA_CASUAL:
            return self._make_casual_manga_fa(raw_fa)
        elif self.translation_style == STYLE_LITERARY:
            return raw_fa.strip()
        else:
            return raw_fa.strip()

    def process_rect(self, rect):
        bbox = (rect.left(), rect.top(), rect.right(), rect.bottom())
        img = ImageGrab.grab(bbox=bbox)
        arr = np.array(img)

        def worker():
            try:
                lines = self.reader.readtext(arr, detail=0, paragraph=True)
                text = " ".join([l.strip() for l in lines if l.strip()]).strip()
                if not text:
                    self.signals.error_occurred.emit("متنی داخل کادر پیدا نشد.")
                    return
                fa = self._translate_text(text)
                self.signals.result_ready.emit(text, fa)
            except Exception as e:
                traceback.print_exc()
                self.signals.error_occurred.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def exit_app(self):
        self.tray.hide()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec_())


if __name__ == "__main__":
    try:
        AppController().run()
    except Exception:
        traceback.print_exc()
        input("خطایی رخ داد. برای خروج Enter بزنید...")