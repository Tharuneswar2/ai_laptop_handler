"""
conversation/response_builder.py — Natural response generation for the creator-assistant.

Generates short, polite, human-like responses. Always addresses the creator as "Sir".
"""

import logging
import random
from typing import Optional

from conversation.schemas import (
    CreatorIntent,
    IntentType,
    TaskResult,
    TaskState,
)

logger = logging.getLogger(__name__)

# Creator address
CREATOR = "Sir"

# Response templates organized by category
_ACKNOWLEDGMENTS = [
    "Got it, {creator}.",
    "Right away, {creator}.",
    "On it, {creator}.",
    "Understood, {creator}.",
    "Sure thing, {creator}.",
    "Doing that now, {creator}.",
    "Certainly, {creator}.",
    "Consider it done, {creator}.",
]

_SUCCESS_TEMPLATES = {
    IntentType.OPEN_APP: "Opened it, {creator}.",
    IntentType.CLOSE_APP: "Closed it, {creator}.",
    IntentType.SEARCH_WEB: "Here are the results, {creator}.",
    IntentType.SUMMARIZE_TEXT: "Here is the summary, {creator}.",
    IntentType.READ_FILE: "Found it, {creator}.",
    IntentType.WRITE_FILE: "Done writing, {creator}.",
    IntentType.RUN_SCRIPT: "Command completed, {creator}.",
    IntentType.CHECK_STATUS: "Here is the status, {creator}.",
    IntentType.CONTROL_SETTING: "Setting adjusted, {creator}.",
    IntentType.CREATE_PROJECT: "Project created, {creator}.",
    IntentType.LIST_APPS: "Here is the list, {creator}.",
    IntentType.SCREENSHOT: "Screenshot saved, {creator}.",
    IntentType.CONVERSATION: "",
    IntentType.UNKNOWN: "Done, {creator}.",
}

_CLARIFICATION_TEMPLATES = [
    "I need one detail before I continue, {creator}. {question}",
    "Could you clarify, {creator}? {question}",
    "Which one do you mean, {creator}? {question}",
    "I need a bit more info, {creator}. {question}",
]

_FAILURE_TEMPLATES = [
    "I could not complete that, {creator}. {reason}",
    "Something went wrong, {creator}. {reason}",
    "That did not work, {creator}. {reason}",
    "Sorry, {creator}, but {reason}",
]

_BLOCKED_TEMPLATES = [
    "I can only respond to the creator, {creator}.",
    "I am sorry, but I need creator authorization for that.",
    "That action requires the creator's approval.",
]

_GREETING_RESPONSES = [
    "Hello, {creator}. How can I help you today?",
    "Hi there, {creator}. What can I do for you?",
    "Good to see you, {creator}. Ready when you are.",
    "Hello, {creator}. I am at your service.",
    "Hey, {creator}. What would you like me to do?",
]

_FAREWELL_RESPONSES = [
    "Goodbye, {creator}. Let me know if you need anything.",
    "See you later, {creator}.",
    "Take care, {creator}. I will be here when you need me.",
    "Bye, {creator}. Have a great day.",
]

_CONFUSION_TEMPLATES = [
    "I am not sure I understand, {creator}. Could you rephrase?",
    "I did not quite catch that, {creator}. Could you say it again?",
    "I am not sure what you mean, {creator}. Can you try again?",
]


class ResponseBuilder:
    """
    Generates natural, short, polite responses for the creator.
    Always addresses the creator as "Sir".
    """

    def __init__(self, creator_name: str = CREATOR):
        self.creator_name = creator_name

    def acknowledge(self) -> str:
        """Generate a short acknowledgment."""
        template = random.choice(_ACKNOWLEDGMENTS)
        return template.format(creator=self.creator_name)

    def task_started(self, intent: CreatorIntent) -> str:
        """Generate a response when a task starts."""
        ack = self.acknowledge()
        return ack

    def task_completed(self, intent: CreatorIntent, result: TaskResult) -> str:
        """Generate a response when a task completes successfully."""
        # For conversation/chat intents, use the LLM response directly
        if intent.intent_type == IntentType.CONVERSATION and result.message:
            return result.message

        template = _SUCCESS_TEMPLATES.get(intent.intent_type, "Done, {creator}.")
        response = template.format(creator=self.creator_name)

        # Add result details if they add value
        if result.message and len(result.message) < 150:
            # For status checks, include the message
            if intent.intent_type in (IntentType.CHECK_STATUS, IntentType.LIST_APPS, IntentType.SEARCH_WEB):
                response = f"{result.message}"

        return response

    def task_failed(self, intent: CreatorIntent, result: TaskResult) -> str:
        """Generate a response when a task fails."""
        reason = result.message if result.message else "an unknown error occurred."
        # Truncate long error messages
        if len(reason) > 120:
            reason = reason[:117] + "..."
        template = random.choice(_FAILURE_TEMPLATES)
        return template.format(creator=self.creator_name, reason=reason)

    def needs_clarification(self, question: str) -> str:
        """Generate a clarification question."""
        template = random.choice(_CLARIFICATION_TEMPLATES)
        return template.format(creator=self.creator_name, question=question)

    def blocked(self) -> str:
        """Generate a response for blocked actions."""
        template = random.choice(_BLOCKED_TEMPLATES)
        return template.format(creator=self.creator_name)

    def confused(self) -> str:
        """Generate a response when the assistant is confused."""
        template = random.choice(_CONFUSION_TEMPLATES)
        return template.format(creator=self.creator_name)

    def status_check(self, message: str) -> str:
        """Generate a response for status checks."""
        return message

    def greeting(self) -> str:
        """Generate a greeting response."""
        template = random.choice(_GREETING_RESPONSES)
        return template.format(creator=self.creator_name)

    def farewell(self) -> str:
        """Generate a farewell response."""
        template = random.choice(_FAREWELL_RESPONSES)
        return template.format(creator=self.creator_name)

    def custom(self, text: str) -> str:
        """Return a custom response as-is."""
        return text
