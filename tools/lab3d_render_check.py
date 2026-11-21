"""Check that the 3D laboratory (tab 9) really renders and responds: pixels drawn, picking by a mouse click,
exploded view, rotor rotation, hidden components, powertrain scene.

Needs a display with a 3D graphics API (any desktop: Direct3D on Windows, Metal on macOS, OpenGL/Vulkan on
Linux). Headless Linux (CI, containers):

    xvfb-run -a -s "-screen 0 1280x1024x24" env QT_QPA_PLATFORM=xcb QSG_RHI_BACKEND=opengl \
        python tools/lab3d_render_check.py --out docs/images/lab3d_check

Prints a JSON report; the exit code is 0 when every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path


def run(out: Path | None) -> dict:
    from PySide6.QtCore import QPoint, QSettings, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp(prefix="evlab_3d_"))
    app = QApplication.instance() or QApplication(sys.argv)
    from evlab.core.session import Session
    from evlab.gui import theme
    from evlab.gui.tab_lab3d import Lab3DTab

    theme.apply(app, "dark")

    def pump(ms: int = 1200) -> None:
        t = time.time()
        while (time.time() - t) * 1000 < ms:
            app.processEvents()
            time.sleep(0.01)

    tab = Lab3DTab(Session())
    tab.resize(1200, 760)
    tab.show()
    pump(1500)
    view = tab.view
    report: dict = {"platform": QGuiApplication.platformName(), "render_ok": tab.render_ok}

    def image(name: str):
        pump()
        img = view.grabFramebuffer()
        if out is not None:
            out.mkdir(parents=True, exist_ok=True)
            img.save(str(out / f"{name}.png"))
        return img

    def drawn(img) -> float:
        """Fraction of the pixels that differ from the background colour."""
        bg = img.pixelColor(2, 2)
        n = hit = 0
        for y in range(0, img.height(), 4):
            for x in range(0, img.width(), 4):
                n += 1
                c = img.pixelColor(x, y)
                hit += abs(c.red() - bg.red()) + abs(c.green() - bg.green()) + abs(c.blue() - bg.blue()) > 24
        return hit / n

    def changed(a, b) -> float:
        n = hit = 0
        for y in range(0, a.height(), 4):
            for x in range(0, a.width(), 4):
                n += 1
                ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
                hit += abs(ca.red() - cb.red()) + abs(ca.green() - cb.green()) + abs(ca.blue() - cb.blue()) > 24
        return hit / n

    motor_keys = set(tab.parts)
    base = image("1_moteur_coupe")
    report["motor_drawn"] = drawn(base)
    centre = QPoint(view.width() // 2, view.height() // 2)
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
    pump(600)
    report["picked_at_centre"] = tab.bridge.selected
    report["selection_text"] = tab.lbl_selected.text()
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))
    pump(600)
    report["picked_background"] = tab.bridge.selected
    tab.select("")
    tab.chk_labels.setChecked(False)
    plain = image("2_moteur_sans_etiquettes")
    tab.bridge.set_angles(0.6, 0.0, 0.0)  # rotor turned by 0,6 rad
    turned = image("3_rotor_tourne")
    report["rotation_changes_image"] = changed(plain, turned)
    tab.bridge.set_angles(0.0, 0.0, 0.0)
    tab.slider_explode.setValue(100)
    exploded = image("4_vue_eclatee")
    report["explode_changes_image"] = changed(plain, exploded)
    tab.slider_explode.setValue(0)
    tab.group_checks["housing"].setChecked(False)
    no_housing = image("5_sans_carter")
    report["hiding_changes_image"] = changed(plain, no_housing)
    tab.group_checks["housing"].setChecked(True)
    tab.combo_scene.setCurrentIndex(1)
    report["powertrain_drawn"] = drawn(image("6_chaine_de_traction"))
    report["checks"] = {
        "renders": bool(tab.render_ok),
        "motor_drawn": report["motor_drawn"] > 0.05,
        "click_picks_a_part": report["picked_at_centre"] in motor_keys,
        "click_on_background_clears": report["picked_background"] == "",
        "rotation_visible": report["rotation_changes_image"] > 0.001,
        "explode_visible": report["explode_changes_image"] > 0.02,
        "hiding_visible": report["hiding_changes_image"] > 0.02,
        "powertrain_drawn": report["powertrain_drawn"] > 0.05,
    }
    report["ok"] = all(report["checks"].values())
    tab.close()
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="folder for the PNG images")
    rep = run(ap.parse_args().out)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    sys.exit(0 if rep["ok"] else 1)


if __name__ == "__main__":
    main()
