"""Nebius AI Cloud authentication adapter (deployment / evaluation administration only).

The credential slot is ``NEBUIS_CLOUD_API_KEY`` (spelling intentional, user-defined). Its value's
type is not implied by the name, so it is interpreted through an explicitly selected mode:

* ``iam_token`` - the value is an IAM access token (e.g. from ``nebius iam get-access-token``),
  passed to the official SDK as a bearer token. IAM tokens expire (hours); the SDK cannot report
  the expiry of an opaque token, so status says "short-lived, refresh before use".
* ``service_account`` - the official renewable flow: ``NEBIUS_SERVICE_ACCOUNT_ID``,
  ``NEBIUS_PUBLIC_KEY_ID`` and ``NEBIUS_PRIVATE_KEY_FILE``, or ``NEBIUS_CREDENTIALS_FILE``. The
  ``NEBUIS_CLOUD_API_KEY`` value is not used in this mode (an arbitrary string cannot replace these
  fields).

Identity is validated with one read-only call (IAM ``whoami``). No resource is ever created as a
credential test. Missing Cloud credentials never affect Token Factory inference, and nothing here is
reachable from the agent's tools. Token values are never returned, logged or sent to the frontend.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

from nemotwins.config import get_settings

log = logging.getLogger("nemotwins.nebius_cloud")
MODES = ("iam_token", "service_account")
_LAST: dict[str, Any] = {}
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def describe() -> dict:
    """Configuration status without any network call and without secret values."""
    s = get_settings()
    mode = s.nebius_cloud_auth_mode.strip().lower()
    out: dict[str, Any] = {"auth_mode": mode, "project_id": s.nebius_project_id or None,
                           "region": s.nebius_region or None, "configured": False, "status": "not_configured",
                           "detail": "", "checked_at": None}
    if mode not in MODES:
        out.update(status="error", detail=f"NEBIUS_CLOUD_AUTH_MODE must be one of {', '.join(MODES)}")
        return out
    if mode == "iam_token":
        if s.nebius_cloud_api_key.strip():
            out.update(configured=True, status="configured",
                       detail="IAM token in NEBUIS_CLOUD_API_KEY (short-lived; refresh with "
                              "`nebius iam get-access-token`). Not yet checked.")
        else:
            out["detail"] = "NEBUIS_CLOUD_API_KEY is empty; Cloud administration is unavailable (inference is unaffected)."
        return out
    have_file = bool(s.nebius_credentials_file and os.path.isfile(s.nebius_credentials_file))
    have_key = bool(s.nebius_service_account_id and s.nebius_public_key_id and s.nebius_private_key_file
                    and os.path.isfile(s.nebius_private_key_file))
    if have_file or have_key:
        out.update(configured=True, status="configured",
                   detail="Service-account credentials " + ("file" if have_file else "key pair") + " present. Not yet checked.")
    else:
        out["detail"] = ("Service-account mode needs NEBIUS_CREDENTIALS_FILE, or NEBIUS_SERVICE_ACCOUNT_ID + "
                         "NEBIUS_PUBLIC_KEY_ID + NEBIUS_PRIVATE_KEY_FILE (existing files).")
    return out


def _sdk() -> Any:
    from nebius.sdk import SDK  # official SDK (pip package "nebius")

    s = get_settings()
    ua = "nemotwins/1.0"
    if s.nebius_cloud_auth_mode.strip().lower() == "iam_token":
        from nebius.aio.token.static import Bearer
        from nebius.aio.token.token import Token

        return SDK(credentials=Bearer(Token(s.nebius_cloud_api_key.strip())), user_agent_prefix=ua)
    if s.nebius_credentials_file:
        return SDK(credentials_file_name=s.nebius_credentials_file, user_agent_prefix=ua)
    return SDK(service_account_private_key_file_name=s.nebius_private_key_file,
               service_account_public_key_id=s.nebius_public_key_id,
               service_account_id=s.nebius_service_account_id, user_agent_prefix=ua)


def check(timeout_s: float = 20.0) -> dict:
    """Read-only identity check (IAM whoami). Returns status only: never the token or full identity."""
    out = describe()
    if not out["configured"]:
        return out
    try:
        sdk = _sdk()
    except ImportError:
        out.update(status="sdk_missing", detail="The `nebius` Python SDK is not installed.")
        return out
    except Exception as exc:  # noqa: BLE001 - invalid credential material
        out.update(status="error", detail=f"Could not initialise the SDK: {type(exc).__name__}", checked_at=_now())
        return out
    try:
        resp = sdk.whoami(timeout=timeout_s).wait()
        kind = "user" if getattr(resp, "user_profile", None) else (
            "service account" if getattr(resp, "service_account_profile", None) else "identity")
        out.update(status="ok", detail=f"Authenticated as a {kind} (read-only IAM whoami).", checked_at=_now())
    except TypeError:
        resp = sdk.whoami().wait()
        out.update(status="ok", detail="Authenticated (read-only IAM whoami).", checked_at=_now())
    except Exception as exc:  # noqa: BLE001 - expired / invalid token, network
        msg = type(exc).__name__
        code = getattr(exc, "code", None)
        if code is not None:
            msg += f" ({code() if callable(code) else code})"
        out.update(status="error", detail=f"Identity check failed: {msg}. An IAM token may have expired.",
                   checked_at=_now())
    finally:
        try:
            sdk.sync_close()
        except Exception:  # noqa: BLE001
            pass
    with _LOCK:
        _LAST.clear()
        _LAST.update(out)
    return out


def last() -> dict:
    """Most recent check result, or the static description when never checked."""
    with _LOCK:
        return dict(_LAST) if _LAST else describe()
