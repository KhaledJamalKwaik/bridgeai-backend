"""
LLM-powered Creative Suggestions Generator
"""
import json
import logging
from typing import Dict, List, Any
from openai import OpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
# Initialize OpenAI client with Groq configuration
client = OpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)


def generate_creative_suggestions(
    project_context: Dict[str, Any],
    current_input: str
) -> List[Dict[str, Any]]:
    """
    Generate creative suggestions for additional features and scenarios
    
    Args:
        project_context: Comprehensive project context
        current_input: Current user input
        
    Returns:
        List of creative suggestions
    """
    try:
        prompt = _build_suggestions_prompt(project_context, current_input)
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a creative software analyst who excels at identifying opportunities for additional features, alternative scenarios, and system enhancements. You think beyond the obvious requirements to propose valuable additions."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,  # Higher creativity
            max_tokens=2000
        )
        
        suggestions_text = response.choices[0].message.content
        suggestions = _parse_suggestions_response(suggestions_text)
        
        logger.info(f"Generated {len(suggestions)} creative suggestions")
        return suggestions
        
    except Exception as e:
        logger.error(f"Failed to generate suggestions: {str(e)}")
        return []


def _build_suggestions_prompt(project_context: Dict[str, Any], current_input: str) -> str:
    """Build the prompt for creative suggestions generation"""
    
    existing_reqs = "\n".join(project_context.get("existing_requirements", [])[:5])
    features = "\n".join(project_context.get("features", [])[:5])
    use_cases = "\n".join(project_context.get("use_cases", [])[:5])
    tech_details = "\n".join(project_context.get("technical_details", [])[:3])
    
    return f"""
Based on the following project context, generate creative suggestions for additional features, scenarios, and enhancements:

CURRENT USER INPUT:
{current_input}

EXISTING REQUIREMENTS:
{existing_reqs or "No existing requirements found"}

CURRENT FEATURES:
{features or "No features documented yet"}

USE CASES:
{use_cases or "No use cases documented yet"}

TECHNICAL CONTEXT:
{tech_details or "No technical details available"}

Please provide creative suggestions in the following categories:

1. ADDITIONAL FEATURES - New functionality that would complement existing requirements
2. ALTERNATIVE SCENARIOS - Different ways users might interact with the system
3. INTEGRATION OPPORTUNITIES - Ways to connect with other systems or services
4. ENHANCEMENT IDEAS - Improvements to existing functionality
5. FUTURE CONSIDERATIONS - Features for potential future phases

For each suggestion, provide:
- Category (from above)
- Title (brief, descriptive)
- Description (2-3 sentences)
- Value proposition (why this would be beneficial)
- Implementation complexity (Low/Medium/High)

Format your response as a JSON array of suggestion objects:
[
  {{
    "category": "ADDITIONAL_FEATURES",
    "title": "Feature Title",
    "description": "Detailed description of the feature...",
    "value_proposition": "Why this feature would be valuable...",
    "complexity": "Medium",
    "priority": "High"
  }}
]

Generate 5-8 diverse, creative suggestions that go beyond the obvious requirements.
"""


def _parse_suggestions_response(response_text: str) -> List[Dict[str, Any]]:
    """Parse the LLM response into structured suggestions"""
    try:
        # Try to extract JSON from the response
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1
        
        if start_idx != -1 and end_idx != 0:
            json_text = response_text[start_idx:end_idx]
            suggestions = json.loads(json_text)
            
            # Validate and clean suggestions
            validated_suggestions = []
            for suggestion in suggestions:
                if _validate_suggestion(suggestion):
                    validated_suggestions.append(suggestion)
            
            return validated_suggestions
        else:
            # Fallback: parse as text
            return _parse_text_suggestions(response_text)
            
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON response, attempting text parsing")
        return _parse_text_suggestions(response_text)
    except Exception as e:
        logger.error(f"Failed to parse suggestions response: {str(e)}")
        return []


def _validate_suggestion(suggestion: Dict[str, Any]) -> bool:
    """Validate that a suggestion has required fields"""
    required_fields = ["category", "title", "description", "value_proposition"]
    return all(field in suggestion and suggestion[field] for field in required_fields)


def _parse_text_suggestions(text: str) -> List[Dict[str, Any]]:
    """Fallback parser for non-JSON responses"""
    suggestions = []
    
    # Simple text parsing logic
    lines = text.split('\n')
    current_suggestion = {}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('Title:') or line.startswith('**Title'):
            if current_suggestion:
                suggestions.append(current_suggestion)
            current_suggestion = {
                "title": line.split(':', 1)[1].strip().replace('**', ''),
                "category": "ADDITIONAL_FEATURES",
                "complexity": "Medium",
                "priority": "Medium"
            }
        elif line.startswith('Description:') and current_suggestion:
            current_suggestion["description"] = line.split(':', 1)[1].strip()
        elif line.startswith('Value:') and current_suggestion:
            current_suggestion["value_proposition"] = line.split(':', 1)[1].strip()
    
    if current_suggestion:
        suggestions.append(current_suggestion)
    
    return suggestions[:8]  # Limit to 8 suggestions