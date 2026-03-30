import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExecutionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ProcessStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class StepType(str, enum.Enum):
    agent = "agent"
    skill = "skill"
    condition = "condition"
    sub_workflow = "sub_workflow"
    plan = "plan"


# ---------------------------------------------------------------------------
# Workflow Definition
# ---------------------------------------------------------------------------


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    triggers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recovery: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    executions: Mapped[list["WorkflowExecution"]] = relationship(back_populates="workflow")


# ---------------------------------------------------------------------------
# Workflow Execution
# ---------------------------------------------------------------------------


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="execution_status"),
        nullable=False,
        default=ExecutionStatus.pending,
    )
    trigger_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    parent_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow: Mapped["WorkflowDefinition"] = relationship(back_populates="executions")
    process_entries: Mapped[list["ProcessEntry"]] = relationship(back_populates="execution")
    parent_execution: Mapped["WorkflowExecution | None"] = relationship(
        remote_side="WorkflowExecution.id",
    )


# ---------------------------------------------------------------------------
# Process Entry (per-step execution)
# ---------------------------------------------------------------------------


class ProcessEntry(Base):
    __tablename__ = "process_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[StepType] = mapped_column(
        Enum(StepType, name="step_type"), nullable=False
    )
    target_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[ProcessStatus] = mapped_column(
        Enum(ProcessStatus, name="process_status"),
        nullable=False,
        default=ProcessStatus.pending,
    )
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)

    execution: Mapped["WorkflowExecution"] = relationship(back_populates="process_entries")


# ---------------------------------------------------------------------------
# Context Entry (context bus persistence / audit trail)
# ---------------------------------------------------------------------------


class ContextEntry(Base):
    __tablename__ = "context_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    context_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    written_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    written_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
