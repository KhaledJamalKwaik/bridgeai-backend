"""
Creative Suggestions Agent - Proposes additional features and scenarios
"""
import json
import logging
from typing import Dict, List, Any
from app.ai.state import AgentState
from app.ai.memory_service import search_project_memories
from .llm_suggestions_generator import generate_creative_suggestions

logger = logging.getLogger(__name__)


def suggestions_node(state: AgentState) -> AgentState:
    """
    Creative Suggestions Agent that analyzes project context and proposes:
    - Additional features that complement existing requirements
    - Alternative scenarios and use cases
    - Integration possibilities
    - Enhancement opportunities
    
    Args:
        state: Current agent state with project context
        
    Returns:
        Updated state with creative suggestions
    """
    try:
        project_id = state.get("project_id")
        db = state.get("db")
        user_input = state.get("user_input", "")
        
        if not project_id or not db:
            logger.warning("Missing project_id or db session for suggestions")
            state["suggestions"] = []
            return state
        
        # Gather project context from memory
        project_context = _gather_project_context(db, project_id, user_input)
        
        # Generate creative suggestions
        suggestions = generate_creative_suggestions(
            project_context=project_context,
            current_input=user_input
        )
        
        # Store suggestions in state
        state["suggestions"] = suggestions
        state["suggestions_generated"] = True
        
        # Format output for user
        if suggestions:
            response = "Here are some suggestions based on your project:\n\n"
            for i, suggestion in enumerate(suggestions, 1):
                category = suggestion.get('category', '').replace('_', ' ').title()
                title = suggestion.get('title', 'Suggestion')
                description = suggestion.get('description', '')
                value = suggestion.get('value_proposition', '')
                complexity = suggestion.get('complexity', 'Medium')
                
                response += f"{i}. **{title}** ({category})\n"
                response += f"   {description}\n"
                if value:
                    response += f"   💡 *Value: {value}*\n"
                response += f"   ⚙️ Complexity: {complexity}\n\n"
            state["output"] = response
        else:
            state["output"] = "I don't have any additional suggestions at this time."
        
        logger.info(f"Generated {len(suggestions)} creative suggestions for project {project_id}")
        return state
        
    except Exception as e:
        logger.error(f"Suggestions node failed: {str(e)}")
        state["suggestions"] = []
        state["suggestions_error"] = str(e)
        return state


def _gather_project_context(db, project_id: int, current_input: str) -> Dict[str, Any]:
    """
    Gather comprehensive project context for suggestion generation
    
    Args:
        db: Database session
        project_id: Project ID
        current_input: Current user input
        
    Returns:
        Project context dictionary
    """
    context = {
        "project_id": project_id,
        "current_input": current_input,
        "existing_requirements": [],
        "features": [],
        "use_cases": [],
        "technical_details": []
    }
    
    try:
        # Search for existing CRS documents
        crs_memories = search_project_memories(
            db=db,
            project_id=project_id,
            query="requirements specification functional non-functional",
            limit=10,
            similarity_threshold=0.2
        )
        
        # Search for feature-related memories
        feature_memories = search_project_memories(
            db=db,
            project_id=project_id,
            query="feature functionality capability module component",
            limit=10,
            similarity_threshold=0.2
        )
        
        # Search for use case memories
        usecase_memories = search_project_memories(
            db=db,
            project_id=project_id,
            query="use case scenario workflow process user story",
            limit=10,
            similarity_threshold=0.2
        )
        
        # Categorize memories
        context["existing_requirements"] = [m["text"] for m in crs_memories]
        context["features"] = [m["text"] for m in feature_memories]
        context["use_cases"] = [m["text"] for m in usecase_memories]
        
        # Get technical context
        tech_memories = search_project_memories(
            db=db,
            project_id=project_id,
            query="technology stack architecture database API integration",
            limit=5,
            similarity_threshold=0.3
        )
        context["technical_details"] = [m["text"] for m in tech_memories]
        
    except Exception as e:
        logger.error(f"Failed to gather project context: {str(e)}")
    
    return context


def should_generate_suggestions(state: AgentState) -> bool:
    """
    Determine if suggestions should be generated based on state
    
    Args:
        state: Current agent state
        
    Returns:
        True if suggestions should be generated
    """
    # Generate suggestions if:
    # 1. User explicitly requests suggestions
    # 2. CRS is complete and we want to propose enhancements
    # 3. Template filling is done and we can suggest additional features
    
    user_input = state.get("user_input", "").lower()
    crs_complete = state.get("crs_is_complete", False)
    
    suggestion_keywords = [
        "suggest", "recommend", "additional", "more features", 
        "what else", "enhance", "improve", "extend", "expand"
    ]
    
    return (
        any(keyword in user_input for keyword in suggestion_keywords) or
        crs_complete
    )