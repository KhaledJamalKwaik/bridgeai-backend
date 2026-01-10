"""
LLM-powered Template Filler for CRS (Customer Requirements Specification) generation.
Maps clarified requirements to a structured CRS template.
"""

import os
import json
import re
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict
import logging

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from app.ai.llm_factory import get_template_filler_llm

logger = logging.getLogger(__name__)


@dataclass
class CRSTemplate:
    """Structured CRS Template for requirement documentation."""
    
    # Project Overview
    project_title: str = ""
    project_description: str = ""
    project_objectives: list = field(default_factory=list)
    
    # Stakeholders
    target_users: list = field(default_factory=list)
    stakeholders: list = field(default_factory=list)
    
    # Functional Requirements
    functional_requirements: list = field(default_factory=list)
    
    # Non-Functional Requirements
    performance_requirements: list = field(default_factory=list)
    security_requirements: list = field(default_factory=list)
    scalability_requirements: list = field(default_factory=list)
    
    # Technical Specifications
    technology_stack: Dict[str, Any] = field(default_factory=dict)
    integrations: list = field(default_factory=list)
    
    # Constraints
    budget_constraints: str = ""
    timeline_constraints: str = ""
    technical_constraints: list = field(default_factory=list)
    
    # Success Criteria
    success_metrics: list = field(default_factory=list)
    acceptance_criteria: list = field(default_factory=list)
    
    # Additional Notes
    assumptions: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    out_of_scope: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def get_summary_points(self) -> list:
        """Generate summary points from the template."""
        points = []
        
        if self.project_title:
            points.append(f"Project: {self.project_title}")
        
        if self.project_objectives:
            points.append(f"Objectives: {len(self.project_objectives)} defined")
        
        if self.functional_requirements:
            points.append(f"Functional Requirements: {len(self.functional_requirements)} items")
        
        if self.target_users:
            points.append(f"Target Users: {', '.join(self.target_users[:3])}")
        
        if self.timeline_constraints:
            points.append(f"Timeline: {self.timeline_constraints}")
        
        if self.budget_constraints:
            points.append(f"Budget: {self.budget_constraints}")
        
        return points


class LLMTemplateFiller:
    """
    LLM-powered CRS template filler using Groq LLM.
    Extracts and maps requirements from conversation to structured CRS format.
    """

    EXTRACTION_PROMPT = """
You are an expert Business Analyst specializing in requirements documentation.

Your task is to ANALYZE and SYNTHESIZE the conversation into a well-structured Customer Requirements Specification (CRS) document.

CRITICAL INSTRUCTIONS:
1. DO NOT copy raw conversation text into the output
2. DO NOT include chat messages or dialogue in any field
3. SYNTHESIZE information from multiple messages into concise, professional statements
4. Each requirement should be a clear, specific, actionable item
5. project_description should be a 2-4 sentence summary, NOT the entire conversation
6. functional_requirements should be structured items with clear titles and descriptions

USER'S LATEST INPUT:
{user_input}

CONVERSATION HISTORY:
{conversation_history}

PREVIOUSLY EXTRACTED FIELDS:
{extracted_fields}

IMPORTANT FORMATTING RULES:
- project_title: Short name (3-6 words max)
- project_description: Concise paragraph (50-150 words) summarizing the project purpose
- project_objectives: List of 3-7 clear goals (one sentence each)
- functional_requirements: Each item MUST have id, title, description, and priority
  - id: Format "FR-001", "FR-002", etc.
  - title: Short descriptive name (3-8 words)
  - description: One clear sentence explaining the requirement
  - priority: "high", "medium", or "low"
- All list items should be concise (one sentence each)
- DO NOT dump entire messages into fields

Return ONLY a valid JSON object (no markdown, no code blocks):
{{
    "project_title": "Short Project Name",
    "project_description": "A concise 2-4 sentence description summarizing what the project aims to achieve and its main purpose.",
    "project_objectives": ["Clear objective 1", "Clear objective 2"],
    "target_users": ["User type 1", "User type 2"],
    "stakeholders": ["Stakeholder 1", "Stakeholder 2"],
    "functional_requirements": [
        {{
            "id": "FR-001",
            "title": "Short Requirement Title",
            "description": "Clear one-sentence description of what this requirement entails.",
            "priority": "high"
        }},
        {{
            "id": "FR-002",
            "title": "Another Requirement",
            "description": "Description of the second requirement.",
            "priority": "medium"
        }}
    ],
    "performance_requirements": ["Concise performance requirement"],
    "security_requirements": ["Concise security requirement"],
    "scalability_requirements": ["Concise scalability requirement"],
    "technology_stack": {{
        "frontend": ["Technology"],
        "backend": ["Technology"],
        "database": ["Database"],
        "other": []
    }},
    "integrations": ["Integration 1"],
    "budget_constraints": "Budget information or 'Not specified'",
    "timeline_constraints": "Timeline information or 'Not specified'",
    "technical_constraints": ["Concise constraint"],
    "success_metrics": ["Clear metric"],
    "acceptance_criteria": ["Clear criteria"],
    "assumptions": ["Clear assumption"],
    "risks": ["Identified risk"],
    "out_of_scope": ["What is excluded"]
}}

If information for a field is not available, use empty strings for text fields and empty arrays for list fields.
REMEMBER: Synthesize and summarize - do not copy raw conversation text!

Return pure JSON now:
"""

    SUMMARY_PROMPT = """
You are a Business Analyst creating a concise summary of a CRS document.

CRS CONTENT:
{crs_content}

Generate a brief, executive-level summary (3-5 bullet points) highlighting:
1. What the project is about
2. Key features/requirements
3. Target audience
4. Any important constraints or timelines

IMPORTANT: Return ONLY a valid JSON object without any markdown formatting.

{{
    "summary_points": ["Point 1", "Point 2", "Point 3"],
    "overall_summary": "One paragraph summary of the entire CRS"
}}

Return pure JSON now:
"""

    def __init__(self):
        """
        Initialize the template filler with Groq LLM.
        
        Model configuration is now centralized in app.core.config.
        To change the model, update the LLM_TEMPLATE_FILLER_MODEL setting in your .env file.
        """
        # Use centralized LLM factory
        self.llm = get_template_filler_llm()

        self.extraction_prompt = ChatPromptTemplate.from_template(self.EXTRACTION_PROMPT)
        self.summary_prompt = ChatPromptTemplate.from_template(self.SUMMARY_PROMPT)

    def _extract_json(self, text: str) -> Dict:
        """Extract JSON from LLM response, handling markdown code blocks."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            
            # Try to find any JSON object in the text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            
            raise ValueError(f"Could not extract valid JSON from response: {text[:200]}...")

    def _call_llm(self, messages) -> str:
        """Call Groq LLM and return the response content."""
        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            raise

    def extract_requirements(
        self, 
        user_input: str, 
        conversation_history: list, 
        extracted_fields: Dict[str, Any]
    ) -> CRSTemplate:
        """
        Extract requirements from conversation and map to CRS template.
        
        Args:
            user_input: Latest user message
            conversation_history: List of previous messages
            extracted_fields: Previously extracted requirement fields
            
        Returns:
            CRSTemplate: Populated CRS template
        """
        try:
            history_text = "\n".join(conversation_history) if conversation_history else "No previous conversation"
            fields_text = json.dumps(extracted_fields, indent=2) if extracted_fields else "No previously extracted fields"

            messages = self.extraction_prompt.format_messages(
                user_input=user_input,
                conversation_history=history_text,
                extracted_fields=fields_text
            )

            raw = self._call_llm(messages)
            logger.info(f"LLM Extraction Response: {raw[:300]}...")

            result = self._extract_json(raw)

            # Map JSON to CRSTemplate
            template = CRSTemplate(
                project_title=result.get("project_title", ""),
                project_description=result.get("project_description", ""),
                project_objectives=result.get("project_objectives", []),
                target_users=result.get("target_users", []),
                stakeholders=result.get("stakeholders", []),
                functional_requirements=result.get("functional_requirements", []),
                performance_requirements=result.get("performance_requirements", []),
                security_requirements=result.get("security_requirements", []),
                scalability_requirements=result.get("scalability_requirements", []),
                technology_stack=result.get("technology_stack", {}),
                integrations=result.get("integrations", []),
                budget_constraints=result.get("budget_constraints", ""),
                timeline_constraints=result.get("timeline_constraints", ""),
                technical_constraints=result.get("technical_constraints", []),
                success_metrics=result.get("success_metrics", []),
                acceptance_criteria=result.get("acceptance_criteria", []),
                assumptions=result.get("assumptions", []),
                risks=result.get("risks", []),
                out_of_scope=result.get("out_of_scope", [])
            )

            return template

        except Exception as e:
            logger.error(f"Requirement extraction failed: {str(e)}")
            # Return empty template on error
            return CRSTemplate()

    def generate_summary(self, crs_template: CRSTemplate) -> Dict[str, Any]:
        """
        Generate a summary of the CRS document.
        
        Args:
            crs_template: Populated CRS template
            
        Returns:
            Dictionary with summary_points and overall_summary
        """
        try:
            crs_content = crs_template.to_json()

            messages = self.summary_prompt.format_messages(
                crs_content=crs_content
            )

            raw = self._call_llm(messages)
            logger.info(f"LLM Summary Response: {raw[:200]}...")

            result = self._extract_json(raw)

            return {
                "summary_points": result.get("summary_points", crs_template.get_summary_points()),
                "overall_summary": result.get("overall_summary", "")
            }

        except Exception as e:
            logger.error(f"Summary generation failed: {str(e)}")
            return {
                "summary_points": crs_template.get_summary_points(),
                "overall_summary": f"CRS document for: {crs_template.project_title}"
            }

    def fill_template(
        self,
        user_input: str,
        conversation_history: list,
        extracted_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Complete workflow: Extract requirements, fill template, generate summary.
        
        Args:
            user_input: Latest user message
            conversation_history: List of previous messages
            extracted_fields: Previously extracted fields
            
        Returns:
            Dictionary containing:
                - crs_template: The populated CRS template as dict
                - crs_content: JSON string of the CRS
                - summary_points: List of key points
                - overall_summary: Executive summary
                - is_complete: Whether the CRS has sufficient information
        """
        logger.info(f"Filling CRS template from input: {user_input[:100]}...")

        # Extract requirements and fill template
        template = self.extract_requirements(
            user_input=user_input,
            conversation_history=conversation_history,
            extracted_fields=extracted_fields
        )

        # Generate summary
        summary = self.generate_summary(template)

        # Check completeness
        is_complete = self._check_completeness(template)

        return {
            "crs_template": template.to_dict(),
            "crs_content": template.to_json(),
            "summary_points": summary["summary_points"],
            "overall_summary": summary["overall_summary"],
            "is_complete": is_complete
        }

    def _check_completeness(self, template: CRSTemplate) -> bool:
        """
        Check if the CRS template has sufficient information.
        
        Returns True if essential fields are populated.
        """
        essential_filled = all([
            template.project_title,
            template.project_description,
            len(template.functional_requirements) > 0
        ])
        
        # Count how many optional fields are filled
        optional_filled = sum([
            len(template.project_objectives) > 0,
            len(template.target_users) > 0,
            bool(template.timeline_constraints and template.timeline_constraints != "Not specified"),
            bool(template.budget_constraints and template.budget_constraints != "Not specified"),
            len(template.success_metrics) > 0
        ])
        
        # Consider complete if essentials are filled and at least 2 optional fields
        return essential_filled and optional_filled >= 2
