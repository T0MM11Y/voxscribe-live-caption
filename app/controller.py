"""Application controller entry point.

The current desktop controller is implemented by VoxScribeApp while the app is
being migrated from the legacy flat module layout.
"""

from app.ui.main_window import VoxScribeApp


AppController = VoxScribeApp
