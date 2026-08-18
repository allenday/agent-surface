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
from agent_surface.references import (
    DuplicateReferenceCodec,
    InvalidReference,
    MissingReferenceCodec,
    ReferenceCodec,
    ReferenceRegistry,
    ReferenceValue,
    encode_scalar,
)
from agent_surface.rendering import RenderOptions, render, render_envelope
from agent_surface.skills import bundled_skill_path

__all__ = [
    "Action",
    "ActionCollection",
    "App",
    "BoundedCollection",
    "CommandView",
    "DuplicateReferenceCodec",
    "ErrorEnvelope",
    "ErrorInfo",
    "InvalidReference",
    "MissingReferenceCodec",
    "OperationError",
    "OutputBudget",
    "OutputBudgetExceeded",
    "ParsedCommand",
    "ReferenceCodec",
    "ReferenceRegistry",
    "ReferenceValue",
    "RenderOptions",
    "SuccessEnvelope",
    "__version__",
    "bundled_skill_path",
    "encode_scalar",
    "render",
    "render_envelope",
]
