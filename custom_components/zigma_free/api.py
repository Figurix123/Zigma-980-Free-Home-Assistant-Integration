"""Authenticated client for the Zigma Free local HTTP API."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class ZigmaApiError(Exception):
    """Base API error."""


class ZigmaAuthenticationError(ZigmaApiError):
    """The robot rejected the configured access key."""


class ZigmaLocalApi:
    """Small async client for the documented v1.1-rc10 endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        access_key: str,
    ) -> None:
        self._session = session
        self._base_url = f"http://{host}:{port}"
        self._headers = {"Authorization": f"Bearer {access_key}"}

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = dict(self._headers)
        kwargs: dict[str, Any] = {"headers": headers, "timeout": aiohttp.ClientTimeout(total=8)}
        if payload is not None:
            headers["X-Zigma-Request"] = "1"
            kwargs["json"] = payload
        try:
            async with self._session.request(
                method, f"{self._base_url}{path}", **kwargs
            ) as response:
                if response.status == 401:
                    raise ZigmaAuthenticationError("Robot rejected the access key")
                if response.status >= 400:
                    detail = await response.text()
                    raise ZigmaApiError(
                        f"{method} {path} returned HTTP {response.status}: {detail[:200]}"
                    )
                try:
                    result = await response.json()
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise ZigmaApiError(f"{method} {path} did not return JSON") from err
                if not isinstance(result, dict):
                    raise ZigmaApiError(f"{method} {path} returned an unexpected payload")
                return result
        except ZigmaApiError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ZigmaApiError(f"Could not reach the robot at {self._base_url}") from err

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch robot status."""
        return await self._request("GET", "/api/status")

    async def async_send_command(self, action: str, **parameters: Any) -> dict[str, Any]:
        """Dispatch an action; success means accepted by the local agent."""
        return await self._request(
            "POST", "/api/commands", {"action": action, **parameters}
        )
