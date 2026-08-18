"""Typed application surfaces for agents."""

__version__ = "0.1.0"

from agent_surface.app import App
from agent_surface.budgets import BoundedCollection, OutputBudget, OutputBudgetExceeded
from agent_surface.contracts import (
    Action,
    ActionCollection,
    CommandView,
    ErrorEnvelope,
    ErrorInfo,
    ParsedCommand,
    SuccessEnvelope,
)
from agent_surface.operations import OperationError
from agent_surface.skills import bundled_skill_path

__all__ = [
    "Action",
    "ActionCollection",
    "App",
    "BoundedCollection",
    "CommandView",
    "ErrorEnvelope",
    "ErrorInfo",
    "OperationError",
    "OutputBudget",
    "OutputBudgetExceeded",
    "ParsedCommand",
    "SuccessEnvelope",
    "__version__",
    "bundled_skill_path",
]
