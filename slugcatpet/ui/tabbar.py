"""侧边 Tab：收起态可拖动箭头，展开态图标盘+动作列。"""
from __future__ import annotations
import math
from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QGridLayout,
                               QFrame, QLabel, QGraphicsOpacityEffect)
from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QRect, QRectF,
                            QPointF, QPoint, QSize, QEvent)
from PySide6.QtGui import (QGuiApplication, QColor, QPainter, QPen, QPolygonF,
                           QPainterPath, QPixmap, QIcon, QLinearGradient,
                           QRadialGradient)
from ..i18n import t
from ..cats import get as get_cat_def
from .tips import install as install_tip

# 图标猫用 Saint 定义
_SAINT = get_cat_def("saint")
_HEAD_ATLAS, _HEAD_FAM = _SAINT.frames["head"]
_FACE_ATLAS, _FACE_FAM = _SAINT.frames["face"]

COLLAPSED_W, COLLAPSED_H = 24, 48
EXPANDED_W = 120
EXPANDED_H = 250                       # 仅估值，实际走 _expanded_h()
SLIDE_MS = 150
# 图标盘配色（贴合面板绿橄榄调）
_ICON_GREY = QColor(192, 199, 183)
_POLE_EDGE = QColor(20, 22, 26)
_POLE_SHEEN = QColor(104, 112, 126)
_POLE_CORE = QColor(40, 42, 47)
_POLE_TILE = QColor(255, 255, 255, 12)
_ICON_SAINT = QColor(*_SAINT.body_color)
_ICON_EYE = QColor(*_SAINT.eye_color)
_ICON_AMBER = QColor(233, 203, 138)
_ICON_FACET = QColor(70, 76, 66, 160)
_ICON_RED = QColor(210, 96, 84)
_FRUIT_TOP = QColor(140, 185, 255)
_FRUIT_BOT = QColor(28, 64, 210)
_FRUIT_OUTLINE = QColor(22, 26, 44)
_LAMP_OUTLINE = QColor(255, 70, 20)
_LAMP_FLESH = QColor(255, 248, 230)
_SLIME_BODY = QColor(255, 122, 26)
_SLIME_TENDRIL = QColor(204, 92, 16)
_SLIME_GLOW = QColor(255, 150, 50, 90)
_BAT_BODY = QColor(24, 26, 30)
_BAT_EYE = QColor(232, 236, 226)


def _pen(c, w, cap=True):
    p = QPen(c, w)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if cap:
        p.setCapStyle(Qt.PenCapStyle.RoundCap)
    return p


_CAT_HEAD = "Kill_Slugcat"             # 横杆实心猫头帧


def _cat_ready(atlas):
    """图集含所需帧才叠猫，否则回退纯杆。"""
    if atlas is None:
        return False
    base = atlas.get("base")
    return (base.has("BodyA") and base.has("LegsAVerticalPole") and base.has("PlayerArm0")
            and atlas.get(_FACE_ATLAS).has(_FACE_FAM + "1") and base.has("OnTopOfTerrainHand")
            and atlas.get(_HEAD_ATLAS).has(_HEAD_FAM + "0") and atlas.get("ui").has(_CAT_HEAD))


def _blit(p, atlas, key, frame, center, k, w, rot=0.0, tint=None):
    """图集帧染色缩放绘制；rot 顺时针度。"""
    pm = atlas.sprite(key, frame, tint or _ICON_SAINT, padded=False)
    sc = k * w / 22.0
    pw, ph = pm.width() * sc, pm.height() * sc
    p.save()
    p.translate(center.x(), center.y())
    if rot:
        p.rotate(rot)
    p.drawPixmap(QRectF(-pw / 2, -ph / 2, pw, ph), pm, QRectF(pm.rect()))
    p.restore()


def _pole_rod(p, r, vertical):
    """近黑圆柱杆 + 高光渐变 + 圆头。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    if vertical:
        bw = w * 0.22
        rod = QRectF(cx - bw / 2, r.top() + h * 0.04, bw, h * 0.92)
        g = QLinearGradient(rod.left(), 0.0, rod.right(), 0.0)   # 横向受光
        rad = bw / 2
    else:
        bh = h * 0.24
        rod = QRectF(r.left() + w * 0.04, cy - bh / 2, w * 0.92, bh)
        g = QLinearGradient(0.0, rod.top(), 0.0, rod.bottom())   # 纵向受光
        rad = bh / 2
    g.setColorAt(0.0, _POLE_EDGE)
    g.setColorAt(0.30, _POLE_SHEEN)
    g.setColorAt(0.55, _POLE_CORE)
    g.setColorAt(1.0, _POLE_EDGE)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(rod, rad, rad)


def _paint_pole_icon(p, r, vertical, atlas=None):
    """近黑杆+高光渐变；有图集叠 Saint 绿蛞蝓猫。"""
    w = r.width()
    L, T = r.left(), r.top()

    def Pt(fx, fy):
        return QPointF(L + fx * w, T + fy * r.height())

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_POLE_TILE)
    p.drawRoundedRect(r, w * 0.24, w * 0.24)

    if not _cat_ready(atlas):
        _pole_rod(p, r, vertical)
        return

    if vertical:
        # 整猫在杆后，右手压杆前
        _blit(p, atlas, "base", "LegsAVerticalPole", Pt(0.60, 0.66), 0.95, w)
        _blit(p, atlas, "base", "BodyA", Pt(0.64, 0.48), 0.50, w)
        _blit(p, atlas, "base", "PlayerArm0", Pt(0.56, 0.47), 0.36, w, rot=16.0)
        _blit(p, atlas, _HEAD_ATLAS, _HEAD_FAM + "0", Pt(0.64, 0.30), 0.46, w)
        _blit(p, atlas, _FACE_ATLAS, _FACE_FAM + "1", Pt(0.64, 0.28), 0.46, w, tint=_ICON_EYE)
        _blit(p, atlas, "base", "OnTopOfTerrainHand", Pt(0.39, 0.35), 0.37, w)  # 左手·杆后
        _pole_rod(p, r, vertical)                           # 杆压上
        _blit(p, atlas, "base", "OnTopOfTerrainHand", Pt(0.575, 0.47), 0.37, w)  # 右手·杆前
    else:
        # 先画猫，最后压杆盖住臂中段
        p.setPen(_pen(_ICON_SAINT, 0.11 * w))
        p.drawLine(Pt(0.5, 0.78), Pt(0.5, 0.88))            # 小身
        p.setPen(_pen(_ICON_SAINT, 0.045 * w))
        p.drawLine(Pt(0.5, 0.88), Pt(0.44, 0.97))           # 双腿垂
        p.drawLine(Pt(0.5, 0.88), Pt(0.56, 0.97))
        _blit(p, atlas, "ui", _CAT_HEAD, Pt(0.5, 0.82), 0.60, w)   # 大头
        p.setPen(_pen(_ICON_SAINT, 0.055 * w))              # 双臂上举
        p.drawLine(Pt(0.45, 0.74), Pt(0.415, 0.325))
        p.drawLine(Pt(0.55, 0.74), Pt(0.585, 0.325))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_ICON_SAINT)
        rr = 0.033 * w
        for hx in (0.415, 0.585):                           # 爪尖
            p.drawEllipse(Pt(hx, 0.325), rr, rr)
        _pole_rod(p, r, vertical)                           # 杆最后压上


def _paint_place_icon(p, kind, r, atlas=None):
    """在矩形 r 内画一个可交互实体图标。"""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()

    if kind == "vpole":
        _paint_pole_icon(p, r, vertical=True, atlas=atlas)
    elif kind == "hpole":
        _paint_pole_icon(p, r, vertical=False, atlas=atlas)
    elif kind == "fruit":
        # 果子 sprite 缩小+蓝渐变，缺图集回退矢量
        if atlas is not None and atlas.get("base").has("DangleFruit0A"):
            _paint_fruit_sprite(p, r, atlas)
        else:
            _paint_fruit_fallback(p, r)
    elif kind == "stone":
        # 不规则鹅卵石 + 棱线
        ox, oy = cx, cy + h * 0.04
        pts = [(-0.54, 0.12), (-0.30, -0.40), (0.10, -0.46),
               (0.54, -0.12), (0.46, 0.34), (-0.12, 0.46)]
        poly = [QPointF(ox + dx * w * 0.56, oy + dy * h * 0.50) for dx, dy in pts]
        p.setPen(_pen(_ICON_GREY, max(1.8, w * 0.13), cap=False)); p.setBrush(_ICON_GREY)
        p.drawPolygon(QPolygonF(poly))
        p.setPen(_pen(_ICON_FACET, max(1.2, w * 0.07))); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(ox - w * 0.20, oy - h * 0.16),
                   QPointF(ox + w * 0.08, oy - h * 0.24))
    elif kind == "lamp":
        # 灯泡 sprite+暖光圈，缺图集回退矢量
        if atlas is not None and atlas.get("base").has("DangleFruit0A"):
            _paint_lamp_sprite(p, r, atlas)
        else:
            d = w * 0.42
            bulb = QRectF(0, 0, d, d); bulb.moveCenter(QPointF(cx, cy))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(_ICON_AMBER)
            p.drawEllipse(bulb)
            p.setPen(_pen(_ICON_AMBER, max(1.4, w * 0.08))); p.setBrush(Qt.BrushStyle.NoBrush)
            bc, rad = bulb.center(), d / 2
            for k in range(8):
                a = math.radians(22.5 + 45 * k)
                p.drawLine(
                    QPointF(bc.x() + math.cos(a) * (rad + w * 0.05),
                            bc.y() - math.sin(a) * (rad + w * 0.05)),
                    QPointF(bc.x() + math.cos(a) * (rad + w * 0.18),
                            bc.y() - math.sin(a) * (rad + w * 0.18)))
    elif kind == "slimemold":
        _paint_slimemold_icon(p, r, atlas)
    elif kind == "batfly":
        # 蝙蝠剪影：身+双翅+亮眼
        bx, by = cx, cy + h * 0.06
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(_BAT_BODY)
        for sgn in (-1, 1):                                    # 双翅镜像
            wing = [QPointF(bx + sgn * w * 0.02, by - h * 0.16),
                    QPointF(bx + sgn * w * 0.46, by - h * 0.34),
                    QPointF(bx + sgn * w * 0.30, by + h * 0.06),
                    QPointF(bx + sgn * w * 0.02, by + h * 0.10)]
            p.drawPolygon(QPolygonF(wing))
        body = QRectF(0, 0, w * 0.26, h * 0.40)
        body.moveCenter(QPointF(bx, by))
        p.drawEllipse(body)
        p.setBrush(_BAT_EYE)
        p.drawEllipse(QPointF(bx, by - h * 0.09), w * 0.035, w * 0.035)
    elif kind == "clear":
        # 禁止圈 ⊘
        d = min(w, h) * 0.90
        ring = QRectF(0, 0, d, d); ring.moveCenter(QPointF(cx, cy))
        p.setPen(_pen(_ICON_RED, max(1.8, w * 0.13))); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ring)
        a, rr = math.radians(45), d / 2
        p.drawLine(QPointF(cx - math.cos(a) * rr, cy + math.sin(a) * rr),
                   QPointF(cx + math.cos(a) * rr, cy - math.sin(a) * rr))


def _paint_lamp_sprite(p, r, atlas):
    """灯笼 sprite 缩小+暖光圈。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    glow_r = min(w, h) * 0.52
    grad = QRadialGradient(QPointF(cx, cy), glow_r)
    grad.setColorAt(0.0, QColor(255, 150, 70, 165))
    grad.setColorAt(0.45, QColor(255, 100, 35, 80))
    grad.setColorAt(1.0, QColor(255, 70, 0, 0))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(grad)
    p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)
    sw, sh = atlas.source_size("base", "DangleFruit0A")
    s = min(w / sw, h / sh) * 0.58                                 # 留出光圈
    dw, dh = sw * s, sh * s
    dst = QRectF(cx - dw / 2, cy - dh / 2, dw, dh)
    outline = atlas.sprite("base", "DangleFruit0A", _LAMP_OUTLINE)
    flesh = atlas.sprite("base", "DangleFruit0B", _LAMP_FLESH)
    p.save()                                                      # 镜像：粗头朝上
    p.translate(cx, cy); p.scale(1.0, -1.0)
    local = QRectF(-dw / 2, -dh / 2, dw, dh)
    p.drawPixmap(local, outline, QRectF(outline.rect()))
    p.drawPixmap(local, flesh, QRectF(flesh.rect()))
    p.restore()


def _paint_fruit_sprite(p, r, atlas):
    """果子 sprite 缩小绘入 r，果肉套蓝渐变。"""
    sw, sh = atlas.source_size("base", "DangleFruit0A")
    s = min(r.width() / sw, r.height() / sh) * 0.8
    dw, dh = sw * s, sh * s
    dst = QRectF(r.center().x() - dw / 2, r.center().y() - dh / 2, dw, dh)
    outline = atlas.sprite("base", "DangleFruit0A", _FRUIT_OUTLINE)
    flesh = atlas.sprite("base", "DangleFruit0B")                  # 白模，下面渐变上色
    ss = 4                                                          # 超采样防锯齿
    lw, lh = max(1, int(dw * ss)), max(1, int(dh * ss))
    layer = QPixmap(lw, lh); layer.fill(Qt.GlobalColor.transparent)
    lp = QPainter(layer)
    lp.drawPixmap(QRectF(0, 0, lw, lh), flesh, QRectF(flesh.rect()))
    lp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    g = QLinearGradient(QPointF(0, 0), QPointF(0, lh))
    g.setColorAt(0.0, _FRUIT_TOP); g.setColorAt(1.0, _FRUIT_BOT)
    lp.fillRect(layer.rect(), g); lp.end()
    p.drawPixmap(dst, outline, QRectF(outline.rect()))
    p.drawPixmap(dst, layer, QRectF(layer.rect()))


def _paint_slimemold_icon(p, r, atlas=None):
    """黏菌 sprite 染橙；缺图集回退矢量。"""
    if atlas is not None and atlas.get("ui").has("Symbol_SlimeMold"):
        sw, sh = atlas.source_size("ui", "Symbol_SlimeMold")
        s = min(r.width() / sw, r.height() / sh) * 0.92
        dw, dh = sw * s, sh * s
        pm = atlas.sprite("ui", "Symbol_SlimeMold", _SLIME_BODY)
        p.drawPixmap(QRectF(r.center().x() - dw / 2, r.center().y() - dh / 2, dw, dh),
                     pm, QRectF(pm.rect()))
        return
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    bx, by = cx, cy - h * 0.14
    glow_r = min(w, h) * 0.42
    grad = QRadialGradient(QPointF(bx, by), glow_r)
    grad.setColorAt(0.0, _SLIME_GLOW)
    grad.setColorAt(1.0, QColor(255, 150, 50, 0))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(grad)
    p.drawEllipse(QPointF(bx, by), glow_r, glow_r)
    p.setPen(_pen(_SLIME_TENDRIL, max(1.6, w * 0.09)))
    for dx in (-0.22, -0.05, 0.12, 0.28):
        sx = bx + dx * w
        p.drawLine(QPointF(sx, by + h * 0.06),
                   QPointF(sx + dx * w * 0.25, by + h * 0.42))
    d = min(w, h) * 0.34
    bulb = QRectF(0, 0, d, d); bulb.moveCenter(QPointF(bx, by))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(_SLIME_BODY)
    p.drawEllipse(bulb)


def _paint_fruit_fallback(p, r):
    """无图集时的矢量水滴果回退。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    path = QPainterPath()
    path.moveTo(QPointF(cx, r.top()))
    path.cubicTo(QPointF(cx + w * 0.50, cy - h * 0.10),
                 QPointF(cx + w * 0.42, r.bottom()), QPointF(cx, r.bottom()))
    path.cubicTo(QPointF(cx - w * 0.42, r.bottom()),
                 QPointF(cx - w * 0.50, cy - h * 0.10), QPointF(cx, r.top()))
    g = QLinearGradient(QPointF(0, r.top()), QPointF(0, r.bottom()))
    g.setColorAt(0.0, _FRUIT_TOP); g.setColorAt(1.0, _FRUIT_BOT)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(g); p.drawPath(path)


def _make_place_icon(kind, size, dpr, atlas=None):
    """渲染图标为 QPixmap（离屏，避免按钮重复开 painter）。"""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    r = QRectF(0, 0, size, size)
    r.adjust(size * 0.10, size * 0.10, -size * 0.10, -size * 0.10)
    p = QPainter(pm)
    _paint_place_icon(p, kind, r, atlas)
    p.end()
    return pm


class TabBar(QWidget):
    def __init__(self, pet, app, params=None):
        super().__init__()
        self.pet = pet
        self.app = app
        self.params = params or {}
        self.expanded = False
        self._drag = None

        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Dialog)
        self.setWindowFlags(flags)
        self.setWindowTitle("slugcatpet")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        self._screen = screen
        self._edge_x = screen.x() + screen.width() - COLLAPSED_W
        self._y = self.params.get("tab_y", screen.y() + (screen.height() - EXPANDED_H) // 2)

        self._build()
        self._apply_collapsed()

    def _build(self):
        self._panel = QWidget(self)
        lay = QVBoxLayout(self._panel)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        self._panel_lay = lay     # 供 _expanded_h 读内容高度

        # 图标盘：3 列网格
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        atlas = getattr(self.pet, "atlas", None)
        place_items = [("vpole", t("tip_vpole"), self._place_vpole),
                       ("hpole", t("tip_hpole"), self._place_hpole),
                       ("fruit", t("tip_fruit"), self._place_fruit),
                       ("stone", t("tip_stone"), self._place_stone),
                       ("lamp", t("tip_lamp"), self._place_lamp),
                       ("slimemold", t("tip_slimemold"), self._place_slimemold),
                       ("batfly", t("tip_batfly"), self._place_batfly),
                       ("clear", t("tip_clear"), self._clear_all)]
        for i, (kind, tip, cb) in enumerate(place_items):
            ib = QPushButton()
            ib.setIcon(QIcon(_make_place_icon(kind, 22, dpr, atlas)))
            ib.setIconSize(QSize(22, 22))
            ib.setFixedHeight(32)
            install_tip(ib, tip)
            ib.setCursor(Qt.CursorShape.PointingHandCursor)
            ib.clicked.connect(cb)
            grid.addWidget(ib, i // 3, i % 3)
        grid_host = QWidget()
        grid_host.setLayout(grid)
        lay.addWidget(grid_host)
        lay.addWidget(self._divider())

        def btn(text, enabled, cb, tip=None):
            b = QPushButton(text)
            b.setEnabled(enabled)
            if tip:
                install_tip(b, tip)
            if cb:
                b.clicked.connect(cb)
            b.setFixedHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)
            return b

        btn(t("btn_open_settings"), True, self._open_settings)
        btn(t("btn_quit_app"), True, self._quit)
        self._panel.setStyleSheet(
            "QWidget{background:rgba(30,34,40,235);border-radius:8px;}"
            "QPushButton{color:#e8f5d8;background:rgba(60,70,55,255);border:1px solid #4a5a3a;"
            "border-radius:5px;font-size:12px;}"
            "QPushButton:enabled:hover{background:rgba(80,100,70,255);}"
            "QPushButton:disabled{color:#777;background:rgba(45,48,52,255);}")

        # eventFilter 区分拖动/点击
        self._arrow = QPushButton("‹", self)
        self._arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow.installEventFilter(self)
        self._arrow_press = None
        self._arrow_moved = False
        self._arrow.setStyleSheet(
            "QPushButton{color:#cfe8b8;background:rgba(40,46,40,180);"
            "border:none;border-top-left-radius:8px;border-bottom-left-radius:8px;font-size:18px;}"
            "QPushButton:hover{background:rgba(60,72,55,255);}")

        # toast 需顶层窗口，防裁切
        self._toast_lbl = QLabel("", None)
        self._toast_lbl.setWindowFlags(Qt.WindowType.FramelessWindowHint
                                       | Qt.WindowType.WindowStaysOnTopHint
                                       | Qt.WindowType.ToolTip)
        self._toast_lbl.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._toast_lbl.setStyleSheet(
            "QLabel{color:#fff;background:rgba(20,22,26,235);border-radius:6px;padding:5px 9px;font-size:12px;}")
        self._toast_lbl.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_lbl.hide)

    def _apply_collapsed(self):
        self.expanded = False
        h = COLLAPSED_H
        self.setGeometry(self._edge_x, self._y, COLLAPSED_W, h)
        self._arrow.setGeometry(0, 0, COLLAPSED_W, h)
        self._arrow.setText("‹")
        self._arrow.show()
        self._panel.hide()
        eff = QGraphicsOpacityEffect(self._arrow)
        eff.setOpacity(0.45)
        self._arrow.setGraphicsEffect(eff)

    @staticmethod
    def _divider():
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet("background:rgba(120,150,100,90);border:none;")
        return f

    def _expanded_h(self):
        # 高度随内容自适应
        return self._panel_lay.sizeHint().height()

    def _apply_expanded(self):
        self.expanded = True
        h = self._expanded_h()
        x = self._screen.x() + self._screen.width() - EXPANDED_W
        self.setGeometry(x, self._y, EXPANDED_W, h)
        self._panel.setGeometry(0, 0, EXPANDED_W, h)
        self._panel.show()
        self._arrow.setGeometry(0, 0, 16, h)   # 展开态收起条
        self._arrow.setText("›")
        self._arrow.setGraphicsEffect(None)
        self._arrow.raise_()

    def toggle(self):
        if self.expanded:
            self._animate_to(self._edge_x, COLLAPSED_W, COLLAPSED_H, self._apply_collapsed)
        else:
            self._apply_expanded()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            if not self.expanded:
                self._apply_expanded()

    def _animate_to(self, x, w, h, done):
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(SLIDE_MS)
        anim.setStartValue(self.geometry())
        anim.setEndValue(QRect(x, self._y, w, h))
        anim.finished.connect(done)
        anim.start()
        self._anim = anim

    def eventFilter(self, obj, ev):
        if obj is self._arrow:
            try:
                t = ev.type()
            except AttributeError:
                return False                   # 关停期丢 type，放行
            if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                self._arrow_press = ev.globalPosition().y() - self.y()
                self._arrow_moved = False
                return False
            if t == QEvent.Type.MouseMove and self._arrow_press is not None and not self.expanded:
                ny = int(ev.globalPosition().y() - self._arrow_press)
                ny = max(self._screen.y(),
                         min(self._screen.y() + self._screen.height() - self.height(), ny))
                if abs(ny - self._y) > 2:
                    self._arrow_moved = True
                self._y = ny
                self.move(self._edge_x, ny)
                return False
            if t == QEvent.Type.MouseButtonRelease and ev.button() == Qt.MouseButton.LeftButton \
                    and self._arrow_press is not None:
                moved = self._arrow_moved
                self._arrow_press = None
                self._arrow_moved = False
                if moved and not self.expanded:
                    self.params["tab_y"] = self._y
                else:
                    self.toggle()
                return True
        return super().eventFilter(obj, ev)

    def _toast(self, msg):
        self._toast_lbl.setText(msg)
        self._toast_lbl.adjustSize()
        # 全局坐标定位于 tab 左侧
        right = EXPANDED_W if self.expanded else COLLAPSED_W
        gx = self._screen.x() + self._screen.width() - self._toast_lbl.width() - right - 8
        gy = self._y + 10
        self._toast_lbl.move(gx, gy)
        self._toast_lbl.show()
        self._toast_lbl.raise_()
        self._toast_timer.start(1600)

    def _collapse(self):
        """收起 tab，让出屏幕。"""
        if self.expanded:
            self.toggle()

    def _place_fruit(self):
        if self.pet.can_place_fruit():
            self.pet.enter_place_fruit_mode()
            self._collapse()
        else:
            self._toast(t("toast_max_fruit"))

    def _place_stone(self):
        if self.pet.can_place_stone():
            self.pet.enter_place_stone_mode()
            self._collapse()
        else:
            self._toast(t("toast_max_stone"))

    def _place_lamp(self):
        # 单灯替换旧灯，清除走"清除物体"
        self.pet.enter_place_lamp_mode()
        self._collapse()

    def _place_slimemold(self):
        if self.pet.can_place_slimemold():
            self.pet.enter_place_slimemold_mode()
            self._collapse()
        else:
            self._toast(t("toast_max_slimemold"))

    def _place_batfly(self):
        if self.pet.can_place_batfly():
            self.pet.enter_place_batfly_mode()
            self._collapse()
        else:
            self._toast(t("toast_max_batfly"))

    def _place_vpole(self):
        if self.pet.can_place_pole("vertical"):
            self.pet.enter_place_vpole_mode()
            self._collapse()
        else:
            self._toast(t("toast_max_vpole"))

    def _place_hpole(self):
        if self.pet.can_place_pole("horizontal"):
            self.pet.enter_place_hpole_mode()
            self._collapse()
        else:
            self._toast(t("toast_max_hpole"))

    def _clear_all(self):
        if (self.pet.fruits or self.pet.stones or self.pet.slimemolds
                or self.pet.batflies or self.pet.poles or self.pet.lamp is not None):
            self.pet.clear_all_items()
        else:
            self._toast(t("toast_no_object"))

    def _open_settings(self):
        # 转发给 window 打开设置窗
        self.pet.open_settings()

    def _quit(self):
        # 释放劫持后再 quit
        try:
            from ..platform.cursorfx import abort_all
            abort_all()
        except Exception:
            pass
        self.app.quit()
