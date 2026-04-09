"""AI Nexus Pydantic models.

This package provides Pydantic models for the AI Nexus knowledge graph system.
Models are organized by domain: entities, relations, rules, audit logging, and extraction.
"""

from .audit import (
    AuditLog,
    HookRequest,
    KnowledgeCandidate,
)
from .entity import Entity, EntityBase, EntityCreate, EntityUpdate
from .extraction import (
    ExtractedEntity,
    ExtractedItem,
    ExtractedRelation,
    ExtractedRule,
    ExtractionResult,
)
from .relation import Relation, RelationBase, RelationCreate
from .rule import Rule, RuleBase, RuleCreate, RuleUpdate
from .violation import (
    ViolationEvent,
    ViolationEventCreate,
    ViolationEventUpdate,
    ViolationStats,
)

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
    # Extraction models
    "ExtractedItem",
    "ExtractedEntity",
    "ExtractedRelation",
    "ExtractedRule",
    "ExtractionResult",
    # Violation models
    "ViolationEvent",
    "ViolationEventCreate",
    "ViolationEventUpdate",
    "ViolationStats",
]
