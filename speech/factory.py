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
    use_aws_live: bool = False,
    aws_region: str = "ap-south-1",
    aws_language: str = "en-US",
    aws_sample_rate: int = 16000,
    aws_microphone: str = None,
    wake_words: list = None,
    debug: bool = False,
) -> SpeechProvider:
    """
    Create and configure a speech provider.

    Args:
        use_aws: If True, create Amazon Transcribe provider (sounddevice).
        use_aws_live: If True, create WebRTC Amazon Transcribe provider.
        aws_region: AWS region for Transcribe.
        aws_language: Language code for Transcribe.
        aws_sample_rate: Audio sample rate.
        aws_microphone: Microphone device name (WebRTC mode).
        wake_words: Custom wake words list.
        debug: Enable debug logging.

    Returns:
        Configured SpeechProvider instance.
    """
    if use_aws_live:
        try:
            from speech.amazon_webrtc import WebRTCAmazonProvider

            provider = WebRTCAmazonProvider(
                region=aws_region,
                language_code=aws_language,
                sample_rate=aws_sample_rate,
                microphone_name=aws_microphone,
                wake_words=wake_words,
                debug=debug,
            )
            register_provider(provider)
            logger.info("Created WebRTC Amazon Transcribe provider (region=%s)", aws_region)
            return provider
        except ImportError as e:
            logger.error(
                "Failed to create WebRTC provider: %s. Falling back to standard AWS.",
                e,
            )
        except Exception as e:
            logger.error(
                "Failed to initialize WebRTC provider: %s. Falling back to standard AWS.",
                e,
            )

    if use_aws:
        try:
            from speech.amazon_transcribe import AmazonTranscribeProvider

            provider = AmazonTranscribeProvider(
                region=aws_region,
                language_code=aws_language,
                sample_rate=aws_sample_rate,
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
