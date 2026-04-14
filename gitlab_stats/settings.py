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


def _normalize_supabase_target(raw_target: str) -> str:
    """Normalize Supabase target environment names."""
    normalized = raw_target.strip().lower()
    if normalized in {"", "prod", "production"}:
        return "prod"
    if normalized in {"dev", "development"}:
        return "dev"
    return "prod"


def read_supabase_setting(name: str) -> str:
    """Read target-scoped Supabase setting, then fallback to legacy name."""
    target = _normalize_supabase_target(read_setting("SUPABASE_TARGET"))
    prefix = "SUPABASE_DEV_" if target == "dev" else "SUPABASE_PROD_"
    scoped_name = name.replace("SUPABASE_", prefix, 1)

    scoped_value = read_setting(scoped_name)
    if scoped_value:
        return scoped_value

    return read_setting(name)
