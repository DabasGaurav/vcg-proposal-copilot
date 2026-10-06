"""Small JSON schemas for local Ollama structured output."""

REQUIREMENT = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "category": {"type": "string", "enum": ["CONTENT", "PROCEDURAL", "COMMERCIAL", "COMPLIANCE"]},
        "handling": {"type": "string", "enum": ["NEEDS_EVIDENCE", "NEEDS_HUMAN_INPUT", "TEMPLATE_SATISFIABLE", "PROCEDURAL_ONLY", "CAPABILITY_GAP"]},
        "mandatory": {"type": ["boolean", "null"]},
        "extraction_confidence": {"type": "number"},
        "quote": {"type": "string"},
        "section": {"type": "string"},
    },
    "required": ["text", "category", "handling", "mandatory", "extraction_confidence", "quote", "section"],
    "additionalProperties": False,
}

EXTRACT = {
    "type": "object",
    "properties": {
        "client": {"type": ["string", "null"]},
        "problem_statement": {"type": ["string", "null"]},
        "timeline": {"type": ["string", "null"]},
        "scope_items": {"type": "array", "items": {"type": "string"}},
        "deliverables": {"type": "array", "items": {"type": "string"}},
        "evaluation_criteria": {"type": "array", "items": {"type": "string"}},
        "requirements": {"type": "array", "items": REQUIREMENT},
        "procedural_checklist": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["client", "problem_statement", "timeline", "scope_items", "deliverables",
                 "evaluation_criteria", "requirements", "procedural_checklist", "warnings"],
    "additionalProperties": False,
}

PLAN_ITEM = {
    "type": "object",
    "properties": {
        "requirement_id": {"type": "string"},
        "evidence_need": {"type": "string"},
        "target_section": {"type": "string"},
    },
    "required": ["requirement_id", "evidence_need", "target_section"],
    "additionalProperties": False,
}

PLAN = {
    "type": "object",
    "properties": {
        "checklist": {"type": "array", "items": PLAN_ITEM},
        "human_input_requirements": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["checklist", "human_input_requirements"],
    "additionalProperties": False,
}

CLAIM_SPLIT = {"type": "array", "items": {"type": "string"}}

BY_STAGE = {"extract": EXTRACT, "plan": PLAN, "claim_split": CLAIM_SPLIT}
