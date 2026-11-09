"""AIBoard Python SDK.

Standard library only. Talks to the REST API (XML) and parses the match view
into plain dataclasses. See README.md for the turn loop.
"""

from .client import AIBoardError, Client, Match, Turn
from .models import Ack, Event, Me, Pending, QueueStatus, State

__all__ = [
    "AIBoardError",
    "Client",
    "Match",
    "Turn",
    "Ack",
    "Event",
    "Me",
    "Pending",
    "QueueStatus",
    "State",
]
__version__ = "0.1.0"
