# SPDX-License-Identifier: GPL-3.0-or-later
# Modified 2026-11 by Ezequiel M. Rezende (@em-rezende): see CREDITS.md.
"""The «Site Analysis» tab in the side shelf.

The same sections as the web app — hour and sun, location, EPW climate,
solar diagram, wind, map and context, masses, annotations, view and
export — collapsible (``FoldSection``) and narrow, as docs/plugins.md asks
for a tab that stays open while modeling.
"""
from __future__ import annotations

import math
import os

from PySide6.QtCore import (QEvent, QObject, QRectF, QSignalBlocker, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QColor, QVector3D
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QCheckBox, QColorDialog, QComboBox,
    QDial, QDoubleSpinBox, QSizePolicy,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSlider, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from views.fold_section import FoldSection, narrow, wrapping_form

from . import actions as act
from . import climate, export, geometry as geo, solar, pick_tool
from .data import pin_label_text, wind_label_text
from .drawing import legend_rows
from .charts import MonthChart, RoseChart
from .i18n import tr

_SET = "analisis_sitio/"

# (glyph, English search name, translated name)
ICONS = (
    ("★", "featured star"), ("📍", "pin marker"), ("🌳", "park tree"),
    ("🏠", "house home"), ("🏫", "school"), ("🎓", "university"),
    ("🏥", "hospital health"), ("⚚", "health center"), ("🏛", "institutional"),
    ("⛪", "church temple"), ("🛒", "commerce market"), ("🍴", "restaurant"),
    ("☕", "café coffee"), ("🚌", "bus stop"), ("🚇", "subway metro"),
    ("🚉", "train station"), ("🚲", "bicycle bike lane"), ("🅿", "parking lot"),
    ("⛽", "gas station"), ("✈", "airport"), ("⚓", "port harbor"),
    ("⚽", "sport court"), ("💧", "water"), ("🌊", "river stream"),
    ("⛰", "mountain hill"), ("🌬", "wind"), ("☀", "sun"), ("☂", "rain"),
    ("🔊", "noise"), ("👁", "visual landmark"), ("⚠", "risk hazard"),
    ("⚡", "energy"), ("🏭", "industry"), ("🗑", "waste"),
    ("♿", "accessible"), ("⚑", "flag landmark"), ("🛈", "information"),
)


def _section(title: str, key: str, default_open: bool = False) -> FoldSection:
    return FoldSection(tr(title), _SET + "open_" + key, default_open=default_open)


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: palette(mid); font-size: 11px;")
    return lbl


def _kv(rows) -> str:
    return ("<table width='100%' cellspacing='0' cellpadding='1'>"
            + "".join(f"<tr><td style='color:gray'>{k}</td>"
                      f"<td align='right'>{v}</td></tr>" for k, v in rows)
            + "</table>")


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color: str = "#ffffff", parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 22)
        self._color = color
        self._paint()
        self.clicked.connect(self._pick)

    def color(self) -> str:
        return self._color

    def setColor(self, c: str) -> None:              # noqa: N802
        self._color = c or "#ffffff"
        self._paint()

    def _paint(self) -> None:
        self.setStyleSheet(f"QPushButton {{ background: {self._color}; "
                           "border: 1px solid #7f8a99; border-radius: 3px; }")

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, tr("Color"))
        if c.isValid():
            self.setColor(c.name())
            self.colorChanged.emit(self._color)


def _dspin(lo, hi, step=1.0, dec=1, suffix="") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(dec)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def _ispin(lo, hi, suffix="") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def _row(*widgets, stretch_last=False) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    for i, w in enumerate(widgets):
        if isinstance(w, str):
            w = QLabel(tr(w))
        h.addWidget(w, 1 if (stretch_last and i == len(widgets) - 1) else 0)
    if not stretch_last:
        h.addStretch(1)
    return h


class _WheelGuard(QObject):
    """The mouse wheel scrolls the tab, it does not change values: a
    dropdown or a numeric field only responds to the wheel after being
    clicked (avoids changing the time zone, north or diagram center by
    accident while scrolling the panel)."""

    def __init__(self, scroll) -> None:
        super().__init__(scroll)
        self.scroll = scroll

    def eventFilter(self, obj, ev) -> bool:          # noqa: N802
        if ev.type() == QEvent.Wheel and not obj.hasFocus():
            sb = self.scroll.verticalScrollBar()
            sb.setValue(sb.value() - int(ev.angleDelta().y() / 120.0
                                         * sb.singleStep() * 3))
            return True
        return False


class LegendWidget(QWidget):
    """Conventions for what is visible in the view (before, a floating
    box). Symbols and names only: the values live in their sections."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rows = []
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def set_rows(self, rows) -> None:
        self.rows = rows
        self.setFixedHeight(max(20, 21 * len(rows) + 4))
        self.update()

    def paintEvent(self, _ev) -> None:              # noqa: N802
        from PySide6.QtGui import QPainter
        from .drawing import legend_symbol
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        text = self.palette().color(self.palette().ColorRole.Text)
        if not self.rows:
            p.setPen(text)
            p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter,
                       tr("Nothing visible in the view."))
        for i, r in enumerate(self.rows):
            y = 2 + i * 21 + 10
            legend_symbol(p, r["sym"], r["c"], 4, y, 13)
            p.setPen(text)
            p.drawText(QRectF(34, y - 10, self.width() - 36, 20),
                       Qt.AlignLeft | Qt.AlignVCenter, r["s"])
        p.end()


class SitePanel(QWidget):
    """The panel. ``refresh()`` reads the document; every control writes."""

    def __init__(self, sitio, overlay) -> None:
        super().__init__()
        self.sitio = sitio
        self.app = sitio.app
        self.overlay = overlay
        self._busy = False
        self._binds = []
        self._mass_rows = []
        self._geocoder = None
        self._osm = None
        self._floating_notes = None
        self._floating_scale = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self._lay = QVBoxLayout(body)
        self._lay.setContentsMargins(6, 4, 6, 8)
        self._lay.setSpacing(4)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self._scroll = scroll

        # Tab order (1 → 12).
        self._build_epw()           # 1  Load EPW file
        self._build_location()      # 2  Location
        self._build_north()         # 3  Project north
        self._build_time()          # 4  Date, hour and shadows (+ solar diagram)
        self._build_wind()          # 5  Winds
        self._build_charts()        # 6  Climate data
        self._build_map()           # 7  Basemap and context
        self._build_masses()        # 8  Masses and lots
        self._build_pins()          # 9  Annotations
        self._build_view()          # 10 Visualization (+ conventions)
        self._build_solar()         # 11 Solar radiation and shadows
        self._build_export()        # 12 Export image (+ floating panel)
        self._lay.addStretch(1)
        self._wheel_guard = _WheelGuard(scroll)
        for w in body.findChildren(QWidget):
            if isinstance(w, (QComboBox, QAbstractSpinBox, QSlider, QDial)):
                w.setFocusPolicy(Qt.StrongFocus)
                w.installEventFilter(self._wheel_guard)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(60)
        self._refresh_timer.timeout.connect(self.refresh)
        sitio.changed.connect(self.schedule_refresh)
        self.refresh()

    # ---- Control ↔ view bindings -------------------------------------------
    def _bind(self, w, path, kind=None, after=None, scale=1.0):
        kind = kind or ("check" if isinstance(w, QCheckBox) else
                        "color" if isinstance(w, ColorButton) else
                        "text" if isinstance(w, QLineEdit) else
                        "combo" if isinstance(w, QComboBox) else
                        "slider" if isinstance(w, QSlider) else "spin")
        self._binds.append((w, tuple(path), kind, scale))

        def write(*_a):
            if self._busy:
                return
            v = self.sitio.store.view()
            node = v
            for k in path[:-1]:
                node = node[k]
            if kind == "check":
                val = w.isChecked()
            elif kind == "color":
                val = w.color()
            elif kind == "text":
                val = w.text()
            elif kind == "combo":
                val = w.currentData()
            elif kind == "slider":
                val = w.value() / scale
            else:
                val = w.value()
            node[path[-1]] = val
            self.sitio.store.touch()
            if after:
                after()
            self.sitio.update_animation()

        sig = {"check": w.toggled if kind == "check" else None,
               "color": getattr(w, "colorChanged", None),
               "text": getattr(w, "editingFinished", None),
               "combo": getattr(w, "currentIndexChanged", None),
               "slider": getattr(w, "valueChanged", None),
               "spin": getattr(w, "valueChanged", None)}[kind]
        sig.connect(write)
        return w

    def _read_binds(self) -> None:
        v = self.sitio.store.view()
        for w, path, kind, scale in self._binds:
            node = v
            try:
                for k in path:
                    node = node[k]
            except (KeyError, TypeError):
                continue
            with QSignalBlocker(w):
                if kind == "check":
                    w.setChecked(bool(node))
                elif kind == "color":
                    w.setColor(str(node))
                elif kind == "text":
                    w.setText(str(node))
                elif kind == "combo":
                    i = w.findData(node)
                    w.setCurrentIndex(max(0, i))
                elif kind == "slider":
                    w.setValue(int(round(float(node) * scale)))
                else:
                    w.setValue(type(w.value())(node))

    # ---- Hour and sun ------------------------------------------------------
    def _build_time(self) -> None:
        sec = _section("4 · ☀  Date, hour and shadows", "time", True)
        g = QGridLayout(sec.body)
        g.setContentsMargins(6, 6, 6, 6)
        g.addWidget(QLabel(tr("Date")), 1, 0)
        self.doy = QSlider(Qt.Horizontal)
        self.doy.setRange(1, 365)
        self.doy.valueChanged.connect(self._on_doy)
        g.addWidget(self.doy, 1, 1)
        self.doy_lbl = QLabel("")
        self.doy_lbl.setMinimumWidth(52)
        g.addWidget(self.doy_lbl, 1, 2)
        g.addWidget(QLabel(tr("Time")), 2, 0)
        self.hour = QSlider(Qt.Horizontal)
        self.hour.setRange(0, 24 * 4 - 1)
        self.hour.valueChanged.connect(self._on_hour)
        g.addWidget(self.hour, 2, 1)
        self.hour_lbl = QLabel("")
        g.addWidget(self.hour_lbl, 2, 2)
        quick = QGridLayout()
        for i, (txt, doy) in enumerate((
                (tr("March equinox"), 80),
                (tr("June solstice"), 172),
                (tr("September equinox"), 266),
                (tr("December solstice"), 355))):
            b = QPushButton(txt)
            b.setStyleSheet("font-size: 11px;")
            b.clicked.connect(lambda _c=False, d=doy: self.sitio.set_when(doy=d))
            quick.addWidget(b, i // 2, i % 2)
        g.addLayout(quick, 3, 0, 1, 3)
        self.anim_btn = QPushButton(tr("▶  Animate sun path"))
        self.anim_btn.setCheckable(True)
        self.anim_btn.clicked.connect(self._on_anim)
        g.addWidget(self.anim_btn, 4, 0, 1, 3)
        self.shadow_on = QCheckBox(tr("Cast shadows (real sun)"))
        self.shadow_on.toggled.connect(
            lambda on: None if self._busy else self.sitio.set_shadows(on))
        g.addWidget(self.shadow_on, 5, 0, 1, 3)
        g.addWidget(QLabel(tr("Darkness")), 6, 0)
        self.shadow_dark = QSlider(Qt.Horizontal)
        self.shadow_dark.setRange(0, 80)
        self.shadow_dark.valueChanged.connect(self._on_dark)
        g.addWidget(self.shadow_dark, 6, 1, 1, 2)
        self.sun_kv = QLabel("")
        self.sun_kv.setTextFormat(Qt.RichText)
        g.addWidget(self.sun_kv, 7, 0, 1, 3)
        g.addWidget(self._build_sun(), 8, 0, 1, 3)
        self._lay.addWidget(sec)

    def _on_doy(self, v: int) -> None:
        if not self._busy:
            self.sitio.set_when(doy=v)

    def _on_hour(self, v: int) -> None:
        if not self._busy:
            self.sitio.set_when(hour=v / 4.0)

    def _on_dark(self, v: int) -> None:
        if not self._busy:
            sh = self.sitio.shadows()
            self.sitio.set_shadows(sh.enabled if sh else False,
                                   darkness=1.0 - v / 100.0)

    def _on_anim(self) -> None:
        on = self.sitio.toggle_sun_animation()
        self.anim_btn.setChecked(on)

    # ---- Location ----------------------------------------------------------
    def _build_location(self) -> None:
        sec = _section("2 · ◉  Location", "loc", True)
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        self.geo_q = QLineEdit()
        self.geo_q.setPlaceholderText(tr("Search address or paste «lat, lon»"))
        self.geo_q.returnPressed.connect(self._on_search)
        b = QPushButton(tr("Search"))
        b.clicked.connect(self._on_search)
        lay.addLayout(_row(self.geo_q, b, stretch_last=False))
        self.geo_res = QListWidget()
        self.geo_res.setMaximumHeight(110)
        self.geo_res.hide()
        self.geo_res.itemActivated.connect(self._on_result)
        self.geo_res.itemClicked.connect(self._on_result)
        lay.addWidget(self.geo_res)
        pick = QPushButton(tr("Pick on the map…"))
        pick.clicked.connect(self._on_pick_map)
        lay.addWidget(pick)
        form = wrapping_form(None)
        self.site_name = self._bind(QLineEdit(), ["site_name"])
        form.addRow(tr("Name"), self.site_name)
        self.lat = _dspin(-90, 90, 0.0001, 6)
        self.lon = _dspin(-180, 180, 0.0001, 6)
        form.addRow(tr("Latitude"), self.lat)
        form.addRow(tr("Longitude"), self.lon)
        apply = QPushButton(tr("Apply coordinates"))
        apply.clicked.connect(self._on_apply_latlon)
        form.addRow("", apply)
        self.tz = QComboBox()
        self.tz.addItem(tr("Automatic (by longitude)"), None)
        for off in range(-12, 15):
            self.tz.addItem(f"UTC{off:+03d}:00", off)
        self.tz.currentIndexChanged.connect(
            lambda _i: None if self._busy else self.sitio.set_tz(
                self.tz.currentData()))
        form.addRow(tr("Time zone"), self.tz)
        lay.addLayout(form)
        narrow(self.tz, self.lat, self.lon)
        self.loc_hint = _hint("")
        lay.addWidget(self.loc_hint)
        self._lay.addWidget(sec)

    def _on_search(self) -> None:
        q = self.geo_q.text().strip()
        if not q:
            return
        import re
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$", q)
        if m:
            self._set_site(float(m.group(1)), float(m.group(2)),
                           tr("Coordinates"))
            return
        if self._geocoder is None:
            from georef.geocode import Geocoder
            self._geocoder = Geocoder(self)
            self._geocoder.resultsReady.connect(self._on_places)
            self._geocoder.failed.connect(
                lambda msg: self._flash(tr("Search failed: {error}", error=msg)))
        self.geo_res.clear()
        self.geo_res.addItem(tr("Searching…"))
        self.geo_res.show()
        self._geocoder.search(q)

    def _on_places(self, places) -> None:
        self.geo_res.clear()
        if not places:
            self.geo_res.addItem(tr("No results"))
        for p in places:
            it = QListWidgetItem(p.name)
            it.setData(Qt.UserRole, (p.lat, p.lon, p.name))
            it.setToolTip(f"{p.lat:.5f}, {p.lon:.5f}")
            self.geo_res.addItem(it)
        self.geo_res.show()

    def _on_result(self, it) -> None:
        data = it.data(Qt.UserRole)
        if data:
            lat, lon, name = data
            self._set_site(lat, lon, ", ".join(name.split(",")[:2]).strip())
            self.geo_res.hide()

    def _set_site(self, lat, lon, name=None, tz=None, alt=None) -> bool:
        d = self.sitio.datum()
        if d is not None:
            dist = math.hypot((lat - d.lat) * 111320.0,
                              (lon - d.lon) * 111320.0 * math.cos(math.radians(lat)))
            if dist > 1.0:
                ans = QMessageBox.question(
                    self, tr("Move the project origin"),
                    tr("The project already has a location. The new point "
                       "becomes the origin (0,0): what is drawn keeps its "
                       "local coordinates and appears at the new site "
                       "({dist:,.0f} m away).\n\nMove the origin?",
                       dist=dist))
                if ans != QMessageBox.Yes:
                    return False
        self.sitio.set_location(lat, lon, alt=alt, tz=tz)
        if name and not self.sitio.store.view().get("site_name"):
            self.sitio.store.view()["site_name"] = name
        self.refresh()
        return True

    def _on_pick_map(self) -> None:
        from georef.tiles import DEFAULT_SOURCE_ID, PRESETS
        from views.location_dialog import pick_location
        s = self.sitio.site()
        res = pick_location(PRESETS[DEFAULT_SOURCE_ID], s["lat"], s["lon"],
                            self.app.window)
        if res is not None:
            self._set_site(res[0], res[1])

    def _on_apply_latlon(self) -> None:
        self._set_site(self.lat.value(), self.lon.value())

    # ---- 1 · Climate (EPW) -------------------------------------------------
    def _build_epw(self) -> None:
        sec = _section("1 · ☁  Load EPW file", "epw", True)
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        b = QPushButton(tr("Open EPW file…"))
        b.clicked.connect(self._on_open_epw)
        lay.addWidget(b)
        self.epw_use_loc = QCheckBox(tr("Use the EPW location for the site"))
        self.epw_use_loc.setChecked(True)
        lay.addWidget(self.epw_use_loc)
        self.epw_none = _hint(tr("Free EPW files at climate.onebuilding.org "
                                 "or energyplus.net/weather. Saved in the .igz."))
        lay.addWidget(self.epw_none)
        self.epw_box = QWidget()
        el = QVBoxLayout(self.epw_box)
        el.setContentsMargins(0, 4, 0, 0)
        self.epw_kv = QLabel("")
        self.epw_kv.setTextFormat(Qt.RichText)
        el.addWidget(self.epw_kv)
        el.addWidget(QLabel(tr("<b>Analysis period</b>")))
        per = QGridLayout()
        self.m0, self.m1 = QComboBox(), QComboBox()
        for i, m in enumerate(climate.MONTHS_EN):
            self.m0.addItem(tr(m), i + 1)
            self.m1.addItem(tr(m), i + 1)
        self.h0, self.h1 = _ispin(0, 23), _ispin(1, 24)
        self._bind(self.m0, ["period", "m0"], after=self._refresh_climate)
        self._bind(self.m1, ["period", "m1"], after=self._refresh_climate)
        self._bind(self.h0, ["period", "h0"], after=self._refresh_climate)
        self._bind(self.h1, ["period", "h1"], after=self._refresh_climate)
        per.addWidget(QLabel(tr("Months")), 0, 0)
        per.addWidget(self.m0, 0, 1)
        per.addWidget(self.m1, 0, 2)
        per.addWidget(QLabel(tr("Hours")), 1, 0)
        per.addWidget(self.h0, 1, 1)
        per.addWidget(self.h1, 1, 2)
        narrow(self.m0, self.m1)
        el.addLayout(per)
        self.epw_stats = QLabel("")
        self.epw_stats.setTextFormat(Qt.RichText)
        self.epw_stats.setWordWrap(True)
        el.addWidget(self.epw_stats)
        b = QPushButton(tr("Remove EPW"))
        b.clicked.connect(lambda: act.clear_epw(self.sitio))
        el.addWidget(b)
        lay.addWidget(self.epw_box)
        self._lay.addWidget(sec)

    # ---- 3 · North ---------------------------------------------------------
    def _build_north(self) -> None:
        sec = _section("3 · ➤  Project north", "north", True)
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        top = QHBoxLayout()
        self.north_dial = QDial()
        self.north_dial.setRange(0, 359)
        self.north_dial.setWrapping(True)
        self.north_dial.setNotchesVisible(True)
        self.north_dial.setNotchTarget(15)
        self.north_dial.setFixedSize(84, 84)
        # QDial wraps: 0 at the bottom, clockwise; here the knob points
        # where north lies (0° = up = +Y).
        self.north_dial.valueChanged.connect(
            lambda v: self._on_north((v + 180) % 360))
        top.addWidget(self.north_dial)
        col = QVBoxLayout()
        self.north = _dspin(-180, 360, 0.5, 1, "°")
        self.north.setWrapping(True)
        self.north.valueChanged.connect(self._on_north)
        col.addWidget(QLabel(tr("Angle (clockwise from +Y)")))
        col.addWidget(self.north)
        row = QHBoxLayout()
        for t, d in (("0°", 0.0), ("−15°", -15.0), ("+15°", 15.0)):
            b = QPushButton(t)
            b.setStyleSheet("font-size: 11px;")
            if d == 0.0:
                b.clicked.connect(lambda: self._on_north(0.0))
            else:
                b.clicked.connect(lambda _c=False, d=d: self._on_north(
                    self.sitio.site()["north"] + d))
            row.addWidget(b)
        col.addLayout(row)
        top.addLayout(col, 1)
        lay.addLayout(top)
        b = QPushButton(tr("From selected edge (points to north)"))
        b.setToolTip(tr("Select a model line drawn toward geographic north "
                        "(south to north) and click."))
        b.clicked.connect(self._on_north_from_edge)
        lay.addWidget(b)
        self.north_hint = _hint("")
        lay.addWidget(self.north_hint)
        self._lay.addWidget(sec)

    def _on_north(self, deg) -> None:
        if self._busy:
            return
        if self.sitio.datum() is None:
            self._flash(tr("Locate the project first (section 2)."))
            self.refresh()
            return
        deg = ((float(deg) + 180.0) % 360.0) - 180.0
        self.sitio.set_north(deg)
        self.refresh()

    def _on_north_from_edge(self) -> None:
        from core.mesh import Edge
        edges = [e for e in self.sitio.scene.selection if isinstance(e, Edge)]
        if len(edges) != 1:
            self._flash(tr("Selecione uma única aresta que aponte para o norte."))
            return
        e = edges[0]
        a, b = e.v0.position, e.v1.position
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if math.hypot(dx, dy) < 1e-6:
            self._flash(tr("A aresta é vertical: não tem direção no plano."))
            return
        if dy < 0 or (abs(dy) < 1e-9 and dx < 0):
            dx, dy = -dx, -dy           
        self._on_north(math.degrees(math.atan2(dx, dy)))

    def _on_pick_north_edge(self) -> None:
        """Ativa a seleção e monitora; quando o usuário selecionar uma linha, aplica o norte."""
        from core.mesh import Edge
        from PySide6.QtCore import QTimer
        
        win = self.app.window
        vp = self.app.viewport
        
        # 1. Limpa seleção e ativa a ferramenta Selecionar do IngeTrazo
        self.sitio.scene.selection.clear()
        vp.update()
        
        activate = getattr(win, "_activate_tool", None)
        if callable(activate):
            activate("select")
        
        vp.setFocus()
        vp.flash_status(
            tr("Clique na linha que aponta para o Norte (Esc cancela)."), 0
        )
        
        # 2. Cria o timer que vai ficar olhando a seleção
        timer = QTimer(self)
        timer.setInterval(150)  # 150 ms
        
        def _check():
            edges = [e for e in self.sitio.scene.selection if isinstance(e, Edge)]
            if len(edges) == 1:
                # ACHOU! Aplica e para o timer.
                timer.stop()
                self._on_north_from_edge()
                vp.flash_status(tr("✓ Norte aplicado com base na linha selecionada."), 3500)
                vp.update()
        
        timer.timeout.connect(_check)
        timer.start()
        
        # 3. Guarda o timer para poder cancelá-lo se o usuário desistir
        self._north_timer = timer

    def _on_north_from_points(self) -> None:
        """Ativa a seleção e monitora; quando o usuário selecionar uma linha, aplica o norte."""
        from core.mesh import Edge
        from PySide6.QtCore import QTimer, Qt
        
        win = self.app.window
        vp = self.app.viewport
        
        # 1. Limpa seleção e ativa a ferramenta Selecionar do IngeTrazo
        self.sitio.scene.selection.clear()
        vp.update()
        
        activate = getattr(win, "_activate_tool", None)
        if callable(activate):
            activate("select")
        
        vp.setFocus()
        vp.flash_status(
            tr("Clique na linha que aponta para o Norte (Esc cancela)."), 0
        )
        
        # 2. Cria o timer que vai ficar olhando a seleção
        timer = QTimer(self)
        timer.setInterval(150)  # 150 ms
        
        def _check():
            edges = [e for e in self.sitio.scene.selection if isinstance(e, Edge)]
            if len(edges) == 1:
                # ACHOU! Aplica e para o timer.
                timer.stop()
                self._on_north_from_edge()
                vp.flash_status(tr("✓ Norte aplicado com base na linha selecionada."), 3500)
                vp.update()
        
        timer.timeout.connect(_check)
        timer.start()
        
        # 3. Guarda o timer para poder cancelá-lo se o usuário desistir
        self._north_timer = timer
        

    # ---- 6 · Climate data --------------------------------------------------
    def _build_charts(self) -> None:
        sec = _section("6 · ☵  Climate data", "charts", True)
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        self.charts_none = _hint(tr("Load an EPW file (section 1) to see "
                                    "monthly temperature and relative humidity."))
        lay.addWidget(self.charts_none)
        self.charts_box = QWidget()
        el = QVBoxLayout(self.charts_box)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(QLabel(tr("<b>Monthly temperature and relative humidity</b>")))
        self.months_chart = MonthChart()
        el.addWidget(self.months_chart)
        b = QPushButton(tr("Save charts (PNG)…"))
        b.setToolTip(tr("Saves the wind rose and the monthly chart."))
        b.clicked.connect(self._on_save_charts)
        el.addWidget(b)
        lay.addWidget(self.charts_box)
        self._lay.addWidget(sec)

    def _on_open_epw(self) -> None:
        from PySide6.QtCore import QStandardPaths
        dl_dir = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        
        path, _f = QFileDialog.getOpenFileName(
            self, tr("Open weather file"), dl_dir, tr("EnergyPlus Weather (*.epw)"))
        if path:
            self.open_epw(path)

    def open_epw(self, path: str, ask: bool = True) -> bool:
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            info = act.load_epw_text(self.sitio, text)
        except (OSError, climate.EpwError) as exc:
            QMessageBox.warning(self, tr("EPW file"), str(exc))
            return False
        if self.epw_use_loc.isChecked():
            tz = info.get("tz")
            tz = None if tz is None or math.isnan(tz) else tz
            if ask:
                self._set_site(info["lat"], info["lon"],
                               name=", ".join(x for x in (info["city"],
                                                          info["country"]) if x),
                               tz=tz)
            else:
                self.sitio.set_location(info["lat"], info["lon"], tz=tz)
        self._flash(tr("Weather from {city} loaded.",
                       city=info['city'] or tr('the station')))
        self.refresh()
        return True

    def _on_dominant(self) -> None:
        try:
            act.set_winds(self.sitio, act.dominant_winds(self.sitio))
        except act.SiteError as exc:
            self._flash(str(exc))


    def _on_save_charts(self) -> None:
        # Descobre a pasta Documentos do usuário
        from PySide6.QtCore import QStandardPaths
        docs_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        
        # Define o caminho inicial: Documentos/climate.png
        initial_path = os.path.join(docs_dir, "climate.png") if docs_dir else "climate.png"
        
        # Abre o diálogo
        path, _f = QFileDialog.getSaveFileName(
            self, tr("Save charts"), initial_path, tr("PNG image (*.png)"))
        if path:
            try:
                out = export.export_charts(self.sitio, path)
                self._flash(tr("Saved: {names}",
                               names=", ".join(p.split("/")[-1] for p in out)))
            except act.SiteError as exc:
                self._flash(str(exc))

    def _refresh_climate(self) -> None:
        epw = self.sitio.epw()
        self.epw_box.setVisible(epw is not None)
        self.epw_none.setVisible(epw is None)
        self.charts_box.setVisible(epw is not None)
        self.charts_none.setVisible(epw is None)
        self.rose_box.setVisible(epw is not None)
        self.rose_none.setVisible(epw is None)
        self.dominant_btn.setEnabled(epw is not None)
        for i in range(self.pal_custom.count()):
            w = self.pal_custom.itemAt(i).widget()
            if w is not None:
                w.setEnabled(self.pal.currentData() == "custom")
        if epw is None:
            return
        info = epw["info"]
        self.epw_kv.setText(_kv([
            (tr("Station"),
             f"{info.get('city', '')} {info.get('country', '')}"),
            (tr("WMO"), info.get("wmo", "") or "—"),
            (tr("Lat / Lon"), f"{info['lat']:.3f}, {info['lon']:.3f}"),
            (tr("Offset"),
             f"UTC{info['tz']:+g}" if not math.isnan(info.get("tz", math.nan))
             else "—"),
            (tr("Elevation"), f"{info.get('elev', 0):.0f} m")]))
        s = self.sitio.stats()
        if s is None:
            return
        dom = "<br>".join(
            f"{climate.dir16_long_name(d)} {s['freq'][d] * 100:.1f}% · "
            f"{s['avg_sp'][d]:.1f} m/s" for d in s["top"]) or "—"
        self.epw_stats.setText(_kv([
            (tr("Hours"), s["total"]),
            (tr("Mean T"),
             f"{s['avg_t']:.1f} °C ({s['t_min']:.1f} to {s['t_max']:.1f})"),
            (tr("Mean RH"), f"{s['avg_rh']:.0f} %"),
            (tr("Mean wind"), f"{s['avg_ws']:.1f} m/s"),
            (tr("Calms"), f"{s['calm'] * 100:.1f} %"),
            (tr("Dominants"), dom)]))
        w = self.sitio.store.view()["wind"]
        cols = climate.rose_colors(w.get("pal"), w.get("c0"), w.get("c1"))
        self.rose.set_data(s, cols)
        self.months_chart.set_data(s)

    # ---- Solar diagram -----------------------------------------------------
    def _build_sun(self) -> FoldSection:
        """Subsection of 4: how the sun is drawn in the view."""
        sec = _section("Solar diagram", "sun")
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self._bind(QCheckBox(tr("Show solar diagram")),
                                 ["sun", "diagram"]))
        form = wrapping_form(None)
        self.radius = self._bind(_dspin(5, 5000, 5, 0, " m"), ["radius"])
        form.addRow(tr("Diagram radius"), self.radius)
        self.cx, self.cy, self.cz = (_dspin(-1e6, 1e6, 1, 2) for _ in range(3))
        for i, w in enumerate((self.cx, self.cy, self.cz)):
            w.valueChanged.connect(lambda v, i=i: self._on_center(i, v))
        c = QHBoxLayout()
        for w in (self.cx, self.cy, self.cz):
            c.addWidget(w)
        narrow(self.cx, self.cy, self.cz)
        form.addRow(tr("Center (X, Y, Z)"), c)
        lay.addLayout(form)
        row = QHBoxLayout()
        b = QPushButton(tr("Pick center…"))
        b.setToolTip(tr("Click on the model (with inferences) to center the diagram."))
        b.clicked.connect(self._on_pick_center)
        row.addWidget(b)
        b = QPushButton(tr("Origin"))
        b.clicked.connect(lambda: self._set_center((0.0, 0.0, 0.0)))
        row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(QLabel(tr("Paths (21st of each month)")))
        grid = QGridLayout()
        self.month_checks = []
        for i, m in enumerate(climate.MONTHS_EN):
            cb = QCheckBox(tr(m))
            cb.toggled.connect(self._on_months)
            grid.addWidget(cb, i // 4, i % 4)
            self.month_checks.append(cb)
        lay.addLayout(grid)
        for text, key in (
                (tr("Yearly band (solstice to solstice)"), "band"),
                (tr("Hourly analemmas"), "analemma"),
                (tr("Path for the selected day"), "day"),
                (tr("Hour and month labels"), "labels"),
                (tr("Sun ray to the center"), "ray")):
            lay.addWidget(self._bind(QCheckBox(text), ["sun", key]))
        self.sun_color = self._bind(ColorButton(), ["sun", "color"])
        self.sun_ball = self._bind(ColorButton(), ["sun", "ball"])
        lay.addLayout(_row(tr("Diagram"), self.sun_color, tr("Sun"), self.sun_ball))
        return sec

    def _on_months(self) -> None:
        if self._busy:
            return
        v = self.sitio.store.view()
        v["sun"]["months"] = [i + 1 for i, cb in enumerate(self.month_checks)
                              if cb.isChecked()]
        self.sitio.store.touch()

    def _on_center(self, i, val) -> None:
        if self._busy:
            return
        v = self.sitio.store.view()
        c = list(v["center"])
        c[i] = float(val)
        v["center"] = c
        self.sitio.store.touch()

    def _set_center(self, p) -> None:
        self.sitio.store.view()["center"] = [float(p[0]), float(p[1]), float(p[2])]
        self.sitio.store.touch()
        self.refresh()

    def _on_pick_center(self) -> None:
        prompt = tr("Click where the diagram center goes")
        tool = pick_tool.make_pick_tool(
            prompt,
            lambda p, _c: self._set_center((p.x(), p.y(), p.z())),
            lambda: pick_tool.end(self.app))
        pick_tool.begin(self.app, tool, prompt)
        
    # ---- 5 · Winds ---------------------------------------------------------
    def _build_wind(self) -> None:
        sec = _section("5 · ≋  Winds", "wind", True)
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        # Wind rose (EPW) and its color, first.
        self.rose_none = _hint(tr("Load an EPW file (section 1) to see the "
                                  "wind rose."))
        lay.addWidget(self.rose_none)
        self.rose_box = QWidget()
        rl = QVBoxLayout(self.rose_box)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel(tr("<b>Wind rose</b> (period from section 1)")))
        self.rose = RoseChart()
        rl.addWidget(self.rose)
        form = wrapping_form(None)
        self.pal = QComboBox()
        for k, (name, _c) in climate.PALETTES.items():
            self.pal.addItem(climate.palette_name(k), k)
        self._bind(self.pal, ["wind", "pal"], after=self._refresh_climate)
        form.addRow(tr("Color"), self.pal)
        c0 = self._bind(ColorButton(), ["wind", "c0"], after=self._refresh_climate)
        c1 = self._bind(ColorButton(), ["wind", "c1"], after=self._refresh_climate)
        self.pal_custom = _row(c0, QLabel("→"), c1)
        form.addRow(tr("Calm → strong"), self.pal_custom)
        narrow(self.pal)
        rl.addLayout(form)
        lay.addWidget(self.rose_box)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)
        # In the view.
        for text, key in (
                (tr("3D ground wind rose (needs EPW)"), "rose"),
                (tr("Hourly wind arrow (EPW, blue)"), "hourly"),
                (tr("Wind arrows"), "show"),
                (tr("Animate flow"), "anim")):
            lay.addWidget(self._bind(QCheckBox(text), ["wind", key]))
        form = wrapping_form(None)
        form.addRow(tr("3D rose opacity"), self._bind(_dspin(0.15, 1, 0.05, 2),
                                                      ["wind", "opa"]))
        form.addRow(tr("3D rose size"),
                    self._bind(_dspin(0.2, 1.3, 0.02, 2, tr(" × R")),
                               ["wind", "scale"]))
        form.addRow(tr("Arrow height"), self._bind(_dspin(0, 200, 1, 1, " m"),
                                                   ["wind", "height"]))
        form.addRow(tr("Thickness"), self._bind(_dspin(0.3, 3, 0.1, 1),
                                                ["wind", "width"]))
        lay.addLayout(form)
        lay.addWidget(QLabel(tr("Directions (where the wind comes from)")))
        self.winds = QTableWidget(0, 5)
        self.winds.setHorizontalHeaderLabels(
            ["", tr("Label"), tr("Dir °"), "m/s", ""])
        hh = self.winds.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.winds.verticalHeader().hide()
        self.winds.setMaximumHeight(150)
        self.winds.itemChanged.connect(self._on_wind_item)
        self.winds.cellDoubleClicked.connect(self._on_wind_dbl)
        lay.addWidget(self.winds)
        row = QHBoxLayout()
        b = QPushButton(tr("+ Add"))
        b.clicked.connect(self._on_wind_add)
        row.addWidget(b)
        b = QPushButton(tr("Remove"))
        b.clicked.connect(self._on_wind_del)
        row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(_hint(tr("Double-click the color to change it.")))
        self.dominant_btn = QPushButton(tr("Apply dominant winds (EPW)"))
        self.dominant_btn.clicked.connect(self._on_dominant)
        lay.addWidget(self.dominant_btn)
        self._lay.addWidget(sec)

    def _fill_winds(self) -> None:
        winds = self.sitio.store.content()["winds"]
        with QSignalBlocker(self.winds):
            self.winds.setRowCount(len(winds))
            for r, w in enumerate(winds):
                on = QTableWidgetItem()
                on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                on.setCheckState(Qt.Checked if w.get("on", True) else Qt.Unchecked)
                self.winds.setItem(r, 0, on)
                self.winds.setItem(r, 1, QTableWidgetItem(
                    wind_label_text(str(w.get("label", "")))))
                self.winds.setItem(r, 2, QTableWidgetItem(
                    f"{float(w.get('dir', 0)):g}"))
                self.winds.setItem(r, 3, QTableWidgetItem(
                    f"{float(w.get('speed', 0)):g}"))
                col = QTableWidgetItem("   ")
                col.setFlags(Qt.ItemIsEnabled)
                col.setBackground(QColor(w.get("color", "#ffffff")))
                self.winds.setItem(r, 4, col)

    def _winds_from_table(self) -> list:
        old = self.sitio.store.content()["winds"]
        out = []
        for r in range(self.winds.rowCount()):
            base = dict(old[r]) if r < len(old) else {}
            try:
                d = float(self.winds.item(r, 2).text().replace(",", "."))
                sp = float(self.winds.item(r, 3).text().replace(",", "."))
            except (AttributeError, ValueError):
                d, sp = float(base.get("dir", 0)), float(base.get("speed", 0))
            base.update({"on": self.winds.item(r, 0).checkState() == Qt.Checked,
                         "label": self.winds.item(r, 1).text(),
                         "dir": d % 360.0, "speed": max(0.0, sp)})
            out.append(base)
        return out

    def _on_wind_item(self, _it) -> None:
        if not self._busy:
            act.set_winds(self.sitio, self._winds_from_table())

    def _on_wind_dbl(self, r, c) -> None:
        if c != 4:
            return
        winds = self._winds_from_table()
        col = QColorDialog.getColor(QColor(winds[r].get("color", "#ffffff")), self)
        if col.isValid():
            winds[r]["color"] = col.name()
            act.set_winds(self.sitio, winds)

    def _on_wind_add(self) -> None:
        from .data import WIND_COLORS
        winds = self._winds_from_table()
        winds.append({"on": True,
                      "label": tr("Wind {n}", n=len(winds) + 1),
                      "dir": 90.0, "speed": 2.0,
                      "color": WIND_COLORS[len(winds) % len(WIND_COLORS)]})
        act.set_winds(self.sitio, winds)

    def _on_wind_del(self) -> None:
        r = self.winds.currentRow()
        winds = self._winds_from_table()
        if 0 <= r < len(winds):
            del winds[r]
            act.set_winds(self.sitio, winds)

    # ---- Map and context ---------------------------------------------------
    def _build_map(self) -> None:
        sec = _section("7 · ▦  Basemap and context", "map")
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        from georef.tiles import PRESETS
        form = wrapping_form(None)
        self.prov = QComboBox()
        for k, src in PRESETS.items():
            self.prov.addItem(src.name, k)
        self.prov.addItem(tr("Custom tile URL (XYZ)…"), "custom")
        self._bind(self.prov, ["map", "provider"], after=self._sync_custom)
        form.addRow(tr("Map source"), self.prov)
        self.custom = self._bind(QLineEdit(), ["map", "custom"])
        self.custom.setPlaceholderText("https://…/{z}/{x}/{y}.png")
        form.addRow(tr("URL"), self.custom)
        self.extent = self._bind(_dspin(100, 5000, 50, 0, " m"), ["map", "extent"])
        form.addRow(tr("Extent"), self.extent)
        self.zoom = QComboBox()
        self.zoom.addItem(tr("Automatic"), 0)
        for z in range(14, 20):
            self.zoom.addItem(str(z), z)
        self._bind(self.zoom, ["map", "zoom"])
        form.addRow(tr("Zoom"), self.zoom)
        narrow(self.prov, self.zoom, self.custom)
        lay.addLayout(form)
        b = QPushButton(tr("Download basemap"))
        b.clicked.connect(self._on_basemap)
        lay.addWidget(b)
        self.map_show = QCheckBox(tr("Show map"))
        self.map_show.toggled.connect(self._on_map_show)
        self.map_opa = QSlider(Qt.Horizontal)
        self.map_opa.setRange(10, 100)
        self.map_opa.valueChanged.connect(self._on_map_opa)
        lay.addLayout(_row(self.map_show, tr("Opacity"), self.map_opa,
                           stretch_last=True))
        lay.addWidget(_hint(tr("The map is IngeTrazo's basemap layer (also in "
                               "the Terrain tab, with 3D terrain).")))
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)
        lay.addWidget(QLabel(tr("<b>Context buildings (OpenStreetMap)</b>")))
        form = wrapping_form(None)
        form.addRow(tr("Radius"), self._bind(_dspin(50, 2000, 50, 0, " m"),
                                              ["ctx", "radius"]))
        form.addRow(tr("Default height"),
                    self._bind(_dspin(2, 100, 1, 1, " m"), ["ctx", "def_h"]))
        lay.addLayout(form)
        lay.addWidget(self._bind(
            QCheckBox(tr("Seat on the 3D terrain (if any)")), ["ctx", "terrain"]))
        self.osm_btn = QPushButton(tr("Load 3D buildings"))
        self.osm_btn.clicked.connect(self._on_osm)
        lay.addWidget(self.osm_btn)
        self.ctx_count = _hint("")
        lay.addWidget(self.ctx_count)
        self.ctx_show = QCheckBox(tr("Show buildings"))
        self.ctx_show.toggled.connect(self._on_ctx_show)
        lay.addWidget(self.ctx_show)
        form = wrapping_form(None)
        col = self._bind(ColorButton(), ["ctx", "color"],
                         after=lambda: act.restyle_context(self.sitio))
        form.addRow(tr("Color"), col)
        form.addRow(tr("Opacity"), self._bind(
            _dspin(0.05, 1, 0.05, 2), ["ctx", "opacity"],
            after=lambda: act.restyle_context(self.sitio)))
        self.hscale = _dspin(0.2, 3, 0.1, 1, tr(" ×"))
        self._bind(self.hscale, ["ctx", "hscale"])
        apply_h = QPushButton(tr("Apply"))
        apply_h.clicked.connect(self._on_rebuild_ctx)
        form.addRow(tr("Height scale"), _row(self.hscale, apply_h))
        lay.addLayout(form)
        self.ctx_edit = QCheckBox(tr("Edit buildings: click in the view"))
        self.ctx_edit.toggled.connect(self._on_ctx_edit)
        lay.addWidget(self.ctx_edit)
        self.bld_box = QWidget()
        bl = wrapping_form(self.bld_box)
        self.bld_name = QLabel("")
        bl.addRow(tr("Building"), self.bld_name)
        self.bld_h = _dspin(1, 500, 0.5, 1, " m")
        self.bld_min = _dspin(0, 500, 0.5, 1, " m")
        bl.addRow(tr("Height"), self.bld_h)
        bl.addRow(tr("Base"), self.bld_min)
        row = QHBoxLayout()
        b = QPushButton(tr("Apply"))
        b.clicked.connect(self._on_bld_apply)
        row.addWidget(b)
        b = QPushButton(tr("Hide"))
        b.clicked.connect(self._on_bld_hide)
        row.addWidget(b)
        bl.addRow("", row)
        self.bld_box.hide()
        lay.addWidget(self.bld_box)
        row = QHBoxLayout()
        b = QPushButton(tr("Show hidden"))
        b.clicked.connect(self._on_unhide_all)
        row.addWidget(b)
        b = QPushButton(tr("Remove context"))
        b.clicked.connect(lambda: act.set_context(
            self.sitio, None, tr("Context removed.")))
        row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(_hint(tr("The context is a locked group in the "
                               "«OSM Context» layer: it casts shadow and "
                               "exports like the rest. © OpenStreetMap "
                               "contributors.")))
        self._lay.addWidget(sec)

    def _sync_custom(self) -> None:
        self.custom.setVisible(self.prov.currentData() == "custom")

    def _on_basemap(self) -> None:
        v = self.sitio.store.view()["map"]
        try:
            z = act.load_basemap(self.sitio, v["provider"], v["extent"],
                                 v.get("zoom", 0), v.get("custom", ""))
            self._flash(tr("Basemap: {extent:.0f} m, zoom {z}.",
                           extent=v['extent'], z=z))
            self.refresh()
        except act.SiteError as exc:
            self._flash(str(exc))

    def _on_map_show(self, on) -> None:
        if self._busy:
            return
        layer = getattr(self.sitio.scene, "tile_layer", None)
        if layer is not None:
            layer.visible = bool(on)
            self.sitio.store.touch()

    def _on_map_opa(self, v) -> None:
        if self._busy:
            return
        layer = getattr(self.sitio.scene, "tile_layer", None)
        if layer is not None:
            layer.opacity = v / 100.0
            self.sitio.store.touch()

    def _on_osm(self) -> None:
        d = self.sitio.datum()
        if d is None:
            self._flash(tr("Locate the project before loading buildings."))
            return
        if self._osm is None:
            from .osm import OsmWorker
            self._osm = OsmWorker(self)
            self._osm.finished.connect(self._on_osm_done)
            self._osm.failed.connect(self._on_osm_failed)
        r = self.sitio.store.view()["ctx"]["radius"]
        if self._osm.start(d.lat, d.lon, r):
            self.osm_btn.setEnabled(False)
            self.osm_btn.setText(tr("Downloading from OpenStreetMap…"))

    def _on_osm_done(self, payload) -> None:
        self.osm_btn.setEnabled(True)
        self.osm_btn.setText(tr("Load 3D buildings"))
        try:
            act.context_from_osm(self.sitio, payload)
        except act.SiteError as exc:
            self._flash(str(exc))
        self.refresh()

    def _on_osm_failed(self, msg) -> None:
        self.osm_btn.setEnabled(True)
        self.osm_btn.setText(tr("Load 3D buildings"))
        QMessageBox.warning(self, tr("OpenStreetMap"), msg)

    def _on_ctx_show(self, on) -> None:
        if self._busy:
            return
        g = act.context_group(self.sitio)
        if g is not None:
            g.hidden = not on
            self.sitio.store.touch()
            notify = getattr(self.app.viewport, "notify_scene_changed", None)
            if callable(notify):
                notify()

    def _on_rebuild_ctx(self) -> None:
        bl = self.sitio.store.context().get("buildings")
        if bl:
            import copy
            act.set_context(self.sitio, copy.deepcopy(bl),
                            tr("Context updated."))

    def _on_ctx_edit(self, on) -> None:
        self.sitio.edit_context = bool(on)
        if not on:
            self.sitio.selected_building = None
            self.app.release_pick()
        self.refresh()
        self.app.viewport.update()

    def building_selected(self, bid) -> None:
        self.sitio.selected_building = bid
        self.refresh()

    def _on_bld_apply(self) -> None:
        bid = self.sitio.selected_building
        if bid:
            act.update_building(self.sitio, bid, h=self.bld_h.value(),
                                min=self.bld_min.value(), src="user")

    def _on_bld_hide(self) -> None:
        bid = self.sitio.selected_building
        if bid:
            act.update_building(self.sitio, bid, hidden=True)
            self.sitio.selected_building = None
            self.app.release_pick()

    def _on_unhide_all(self) -> None:
        import copy
        bl = copy.deepcopy(self.sitio.store.context().get("buildings") or [])
        if any(b.get("hidden") for b in bl):
            for b in bl:
                b["hidden"] = False
            act.set_context(self.sitio, bl)

    # ---- Masses ------------------------------------------------------------
    def _build_masses(self) -> None:
        sec = _section("8 · ⬛  Masses and lots", "mass", True)
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(_hint(tr("Draw the footprint with Rectangle, Polygon or "
                               "Line, select the face(s) and convert them:")))
        row = QGridLayout()
        b = QPushButton(tr("⬛ Mass from selection"))
        b.clicked.connect(lambda: self._make_masses("mass"))
        row.addWidget(b, 0, 0)
        b = QPushButton(tr("▬ Lot from selection"))
        b.clicked.connect(lambda: self._make_masses("lot"))
        row.addWidget(b, 0, 1)
        lay.addLayout(row)
        form = wrapping_form(None)
        form.addRow(tr("Initial height"), self._bind(_dspin(0, 500, 0.5, 2, " m"),
                                                     ["model", "def_h"]))
        form.addRow(tr("Floor height"), self._bind(_dspin(2, 10, 0.1, 2, " m"),
                                                   ["model", "floor_h"]))
        lay.addLayout(form)
        self.mass_list = QListWidget()
        self.mass_list.setMaximumHeight(150)
        self.mass_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.mass_list.currentRowChanged.connect(self._on_mass_row)
        lay.addWidget(self.mass_list)
        self.mass_box = QWidget()
        mf = wrapping_form(self.mass_box)
        self.mp_name = QLineEdit()
        self.mp_name.editingFinished.connect(self._on_mass_name)
        mf.addRow(tr("Name"), self.mp_name)
        self.mp_kind = QComboBox()
        self.mp_kind.addItem(tr("Mass (volume)"), "mass")
        self.mp_kind.addItem(tr("Lot / area"), "lot")
        self.mp_kind.currentIndexChanged.connect(
            lambda _i: self._mass_change(kind=self.mp_kind.currentData()))
        mf.addRow(tr("Type"), self.mp_kind)
        self.mp_h = _dspin(0, 1000, 0.5, 2, " m")
        self.mp_h.valueChanged.connect(lambda v: self._mass_change(h=v))
        mf.addRow(tr("Height"), self.mp_h)
        self.mp_floors = _ispin(0, 300)
        self.mp_floors.valueChanged.connect(self._on_floors)
        mf.addRow(tr("Floors"), self.mp_floors)
        self.mp_base = _dspin(-1000, 1000, 0.5, 2, " m")
        self.mp_base.valueChanged.connect(lambda v: self._mass_change(base=v))
        mf.addRow(tr("Base elevation"), self.mp_base)
        self.mp_color = ColorButton()
        self.mp_color.colorChanged.connect(lambda c: self._mass_change(color=c))
        self.mp_opa = _dspin(0.1, 1, 0.05, 2)
        self.mp_opa.valueChanged.connect(lambda v: self._mass_change(opacity=v))
        mf.addRow(tr("Color"),
                  _row(self.mp_color, tr("Opacity"), self.mp_opa))
        self.mp_kv = QLabel("")
        self.mp_kv.setTextFormat(Qt.RichText)
        mf.addRow(self.mp_kv)
        g = QGridLayout()
        for i, (txt, fn) in enumerate((
                (tr("⟲ 15°"), lambda: self._mass_op("rotL")),
                (tr("⟳ 15°"), lambda: self._mass_op("rotR")),
                (tr("Duplicate"), lambda: self._mass_op("dup")),
                (tr("Select"), lambda: self._mass_op("sel")),
                (tr("Delete"), lambda: self._mass_op("del")))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            g.addWidget(b, i // 3, i % 3)
        mf.addRow(g)
        self.mass_box.hide()
        narrow(self.mp_kind, self.mp_name)
        lay.addWidget(self.mass_box)
        self.mass_sum = QLabel("")
        self.mass_sum.setTextFormat(Qt.RichText)
        lay.addWidget(self.mass_sum)
        lay.addWidget(_hint(tr("Masses are model groups: they move, rotate "
                               "and push with IngeTrazo tools, and the panel "
                               "reads their current shape. They cast shadow.")))
        self._lay.addWidget(sec)

    def _make_masses(self, kind) -> None:
        try:
            made = act.create_masses_from_faces(self.sitio, kind)
        except act.SiteError as exc:
            self._flash(str(exc))
            return
        self.refresh()
        if made:
            self.select_mass(made[-1])

    def _current_mass(self):
        r = self.mass_list.currentRow()
        return self._mass_rows[r] if 0 <= r < len(self._mass_rows) else None

    def select_mass(self, group) -> None:
        if group in self._mass_rows:
            self.mass_list.setCurrentRow(self._mass_rows.index(group))

    def _on_mass_row(self, _r) -> None:
        if not self._busy:
            self._fill_mass()

    def _fill_mass(self) -> None:
        g = self._current_mass()
        self.mass_box.setVisible(g is not None)
        if g is None:
            return
        p = act.sync_from_mesh(self.sitio, g)
        st = geo.mass_stats(p)
        self._busy = True
        try:
            self.mp_name.setText(g.name)
            self.mp_kind.setCurrentIndex(0 if p["kind"] == "mass" else 1)
            self.mp_h.setValue(p["h"])
            self.mp_h.setEnabled(p["kind"] == "mass")
            self.mp_floors.setEnabled(p["kind"] == "mass")
            self.mp_floors.setValue(st["floors"])
            self.mp_base.setValue(p["base"])
            self.mp_color.setColor(p["color"])
            self.mp_opa.setValue(p["opacity"])
        finally:
            self._busy = False
        rows = [(tr("Footprint area"), f"{st['area']:,.1f} m²"),
                (tr("Perimeter"), f"{st['perimeter']:,.1f} m")]
        if p["kind"] == "mass":
            rows += [(tr("Volume"), f"{st['volume']:,.0f} m³"),
                     (tr("Gross floor area"),
                      tr("{gfa:,.0f} m² ({floors} floors)",
                         gfa=st['gfa'], floors=st['floors'])),
                     (tr("Top elevation"), f"{st['top']:.2f} m")]
        self.mp_kv.setText(_kv(rows))

    def _mass_change(self, **changes) -> None:
        if self._busy:
            return
        g = self._current_mass()
        if g is None:
            return
        new = act.update_mass(self.sitio, g, changes)
        if new is not None:
            self.refresh()
            self.select_mass(new)

    def _on_floors(self, n) -> None:
        if self._busy:
            return
        fh = float(self.sitio.store.view()["model"]["floor_h"])
        self._mass_change(h=n * fh, floor_h=fh)

    def _on_mass_name(self) -> None:
        g = self._current_mass()
        name = self.mp_name.text().strip()
        if g is not None and name and name != g.name:
            g.name = name
            self.sitio.store.touch()
            notify = getattr(self.app.viewport, "notify_scene_changed", None)
            if callable(notify):
                notify()
            self.refresh()

    def _mass_op(self, op) -> None:
        g = self._current_mass()
        if g is None:
            return
        if op in ("rotL", "rotR"):
            new = act.rotate_mass(self.sitio, g, 15.0 if op == "rotL" else -15.0)
        elif op == "dup":
            new = act.duplicate_mass(self.sitio, g)
        elif op == "del":
            act.delete_mass(self.sitio, g)
            new = None
        else:
            sc = self.sitio.scene
            sc.selection.clear()
            sc.selection.add(g)
            self.app.viewport.update()
            new = g
        self.refresh()
        if new is not None:
            self.select_mass(new)

    def _refresh_masses(self) -> None:
        cur = self._current_mass()
        rows = act.masses(self.sitio)
        self._mass_rows = rows
        with QSignalBlocker(self.mass_list):
            self.mass_list.clear()
            for g in rows:
                p = act.sync_from_mesh(self.sitio, g)
                st = geo.mass_stats(p)
                if p["kind"] == "lot":
                    txt = tr("▬ {name} · {area:,.0f} m²",
                             name=g.name, area=st['area'])
                else:
                    txt = tr("⬛ {name} · {h:.1f} m · {floors} fl · "
                             "{area:,.0f} m²",
                             name=g.name, h=p['h'], floors=st['floors'],
                             area=st['area'])
                it = QListWidgetItem(txt)
                it.setForeground(QColor(p["color"]).darker(105))
                self.mass_list.addItem(it)
            if cur in rows:
                self.mass_list.setCurrentRow(rows.index(cur))
        self._fill_mass()
        t = act.summary(self.sitio)
        rows = []
        if t["masses"]:
            rows += [(tr("Masses"), t["masses"]),
                     (tr("Total footprint"), f"{t['footprint']:,.0f} m²"),
                     (tr("Gross floor area"), f"{t['gfa']:,.0f} m²"),
                     (tr("Volume"), f"{t['volume']:,.0f} m³")]
        if t["lots"]:
            rows.append((tr("Lot area"), f"{t['lot_area']:,.0f} m²"))
        if "ios" in t:
            rows += [(tr("Floor area ratio"), f"{t['ios']:.2f}"),
                     (tr("Building ratio"), f"{t['ica']:.2f}")]
        self.mass_sum.setText(_kv(rows) if rows else "")

    # ---- Annotations -------------------------------------------------------
    def _build_pins(self) -> None:
        sec = _section("9 · ⌖  Annotations", "pins")
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        self.icon_q = QLineEdit()
        self.icon_q.setPlaceholderText(tr("Search icon (tree, bus, hospital…)"))
        self.icon_q.textChanged.connect(self._fill_icons)
        lay.addWidget(self.icon_q)
        self.icons = QListWidget()
        self.icons.setViewMode(QListWidget.IconMode)
        self.icons.setFlow(QListWidget.LeftToRight)
        self.icons.setWrapping(True)
        self.icons.setResizeMode(QListWidget.Adjust)
        self.icons.setMaximumHeight(96)
        self.icons.setSpacing(2)
        lay.addWidget(self.icons)
        self._fill_icons()
        row = QGridLayout()
        b = QPushButton(tr("⌖ Point (click in the view)"))
        b.clicked.connect(lambda: self._place_pin(False))
        row.addWidget(b, 0, 0)
        b = QPushButton(tr("★ With the selected icon"))
        b.clicked.connect(lambda: self._place_pin(True))
        row.addWidget(b, 0, 1)
        lay.addLayout(row)
        self.pin_list = QListWidget()
        self.pin_list.setMaximumHeight(120)
        self.pin_list.currentRowChanged.connect(self._on_pin_row)
        lay.addWidget(self.pin_list)
        self.pin_box = QWidget()
        pf = wrapping_form(self.pin_box)
        self.pp_label = QLineEdit()
        self.pp_label.editingFinished.connect(self._on_pin_label)
        pf.addRow(tr("Text"), self.pp_label)
        row = QHBoxLayout()
        b = QPushButton(tr("Use selected icon"))
        b.clicked.connect(self._on_pin_icon)
        row.addWidget(b)
        b = QPushButton(tr("Remove icon"))
        b.clicked.connect(lambda: self._pin_set(icon=None))
        row.addWidget(b)
        b = QPushButton(tr("Delete"))
        b.clicked.connect(self._on_pin_del)
        row.addWidget(b)
        pf.addRow(row)
        self.pin_box.hide()
        lay.addWidget(self.pin_box)
        lay.addWidget(QLabel(tr("<b>Annotation style</b>")))
        form = wrapping_form(None)
        a = ["annot"]
        form.addRow(tr("Icon · Text · Line"), _row(
            self._bind(ColorButton(), a + ["color"]),
            self._bind(ColorButton(), a + ["text"]),
            self._bind(ColorButton(), a + ["line"])))
        form.addRow(self._bind(QCheckBox(tr("Circular background / label")),
                               a + ["bg"]),
                    self._bind(ColorButton(), a + ["bg_color"]))
        form.addRow(tr("Size"), self._bind(_dspin(1, 80, 0.5, 1, " m"),
                                            a + ["size"]))
        form.addRow(tr("Height"), self._bind(_dspin(0, 200, 1, 1, " m"),
                                              a + ["h"]))
        lay.addLayout(form)
        lay.addWidget(self._bind(QCheckBox(tr("Leader line to the ground")),
                                 a + ["line_on"]))
        lay.addWidget(self._bind(QCheckBox(tr("Show text")), a + ["label_on"]))
        b = QPushButton(tr("Apply style to all"))
        b.clicked.connect(lambda: act.style_all_pins(self.sitio))
        lay.addWidget(b)
        lay.addWidget(_hint(tr("With the Select tool: click an annotation "
                               "to select it; Del removes it.")))
        self._lay.addWidget(sec)

    def _fill_icons(self) -> None:
        q = self.icon_q.text().strip().lower() if hasattr(self, "icon_q") else ""
        cur = (self.icons.currentItem().data(Qt.UserRole)
               if self.icons.currentItem() else None)
        self.icons.clear()
        for g, name in ICONS:
            tr_name = tr(name)
            if q and q not in name.lower() and q not in tr_name.lower():
                continue
            it = QListWidgetItem(g)
            it.setData(Qt.UserRole, g)
            it.setToolTip(tr_name)
            it.setTextAlignment(Qt.AlignCenter)
            f = it.font()
            f.setPointSize(15)
            it.setFont(f)
            self.icons.addItem(it)
            if g == cur:
                self.icons.setCurrentItem(it)

    def _chosen_icon(self):
        it = self.icons.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _place_pin(self, with_icon: bool) -> None:
        icon = self._chosen_icon() if with_icon else None
        if with_icon and not icon:
            self._flash(tr("Choose an icon from the list first."))
            return
        name = next((n.split()[0].capitalize() for g, n in ICONS if g == icon),
                    None)

        def done(p, _ctx):
            act.add_pin(self.sitio, p, label=name, icon=icon)

        prompt = tr("Click where the annotation goes")
        tool = pick_tool.make_pick_tool(prompt, done,
                                        lambda: pick_tool.end(self.app),
                                        repeat=True)
        pick_tool.begin(self.app, tool,
                        tr("Click where the annotation goes (several in a row)"))

    def _current_pin(self):
        pid = self.sitio.selected_pin
        for p in self.sitio.store.content()["pins"]:
            if p.get("id") == pid:
                return p
        return None

    def _on_pin_row(self, r) -> None:
        if self._busy:
            return
        pins = self.sitio.store.content()["pins"]
        self.sitio.selected_pin = pins[r]["id"] if 0 <= r < len(pins) else None
        self._fill_pin()
        self.app.viewport.update()

    def _fill_pin(self) -> None:
        p = self._current_pin()
        self.pin_box.setVisible(p is not None)
        if p is not None:
            with QSignalBlocker(self.pp_label):
                self.pp_label.setText(pin_label_text(str(p.get("label", ""))))

    def _pin_set(self, **ch) -> None:
        pid = self.sitio.selected_pin
        if pid:
            act.update_pin(self.sitio, pid, **ch)

    def _on_pin_label(self) -> None:
        p = self._current_pin()
        if p is not None and self.pp_label.text() != pin_label_text(
                str(p.get("label", ""))):
            self._pin_set(label=self.pp_label.text())

    def _on_pin_icon(self) -> None:
        icon = self._chosen_icon()
        if icon:
            self._pin_set(icon=icon)

    def _on_pin_del(self) -> None:
        pid = self.sitio.selected_pin
        if pid:
            act.delete_pin(self.sitio, pid)
            self.app.release_pick()

    def pin_selected(self, pid) -> None:
        self.sitio.selected_pin = pid
        self.refresh()

    # ---- View --------------------------------------------------------------
    def _build_view(self) -> None:
        sec = _section("10 · ◐  Visualization", "view", True)
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        self.on = self._bind(QCheckBox(tr("Show analysis in the view")), ["on"])
        lay.addWidget(self.on)
        lay.addWidget(self._bind(QCheckBox(tr("Compass and degrees")),
                                 ["view", "compass"]))
        form = wrapping_form(None)
        form.addRow(tr("Rings"), _row(self._bind(_ispin(0, 20), ["rings", "n"]),
                                      tr("every"),
                                      self._bind(_dspin(1, 1000, 5, 0, " m"),
                                                 ["rings", "step"]),
                                      self._bind(ColorButton(),
                                                 ["rings", "color"])))
        form.addRow(tr("Label scale"),
                    self._bind(_dspin(0.4, 2.5, 0.1, 1), ["view", "label_scale"]))
        lay.addLayout(form)
        lay.addWidget(QLabel(tr("<b>Conventions</b>")))
        self.legend = LegendWidget()
        lay.addWidget(self.legend)
        lay.addWidget(QLabel(tr("<b>Views</b>")))
        g = QGridLayout()
        views = ((tr("Top"), "top"), (tr("Iso SE"), "iso_se"),
                 (tr("Iso SW"), "iso_sw"), (tr("Iso NE"), "iso_ne"),
                 (tr("Iso NW"), "iso_nw"), (tr("Aerial"), "persp"),
                 (tr("From the sun"), "sun"),
                 (tr("Fit"), "fit"),
                 (tr("Persp./Paral."), "proj"))
        for i, (t, k) in enumerate(views):
            b = QPushButton(t)
            b.clicked.connect(lambda _c=False, k=k: self.set_view(k))
            g.addWidget(b, i // 3, i % 3)
        lay.addLayout(g)
        self._lay.addWidget(sec)

    def set_view(self, key: str) -> None:
        vp = self.app.viewport
        cam = vp.camera
        v = self.sitio.store.view()
        cx, cy, cz = v["center"]
        R = float(v["radius"]) * 1.3
        if key == "proj":
            cam.perspective = not cam.perspective
            vp.update()
            return
        if key == "top":
            cam.set_view("top")
        elif key.startswith("iso_"):
            yaw = {"iso_se": -45.0, "iso_sw": -135.0, "iso_ne": 45.0,
                   "iso_nw": 135.0}[key]
            cam.yaw, cam.pitch = math.radians(yaw), math.radians(35.0)
        elif key == "persp":
            cam.perspective = True
            cam.yaw, cam.pitch = math.radians(-60.0), math.radians(22.0)
        elif key == "sun":
            alt, az = self.sitio.sun_now()
            if alt <= 0:
                self._flash(tr("The sun is below the horizon at this hour."))
                return
            dx, dy, _dz = self.sitio.frame().direction(alt, az)
            cam.yaw = math.atan2(dy, dx)
            cam.pitch = math.radians(max(alt, 3.0))
        fit = getattr(cam, "fit_to", None)
        if callable(fit):
            fit(QVector3D(cx - R, cy - R, cz), QVector3D(cx + R, cy + R, cz + R * 0.6))
        else:
            cam.target = QVector3D(cx, cy, cz)
            cam.distance = R * 2.2
        vp.update()

    # ---- 12 · Export -------------------------------------------------------
    def _build_export(self) -> None:
        sec = _section("12 · ⇩  Export image", "export")
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        form = wrapping_form(None)
        self.res = QComboBox()
        for t, w in ((tr("FHD (1920)"), 1920), (tr("2K (2560)"), 2560),
                     (tr("4K (3840)"), 3840), (tr("5K (5120)"), 5120)):
            self.res.addItem(t, w)
        form.addRow(tr("Resolution"), self.res)
        narrow(self.res)
        lay.addLayout(form)
        b = QPushButton(tr("Export image (PNG)…"))
        b.clicked.connect(self._on_png)
        lay.addWidget(b)
        lay.addWidget(_hint(tr("The image is the current view with the "
                               "analysis on top, including the info panel "
                               "if visible.")))
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)
        form = wrapping_form(None)
        form.addRow(tr("Panel title"),
                    self._bind(QLineEdit(), ["view", "notes_title"]))
        corner = QComboBox()
        for k, t in (("tr", tr("Top right")), ("tl", tr("Top left")),
                     ("br", tr("Bottom right")), ("bl", tr("Bottom left"))):
            corner.addItem(t, k)
        form.addRow(tr("Position"), self._bind(corner, ["view", "notes_corner"]))
        narrow(corner)
        lay.addLayout(form)
        # Hidden at IngeTrazo start: it is a session setting, not a
        # document one (a .igz does not turn it back on when reopened).
        self.notes_on = QCheckBox(tr("Show floating info and conventions "
                                     "panel"))
        self.notes_on.toggled.connect(self._on_notes)
        lay.addWidget(self.notes_on)
        self._lay.addWidget(sec)

    def _on_notes(self, on) -> None:
        if self._busy:
            return
        self.sitio.show_notes = bool(on)

        if on:
            if self._floating_notes is None:
                from .drawing import FloatingBox
                self._floating_notes = FloatingBox(
                    self.app.viewport,
                    draw_func=lambda p, r, ls: self.overlay._notes(
                        p, self.app.viewport, self.sitio.store.view(), ls, rect=r),
                    label_scale=lambda: self.sitio.store.view()["view"].get(
                        "label_scale", 1.0),
                    anchor="tl",
                )
                self._floating_notes.resize_to_content()
                self._floating_notes.move(20, 20)
            self._floating_notes.show()
            self._floating_notes.raise_()
        else:
            if self._floating_notes:
                self._floating_notes.hide()
                
                
    def _ask_save(self, title, name, filt):
        path, _f = QFileDialog.getSaveFileName(self, title, name, filt)
        return path

    def _stem(self) -> str:
        n = self.sitio.store.view().get("site_name") or "site"
        return "".join(c if c.isalnum() else "_" for c in n).strip("_") or "site"

    def _on_png(self) -> None:
        from PySide6.QtCore import QStandardPaths
        docs_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        
        # Cria o nome do arquivo baseado no nome do sítio
        filename = self._stem() + "_analysis.png"
        initial_path = os.path.join(docs_dir, filename) if docs_dir else filename
        
        path = self._ask_save(tr("Export image"),
                              initial_path,
                              tr("PNG image (*.png)"))
        if path:
            try:
                export.export_png(self.sitio, self.overlay, path,
                                  self.res.currentData())
                self._flash(tr("Image saved: {path}", path=path))
            except act.SiteError as exc:
                self._flash(str(exc))

    # ---- 11 · Solar radiation and shadows ----------------------------------
    def _build_solar(self) -> None:
        from . import radiation as rad
        sec = _section("11 · ☀  Solar radiation and shadows", "solar", True)
        lay = QVBoxLayout(sec.body)
        lay.setContentsMargins(6, 6, 6, 6)
        r, d = ["rad"], ["sd"]
        # Common: which surfaces and at what detail.
        form = wrapping_form(None)
        tgt = QComboBox()
        for k, t in (("all", tr("Whole model (excluding OSM context)")),
                     ("masses", tr("Masses and lots")),
                     ("sel", tr("Selection (faces or groups)")),
                     ("none", tr("Ground only"))):
            tgt.addItem(t, k)
        form.addRow(tr("Surfaces"), self._bind(tgt, r + ["target"]))
        resn = QComboBox()
        for k, t in (("faces:1.0", tr("Per surface (one color per face)")),
                     ("cells:2.0", tr("2 m grid")), ("cells:1.0", tr("1 m grid")),
                     ("cells:0.5", tr("0.5 m grid"))):
            resn.addItem(t, k)
        resn.currentIndexChanged.connect(self._on_rad_res)
        self.rad_res = resn
        form.addRow(tr("Resolution"), resn)
        self.ground_r = _dspin(0, 2000, 10, 0, " m")
        self.ground_r.setSpecialValueText(tr("automatic"))
        self._bind(self.ground_r, r + ["ground_r"])
        form.addRow(self._bind(QCheckBox(tr("Surrounding ground")),
                               r + ["ground"]),
                    _row(tr("margin"), self.ground_r))
        narrow(tgt, resn)
        lay.addLayout(form)
        # Radiation.
        lay.addWidget(QLabel(tr("<b>Incident solar radiation</b>")))
        form = wrapping_form(None)
        per = QComboBox()
        for k, t in (("day", tr("Day in section 4")),
                     ("month", tr("One month")),
                     ("period", tr("Analysis period (section 1)")),
                     ("year", tr("Full year"))):
            per.addItem(t, k)
        self.rad_per = self._bind(per, r + ["period"], after=self._sync_rad)
        form.addRow(tr("Period"), per)
        mon = QComboBox()
        for i, m in enumerate(climate.MONTHS_LONG_EN):
            mon.addItem(climate.month_long(i), i + 1)
        self.rad_month = self._bind(mon, r + ["month"])
        self.rad_month_lbl = QLabel(tr("Month"))
        form.addRow(self.rad_month_lbl, mon)
        form.addRow(tr("Ground albedo"),
                    self._bind(_dspin(0, 0.9, 0.05, 2), r + ["albedo"]))
        narrow(per, mon)
        lay.addLayout(form)
        self.rad_src = _hint("")
        lay.addWidget(self.rad_src)
        b = QPushButton(tr("☀  Compute radiation"))
        b.clicked.connect(self._on_rad)
        lay.addWidget(b)
        # Shadows.
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)
        lay.addWidget(QLabel(tr("<b>Shadow study</b>")))
        self.sd_date = _hint("")
        lay.addWidget(self.sd_date)
        form = wrapping_form(None)
        form.addRow(tr("From"), self._bind(_ispin(0, 23, ":00 h"), d + ["h0"]))
        form.addRow(tr("To"), self._bind(_ispin(1, 24, ":00 h"), d + ["h1"]))
        step = QComboBox()
        for m in (15, 20, 30, 60):
            step.addItem(tr("every {m} min", m=m), m)
        form.addRow(tr("Interval"), self._bind(step, d + ["step"]))
        narrow(step)
        lay.addLayout(form)
        b = QPushButton(tr("◑  Compute shadow study"))
        b.clicked.connect(self._on_sd)
        lay.addWidget(b)
        # Result in the view.
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)
        self.map_box = QWidget()
        ml = QVBoxLayout(self.map_box)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(QLabel(tr("<b>Result in the view</b>")))
        self.map_pick = QComboBox()
        self.map_pick.currentIndexChanged.connect(self._on_map_pick)
        ml.addWidget(self.map_pick)
        self.legend_on = self._bind(
            QCheckBox(tr("Show floating scale panel (radiation / shadows)")),
            r + ["legend"])
        ml.addWidget(self.legend_on)
        self.map_kv = QLabel("")
        self.map_kv.setTextFormat(Qt.RichText)
        self.map_kv.setWordWrap(True)
        ml.addWidget(self.map_kv)
        self.rad_opts = QWidget()
        rl = wrapping_form(self.rad_opts)
        pal = QComboBox()
        for k in rad.PALETTES:
            pal.addItem(rad.palette_name(k), k)
        self._bind(pal, r + ["palette"], after=self._rad_recolor)
        rl.addRow(tr("Colors"), pal)
        rl.addRow(self._bind(QCheckBox(tr("Automatic scale (min–max)")),
                             r + ["auto"], after=self._rad_recolor))
        self.rad_lo = self._bind(_dspin(0, 1e6, 10, 1, " kWh/m²"), r + ["vmin"],
                                 after=self._rad_recolor)
        self.rad_hi = self._bind(_dspin(0, 1e6, 10, 1, " kWh/m²"), r + ["vmax"],
                                 after=self._rad_recolor)
        rl.addRow(tr("Minimum"), self.rad_lo)
        rl.addRow(tr("Maximum"), self.rad_hi)
        narrow(pal)
        ml.addWidget(self.rad_opts)
        self.sd_opts = QWidget()
        sl = wrapping_form(self.sd_opts)
        spal = QComboBox()
        for k in rad.PALETTES:
            spal.addItem(rad.palette_name(k), k)
        self._bind(spal, d + ["palette"], after=self._sd_recolor)
        sl.addRow(tr("Colors"), spal)
        show = QComboBox()
        show.addItem(tr("Shade hours"), "shade")
        show.addItem(tr("Sun hours (insolation)"), "sun")
        self._bind(show, d + ["show"], after=self._sd_recolor)
        sl.addRow(tr("Show"), show)
        narrow(spal, show)
        ml.addWidget(self.sd_opts)
        b = QPushButton(tr("Remove the displayed result"))
        b.clicked.connect(self._on_map_clear)
        ml.addWidget(b)
        lay.addWidget(self.map_box)
        lay.addWidget(_hint(tr(
            "Radiation: direct (with shadows from the whole model and the "
            "context) + diffuse with the real sky view + ground reflection. "
            "Shadows: shade hours per point, sampling the sun at each "
            "interval. Turn off projected shadows (section 4) to read the "
            "colors well.")))
        self._lay.addWidget(sec)

    def _sync_rad(self) -> None:
        on = self.rad_per.currentData() == "month"
        self.rad_month.setVisible(on)
        self.rad_month_lbl.setVisible(on)

    def _on_rad_res(self, _i) -> None:
        if self._busy:
            return
        mode, grid = self.rad_res.currentData().split(":")
        v = self.sitio.store.view()["rad"]
        v["mode"], v["grid"] = mode, float(grid)
        self.sitio.store.touch()

    def _progress(self, title: str):
        from PySide6.QtWidgets import QApplication, QProgressDialog
        dlg = QProgressDialog(title, tr("Cancel"), 0, 1000, self.app.window)
        dlg.setWindowTitle(tr("Site analysis"))
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)

        def cb(frac, text=None):
            dlg.setValue(int(max(0.0, min(1.0, frac)) * 1000))
            if text:
                dlg.setLabelText(f"{title}\n{text}")
            QApplication.processEvents()
            return dlg.wasCanceled()
        return dlg, cb

    def _settings(self, extra: dict) -> dict:
        s = dict(self.sitio.store.view()["rad"])
        if s.get("target") == "none":
            s["target"], s["ground"] = "ground", True
        s.update(extra)
        return s

    def _run_map(self, fn, settings, title, cancelled) -> None:
        dlg, cb = self._progress(title)
        try:
            res = fn(self.sitio, settings, cb)
        except act.SiteError as exc:
            dlg.close()
            self._flash(str(exc))
            return
        dlg.close()
        if res is None:
            self._flash(cancelled)
        self.refresh()

    def _on_rad(self) -> None:
        from . import radiation as rad
        self._run_map(rad.analyse, self._settings({}),
                      tr("Computing incident radiation…"),
                      tr("Radiation computation cancelled."))

    def _on_sd(self) -> None:
        from . import radiation as rad
        sd = self.sitio.store.view()["sd"]
        self._run_map(rad.shadow_study,
                      self._settings({"h0": sd["h0"], "h1": sd["h1"],
                                      "step": sd["step"],
                                      "palette": sd.get("palette", "grises"),
                                      "show": sd.get("show", "shade")}),
                      tr("Shadow study…"),
                      tr("Shadow study cancelled."))

    def _rad_recolor(self) -> None:
        from . import radiation as rad
        v = self.sitio.store.view()["rad"]
        rad.recolor(self.sitio, "radiation", palette=v["palette"],
                    auto=v["auto"], vmin=v["vmin"], vmax=v["vmax"])
        self.schedule_refresh()

    def _sd_recolor(self) -> None:
        from . import radiation as rad
        sd = self.sitio.store.view()["sd"]
        rad.recolor(self.sitio, "shadows", palette=sd.get("palette", "grises"),
                    show=sd.get("show", "shade"))
        self.schedule_refresh()

    def _on_map_pick(self, _i) -> None:
        from . import radiation as rad
        if self._busy:
            return
        rad.show_map(self.sitio, self.map_pick.currentData())
        self.refresh()

    def _on_map_clear(self) -> None:
        from . import radiation as rad
        from .data import run_step
        g = rad.visible_map(self.sitio.scene, self.sitio.store.key)
        if g is None:
            return

        def mutate(sc):
            if g in sc.groups:
                sc.groups.remove(g)
            sc.selection.discard(g)

        run_step(self.app.viewport, mutate,
                 message=tr("Result removed."))
        self.refresh()

    def _refresh_rad(self) -> None:
        from . import radiation as rad
        st = self.sitio
        key = st.store.key
        v = st.store.view()["rad"]
        i = self.rad_res.findData(f"{v['mode']}:{float(v['grid']):.1f}")
        with QSignalBlocker(self.rad_res):
            self.rad_res.setCurrentIndex(max(0, i))
        self._sync_rad()
        self.ground_r.setEnabled(bool(v.get("ground", True)))
        epw = st.epw()
        self.rad_src.setText(
            tr("Weather: EPW from {city} (hourly DNI and DHI).",
               city=epw['info'].get('city') or tr('the station')) if epw else
            tr("No EPW: a theoretical clear sky is used (maximum possible "
               "values). Load an EPW in section 1 for the real weather."))
        m, d = solar.month_day(st.when()[0])
        self.sd_date.setText(
            tr("Day: {d} {month} (the date in section 4).",
               d=d, month=climate.month_long(m - 1)))
        groups = {k: rad.find_group(st.scene, key, k) for k in rad.KINDS}
        shown = rad.visible_map(st.scene, key)
        self.map_box.setVisible(any(groups.values()))
        with QSignalBlocker(self.map_pick):
            self.map_pick.clear()
            self.map_pick.addItem(tr("None"), None)
            for k, title in (("radiation", tr("Solar radiation map")),
                             ("shadows", tr("Shadow study (shade hours)"))):
                if groups[k] is not None:
                    self.map_pick.addItem(title, k)
            kind = (shown.ext[key]["kind"] if shown is not None else None)
            self.map_pick.setCurrentIndex(max(0, self.map_pick.findData(kind)))
        self.rad_opts.setVisible(kind == "radiation")
        self.sd_opts.setVisible(kind == "shadows")
        self.rad_lo.setEnabled(not v["auto"])
        self.rad_hi.setEnabled(not v["auto"])
        if shown is None:
            self.map_kv.setText("")
            return
        data = shown.ext.get(key) or {}
        sm = data.get("summary") or {}
        if kind == "radiation":
            rows = [(tr("Period"), data.get("period", "—")),
                    (tr("Weather"), data.get("source", "—"))]
            if sm:
                rows += [(tr("Surfaces"),
                          tr("{n} ({area:,.0f} m²)",
                             n=sm['faces'], area=sm['area'])),
                         (tr("Sample points"),
                          tr("{n:,} · {grid:.2g} m grid",
                             n=sm['cells'], grid=sm['grid'])),
                         (tr("Min / max"),
                          tr("{lo:,.1f} / {hi:,.1f} kWh/m²",
                             lo=sm['min'], hi=sm['max'])),
                         (tr("Mean (area-weighted)"),
                          tr("{v:,.1f} kWh/m²", v=sm['mean'])),
                         (tr("Incident energy"),
                          tr("{v:,.1f} MWh", v=sm['energy'] / 1000)),
                         (tr("Sun positions"),
                          tr("{n} · {s:.1f} s", n=sm['n_sun'],
                             s=sm['seconds']))]
        else:
            rows = [(tr("Day and steps"), data.get("period", "—")),
                    (tr("Sun in the interval"),
                     tr("{h:.1f} h", h=data.get('hours', 0)))]
            if sm:
                a = max(sm["area"], 1e-9)
                rows += [(tr("Analyzed area"), f"{sm['area']:,.0f} m²"),
                         (tr("Mean shade"), tr("{h:.1f} h", h=sm['mean'])),
                         (tr("Always in sun"),
                          tr("{area:,.0f} m² ({pct:.0f} %)",
                             area=sm['full_sun'],
                             pct=sm['full_sun'] / a * 100)),
                         (tr("Always in shade"),
                          tr("{area:,.0f} m² ({pct:.0f} %)",
                             area=sm['full_shade'],
                             pct=sm['full_shade'] / a * 100)),
                         (tr("Sample points"),
                          tr("{n:,} · {s:.1f} s",
                             n=sm['cells'], s=sm['seconds']))]
        self.map_kv.setText(_kv(rows))

    # ---- Refresh -----------------------------------------------------------
    def _flash(self, text: str) -> None:
        self.app.viewport.flash_status(text, 5000)

    def schedule_refresh(self) -> None:
        self._refresh_timer.start()

    def refresh(self) -> None:
        self._busy = True
        try:
            self._read_binds()
            self.notes_on.setChecked(bool(getattr(self.sitio, "show_notes", False)))
            st = self.sitio
            v = st.store.view()
            doy, hour = st.when()
            m, d = solar.month_day(doy)
            self.doy.setValue(doy)
            self.doy_lbl.setText(tr("{d} {month}", d=d,
                                    month=climate.month_short(m - 1)))
            self.hour.setValue(int(round(hour * 4)) % 96)
            s = st.site()
            self.hour_lbl.setText(solar.fmt_hour(hour))
            sh = st.shadows()
            if sh is not None:
                self.shadow_on.setChecked(sh.enabled)
                self.shadow_dark.setValue(int(round((1.0 - sh.darkness) * 100)))
                i = self.tz.findData(sh.utc_offset)
                self.tz.setCurrentIndex(i if i >= 0 else 0)
            alt, az = st.sun_now()
            rise, sset = st.sun_times()
            span = (tr("{h:.1f} h", h=sset - rise)
                    if rise is not None and sset is not None else "—")
            rows = [(tr("Sun"),
                     tr("alt {alt:.1f}° · az {az:.1f}°", alt=alt, az=az)),
                    (tr("Sunrise / sunset"),
                     tr("{rise} / {set}", rise=solar.fmt_hour(rise),
                        set=solar.fmt_hour(sset))),
                    (tr("Sun hours"), span)]
            rec = st.hour_record()
            if rec:
                rows.append((tr("Weather at this hour"),
                             f"{rec['t']:.1f} °C · {rec['rh']:.0f} % · "
                             f"{rec['ws']:.1f} m/s"))
            self.sun_kv.setText(_kv(rows))
            self.anim_btn.setChecked(st.animating_sun)
            self.anim_btn.setText(tr("■  Stop") if st.animating_sun
                                  else tr("▶  Animate sun path"))
            self.lat.setValue(s["lat"])
            self.lon.setValue(s["lon"])
            self.north.setValue(s["north"])
            self.north_dial.setValue(int(round(s["north"] + 180.0)) % 360)
            for w in (self.north, self.north_dial):
                w.setEnabled(s["located"])
            self.north_hint.setText(
                tr("Where geographic north lies in the model. Rotates the "
                   "sun, the diagram, the basemap and the terrain; the "
                   "geometry does not move.") if s["located"] else
                tr("Locate the project first (section 2) to set its north."))
            self.legend.set_rows(legend_rows(st))
            self.loc_hint.setText(
                tr("Project location (IngeTrazo datum): used by the sun, "
                   "shadows, map and terrain.") if s["located"] else
                tr("⚠ The project has no location: a default site is used. "
                   "Search the address, pick on the map, or open an EPW."))
            months = set(int(x) for x in v["sun"]["months"])
            for i, cb in enumerate(self.month_checks):
                cb.setChecked(i + 1 in months)
            cx, cy, cz = v["center"]
            self.cx.setValue(cx)
            self.cy.setValue(cy)
            self.cz.setValue(cz)
            self._fill_winds()
            self._sync_custom()
            layer = getattr(st.scene, "tile_layer", None)
            self.map_show.setEnabled(layer is not None)
            self.map_opa.setEnabled(layer is not None)
            if layer is not None:
                self.map_show.setChecked(bool(layer.visible))
                self.map_opa.setValue(int(round(getattr(layer, "opacity", 1) * 100)))
            ctx = st.store.context()
            bl = ctx.get("buildings") or []
            g = act.context_group(st)
            if bl:
                tagged = sum(1 for b in bl if b.get("src") == "tag")
                hidden = sum(1 for b in bl if b.get("hidden"))
                txt = tr("{n} buildings ({tagged} with OSM height",
                         n=len(bl), tagged=tagged)
                if hidden:
                    txt += tr(", {hidden} hidden", hidden=hidden)
                txt += ")."
                self.ctx_count.setText(txt)
            else:
                self.ctx_count.setText(tr("No context buildings."))
            self.ctx_show.setEnabled(g is not None)
            self.ctx_show.setChecked(g is not None and not g.hidden)
            self.ctx_edit.setChecked(st.edit_context)
            b = next((b for b in bl if b.get("id") == st.selected_building), None)
            self.bld_box.setVisible(st.edit_context and b is not None)
            if b is not None:
                self.bld_name.setText(b.get("name") or b["id"])
                self.bld_h.setValue(float(b.get("h", 9)))
                self.bld_min.setValue(float(b.get("min", 0)))
            pins = st.store.content()["pins"]
            self.pin_list.clear()
            sel_row = -1
            for i, p in enumerate(pins):
                self.pin_list.addItem(
                    f"{p.get('icon') or '⌖'}  "
                    f"{pin_label_text(str(p.get('label', '')))}")
                if p.get("id") == st.selected_pin:
                    sel_row = i
            self.pin_list.setCurrentRow(sel_row)
        finally:
            self._busy = False

        # ---- Atualiza o widget de escala flutuante (fora do try/finally) ----
        from . import radiation as rad
        mapa_visivel = rad.visible_map(
            self.sitio.scene, self.sitio.store.key) is not None
        quer_mostrar = (getattr(self, "legend_on", None)
                        and self.legend_on.isChecked())

        if mapa_visivel and quer_mostrar:
            if (not hasattr(self, "_floating_scale")
                    or self._floating_scale is None):
                from .drawing import FloatingBox
                self._floating_scale = FloatingBox(
                    self.app.viewport,
                    draw_func=lambda p, r, ls: self.overlay._rad_legend(
                        p, self.app.viewport, self.sitio.store.view(), ls,
                        rect=r),
                    label_scale=lambda: self.sitio.store.view()["view"].get(
                        "label_scale", 1.0),
                    anchor="tr",
                )
                self._floating_scale.resize_to_content()
            self._floating_scale.show()
            self._floating_scale.raise_()
        else:
            if (hasattr(self, "_floating_scale")
                    and self._floating_scale is not None):
                self._floating_scale.hide()

        self._fill_pin()
        self._refresh_climate()
        self._refresh_masses()
        self._refresh_rad()
        