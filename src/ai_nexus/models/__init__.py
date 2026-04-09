"""AI Nexus Pydantic models.

This package provides Pydantic models for the AI Nexus knowledge graph system.
Models are organized by domain: entities, relations, rules, and audit logging.
"""

from .audit import (
    AuditLog,
    HookRequest,
    KnowledgeCandidate,
)
from .entity import Entity, EntityBase, EntityCreate, EntityUpdate
from .relation import Relation, RelationBase, RelationCreate
from .rule import Rule, RuleBase, RuleCreate, RuleUpdate

__all__ = [
    # Entity models
    "Entity",
    "EntityBase",
    "EntityCreate",
    "EntityUpdate",
    # Relation models
    "Relation",
    "RelationBase",
    "RelationCreate",
    # Rule models
    "Rule",
    "RuleBase",
    "RuleCreate",
    "RuleUpdate",
    # Audit models
    "AuditLog",
    "KnowledgeCandidate",
    "HookRequest",
]
