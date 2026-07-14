"""共享渲染原语：软绳/带状/三角网格/atlas sprite 绘制。"""
from __future__ import annotations
import math
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtCore import QPointF, Qt


def draw_rope(painter, points, widths, color) -> None:
    """沿点链画锥形软绳（尾巴/舌头）；points 根→尖，widths 各点全宽。"""
    n = len(points)
    if n < 2:
        return
    half = [w * 0.5 for w in widths]

    def normal(i):
        ax, ay = points[max(0, i - 1)]
        bx, by = points[min(n - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        return -dy / L, dx / L

    left, right = [], []
    for i, (cx, cy) in enumerate(points):
        nx, ny = normal(i)
        hw = half[i]
        left.append(QPointF(cx + nx * hw, cy + ny * hw))
        right.append(QPointF(cx - nx * hw, cy - ny * hw))

    path = QPainterPath()
    path.moveTo(left[0])
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    path.setFillRule(Qt.FillRule.WindingFill)            # 防自交留洞

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*color) if not isinstance(color, QColor) else color)
    painter.drawPath(path)
    # 尖端圆帽
    tx, ty = points[-1]
    painter.drawEllipse(QPointF(tx, ty), half[-1], half[-1])
    painter.restore()


def blit(painter, atlas, element, x, y, rotation, scale_x, scale_y, color,
         ax=0.5, ay=0.5) -> None:
    """画 atlas sprite；锚点 (ax,ay) 归一化，钉在 (x,y)。"""
    key = atlas.find_atlas(element)
    if key is None:                                # 缺帧静默跳过
        return
    col = color if isinstance(color, QColor) else QColor(*color)
    pm = atlas.sprite(key, element, col)
    sw, sh = atlas.source_size(key, element)
    apx, apy = ax * sw, ay * sh
    painter.save()
    painter.translate(x, y)
    if rotation:
        painter.rotate(rotation)
    painter.scale(scale_x, scale_y)
    painter.drawPixmap(QPointF(-apx, -apy), pm)
    painter.restore()


def draw_fruit(painter, atlas, x, y, rot_deg, bites,
               flesh_color=(0, 0, 255), outline_color=(0, 0, 0),
               scalex=1.0, scaley=1.0) -> None:
    """果子两层叠加（A 底 / B 上），k=clamp(3-bites,0,2)。"""
    k = int(max(0, min(2, 3 - bites)))
    blit(painter, atlas, f"DangleFruit{k}A", x, y, rot_deg, scalex, scaley,
         outline_color, ax=0.5, ay=0.5)
    blit(painter, atlas, f"DangleFruit{k}B", x, y, rot_deg, scalex, scaley,
         flesh_color, ax=0.5, ay=0.5)


def draw_stone(painter, atlas, x, y, rot_deg, frame, color=(70, 72, 78), scale=1.0) -> None:
    """石头：Pebble1..14 帧，中心锚 (0.5,0.5)。"""
    blit(painter, atlas, frame, x, y, rot_deg, scale, scale, color, ax=0.5, ay=0.5)


def draw_stone_trail(painter, x, y, ux, uy, length, halfwidth, color, alpha) -> None:
    """抛石运动拖尾：宽端在石头、沿 -(ux,uy) 收成尖的半透明三角。"""
    nx, ny = -uy, ux
    tailx, taily = x - ux * length, y - uy * length
    poly = QPolygonF([QPointF(x + nx * halfwidth, y + ny * halfwidth),
                      QPointF(x - nx * halfwidth, y - ny * halfwidth),
                      QPointF(tailx, taily)])
    col = QColor(color if isinstance(color, QColor) else QColor(*color))
    col.setAlpha(alpha)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(col)
    painter.drawPolygon(poly)
    painter.restore()


def ribbon(painter, points, halfwidths, colors) -> None:
    """带状路径渲染：沿中心线挤出闭合多边形，线性渐变填充。"""
    n = len(points)
    if n < 2:
        return

    def normal(i):
        ax, ay = points[max(0, i - 1)]
        bx, by = points[min(n - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        return -dy / L, dx / L

    left, right = [], []
    for i, (cx, cy) in enumerate(points):
        nx, ny = normal(i)
        hw = halfwidths[i]
        left.append(QPointF(cx + nx * hw, cy + ny * hw))
        right.append(QPointF(cx - nx * hw, cy - ny * hw))

    path = QPainterPath()
    path.moveTo(left[0])
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    path.setFillRule(Qt.FillRule.WindingFill)        # 防自交留洞

    grad = QLinearGradient(QPointF(points[0][0], points[0][1]),
                           QPointF(points[-1][0], points[-1][1]))
    for i, c in enumerate(colors):
        grad.setColorAt(i / (n - 1), QColor(*c))

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawPath(path)
    painter.restore()


def mesh(painter, verts, tris, vcolors, outline: bool = True) -> None:
    """逐三角填充三角网格（尾/舌）；vcolors 逐顶点色（三角取均值）。"""
    if not verts or not tris:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if not outline:
        painter.setPen(Qt.PenStyle.NoPen)
    n = len(verts)
    for (i, j, k) in tris:
        if i >= n or j >= n or k >= n:
            continue
        vi, vj, vk = verts[i], verts[j], verts[k]
        if vi is None or vj is None or vk is None:
            continue
        ci, cj, ck = vcolors[i], vcolors[j], vcolors[k]
        r = int((ci[0] + cj[0] + ck[0]) / 3.0)
        g = int((ci[1] + cj[1] + ck[1]) / 3.0)
        b = int((ci[2] + cj[2] + ck[2]) / 3.0)
        col = QColor(r, g, b)
        if outline:
            # 同色细描边封住 AA 接缝
            painter.setPen(QPen(col, 0.5))
        painter.setBrush(col)
        poly = QPolygonF([QPointF(vi[0], vi[1]),
                          QPointF(vj[0], vj[1]),
                          QPointF(vk[0], vk[1])])
        painter.drawPolygon(poly)
    painter.restore()
