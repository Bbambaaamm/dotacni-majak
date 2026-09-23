from __future__ import annotations

import asyncio
import ipaddress
import random
import socket
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx


class GuardedHttpError(RuntimeError):
    """Base class for guarded HTTP failures."""


class UrlNotAllowedError(GuardedHttpError):
    pass


class UnsafeAddressError(GuardedHttpError):
    pass


class ResponseTooLargeError(GuardedHttpError):
    pass


class TooManyRedirectsError(GuardedHttpError):
    pass


@dataclass(frozen=True, slots=True)
class GuardedResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    url: str

    @property
    def text(self) -> str:
        charset = "utf-8"
        content_type = self.headers.get("content-type", "")
        for part in content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip().strip('"')
        return self.content.decode(charset, errors="replace")


Resolver = Callable[[str, int], Awaitable[list[str]]]
Sleeper = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class GuardedHttpClient:
    """Read-only HTTP client for Source Adapters.

    Security model:
    - HTTPS only.
    - GET/HEAD only.
    - exact hostname allowlist.
    - no URL credentials.
    - DNS/literal IP must resolve exclusively to globally routable addresses.
    - redirects are followed manually and revalidated.
    - bounded concurrency, request rate, retries and response size.

    The DNS preflight materially reduces SSRF risk but is not a substitute for
    network-level egress policy. Production deployment should also restrict
    outbound networking where the runtime supports it.
    """

    RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
    REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
    ALLOWED_METHODS = frozenset({"GET", "HEAD"})

    def __init__(
        self,
        *,
        allowed_hosts: set[str] | frozenset[str],
        requests_per_second: float = 1.0,
        max_concurrency: int = 2,
        timeout_seconds: float = 30.0,
        max_response_bytes: int = 50 * 1024 * 1024,
        max_redirects: int = 3,
        retries: int = 3,
        user_agent: str = "DotacniMajak/0.1 (+https://github.com/Bbambaaamm/dotacni-majak)",
        resolver: Resolver | None = None,
        sleeper: Sleeper = asyncio.sleep,
        clock: Clock = time.monotonic,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be >= 1")
        if max_redirects < 0 or retries < 0:
            raise ValueError("max_redirects/retries must be >= 0")

        normalized = {self._normalize_host(host) for host in allowed_hosts}
        if not normalized:
            raise ValueError("allowed_hosts must not be empty")

        self.allowed_hosts = frozenset(normalized)
        self.requests_per_second = requests_per_second
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self.retries = retries
        self.user_agent = user_agent

        self._resolver = resolver or self._default_resolver
        self._sleep = sleeper
        self._clock = clock
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self) -> "GuardedHttpClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        max_response_bytes: int | None = None,
    ) -> GuardedResponse:
        return await self.request(
            "GET",
            url,
            headers=headers,
            max_response_bytes=max_response_bytes,
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        max_response_bytes: int | None = None,
    ) -> GuardedResponse:
        method = method.upper()
        if method not in self.ALLOWED_METHODS:
            raise UrlNotAllowedError(f"HTTP method {method!r} is not allowed")

        limit = max_response_bytes or self.max_response_bytes
        if limit < 1 or limit > self.max_response_bytes:
            raise ValueError("max_response_bytes override must be within client limit")

        current_url = url
        redirect_count = 0

        while True:
            await self._validate_url(current_url)
            response = await self._request_with_retries(
                method,
                current_url,
                headers=headers,
                max_response_bytes=limit,
            )

            if response.status_code not in self.REDIRECT_STATUS:
                return response

            location = response.headers.get("location")
            if not location:
                return response

            if redirect_count >= self.max_redirects:
                raise TooManyRedirectsError(
                    f"redirect limit exceeded for {url!r}"
                )

            current_url = urljoin(current_url, location)
            redirect_count += 1

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None,
        max_response_bytes: int,
    ) -> GuardedResponse:
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                response = await self._request_once(
                    method,
                    url,
                    headers=headers,
                    max_response_bytes=max_response_bytes,
                )
            except httpx.TransportError as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise GuardedHttpError(f"transport failure for {url!r}") from exc
                await self._sleep(self._backoff_seconds(attempt))
                continue

            if response.status_code not in self.RETRYABLE_STATUS:
                return response

            if attempt >= self.retries:
                return response

            delay = self._retry_after_seconds(response.headers)
            if delay is None:
                delay = self._backoff_seconds(attempt)
            await self._sleep(delay)

        raise GuardedHttpError(f"request failed for {url!r}") from last_error

    async def _request_once(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None,
        max_response_bytes: int,
    ) -> GuardedResponse:
        await self._wait_for_rate_slot()

        request_headers = {"user-agent": self.user_agent, "accept": "*/*"}
        if headers:
            request_headers.update({str(k): str(v) for k, v in headers.items()})

        async with self._semaphore:
            async with self._client.stream(
                method,
                url,
                headers=request_headers,
            ) as response:
                declared_length = response.headers.get("content-length")
                if declared_length:
                    try:
                        length = int(declared_length)
                    except ValueError:
                        length = None
                    if length is not None and length > max_response_bytes:
                        raise ResponseTooLargeError(
                            f"response declares {length} bytes; limit is {max_response_bytes}"
                        )

                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > max_response_bytes:
                        raise ResponseTooLargeError(
                            f"response exceeded {max_response_bytes} bytes"
                        )

                return GuardedResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content=bytes(content),
                    url=str(response.url),
                )

    async def _wait_for_rate_slot(self) -> None:
        interval = 1.0 / self.requests_per_second
        async with self._rate_lock:
            now = self._clock()
            delay = max(0.0, self._next_request_at - now)
            if delay:
                await self._sleep(delay)
                now = self._clock()
            self._next_request_at = max(now, self._next_request_at) + interval

    async def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise UrlNotAllowedError("only HTTPS URLs are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise UrlNotAllowedError("URL credentials are not allowed")
        if not parsed.hostname:
            raise UrlNotAllowedError("URL must contain a hostname")

        host = self._normalize_host(parsed.hostname)
        if host not in self.allowed_hosts:
            raise UrlNotAllowedError(f"hostname {host!r} is not allowlisted")

        port = parsed.port or 443
        if port != 443:
            raise UrlNotAllowedError("only HTTPS port 443 is allowed")

        addresses = await self._resolver(host, port)
        if not addresses:
            raise UnsafeAddressError(f"hostname {host!r} resolved to no addresses")

        unsafe = [address for address in addresses if not self._is_public_address(address)]
        if unsafe:
            raise UnsafeAddressError(
                f"hostname {host!r} resolved to unsafe address(es): {unsafe!r}"
            )

    @staticmethod
    def _normalize_host(host: str) -> str:
        return host.rstrip(".").lower().encode("idna").decode("ascii")

    @staticmethod
    def _is_public_address(value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        return address.is_global

    async def _default_resolver(self, host: str, port: int) -> list[str]:
        def resolve() -> list[str]:
            answers = socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
            return sorted({answer[4][0] for answer in answers})

        return await asyncio.to_thread(resolve)

    @staticmethod
    def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
        raw = headers.get("retry-after")
        if not raw:
            return None

        try:
            return max(0.0, float(raw))
        except ValueError:
            pass

        try:
            timestamp = parsedate_to_datetime(raw).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None

        return max(0.0, timestamp - time.time())

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        base = min(0.5 * (2**attempt), 8.0)
        return base + random.uniform(0.0, base * 0.2)
