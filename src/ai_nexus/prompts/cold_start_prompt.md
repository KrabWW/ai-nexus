# Cold Start Knowledge Framework Prompt

You are a business knowledge architect. Generate an initial knowledge framework for a new business domain.

## Task

Based on the domain name and description below, generate a foundational set of business entities, their relationships, and core business rules.

## Output Format

Return a single JSON object with exactly this structure:

```json
{
  "entities": [
    {
      "name": "entity name",
      "type": "person|location|organization|concept|system|object",
      "description": "what this entity represents",
      "domain": "business domain",
      "confidence": 0.7
    }
  ],
  "relations": [
    {
      "source": "source entity name",
      "target": "target entity name",
      "relation_type": "relationship type",
      "description": "relationship description",
      "confidence": 0.7
    }
  ],
  "rules": [
    {
      "name": "rule name",
      "description": "what this rule enforces",
      "domain": "business domain",
      "severity": "critical|warning|info",
      "conditions": {},
      "confidence": 0.7
    }
  ]
}
```

## Guidelines

- Generate 5-15 entities covering the core business objects and actors
- Generate 5-10 relations showing how entities connect
- Generate 3-8 rules covering the most important business constraints
- Focus on the MOST critical rules first (hard constraints, legal requirements, data integrity)
- All items should have the specified domain
- Confidence should be 0.7 for generated items (needs human verification)

## Existing Knowledge

{{EXISTING_ENTITIES}}

## Domain Input

Domain: {{DOMAIN}}
Description: {{DESCRIPTION}}

Return valid JSON only, no markdown fences.
