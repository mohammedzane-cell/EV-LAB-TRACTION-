"""Screenshots of tab 9 · Labo 3D after the demonstration chain (identification → envelope → map → cycle →
temperatures), in both themes, for docs/images/lab3d/.

Needs a display with a 3D graphics API; headless Linux:

    xvfb-run -a -s "-screen 0 1920x1200x24" env QT_QPA_PLATFORM=xcb QSG_RHI_BACKEND=opengl \
        python tools/capture_lab3d.py --out docs/images/lab3d

Prints the numbers shown in the panel (JSON) so the documentation quotes them exactly.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

SIZE = (1600, 950)


def capture(out: Path, theme_name: str) -> dict:
    from PySide6.QtCore import QEventLoop, QSettings, QTimer
    from PySide6.QtWidgets import QApplication

    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp(prefix="evlab_3d_"))
    app = QApplication.instance() or QApplication(sys.argv)
    from evlab.gui import main_window as mw

    def pump(ms: int = 400) -> None:
        t = time.time()
        while (time.time() - t) * 1000 < ms:
            app.processEvents()
            time.sleep(0.01)

    def wait(signal, action=None, timeout: float = 600.0):
        loop, box = QEventLoop(), {}

        def got(*args):
            box["args"] = args
            loop.quit()

        signal.connect(got)
        if action is not None:
            action()
        QTimer.singleShot(int(timeout * 1000), loop.quit)
        if "args" not in box:
            loop.exec()
        signal.disconnect(got)
        if "args" not in box:
            raise RuntimeError(f"timeout waiting for {signal}")
        pump()
        return box["args"]

    out.mkdir(parents=True, exist_ok=True)
    w = mw.MainWindow(theme_name=theme_name)
    w.resize(*SIZE)
    w.show()
    pump(800)
    if w.tabs.widget(1).envelope is None:
        wait(w.tabs.widget(1).envelope_done, timeout=120)
    t1 = w.tabs.widget(0)
    t1.load_demo()
    pump()
    t1.radios["both"].setChecked(True)
    wait(t1.identification_done, t1.identify)
    w.tabs.setCurrentIndex(1)
    pump(1500)
    t3 = w.tabs.widget(2)
    if t3.stale:
        wait(t3.map_done, lambda: w.tabs.setCurrentIndex(2))
    wait(w.tabs.widget(3).simulation_done, lambda: w.tabs.setCurrentIndex(3))
    wait(w.tabs.widget(4).thermal_done, lambda: w.tabs.setCurrentIndex(4))
    lab = w.tabs.widget(mw.LAB3D_INDEX)
    w.tabs.setCurrentIndex(mw.LAB3D_INDEX)
    pump(2500)
    res = w.tabs.widget(3).result[1]
    k = int(max(range(len(res.p_shaft)), key=lambda i: res.p_shaft[i]))  # strongest traction instant
    t_trac = float(w.tabs.widget(3).result[2].t[k])
    k_reg = int(min(range(len(res.p_shaft)), key=lambda i: res.p_shaft[i]))  # strongest regeneration
    t_reg = float(w.tabs.widget(3).result[2].t[k_reg])
    nums: dict = {"render_ok": lab.render_ok, "t_traction": t_trac, "t_regen": t_reg}
    suffix = "" if theme_name == "dark" else "_clair"

    def shot(name: str) -> None:
        pump(1200)
        w.grab().save(str(out / f"{name}{suffix}.png"))

    lab.seek(t_trac)
    shot("09a_moteur_coupe")
    nums["frame_traction"] = lab.lbl_frame.text()
    nums["scene_note"] = lab.lbl_scene.text()
    lab.chk_labels.setChecked(False)
    lab.slider_explode.setValue(100)
    lab.bridge.request_camera("side")
    shot("09b_moteur_eclate")
    lab.slider_explode.setValue(0)
    lab.bridge.request_camera("iso")
    lab.chk_labels.setChecked(True)
    lab.combo_colours.setCurrentIndex(2)
    lab.select("winding_A")
    shot("09c_moteur_temperatures")
    nums["selection_winding_A"] = lab.lbl_selected.text()
    nums["scale"] = lab.lbl_scale.text()
    lab.combo_colours.setCurrentIndex(0)
    lab.select("")
    lab.combo_scene.setCurrentIndex(1)
    lab.seek(t_trac)
    lab.play()
    pump(1500)
    lab.pause()
    lab.seek(t_trac)
    shot("09d_chaine_traction")
    nums["frame_traction_powertrain"] = lab.lbl_frame.text()
    lab.seek(t_reg)
    lab.play()
    pump(1500)
    lab.pause()
    lab.seek(t_reg)
    shot("09e_chaine_recuperation")
    nums["frame_regen"] = lab.lbl_frame.text()
    nums["playback_note"] = lab.lbl_playback_note.text()
    w.close()
    return nums


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("docs/images/lab3d"))
    ap.add_argument("--theme", choices=("dark", "light", "both"), default="both")
    args = ap.parse_args()
    themes = ("dark", "light") if args.theme == "both" else (args.theme,)
    print(json.dumps({t: capture(args.out, t) for t in themes}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
