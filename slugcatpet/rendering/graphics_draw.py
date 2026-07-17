"""Drawing methods mixed into :class:`slugcatpet.graphics.SlugcatGraphics`."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from ..core.units import clampf
from ..core.gfxmath import (_hsl2rgb, _ang_from_up, _rot, _lerp, _catmull,
                            SHOULDER_OFF_Y, ARM_DIV, ARM_MAX, TAIL_RAD, TONGUE_WIDTH_SCALE)
from ..rendering.primitives import blit, mesh, ribbon


class GraphicsDrawMixin:
    def draw_sprites(self, p, atlas, timeStacker=1.0):
        """按 z 序绘制全部 sprite。"""
        ts = timeStacker
        self._draw_body_hips(p, atlas, ts)
        self._draw_tail(p, ts)
        self._draw_head(p, atlas, ts)
        floor = getattr(self.body, "visual_floor_y", self.body.H)
        p.save()
        p.setClipRect(-1e4, -1e4, 2e4, floor + 1e4)
        self._draw_legs(p, atlas, ts)
        p.restore()
        self._draw_arms(p, atlas, ts)
        # 鳃画在脸之下、头臂之上
        self._draw_gills(p, atlas, ts)
        self._draw_face(p, atlas, ts)
        self._draw_tongue(p)
        self._draw_glow(p)

    def _draw_glow(self, p):
        return

    def _draw_tail(self, p, ts=1.0):
        """尾三角网格绘制。"""
        segs = self.tail_segs
        if segs is None:
            return
        d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
        d0y = _lerp(self._last_draw0[1], self.draw0[1], ts)
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)

        # 网根 = 75%臀 + 25%上身
        cox, coy = getattr(self, "_breath_chest_off", (0.0, 0.0))
        root_x = (d1x * 3.0 + d0x + cox) / 4.0
        root_y = (d1y * 3.0 + d0y + coy) / 4.0

        if self.tail_smooth:  # 仅视觉，物理不变
            self._draw_tail_smooth(p, segs, root_x, root_y, ts)
            return

        prev_x, prev_y = root_x, root_y
        width_scale = 1.0
        root_halfw = 6.0

        verts = [None] * 15

        for i in range(4):
            seg = segs[i]
            cur_x = _lerp(seg.lx, seg.x, ts)
            cur_y = _lerp(seg.ly, seg.y, ts)

            ndx, ndy = cur_x - prev_x, cur_y - prev_y
            dist = math.hypot(ndx, ndy)
            if dist > 1e-6:
                nx, ny = ndx / dist, ndy / dist
            else:
                nx, ny = 0.0, 0.0

            px, py = -ny, nx
            joint_off = 0.0 if i == 0 else dist / 5.0
            rootw_x, rootw_y = px * (root_halfw * width_scale), py * (root_halfw * width_scale)

            verts[i * 4]     = (prev_x - rootw_x + nx * joint_off, prev_y - rootw_y + ny * joint_off)
            verts[i * 4 + 1] = (prev_x + rootw_x + nx * joint_off, prev_y + rootw_y + ny * joint_off)

            if i < 3:
                stretched_rad = TAIL_RAD[i] * seg.stretched
                tipw_x, tipw_y = px * (stretched_rad * width_scale), py * (stretched_rad * width_scale)
                verts[i * 4 + 2] = (cur_x - tipw_x - nx * joint_off, cur_y - tipw_y - ny * joint_off)
                verts[i * 4 + 3] = (cur_x + tipw_x - nx * joint_off, cur_y + tipw_y - ny * joint_off)
            else:
                verts[i * 4 + 2] = (cur_x, cur_y)  # 末段单点尖

            root_halfw = TAIL_RAD[i] * seg.stretched
            prev_x, prev_y = cur_x, cur_y

        # 手编三角表
        tris = [
            (0, 1, 2), (1, 2, 3),
            (4, 5, 6), (5, 6, 7),
            (8, 9, 10), (9, 10, 11),
            (12, 13, 14),
            (2, 3, 4), (3, 4, 5),
            (6, 7, 8), (7, 8, 9),
            (10, 11, 12), (11, 12, 13),
        ]

        vcolors = [self.BODY] * 15
        mesh(p, verts, tris, vcolors)

    def _draw_tail_smooth(self, p, segs, root_x, root_y, ts):
        """Catmull-Rom 平滑，仅视觉不改物理。"""
        width_scale = 1.0

        nodes = [(root_x, root_y)]
        for seg in segs:
            nodes.append((_lerp(seg.lx, seg.x, ts), _lerp(seg.ly, seg.y, ts)))
        widths = [6.0 * width_scale]
        for i in range(4):
            widths.append(TAIL_RAD[i] * segs[i].stretched * width_scale)
        widths[4] = 0.0

        N = max(1, int(self.tail_smooth_subdiv))
        cx = [nodes[0][0]]
        cy = [nodes[0][1]]
        cw = [widths[0]]
        for s in range(4):
            p0 = nodes[max(0, s - 1)]
            p1 = nodes[s]
            p2 = nodes[s + 1]
            p3 = nodes[min(4, s + 2)]
            for j in range(1, N + 1):
                t = j / N
                cx.append(_catmull(p0[0], p1[0], p2[0], p3[0], t))
                cy.append(_catmull(p0[1], p1[1], p2[1], p3[1], t))
                cw.append(_lerp(widths[s], widths[s + 1], t))
        # 单色全带，拼路径一次填充替代逐三角
        M = len(cx)
        left, right = [], []
        for k in range(M):
            kp = max(0, k - 1)
            kn = min(M - 1, k + 1)
            tx, ty = cx[kn] - cx[kp], cy[kn] - cy[kp]
            tl = math.hypot(tx, ty)
            if tl > 1e-6:
                nx, ny = tx / tl, ty / tl
            else:
                nx, ny = 0.0, 1.0
            perpx, perpy = -ny, nx
            w = cw[k]
            left.append(QPointF(cx[k] - perpx * w, cy[k] - perpy * w))
            right.append(QPointF(cx[k] + perpx * w, cy[k] + perpy * w))

        path = QPainterPath()
        path.moveTo(left[0])
        for q in left[1:]:
            path.lineTo(q)
        for q in reversed(right):
            path.lineTo(q)
        path.closeSubpath()
        path.setFillRule(Qt.FillRule.WindingFill)        # 防自交留洞
        col = QColor(*self.BODY)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(col, 0.5))                         # 同色细描边
        p.setBrush(col)
        p.drawPath(path)
        p.restore()

    def _draw_arms(self, p, atlas, ts=1.0):
        d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
        d0y = _lerp(self._last_draw0[1], self.draw0[1], ts)
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)

        body_axis = _ang_from_up(d0x - d1x, d0y - d1y)
        cos_axis = abs(math.cos(math.radians(body_axis)))

        anim = getattr(self.body, "animation", None)

        for j in range(2):   # 0=left, 1=right
            hand = self.hands[j]
            if hand.mode == "Retracted":
                continue

            hx = _lerp(hand.lx, hand.x, ts)
            hy = _lerp(hand.ly, hand.y, ts)

            if anim in ("ClimbOnBeam", "ZeroGPoleGrab") and hand.reached:
                continue

            sh_spread = 4.5 / (hand.retract_counter + 1.0)
            sh_spread *= cos_axis

            lx = (-1.0 + 2.0 * j) * sh_spread
            ly = SHOULDER_OFF_Y
            ox, oy = _rot(lx, ly, body_axis)
            sx, sy = d0x + ox, d0y + oy

            dist = math.hypot(sx - hx, sy - hy)
            idx = int(round(clampf(dist / ARM_DIV, 0.0, float(ARM_MAX))))
            element = "PlayerArm" + str(idx)

            rotation = _ang_from_up(sx - hx, sy - hy) + 90.0

            # scale_y：Crawl 取偏侧号，否则叉积符号
            if self.bodyMode == "Crawl":
                scale_y = -1.0 if d0x < d1x else 1.0
            else:
                denom = math.hypot(d0y - d1y, d0x - d1x) or 1.0
                dtl = ((d0y - d1y) * hx - (d0x - d1x) * hy
                       + d0x * d1y - d0y * d1x) / denom
                scale_y = math.copysign(1.0, -dtl) if dtl != 0.0 else 1.0

            blit(p, atlas, element, hx, hy, rotation,
                 1.0, scale_y, self.BODY, ax=0.9, ay=0.5)

    def _draw_hand_grips(self, p, atlas, ts=1.0):
        """抓握精灵，须在 draw_sprites 与画杆之后单独调。"""
        anim = getattr(self.body, "animation", None)
        grip_elem = ("OnTopOfTerrainHand" if anim in ("ClimbOnBeam", "ZeroGPoleGrab")
                     else "OnTopOfTerrainHand2" if anim in ("HangFromBeam", "GetUpOnBeam")
                     else None)
        if grip_elem is None:
            return
        for j in range(2):
            hand = self.hands[j]
            if hand.mode == "Retracted" or not hand.reached:
                continue
            hx = _lerp(hand.lx, hand.x, ts)
            hy = _lerp(hand.ly, hand.y, ts)
            gy = hy - (0.0 if anim in ("ClimbOnBeam", "ZeroGPoleGrab") else 3.0)
            scale_x = -1.0 if j == 1 else 1.0
            blit(p, atlas, grip_elem, hx, gy, 0.0, scale_x, 1.0, self.BODY, ax=0.5, ay=0.5)

    def _draw_body_hips(self, p, atlas, ts=1.0):
        d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
        d0y = _lerp(self._last_draw0[1], self.draw0[1], ts)
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)
        draw0 = [d0x, d0y]
        draw1 = [d1x, d1y]
        sleep = self.sleep_curl
        body_axis = _ang_from_up(draw0[0] - draw1[0], draw0[1] - draw1[1])

        breath = self.body.breath_phase(ts)
        ddx, ddy = draw0[0] - draw1[0], draw0[1] - draw1[1]
        d = math.hypot(ddx, ddy) or 1.0
        ux, uy = ddx / d, ddy / d
        upright = clampf((abs(uy) - 0.3) / 0.2, 0.0, 1.0)
        fatigue = 1.0 - self.body.energy
        # 力竭喘气：胸位沿体轴抽动
        heave = clampf((fatigue - 0.5) / 0.5, 0.0, 1.0)
        swing = 2.0 * breath - 1.0
        chest_h = swing * heave * 0.5
        head_h = swing * (heave ** 1.5) * 0.75
        self._breath_head_off = (-ux * head_h, -uy * head_h)
        chest_x = draw0[0] + ux * chest_h
        chest_y = draw0[1] + uy * chest_h
        self._breath_chest_off = (ux * chest_h, uy * chest_h)   # 供 _draw_tail 取用
        breath_bob = _lerp(0.5, 1.0, fatigue) * breath * (1.0 - upright)
        body_x = chest_x
        body_y = chest_y + 4.0 * sleep - breath_bob      # y↓ 睡眠下沉+起伏
        body_rot = body_axis
        body_sx = 1.0 + _lerp(_lerp(-0.05, 0.05, breath) * upright, 0.15, sleep)
        body_sy = 1.0                                # 竖直呼吸走 body_y，不缩 Y
        blit(p, atlas, "BodyA", body_x, body_y, body_rot, body_sx, body_sy, self.BODY,
             ax=0.5, ay=0.2105263)

        hip_x = (draw1[0] * 2.0 + chest_x) / 3.0
        hip_y = (draw1[1] * 2.0 + chest_y) / 3.0 + 3.0 * sleep
        tail0 = self.tail_segs[0] if self.tail_segs is not None else None
        if tail0 is not None:
            t0x = _lerp(tail0.lx, tail0.x, ts)
            t0y = _lerp(tail0.ly, tail0.y, ts)
            hip_rot = _ang_from_up(t0x - chest_x, t0y - chest_y)
        else:
            hip_rot = body_axis
        hip_sx = 1.0 + sleep * 0.2 + 0.05 * breath
        hip_sy = 1.0 + sleep * 0.2
        blit(p, atlas, "HipsA", hip_x, hip_y, hip_rot, hip_sx, hip_sy, self.BODY,
             ax=0.5, ay=0.5)

    def _draw_legs(self, p, atlas, ts=1.0):
        if self.bodyMode == "Swimming" and getattr(self.body, "swim_mode", None) == "deep":
            return                                          # 深游隐腿
        x = _lerp(self.legs.lx, self.legs.x, ts)
        y = _lerp(self.legs.ly, self.legs.y, ts)

        lx, ly = self.legs_dir
        rotation = _ang_from_up(-lx, -ly)

        # 仅部分分支写 ±flip，其余沿用上帧
        facing_sx = 1.0 if self.facing > 0 else -1.0

        af = self.anim_frame
        if self.bodyMode == "ClimbingOnBeam":
            anim = getattr(self.body, "animation", None)
            if anim == "BeamTip":
                element = "LegsAPole"
            elif anim == "StandOnBeam":
                element = "LegsAOnPole" + str(af if af < 7 else 0)
                self._legs_scale_x = facing_sx
            elif anim in ("HangFromBeam", "GetUpOnBeam"):
                element = self._leg_air_frame
            else:
                element = "LegsAVerticalPole"
                self._legs_scale_x = facing_sx
                d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)
                y = clampf(y, d1y - 4.0, d1y + 6.0)
        elif self.bodyMode == "Stand":
            if self.is_moving():
                n = len(self._leg_walk_frames)
                element = self._leg_walk_frames[af % n]
            else:
                element = self._leg_walk_frames[0]
            self._legs_scale_x = facing_sx
        elif self.bodyMode == "Crawl":
            if self.is_moving():
                n = len(self._leg_crawl_frames)
                element = self._leg_crawl_frames[(af // 2) % n]
            else:
                element = self._leg_crawl_frames[0]
            self._legs_scale_x = facing_sx
        else:
            element = self._leg_air_frame

        color = self.BODY
        blit(p, atlas, element, x, y, rotation, self._legs_scale_x, 1.0, color, ax=0.5, ay=0.75)

    def _draw_head(self, p, atlas, ts=1.0):
        head = self.head
        b = self.body

        head_ang = self.head_angle

        frame_idx = self._head_frame_index()
        frames = self._head_frames or [self.cat.frames["head"][1] + "0"]
        frame_idx = min(max(frame_idx, 0), len(frames) - 1)
        element = frames[frame_idx]

        scale_x = -1.0 if head_ang < 0.0 else 1.0

        hx_r = _lerp(head.lx, head.x, ts)
        hy_r = _lerp(head.ly, head.y, ts)

        s_curl = self.sleep_curl
        if s_curl > 0.0:
            d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
            d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
            side = 1.0 if d0x >= d1x else -1.0
            hx_r += side * 2.0 * s_curl
            hy_r -= 1.0 * s_curl

        # 喘气头反相偏移，_draw_body_hips 算好
        hox, hoy = getattr(self, "_breath_head_off", (0.0, 0.0))
        hx_r += hox
        hy_r += hoy

        blit(p, atlas, element, hx_r, hy_r, head_ang, scale_x, 1.0, self.BODY,
             ax=0.5, ay=0.5)

    def _draw_gills(self, p, atlas, ts=1.0):
        """溪流鳃绘制。"""
        g = self.gills
        if g is None:
            return
        # 同 _draw_face 锚点算法
        hx_i = _lerp(self.head.lx, self.head.x, ts)
        hy_i = _lerp(self.head.ly, self.head.y, ts)
        d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
        d0y = _lerp(self._last_draw0[1], self.draw0[1], ts)
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)
        if self.sleep_curl > 0.0:
            side = 1.0 if d0x >= d1x else -1.0
            hx_i += side * 2.0 * self.sleep_curl
            hy_i -= 1.0 * self.sleep_curl
        hox, hoy = getattr(self, "_breath_head_off", (0.0, 0.0))
        fx = hx_i + self.face_offset[0] + hox
        fy = hy_i + self.face_offset[1] + hoy

        gf = self.gills_flat
        hip_d = math.hypot(d0x - d1x, d0y - d1y)
        f1x, f1y = _lerp(d1x, d0x, gf), _lerp(d1y, d0y + hip_d, gf)
        body_axis = _ang_from_up(d0x - f1x, d0y - f1y)
        pvx, pvy = _rot(1.0, 0.0, body_axis)
        gh = g.graphic_height or 1.0
        n = len(g.scales)
        half = n // 2
        EFFECT = (223, 45, 234)   # 鳃品红 #DF2DEA
        xf = []
        for k in range(n):
            sc = g.scales[k]
            bx = _lerp(sc.lx, sc.x, ts)
            by = -_lerp(sc.ly, sc.y, ts)          # 鳞内部 y↑ → pet y↓
            if k < half:
                off, rot_off, scale_x = -5.0, 0.0, -sc.width
            else:
                off, rot_off, scale_x = 5.0, 180.0, sc.width
            anchor_x, anchor_y = fx + pvx * off, fy + pvy * off
            rotation = _ang_from_up(bx - anchor_x, by - anchor_y) + rot_off
            xf.append((anchor_x, anchor_y, rotation, scale_x, sc.length / gh))
        # 全 A 底先画，再画全 B 覆盖
        for ax_, ay_, rot, sxx, syy in xf:
            blit(p, atlas, "LizardScaleA3", ax_, ay_, rot, sxx, syy, self.BODY, ax=0.5, ay=0.9)
        for ax_, ay_, rot, sxx, syy in xf:
            blit(p, atlas, "LizardScaleB3", ax_, ay_, rot, sxx, syy, EFFECT, ax=0.5, ay=0.9)

    def _draw_face(self, p, atlas, ts=1.0):
        b = self.body

        hx_i = _lerp(self.head.lx, self.head.x, ts)
        hy_i = _lerp(self.head.ly, self.head.y, ts)
        if self.sleep_curl > 0.0:
            d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
            d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
            side = 1.0 if d0x >= d1x else -1.0
            hx_i += side * 2.0 * self.sleep_curl
            hy_i -= 1.0 * self.sleep_curl
        hox, hoy = getattr(self, "_breath_head_off", (0.0, 0.0))
        fx = hx_i + self.face_offset[0] + hox
        fy = hy_i + self.face_offset[1] + hoy

        rot = self.face_angle
        sx = self.face_scale_x

        # 随机彩色量化存桶，供 karma.py 读、tint 缓存有界
        if self.ascension is not None and not self.dead:
            rh = self._blink_rng._next() / 0x7FFFFFFF
            rs = self._blink_rng._next() / 0x7FFFFFFF
            rl = self._blink_rng._next() / 0x7FFFFFFF
            rh = (min(int(rh * 6.0), 5) + 0.5) / 6.0
            rs = (min(int(rs * 2.0), 1) + 0.5) / 2.0
            rl = (min(int(rl * 3.0), 2) + 0.5) / 3.0
            cr, cg, cb = _hsl2rgb(rh, rs, rl)
            face_color = (int(cr * 255), int(cg * 255), int(cb * 255))
            self._asc_face_color = face_color
        else:
            self._asc_face_color = None
            face_color = self.EYE

        face_b_frames = self._face_frames or [self.cat.frames["face"][1] + "0"]
        face_a_frames = self._face_a_frames or face_b_frames
        n_max_a = len(face_a_frames) - 1

        if self.dead:
            element = "FaceDead"
        elif self.stunned:
            element = "FaceStunned"
        elif self.ascension is not None:
            idx = int(clampf(self._face_angle_index(), 0, 8))
            element = face_a_frames[min(idx, n_max_a)]
        else:
            # sx<0 换 FaceD 族（仅工匠有）
            frames = (self._face_mirror_frames
                      if sx < 0.0 and self._face_mirror_frames else face_b_frames)
            n_max = len(frames) - 1
            if self.sleep_curl > 0.0:
                awake_idx = 7
                drowsy_idx = int(clampf(int(_lerp(awake_idx, 4.0, self.sleep_curl)), 0, 8))
                idx = int(clampf(int(_lerp(drowsy_idx, 1.0, self.sleep_curl)), 0, 8))
            elif b.bodyMode == "ZeroG":
                idx = 0
            elif b.bodyMode == "Crawl" or (b.bodyMode == "Stand" and (b.is_moving() or b.move_dir != 0)):
                idx = 4
            else:
                idx = self._face_angle_index()
            idx = int(clampf(idx, 0, 8))
            element = frames[min(idx, n_max)]

        self._draw_face_scar(p, atlas, element, fx, fy, rot)   # 疤在脸下、头上
        blit(p, atlas, element, fx, fy, rot, sx, 1.0, face_color, ax=0.5, ay=0.5)

    def _draw_face_scar(self, p, atlas, element, fx, fy, rot):
        """工匠面罩疤绘制。"""
        if self._face_scar_frame is None:
            return
        SCAR = (69, 40, 60)          # 面罩疤固定色 #45283C
        scale_x = 1.0
        if getattr(self.body, "animation", None) == "Flip":
            r = math.radians(rot)    # Flip 前移 4，y↓
            x = fx + math.sin(r) * 4.0
            y = fy - math.cos(r) * 4.0
        else:
            digit = len(element) >= 2 and element[-1].isdigit()
            n = int(element[-1]) if digit else 0
            if digit and element[-2] == "C":
                scale_x = 1.0 - n / 8.0
                x = fx + 3.0 + 4.0 * (n / 8.0)
            elif digit and element[-2] == "D":
                x = fx + 3.0 * (1.0 - n / 8.0)
            else:
                x = fx + 3.0
            y = fy - 3.0
        blit(p, atlas, self._face_scar_frame, x, y, rot, scale_x, 1.0, SCAR, ax=0.5, ay=0.5)

    def update_tongue_rope(self):
        """舌渲染链每帧推进（Verlet）；pts[0]=舌尖,[-1]=嘴。"""
        t = self.tongue
        # 无/收起时清链早退
        if t is None or not t.visible:
            self._tongue_rope = None
            self._tongue_rope_v = None
            return

        N = 20
        mx, my = t.mouth
        tx, ty = t.x, t.y

        rope = self._tongue_rope
        rope_v = self._tongue_rope_v
        # 无链/长度变/跳变>80px 时重建
        if (rope is None or len(rope) != N
                or rope_v is None or len(rope_v) != N
                or math.hypot(rope[-1][0] - mx, rope[-1][1] - my) > 80.0):
            rope = [(tx + (mx - tx) * (i / (N - 1)),
                     ty + (my - ty) * (i / (N - 1))) for i in range(N)]
            rope_v = [(0.0, 0.0)] * N

        # 两端钉死
        pts = list(rope)
        vel = list(rope_v)
        pts[0] = (tx, ty)
        pts[-1] = (mx, my)
        vel[0] = (0.0, 0.0)
        vel[-1] = (0.0, 0.0)

        damp = self._rope_damp
        kv = self._rope_pull_vel
        kp = self._rope_pull_pos

        for i in range(1, N - 1):
            gt = i / (N - 1)
            gx = tx + (mx - tx) * gt
            gy = ty + (my - ty) * gt
            x, y = pts[i]
            vx, vy = vel[i]
            x = x + vx
            y = y + vy
            vx *= damp
            vy *= damp
            vx += (gx - x) * kv
            vy += (gy - y) * kv
            x = x + (gx - x) * kp
            y = y + (gy - y) * kp
            pts[i] = (x, y)
            vel[i] = (vx, vy)

        # 约束求解，rest=总长/N*0.1
        rope_total_len = getattr(t, "total", 200.0)
        rest = (rope_total_len / N) * 0.1
        for i in range(1, N):
            ax, ay = pts[i - 1]
            bx, by = pts[i]
            dx, dy = bx - ax, by - ay
            d = math.hypot(dx, dy)
            if d < 1e-6:
                continue
            over = (d - rest)
            ux, uy = dx / d, dy / d
            if i - 1 != 0:
                pax, pay = pts[i - 1]
                pts[i - 1] = (pax + ux * over * 0.5, pay + uy * over * 0.5)
                pvx, pvy = vel[i - 1]
                vel[i - 1] = (pvx + ux * over * 0.5, pvy + uy * over * 0.5)
            if i != N - 1:
                pbx, pby = pts[i]
                pts[i] = (pbx - ux * over * 0.5, pby - uy * over * 0.5)
                qvx, qvy = vel[i]
                vel[i] = (qvx - ux * over * 0.5, qvy - uy * over * 0.5)
        pts[0] = (tx, ty)
        pts[-1] = (mx, my)
        self._tongue_rope = pts
        self._tongue_rope_v = vel

    def _draw_tongue(self, p):
        """只画不推链，pts[0]=舌尖,[-1]=嘴。"""
        t = self.tongue
        if t is None or not t.visible:
            return

        rope = self._tongue_rope
        if rope is None:
            return

        N = 20
        mx, my = t.mouth
        pts = rope

        travel = math.hypot(t.x - mx, t.y - my)
        tot = getattr(t, "total", 200.0)
        req = min(getattr(t, "requested", travel), tot)
        b_denom = travel + 80.0
        b = ((tot + req) * 0.5) / b_denom if b_denom > 1e-6 else 1.0
        b = b ** (0.4 if b >= 1.0 else 1.6)
        if getattr(t, "mode", None) == "attached":
            b = b + (1.0 - b) * 0.5

        PI = math.pi
        tip_x, tip_y = pts[0]
        n1x, n1y = pts[1]
        ddx, ddy = tip_x - n1x, tip_y - n1y
        dl = math.hypot(ddx, ddy) or 1.0
        # 舌尖端外延 1px
        line = [(tip_x + ddx / dl, tip_y + ddy / dl)]
        line += [pts[k] for k in range(1, N - 2)]
        line.append((mx, my))
        m = len(line)
        widths = []
        for i in range(m):
            frac = i / (m - 1)
            taper = math.sin(frac * PI) ** 0.7
            amp = 1.0 + (b - 1.0) * taper
            widths.append((0.2 + 1.6 * amp) * TONGUE_WIDTH_SCALE)

        # 逐点色：雾色→粉白 lerp
        fog = (185, 195, 200)
        HA, HB, HSL_SL, A2, B2 = 0.95, 1.0, 1.0, 0.75, 0.9

        vcolors = []
        for j in range(m):
            mid_t = max(0.0, min(1.0, math.sin(j / max(1, m - 1) * PI)))
            h = HA + (HB - HA) * mid_t
            lv = A2 + (B2 - A2) * (mid_t ** 0.15)
            gr, gg, gb = _hsl2rgb(h, HSL_SL, lv)
            cr = int(fog[0] + (gr * 255.0 - fog[0]) * 0.7)
            cg = int(fog[1] + (gg * 255.0 - fog[1]) * 0.7)
            cb = int(fog[2] + (gb * 255.0 - fog[2]) * 0.7)
            vcolors.append((cr, cg, cb))

        ribbon(p, line, widths, vcolors)


