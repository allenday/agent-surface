"""Stable transport-neutral response contracts."""

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """Base configuration shared by public contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ParsedCommand(ContractModel):
    """Shallow parser-truth view of a CLI invocation."""

    path: tuple[str, ...]
    args: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    flags: tuple[str, ...] = ()


class ResolvedCommand(ContractModel):
    """Optional environment resolution details."""

    executable: str
    version: str
    cwd: str
    config: str | None = None


class CommandView(ContractModel):
    """Raw and parsed views of the command that ran."""

    raw: tuple[str, ...]
    parsed: ParsedCommand
    resolved: ResolvedCommand | None = None


class Action(ContractModel):
    """A concrete or parameterized affordance."""

    rel: str
    description: str = ""
    command: tuple[str, ...] | None = None
    command_template: tuple[str, ...] | None = None
    operation: str | None = None
    target: dict[str, Any] | None = None
    bound: dict[str, Any] = Field(default_factory=dict)
    slots: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_command_shape(self) -> "Action":
        if (self.command is None) == (self.command_template is None):
            raise ValueError("exactly one of command or command_template is required")
        return self


class ActionCollection(ContractModel):
    """A bounded frontier of contextually relevant actions."""

    items: tuple[Action, ...] = ()
    total: int = Field(default=0, ge=0)
    returned: int = Field(default=0, ge=0)
    truncated: bool = False
    discover: Action | None = None

    @model_validator(mode="after")
    def validate_collection(self) -> "ActionCollection":
        if self.returned != len(self.items):
            raise ValueError("returned must equal the number of items")
        if self.total < self.returned:
            raise ValueError("total must be greater than or equal to returned")
        if self.truncated and self.discover is None:
            raise ValueError("discover is required when actions are truncated")
        return self


class ErrorDetail(ContractModel):
    """One machine-readable error location."""

    path: tuple[str | int, ...] = ()
    code: str | None = None
    message: str | None = None
    value: Any = None


class ErrorInfo(ContractModel):
    """Stable error identity and repair context."""

    code: str
    message: str
    details: tuple[ErrorDetail, ...] = ()
    retryable: bool = False


ResultT = TypeVar("ResultT")


class SuccessEnvelope(ContractModel, Generic[ResultT]):
    """Successful agent-facing invocation result."""

    schema_version: Literal["1"] = "1"
    ok: Literal[True] = True
    command: CommandView
    result: ResultT
    next_actions: ActionCollection = Field(default_factory=ActionCollection)


class ErrorEnvelope(ContractModel):
    """Repair-oriented invocation failure."""

    schema_version: Literal["1"] = "1"
    ok: Literal[False] = False
    command: CommandView
    error: ErrorInfo
    fix: str | None = None
    next_actions: ActionCollection = Field(default_factory=ActionCollection)


__all__ = [
    "Action",
    "ActionCollection",
    "CommandView",
    "ErrorDetail",
    "ErrorEnvelope",
    "ErrorInfo",
    "ParsedCommand",
    "ResolvedCommand",
    "SuccessEnvelope",
]
