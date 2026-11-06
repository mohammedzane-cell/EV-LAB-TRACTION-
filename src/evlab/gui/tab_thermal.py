"""Tab "5 · Thermique": Two-node thermal model and insulation life (core.thermal).

Thin view: calls core/, draws results, contains no formula. Empty for now.
"""

from __future__ import annotations

from evlab.core.session import Session
from evlab.gui._placeholder import PlaceholderTab

TITLE = "5 · Thermique"


class ThermalTab(PlaceholderTab):
    """Placeholder until the module is implemented."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, TITLE)
