"""Configuration constants for the Global Signal Desk agents."""

import os

# Keep model selection configurable so the tutorial can follow account availability.
# The defaults reflect the current OpenAI model family as of July 2026.
COMPLEX_REASONING_MODEL = os.getenv("OPENAI_COMPLEX_MODEL", "gpt-5.6-sol")
EFFICIENT_PROCESSING_MODEL = os.getenv("OPENAI_FAST_MODEL", "gpt-5.6-terra")
