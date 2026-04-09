"""Expose all models for easy importing.

Importing models here ensures SQLAlchemy's Base.metadata picks them all up.
"""
from src.models.auth import ApiKey, User
from src.models.base import BaseModel
from src.models.brand import Brand
from src.models.broker import BrokerConfig
from src.models.invocation_log import InvocationLog
from src.models.integration import Integration
from src.models.conversation import Conversation
from src.models.message import Message
from src.models.registry import Agent, AgentCredential, AgentRating
from src.models.task import Task
from src.models.halt_code import HaltCode

# Workflow models (from agent-os)
from src.workflow.models.entities import (  # noqa: F401
    ContextEntry,
    ProcessEntry,
    WorkflowDefinition,
    WorkflowExecution,
)

# Network models (communication networks)
from src.network.models.entities import (  # noqa: F401
    CommunicationNetwork,
    NetworkMessage,
    NetworkParticipant,
)

# Economy models (from agent-economy)
from src.economy.models.wallet import Transaction, Wallet  # noqa: F401
from src.economy.models.order import Order, Trade  # noqa: F401
from src.economy.models.credit_purchase import CreditPurchase  # noqa: F401

__all__ = [
    "BaseModel",
    "User",
    "ApiKey",
    "BrokerConfig",
    "Integration",
    "Conversation",
    "Message",
    "Brand",
    "Agent",
    "AgentRating",
    "AgentCredential",
    "InvocationLog",
    "Task",
    "HaltCode",
    # Workflow
    "WorkflowDefinition",
    "WorkflowExecution",
    "ProcessEntry",
    "ContextEntry",
    # Network
    "CommunicationNetwork",
    "NetworkParticipant",
    "NetworkMessage",
    # Economy
    "Wallet",
    "Transaction",
    "Order",
    "Trade",
    "CreditPurchase",
]
