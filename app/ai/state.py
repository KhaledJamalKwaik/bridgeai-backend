from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    user_input: str
    output: Optional[str]
    conversation_history: List[str]
    user_id: Optional[int]

    # Clarification Agent fields
    clarification_questions: List[str]
    ambiguities: List[Dict[str, Any]]
    needs_clarification: bool

    clarity_score: int
    quality_summary: str

    extracted_fields: Dict[str, Any]

    # Template Filler Agent fields (CRS)
    crs_content: Optional[str]  # JSON string of filled CRS template
    crs_template: Optional[Dict[str, Any]]  # Dictionary representation of CRS
    crs_pattern: Optional[str]  # CRS pattern selection (iso_iec_ieee_29148, ieee_830, or babok)
    summary_points: Optional[List[str]]  # Key summary points from CRS
    crs_is_complete: bool  # Whether CRS has sufficient information
    crs_document_id: Optional[int]  # Database ID of the persisted CRS document
    crs_version: Optional[int]  # Version number of the CRS document

    # Suggestions Agent fields
    suggestions: Optional[List[Dict[str, Any]]]  # Generated creative suggestions
    suggestions_generated: bool  # Whether suggestions have been generated
    suggestions_error: Optional[str]  # Error message if suggestions failed
    suggestion_trigger: Optional[str]  # Trigger source: "keyword", "crs_complete", or "manual"

    # Workflow control
    last_node: Optional[str]
    next_action: Optional[str]

    # Memory and context
    project_id: Optional[int]
    db: Optional[Any]  # SQLAlchemy Session for memory queries
    message_id: Optional[int]
    intent: Optional[str]
