"""Delivery layer: composition root, HTTP surface and jobs.

The app wires concrete adapters to ports and owns no domain rules. In Phase 1 it
exposes health and readiness only; extraction endpoints arrive with the serving
work package (WP8) once there is a pipeline to serve.
"""

from app.main import app, run

__all__ = ["app", "run"]
