"""Shared environment/secret setting helpers."""

from __future__ import annotations

import os
from typing import Any

try:
    import streamlit as st
except ImportError:  # pragma: no cover - optional runtime dependency
    st = None

STREAMLIT_SECRET_EXCEPTIONS: tuple[type[Exception], ...] = (
    AttributeError,
    RuntimeError,
    KeyError,
    TypeError,
)
if st is not None:
    try:
        from streamlit.errors import StreamlitSecretNotFoundError
    except ImportError:  # pragma: no cover - streamlit error type mismatch by version
        pass
    else:
        STREAMLIT_SECRET_EXCEPTIONS = (
            *STREAMLIT_SECRET_EXCEPTIONS,
            StreamlitSecretNotFoundError,
        )


def read_setting(name: str) -> str:
    """Read setting from environment, then Streamlit secrets if available."""
    env_value = os.getenv(name)
    if env_value:
        return env_value.strip()

    if st is None:
        return ""

    try:
        secret_value: Any = st.secrets.get(name)
    except STREAMLIT_SECRET_EXCEPTIONS:
        return ""

    return str(secret_value).strip() if secret_value else ""
