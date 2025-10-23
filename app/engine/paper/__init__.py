"""
Paper trading module.

Provides paper broker with same API as live router for realistic simulation.
"""

from .broker import PaperBroker, PaperPosition, create_paper_broker_app

__all__ = ["PaperBroker", "PaperPosition", "create_paper_broker_app"]
