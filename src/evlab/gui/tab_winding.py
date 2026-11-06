"""Tab "6 · Bobinage": Winding factors, MMF, rotating field (core.winding).

Thin view: calls core/, draws results, contains no formula. Empty for now.
"""

from __future__ import annotations

from evlab.core.session import Session
from evlab.gui._placeholder import PlaceholderTab

TITLE = "6 · Bobinage"


class WindingTab(PlaceholderTab):
    """Placeholder until the module is implemented."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, TITLE)
