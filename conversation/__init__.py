"""
conversation/ — Conversational creator-assistant layer for AI Laptop Handler.

Provides human-like conversation, intent understanding, task orchestration,
and natural responses. Addresses the creator as "Sir".

Modules:
  - schemas: Data structures for intents, tasks, conversation state
  - memory: Short-term conversation memory
  - safety: Creator-first safety checks
  - response_builder: Natural response generation
  - task_orchestrator: Task execution wrapper
  - conversation: Main engine coordinating all components
"""

from conversation.conversation import ConversationEngine, get_conversation_engine

__all__ = ["ConversationEngine", "get_conversation_engine"]
