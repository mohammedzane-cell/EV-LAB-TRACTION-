"""Tab "4 · Véhicule & WLTC": Vehicle on the WLTC cycle, Wh/km (core.vehicle).

Thin view: calls core/, draws results, contains no formula. Empty for now.
"""

from __future__ import annotations

from evlab.core.session import Session
from evlab.gui._placeholder import PlaceholderTab

TITLE = "4 · Véhicule & WLTC"


class VehicleTab(PlaceholderTab):
    """Placeholder until the module is implemented."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, TITLE)
