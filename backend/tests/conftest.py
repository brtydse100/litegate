import os

# Safe defaults for modules imported during test collection. Individual config
# tests override these values when testing precedence and parsing.
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test")
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-characters")
