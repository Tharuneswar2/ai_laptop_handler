"""
speech/factory.py — Speech provider factory.

Creates and configures speech providers based on application settings.
"""

import logging
from typing import Optional

from speech.provider import SpeechProvider, register_provider
from speech.browser import BrowserSpeechProvider, get_browser_provider

logger = logging.getLogger(__name__)


def create_provider(
    use_aws: bool = False,
    aws_region: str = "ap-south-1",
    aws_language: str = "en-US",
    aws_sample_rate: int = 16000,
    wake_words: list = None,
    enable_vad: bool = True,
    debug: bool = False,
) -> SpeechProvider:
    """
    Create and configure a speech provider.

    Args:
        use_aws: If True, create Amazon Transcribe provider.
        aws_region: AWS region for Transcribe.
        aws_language: Language code for Transcribe.
        aws_sample_rate: Audio sample rate.
        wake_words: Custom wake words list.
        enable_vad: Enable Voice Activity Detection.
        debug: Enable debug logging.

    Returns:
        Configured SpeechProvider instance.
    """
    if use_aws:
        try:
            from speech.amazon_transcribe import AmazonTranscribeProvider

            provider = AmazonTranscribeProvider(
                region=aws_region,
                language_code=aws_language,
                sample_rate=aws_sample_rate,
                enable_vad=enable_vad,
                wake_words=wake_words,
                debug=debug,
            )
            register_provider(provider)
            logger.info("Created Amazon Transcribe provider (region=%s)", aws_region)
            return provider
        except ImportError as e:
            logger.error(
                "Failed to create Amazon Transcribe provider: %s. "
                "Falling back to browser provider.",
                e,
            )
        except Exception as e:
            logger.error(
                "Failed to initialize Amazon Transcribe: %s. "
                "Falling back to browser provider.",
                e,
            )

    # Default: browser provider
    provider = get_browser_provider()
    register_provider(provider)
    logger.info("Using browser speech provider.")
    return provider
