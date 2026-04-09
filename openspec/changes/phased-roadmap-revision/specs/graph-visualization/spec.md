## ADDED Requirements

### Requirement: Interactive graph visualization
The system SHALL provide a web-based interactive graph visualization at `/graph` that renders entities, relations, and rules as a navigable force-directed graph.

#### Scenario: View entity relationship graph
- **WHEN** a user navigates to `/graph` in a browser
- **THEN** the page renders a D3.js force-directed graph showing all approved entities as nodes and relations as edges, with color coding by domain

#### Scenario: Filter by domain
- **WHEN** the user selects a domain filter (e.g., "排班") in the graph view
- **THEN** only entities and relations in that domain are displayed, with connected entities from other domains shown as faded nodes

### Requirement: Entity detail panel
The system SHALL show a detail panel when a graph node is clicked, displaying the entity's attributes, related rules, and connected entities.

#### Scenario: Click entity to see details
- **WHEN** the user clicks on the "ICU" entity node
- **THEN** a side panel shows ICU's attributes (床位:12, 级别:三级), related rules (ICU必须24小时值班), and connected entities (医生, 科室)

### Requirement: Rule severity visualization
The system SHALL render rule nodes with visual indicators of severity: critical rules in red, warning in yellow, info in blue.

#### Scenario: Visual severity distinction
- **WHEN** the graph renders rules alongside entities
- **THEN** critical rules appear as red-bordered nodes, warning rules as yellow-bordered, and info rules as blue-bordered, with rule text visible on hover

### Requirement: Graph search
The system SHALL provide a search bar in the graph view that highlights matching nodes and dims non-matching ones.

#### Scenario: Search highlights matching nodes
- **WHEN** the user types "ICU" in the graph search bar
- **THEN** nodes matching "ICU" are highlighted and brought to center, non-matching nodes are dimmed but remain visible
