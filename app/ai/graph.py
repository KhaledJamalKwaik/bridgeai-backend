# app/ai/graph.py

from langgraph.graph import StateGraph, END
from app.ai.state import AgentState

# Nodes
from app.ai.nodes.clarification import clarification_node, should_request_clarification
from app.ai.nodes.memory_node import memory_node
from app.ai.nodes.template_filler import template_filler_node
from app.ai.nodes.suggestions import suggestions_node
from app.ai.nodes.suggestions.suggestions_node import should_generate_suggestions
from app.ai.nodes.echo_node import echo_node


def create_graph():
    """
    Create the LangGraph workflow with:
    1. Clarification Agent - Detects ambiguities and asks clarifying questions
    2. Template Filler Agent - Maps clarified requirements to CRS template

    Workflow:
    1. User input → Clarification Agent
    2. If clarification is needed → END (return questions to client)
    3. If no clarification needed → Template Filler Agent
    4. Template Filler fills CRS → Memory (store requirement) → END
    """

    # Create graph with AgentState as the shared memory type
    graph = StateGraph(AgentState)

    # ----------------------------
    # REGISTER NODES
    # ----------------------------
    graph.add_node("clarification", clarification_node)
    graph.add_node("memory", memory_node)
    graph.add_node("template_filler", template_filler_node)
    graph.add_node("suggestions", suggestions_node)
    graph.add_node("echo", echo_node)  # placeholder for future agent(s)

    # ----------------------------
    # ENTRY POINT
    # ----------------------------
    graph.set_entry_point("clarification")

    # ----------------------------
    # CONDITIONAL ROUTING LOGIC
    # ----------------------------
    def route_after_clarification(state: AgentState) -> str:
        """
        Route after clarification based on:
        1. If clarification needed → END
        2. If suggestions requested → suggestions
        3. Otherwise → template_filler
        """
        # Check if user is asking for suggestions FIRST
        user_input = state.get("user_input", "").lower()
        suggestion_keywords = [
            "suggest", "suggestion", "recommend", "additional", "more features",
            "what else", "enhance", "improve", "extend", "expand", "ideas"
        ]
        
        if any(keyword in user_input for keyword in suggestion_keywords):
            return "suggestions"

        # Then check if clarification is needed
        if should_request_clarification(state):
            return "end"
        # Default: continue to template filler
        return "template_filler"
    
    graph.add_conditional_edges(
        "clarification",
        route_after_clarification,
        {
            "end": END,                      # If clarification needed → stop workflow
            "suggestions": "suggestions",    # If suggestions requested → suggestions
            "template_filler": "template_filler"  # Otherwise continue to template filler
        }
    )

    # ----------------------------
    # TEMPLATE FILLER → MEMORY
    # ----------------------------
    graph.add_edge("template_filler", "memory")

    # ----------------------------
    # MEMORY → SUGGESTIONS (conditional)
    # ----------------------------
    graph.add_conditional_edges(
        "memory",
        should_generate_suggestions,
        {
            True: "suggestions",  # Generate creative suggestions
            False: END            # Skip suggestions and end
        }
    )

    # ----------------------------
    # SUGGESTIONS → END
    # ----------------------------
    graph.add_edge("suggestions", END)

    # ----------------------------
    # COMPILE GRAPH
    # ----------------------------
    return graph.compile()
