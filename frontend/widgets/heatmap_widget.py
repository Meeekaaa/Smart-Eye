import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy

from frontend.styles._colors import _BG_HEATMAP_90, _TEXT_FAINT, _WHITE_04
from frontend.ui_tokens import FONT_SIZE_SUBHEAD, RADIUS_LG, SPACE_XXXS


class HeatmapWidget(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(self._label_style())
        self._source_pixmap = None

    def set_heatmap(self, heatmap_img):
        if heatmap_img is None:
            self.clear()
            self._source_pixmap = None
            return
        if isinstance(heatmap_img, np.ndarray):
            rgb = cv2.cvtColor(heatmap_img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
        elif isinstance(heatmap_img, QPixmap):
            pixmap = heatmap_img
        else:
            return
        self._source_pixmap = pixmap
        self._rescale_source_pixmap()

    def _rescale_source_pixmap(self):
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        scaled = self._source_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_source_pixmap()

    def clear_heatmap(self):
        self._source_pixmap = None
        self.clear()
        self.setText("No Heatmap Data")
        self.setStyleSheet(self._label_style(with_text=True))

    def set_placeholder(self, text: str):
        self._source_pixmap = None
        self.clear()
        self.setText(text)
        self.setStyleSheet(self._label_style(with_text=True))

    @staticmethod
    def _label_style(*, with_text: bool = False) -> str:
        text_rules = ""
        if with_text:
            text_rules = "color: {text}; font-size: {font_size}px;".format(
                text=_TEXT_FAINT,
                font_size=FONT_SIZE_SUBHEAD,
            )
        return """
            QLabel {{
                background-color: {bg};
                {text_rules}
                border: {border_w}px solid {border};
                border-radius: {radius}px;
            }}
        """.format(
            bg=_BG_HEATMAP_90,
            text_rules=text_rules,
            border_w=SPACE_XXXS,
            border=_WHITE_04,
            radius=RADIUS_LG,
        )
