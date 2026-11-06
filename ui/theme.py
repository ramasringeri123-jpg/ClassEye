"""Light, classic professional look: soft background, white cards, navy accents."""

ACCENT = "#1F4E78"
ACCENT_HOVER = "#2A6299"
GOOD = "#1E8449"
BAD = "#C0392B"
WARN = "#D68910"

QSS = f"""
* {{ font-family: "Segoe UI", "SF Pro Text", "Inter", sans-serif; font-size: 10pt; }}
QMainWindow, QWidget#Root {{ background: #F4F6FA; color: #1B2333; }}
QWidget {{ color: #1B2333; }}
QLabel {{ background: transparent; }}

/* sidebar */
QFrame#Sidebar {{ background: #FFFFFF; border-right: 1px solid #DDE3EC; }}
QLabel#Brand {{ font-size: 18pt; font-weight: 700; color: {ACCENT}; padding: 20px 18px 0 18px; }}
QLabel#BrandSub {{ color: #6B7689; padding: 2px 18px 18px 18px; font-size: 9pt; }}
QPushButton#Nav {{ text-align: left; padding: 11px 16px; border: none; border-radius: 8px;
                   margin: 2px 10px; color: #3A4659; background: transparent; font-size: 10.5pt; }}
QPushButton#Nav:hover {{ background: #EEF2F8; color: {ACCENT}; }}
QPushButton#Nav:checked {{ background: {ACCENT}; color: #FFFFFF; font-weight: 600; }}

/* top bar */
QFrame#TopBar {{ background: #FFFFFF; border-bottom: 1px solid #DDE3EC; }}
QLabel#PageTitle {{ font-size: 15pt; font-weight: 700; color: #1B2333; }}
QLabel#Pill {{ padding: 5px 12px; border-radius: 12px; background: #EEF2F8; color: #5B6577; }}
QLabel#PillOk {{ padding: 5px 12px; border-radius: 12px; background: #E3F4EA; color: {GOOD}; font-weight: 600; }}
QLabel#PillLive {{ padding: 5px 12px; border-radius: 12px; background: #FBE5E3; color: {BAD}; font-weight: 700; }}

/* cards */
QFrame#Card {{ background: #FFFFFF; border: 1px solid #DDE3EC; border-radius: 10px; }}
QLabel#CardTitle {{ font-weight: 700; color: {ACCENT}; font-size: 11pt; }}
QLabel#Muted {{ color: #6B7689; }}
QLabel#StatValue {{ font-size: 22pt; font-weight: 700; color: #1B2333; }}
QLabel#StatLabel {{ color: #6B7689; font-size: 9pt; }}
QLabel#Video {{ background: #111827; border-radius: 10px; color: #9CA3AF; font-size: 12pt; }}

/* inputs */
QLineEdit, QComboBox, QSpinBox {{ background: #FFFFFF; border: 1px solid #C9D1DD; border-radius: 6px;
                                  padding: 6px 8px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox QAbstractItemView {{ background: #FFFFFF; border: 1px solid #C9D1DD;
                               selection-background-color: {ACCENT}; selection-color: white; }}
QCheckBox {{ spacing: 8px; }}

/* buttons */
QPushButton {{ background: #FFFFFF; border: 1px solid #C9D1DD; border-radius: 6px; padding: 7px 14px; color: #1B2333; }}
QPushButton:hover {{ background: #EEF2F8; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #A9B4C4; background: #F1F3F7; border-color: #E1E6EE; }}
QPushButton#Primary {{ background: {ACCENT}; border: none; color: white; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Success {{ background: {GOOD}; border: none; color: white; font-weight: 600; }}
QPushButton#Success:hover {{ background: #23964F; }}
QPushButton#Danger {{ background: {BAD}; border: none; color: white; font-weight: 600; }}
QPushButton#Danger:hover {{ background: #D2463A; }}
QPushButton#Primary:disabled, QPushButton#Success:disabled, QPushButton#Danger:disabled {{
    background: #A9B4C4; color: #F4F6FA; }}

/* tables & lists */
QTableWidget, QListWidget {{ background: #FFFFFF; border: 1px solid #DDE3EC; border-radius: 6px;
                             gridline-color: #EEF1F5; alternate-background-color: #F8FAFC; }}
QTableWidget::item, QListWidget::item {{ padding: 5px; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: #DCE7F5; color: #1B2333; }}
QHeaderView::section {{ background: {ACCENT}; color: white; border: none; padding: 7px; font-weight: 600; }}
QProgressBar {{ background: #FFFFFF; border: 1px solid #C9D1DD; border-radius: 6px; height: 14px; text-align: center; }}
QProgressBar::chunk {{ background: {GOOD}; border-radius: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #C9D1DD; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QStatusBar {{ background: #FFFFFF; color: #5B6577; border-top: 1px solid #DDE3EC; }}
QMessageBox, QInputDialog {{ background: #FFFFFF; }}
"""
