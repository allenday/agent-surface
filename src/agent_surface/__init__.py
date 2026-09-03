"""Typed application surfaces for agents."""

__version__ = "0.2.1"

from agent_surface.actions import (
    ActionCandidate,
    ActionCatalog,
    ActionCompiler,
    ActionDefinitionError,
    ActionPolicy,
    ActionPublisher,
    ActionSlotPlan,
    AllowActions,
    DenyAllActions,
    InvalidActionCursor,
    action,
)
from agent_surface.app import App
from agent_surface.budgets import BoundedCollection, OutputBudget, OutputBudgetExceeded
from agent_surface.composition import ComposedApp, CompositionError, MountedOperation
from agent_surface.contracts import (
    Action,
    ActionCollection,
    CommandView,
    ErrorEnvelope,
    ErrorInfo,
    ErrorOutcome,
    ParsedCommand,
    SuccessEnvelope,
    SuccessOutcome,
)
from agent_surface.envelopes import CanonicalEnvelopeRenderer, Invocation
from agent_surface.manifest import (
    ManifestCollision,
    ManifestMismatch,
    generate_manifest,
    installed_manifests,
    load_manifest,
    manifest_for,
    validate_manifests,
    verify_manifest,
    write_manifest,
)
from agent_surface.operations import OperationError, OperationOutcome
from agent_surface.outcomes import ActionProvider, NoActions, error_outcome, success_outcome
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
    "ActionCandidate",
    "ActionCatalog",
    "ActionCollection",
    "ActionCompiler",
    "ActionDefinitionError",
    "ActionPolicy",
    "ActionPublisher",
    "ActionProvider",
    "ActionSlotPlan",
    "AllowActions",
    "App",
    "BoundedCollection",
    "CanonicalEnvelopeRenderer",
    "CommandView",
    "ComposedApp",
    "CompositionError",
    "DuplicateReferenceCodec",
    "DenyAllActions",
    "ErrorEnvelope",
    "ErrorInfo",
    "ErrorOutcome",
    "InvalidReference",
    "InvalidActionCursor",
    "Invocation",
    "ManifestMismatch",
    "ManifestCollision",
    "generate_manifest",
    "installed_manifests",
    "MissingReferenceCodec",
    "MountedOperation",
    "OperationError",
    "OperationOutcome",
    "load_manifest",
    "manifest_for",
    "NoActions",
    "OutputBudget",
    "OutputBudgetExceeded",
    "ParsedCommand",
    "ReferenceCodec",
    "ReferenceRegistry",
    "ReferenceValue",
    "RenderOptions",
    "SuccessEnvelope",
    "SuccessOutcome",
    "__version__",
    "action",
    "bundled_skill_path",
    "encode_scalar",
    "error_outcome",
    "render",
    "render_envelope",
    "verify_manifest",
    "validate_manifests",
    "write_manifest",
    "success_outcome",
]
