"""
LLM Factory - Centralized LLM instance creation

This factory provides a single point of configuration for all AI models used in the application.

IMPORTANT: This system uses GROQ EXCLUSIVELY for all AI operations.
All LLM instances are created using ChatGroq from langchain-groq.

Provider: Groq (https://console.groq.com)
Integration: langchain-groq
"""
import logging
from typing import Optional
from langchain_groq import ChatGroq
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMFactory:
    """
    Factory class for creating Groq LLM instances with centralized configuration.
    
    This factory uses GROQ EXCLUSIVELY - all models are Groq models accessed via the Groq API.
    Supports different models for different components while maintaining consistency.
    
    All instances are ChatGroq objects from langchain-groq.
    """
    
    @staticmethod
    def create_clarification_llm() -> ChatGroq:
        """
        Create LLM instance for clarification/ambiguity detection.
        
        Returns:
            ChatGroq: Configured LLM instance for clarification tasks
        """
        return ChatGroq(
            model=settings.LLM_CLARIFICATION_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=settings.LLM_CLARIFICATION_TEMPERATURE,
            max_tokens=settings.LLM_CLARIFICATION_MAX_TOKENS
        )
    
    @staticmethod
    def create_template_filler_llm() -> ChatGroq:
        """
        Create LLM instance for template filling/CRS generation.
        
        Returns:
            ChatGroq: Configured LLM instance for template filling tasks
        """
        return ChatGroq(
            model=settings.LLM_TEMPLATE_FILLER_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=settings.LLM_TEMPLATE_FILLER_TEMPERATURE,
            max_tokens=settings.LLM_TEMPLATE_FILLER_MAX_TOKENS
        )
    
    @staticmethod
    def create_suggestions_llm() -> ChatGroq:
        """
        Create LLM instance for generating creative suggestions.
        
        Returns:
            ChatGroq: Configured LLM instance for suggestions generation
        """
        return ChatGroq(
            model=settings.LLM_SUGGESTIONS_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=settings.LLM_SUGGESTIONS_TEMPERATURE,
            max_tokens=settings.LLM_SUGGESTIONS_MAX_TOKENS
        )
    
    @staticmethod
    def create_custom_llm(
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> ChatGroq:
        """
        Create a custom LLM instance with specific parameters.
        Falls back to default settings for any unspecified parameters.
        
        Args:
            model: Model name (defaults to LLM_DEFAULT_MODEL)
            temperature: Temperature setting (defaults to 0.3)
            max_tokens: Maximum tokens (defaults to 2048)
            
        Returns:
            ChatGroq: Configured LLM instance
        """
        return ChatGroq(
            model=model or settings.LLM_DEFAULT_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=temperature if temperature is not None else 0.3,
            max_tokens=max_tokens or 2048
        )


# Convenience functions for backward compatibility
def get_clarification_llm() -> ChatGroq:
    """Get LLM instance for clarification tasks."""
    return LLMFactory.create_clarification_llm()


def get_template_filler_llm() -> ChatGroq:
    """Get LLM instance for template filling tasks."""
    return LLMFactory.create_template_filler_llm()


def get_suggestions_llm() -> ChatGroq:
    """Get LLM instance for suggestions generation."""
    return LLMFactory.create_suggestions_llm()


def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None
) -> ChatGroq:
    """
    Get a custom LLM instance.
    
    Args:
        model: Model name (optional)
        temperature: Temperature setting (optional)
        max_tokens: Maximum tokens (optional)
        
    Returns:
        ChatGroq: Configured LLM instance
    """
    return LLMFactory.create_custom_llm(model, temperature, max_tokens)
