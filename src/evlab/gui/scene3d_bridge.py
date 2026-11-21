"""Qt side of the 3D laboratory: core meshes as Qt Quick 3D geometries and the QObject the QML scene reads.

No physics here: the meshes, the angles, the powers and the temperatures come from core.scene3d; this module
packs them for QML (metres → millimetres, radians → degrees: units of the scene) and holds the display state
(explosion, visibility, colour mode, selection).
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Property, QByteArray, QObject, Signal, Slot
from PySide6.QtGui import QColor, QVector3D
from PySide6.QtQml import QQmlEngine
from PySide6.QtQuick3D import QQuick3DGeometry

from evlab.core import scene3d
from evlab.palette import SERIES

MM = 1000.0  # scene unit: millimetre

# appearance of each material role: colour, metalness, roughness, opacity (presentation only)
MATERIALS: dict[str, tuple[str, float, float, float]] = {
    "housing": ("#6C7785", 0.25, 0.5, 1.0),
    "housing_dark": ("#4C5664", 0.2, 0.55, 1.0),
    "steel": ("#A3AEBD", 0.5, 0.35, 1.0),
    "steel_rotor": ("#8E9AAA", 0.5, 0.38, 1.0),
    "aluminium": ("#C9D0D8", 0.6, 0.3, 1.0),
    "copper": ("#C77B3F", 0.55, 0.32, 1.0),
    "phase_A": (SERIES["red"], 0.2, 0.45, 1.0),
    "phase_B": ("#E0A93A", 0.2, 0.45, 1.0),
    "phase_C": (SERIES["blue"], 0.2, 0.45, 1.0),
    "air_gap": ("#22C3D6", 0.0, 0.5, 0.35),
    "shaft": ("#B5BDC7", 0.7, 0.25, 1.0),
    "bearing": ("#D2D8DF", 0.75, 0.2, 1.0),
    "chassis": ("#4A5664", 0.3, 0.6, 1.0),
    "battery": ("#33506E", 0.2, 0.5, 1.0),
    "soc": (SERIES["green"], 0.0, 0.5, 1.0),
    "soc_case": ("#9AA3AF", 0.0, 0.4, 0.25),
    "inverter": ("#4A5866", 0.3, 0.45, 1.0),
    "gear": ("#AEB7C2", 0.7, 0.3, 1.0),
    "gear_final": ("#9AA5B1", 0.7, 0.3, 1.0),
    "differential": ("#6E7A88", 0.5, 0.4, 1.0),
    "tyre": ("#2A3038", 0.0, 0.85, 1.0),
    "rim": ("#B9C1CB", 0.7, 0.3, 1.0),
    "cable_dc": ("#E5534B", 0.1, 0.5, 1.0),
    "cable_ac": ("#E0A93A", 0.1, 0.5, 1.0),
}
PHASE_MATERIALS = ("phase_A", "phase_B", "phase_C")
COLOUR_MODES = ("phases", "materials", "thermal")
# temperature scale (fraction 0 → 1): navy, cyan, amber, red
HEAT_STOPS = ((0.0, "#1F3B73"), (0.35, "#22C3D6"), (0.7, "#E0A93A"), (1.0, "#D64541"))


def heat_colour(fraction: float) -> str:
    """Colour of a position 0…1 on the temperature scale (piecewise-linear between HEAT_STOPS)."""
    f = min(1.0, max(0.0, fraction))
    for (f0, c0), (f1, c1) in zip(HEAT_STOPS[:-1], HEAT_STOPS[1:]):
        if f <= f1:
            a, b = QColor(c0), QColor(c1)
            u = (f - f0) / (f1 - f0)
            return QColor.fromRgbF(a.redF() + u * (b.redF() - a.redF()), a.greenF() + u * (b.greenF() - a.greenF()),
                                   a.blueF() + u * (b.blueF() - a.blueF())).name()
    return HEAT_STOPS[-1][1]


class MeshGeometry(QQuick3DGeometry):
    """A core mesh (m) as a Qt Quick 3D geometry (mm): interleaved position + normal, 32-bit indices."""

    def __init__(self, mesh: scene3d.Mesh) -> None:
        super().__init__()
        self.set_mesh(mesh)

    def set_mesh(self, mesh: scene3d.Mesh) -> None:
        data = np.hstack([mesh.positions * MM, mesh.normals]).astype(np.float32)
        self.clear()
        self.setVertexData(QByteArray(data.tobytes()))
        self.setIndexData(QByteArray(mesh.indices.astype(np.uint32).tobytes()))
        self.setStride(24)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        a = QQuick3DGeometry.Attribute
        self.addAttribute(a.PositionSemantic, 0, a.F32Type)
        self.addAttribute(a.NormalSemantic, 12, a.F32Type)
        self.addAttribute(a.IndexSemantic, 0, a.U32Type)
        lo, hi = mesh.bounds()
        self.setBounds(QVector3D(*(lo * MM)), QVector3D(*(hi * MM)))
        self.update()


def _mm(v) -> list[float]:
    return [float(x) * MM for x in v]


class SceneBridge(QObject):
    """Display state of the 3D scene, read by lab3d.qml (context property « bridge »)."""

    partsChanged = Signal()
    explodeChanged = Signal()
    visibilityChanged = Signal()
    coloursChanged = Signal()
    selectedChanged = Signal()
    labelsChanged = Signal()
    anglesChanged = Signal()
    socChanged = Signal()
    particlesChanged = Signal()
    themeChanged = Signal()
    cameraRequested = Signal(str)  # preset name
    picked = Signal(str)  # part key ("" = nothing)

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[dict] = []
        self._geoms: dict[str, MeshGeometry] = {}
        self._explode = 0.0
        self._visible: dict[str, bool] = {}
        self._mode = "phases"
        self._temps: dict[str, float] = {}  # material → fraction on the temperature scale
        self._selected = ""
        self._labels_on = True
        self._labels: list[dict] = []
        self._angles = {"motor": 0.0, "intermediate": 0.0, "wheel": 0.0}
        self._soc = 1.0
        self._particles: list[dict] = []
        self._theme = {"background": "#0E141B", "accent": "#22C3D6", "text": "#E3E9F1", "card": "#141C26",
                       "border": "#243142", "ground": "#141C26"}
        self.scene_name = ""
        self.radius_mm = 300.0
        self.centre_mm = [0.0, 0.0, 0.0]

    # --- scene content --------------------------------------------------------------------------

    def set_parts(self, scene: str, parts: list[scene3d.Part], labels: dict[str, str], centre, radius: float,
                  main: set[str] | None = None) -> None:
        """Replace the scene: its parts (core), the label of each part (French), its centre and size (m).
        Labels of the « main » parts show when labels are on; any other shows when its part is selected."""
        old = self._geoms
        self._geoms = {}
        for p in parts:
            g = MeshGeometry(p.mesh)
            QQmlEngine.setObjectOwnership(g, QQmlEngine.ObjectOwnership.CppOwnership)
            self._geoms[p.key] = g
        self._old_geoms = old  # kept until QML has released the previous delegates
        self._parts = [{"key": p.key, "group": p.group, "material": p.material, "origin": _mm(p.origin),
                        "axis": p.axis, "spin": p.spin or "", "explode": _mm(p.explode)} for p in parts]
        self._labels = [{"key": p.key, "group": p.group, "text": labels[p.key],
                         "main": main is None or p.key in main,
                         "anchor": _mm(np.add(p.origin, p.anchor)), "explode": _mm(p.explode)}
                        for p in parts if p.key in labels]
        self.scene_name = scene
        self.centre_mm = _mm(centre)
        self.radius_mm = float(radius) * MM
        self._selected = ""
        self.partsChanged.emit()
        self.labelsChanged.emit()
        self.selectedChanged.emit()

    @Property("QVariantList", notify=partsChanged)
    def parts(self) -> list:
        return self._parts

    @Slot(str, result=QObject)
    def geometry(self, key: str) -> QObject | None:
        return self._geoms.get(key)

    @Property("QVariantList", notify=partsChanged)
    def centre(self) -> list:
        return self.centre_mm

    @Property(float, notify=partsChanged)
    def radius(self) -> float:
        return self.radius_mm

    @Property(str, notify=partsChanged)
    def scene(self) -> str:
        return self.scene_name

    def part_keys(self) -> list[str]:
        return [p["key"] for p in self._parts]

    # --- view state -------------------------------------------------------------------------

    @Property(float, notify=explodeChanged)
    def explode(self) -> float:
        return self._explode

    def set_explode(self, x: float) -> None:
        self._explode = float(x)
        self.explodeChanged.emit()

    @Property("QVariantMap", notify=visibilityChanged)
    def visibleGroups(self) -> dict:  # noqa: N802 (QML name)
        return self._visible

    def set_group_visible(self, group: str, on: bool) -> None:
        self._visible[group] = bool(on)
        self.visibilityChanged.emit()

    def group_visible(self, group: str) -> bool:
        return self._visible.get(group, True)

    def set_colour_mode(self, mode: str) -> None:
        if mode not in COLOUR_MODES:
            raise ValueError(f"colour mode must be one of {COLOUR_MODES}")
        self._mode = mode
        self.coloursChanged.emit()

    @property
    def colour_mode(self) -> str:
        return self._mode

    def set_temperatures(self, fractions: dict[str, float]) -> None:
        """Positions on the temperature scale (0…1) of the thermal nodes: "winding" and "frame"."""
        self._temps = dict(fractions)
        if self._mode == "thermal":
            self.coloursChanged.emit()

    def material_colour(self, material: str) -> str:
        colour = MATERIALS[material][0]
        if self._mode == "materials" and material in PHASE_MATERIALS:
            return MATERIALS["copper"][0]
        if self._mode == "thermal":
            if material in PHASE_MATERIALS or material == "copper":
                return heat_colour(self._temps["winding"]) if "winding" in self._temps else MATERIALS["copper"][0]
            if material in ("steel", "housing", "housing_dark"):
                return heat_colour(self._temps["frame"]) if "frame" in self._temps else colour
        return colour

    @Property("QVariantMap", notify=coloursChanged)
    def materials(self) -> dict:
        return {k: {"color": self.material_colour(k), "metalness": v[1], "roughness": v[2], "opacity": v[3]}
                for k, v in MATERIALS.items()}

    @Property(str, notify=selectedChanged)
    def selected(self) -> str:
        return self._selected

    @Slot(str)
    def pick(self, key: str) -> None:
        """Called by QML on a click: the part under the pointer ("" for the background)."""
        self._selected = key if key in self._geoms else ""
        self.selectedChanged.emit()
        self.picked.emit(self._selected)

    @Property(bool, notify=labelsChanged)
    def labelsVisible(self) -> bool:  # noqa: N802 (QML name)
        return self._labels_on

    def set_labels_visible(self, on: bool) -> None:
        self._labels_on = bool(on)
        self.labelsChanged.emit()

    @Property("QVariantList", notify=labelsChanged)
    def labels(self) -> list:
        return self._labels

    # --- playback ------------------------------------------------------------------------------

    def set_angles(self, motor: float, intermediate: float, wheel: float) -> None:
        """Drawn angles, rad (already divided by the display slowdown)."""
        self._angles = {"motor": math.degrees(motor), "intermediate": math.degrees(intermediate),
                        "wheel": math.degrees(wheel)}
        self.anglesChanged.emit()

    @Property(float, notify=anglesChanged)
    def angleMotor(self) -> float:  # noqa: N802 (QML name)
        return self._angles["motor"]

    @Property(float, notify=anglesChanged)
    def angleIntermediate(self) -> float:  # noqa: N802 (QML name)
        return self._angles["intermediate"]

    @Property(float, notify=anglesChanged)
    def angleWheel(self) -> float:  # noqa: N802 (QML name)
        return self._angles["wheel"]

    def set_soc(self, soc: float) -> None:
        self._soc = float(soc)
        self.socChanged.emit()

    @Property(float, notify=socChanged)
    def soc(self) -> float:
        return self._soc

    def set_particles(self, items: list[tuple[np.ndarray, str]]) -> None:
        """Power-flow markers: (position m, colour)."""
        self._particles = [{"pos": _mm(p), "color": c} for p, c in items]
        self.particlesChanged.emit()

    @Property("QVariantList", notify=particlesChanged)
    def particles(self) -> list:
        return self._particles

    # --- theme and camera ------------------------------------------------------------------------

    def set_theme(self, colours: dict[str, str]) -> None:
        self._theme = dict(colours)
        self.themeChanged.emit()

    @Property("QVariantMap", notify=themeChanged)
    def theme(self) -> dict:
        return self._theme

    def request_camera(self, preset: str) -> None:
        self.cameraRequested.emit(preset)
