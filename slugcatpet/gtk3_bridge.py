import math
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, Gdk, GLib
import cairo

from PySide6.QtGui import QImage, QPainter, QColor, QMouseEvent, QCursor, QGuiApplication
from PySide6.QtCore import Qt, QPoint, QPointF

class GTK3Bridge:
    def __init__(self, pet_window):
        self.pet = pet_window
        
        self.width = self.pet.width()
        self.height = self.pet.height()
        
        self.qimg = QImage(self.width, self.height, QImage.Format_ARGB32_Premultiplied)
        self.buffer = self.qimg.bits()
        self.stride = self.qimg.bytesPerLine()
        self.cairo_surface = cairo.ImageSurface.create_for_data(
            self.buffer, cairo.FORMAT_ARGB32, self.width, self.height, self.stride
        )
        
        self.gtk_win = Gtk.Window()
        self.gtk_win.set_title("Slugcat Pet")
        GtkLayerShell.init_for_window(self.gtk_win)
        GtkLayerShell.set_layer(self.gtk_win, GtkLayerShell.Layer.OVERLAY)
        
        screen = QGuiApplication.primaryScreen()
        geo = screen.geometry()
        area = screen.availableGeometry()
        
        GtkLayerShell.set_anchor(self.gtk_win, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self.gtk_win, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self.gtk_win, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self.gtk_win, GtkLayerShell.Edge.RIGHT, True)
        
        margin_top = self.pet.y() - geo.y()
        margin_left = self.pet.x() - geo.x()
        margin_bottom = geo.height() - margin_top - self.height
        margin_right = geo.width() - margin_left - self.width
        
        GtkLayerShell.set_margin(self.gtk_win, GtkLayerShell.Edge.TOP, margin_top)
        GtkLayerShell.set_margin(self.gtk_win, GtkLayerShell.Edge.BOTTOM, margin_bottom)
        GtkLayerShell.set_margin(self.gtk_win, GtkLayerShell.Edge.LEFT, margin_left)
        GtkLayerShell.set_margin(self.gtk_win, GtkLayerShell.Edge.RIGHT, margin_right)
        
        self.gtk_win.set_app_paintable(True)
        screen = self.gtk_win.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.gtk_win.set_visual(visual)
            
        css = Gtk.CssProvider()
        css.load_from_data(b"window { background-color: rgba(0,0,0,0); }")
        self.gtk_win.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        self.gtk_win.connect("draw", self.on_draw)
        self.gtk_win.add_events(Gdk.EventMask.POINTER_MOTION_MASK | 
                                Gdk.EventMask.BUTTON_PRESS_MASK | 
                                Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.gtk_win.connect("button-press-event", self.on_mouse_press)
        self.gtk_win.connect("button-release-event", self.on_mouse_release)
        self.gtk_win.connect("motion-notify-event", self.on_mouse_motion)
        
        self.last_global_pos = QPoint(0, 0)
        self.original_cursor_pos = QCursor.pos
        QCursor.pos = self.mock_cursor_pos
        
        # Override update to prevent QWidget from repainting itself natively
        self.pet.update = self.queue_render
        
        GLib.timeout_add(16, self.render_frame)
        self.gtk_win.show_all()
        
    def mock_cursor_pos(self):
        return self.last_global_pos
        
    def queue_render(self, *args, **kwargs):
        pass

    def on_mouse_press(self, w, e):
        btn = Qt.LeftButton if e.button == 1 else Qt.RightButton if e.button == 3 else Qt.NoButton
        qev = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(e.x, e.y), btn, btn, Qt.NoModifier)
        self.pet.mousePressEvent(qev)
        return False
        
    def on_mouse_release(self, w, e):
        btn = Qt.LeftButton if e.button == 1 else Qt.RightButton if e.button == 3 else Qt.NoButton
        qev = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(e.x, e.y), btn, btn, Qt.NoModifier)
        self.pet.mouseReleaseEvent(qev)
        return False
        
    def on_mouse_motion(self, w, e):
        self.last_global_pos = QPoint(int(e.x), int(e.y))
        return False
        
    def update_region(self):
        region = cairo.Region()
        
        if self.pet._place_mode:
            rect = cairo.RectangleInt(0, 0, self.width, self.height)
            region.union(cairo.Region(rect))
        else:
            scale = self.pet._scale
            for pet in self.pet.pets:
                x = pet.body.chunk0.x * scale
                y = pet.body.chunk0.y * scale
                r = 50 * scale # safe radius to capture body clicks without blocking too much screen
                rect = cairo.RectangleInt(int(x - r), int(y - r), int(r * 2), int(r * 2))
                region.union(cairo.Region(rect))
                
            items = getattr(self.pet, "fruits", []) + getattr(self.pet, "stones", []) + getattr(self.pet, "slimemolds", []) + getattr(self.pet, "batflies", [])
            for item in items:
                x = item.x * scale
                y = item.y * scale
                r = 25 * scale
                rect = cairo.RectangleInt(int(x - r), int(y - r), int(r * 2), int(r * 2))
                region.union(cairo.Region(rect))
                
        self.gtk_win.input_shape_combine_region(region)

    def render_frame(self):
        self.update_region()
        self.qimg.fill(QColor(0, 0, 0, 0))
        
        p = QPainter(self.qimg)
        self.pet.customPaint(p)
        
        self.gtk_win.queue_draw()
        return True

    def on_draw(self, widget, cr):
        cr.set_source_surface(self.cairo_surface, 0, 0)
        cr.paint()
        return False
