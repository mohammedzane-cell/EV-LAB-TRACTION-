"""Tab "1 · Identification": Γ circuit identification from the TP3 / TD5 tests (core.identification).

Thin view: calls core/, draws results, contains no formula. Empty for now.
"""

from __future__ import annotations

from evlab.core.session import Session
from evlab.gui._placeholder import PlaceholderTab

TITLE = "1 · Identification"


class IdentificationTab(PlaceholderTab):
    """Placeholder until the module is implemented."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, TITLE)
