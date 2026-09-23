import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))

from dotacni_majak_source_sdk.http import (
    GuardedHttpClient,
    ResponseTooLargeError,
    UnsafeAddressError,
    UrlNotAllowedError,
)


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def private_resolver(host: str, port: int) -> list[str]:
    return ["127.0.0.1"]


async def no_sleep(_: float) -> None:
    return None


class GuardedHttpClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_allowed_https_host(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain; charset=utf-8"},
                content=b"ok",
                request=request,
            )
        )
        client = GuardedHttpClient(
            allowed_hosts={"example.com"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=transport,
        )
        try:
            response = await client.get("https://example.com/data")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, "ok")
        finally:
            await client.aclose()

    async def test_rejects_non_allowlisted_host(self):
        client = GuardedHttpClient(
            allowed_hosts={"example.com"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        )
        try:
            with self.assertRaises(UrlNotAllowedError):
                await client.get("https://evil.example/data")
        finally:
            await client.aclose()

    async def test_rejects_http_scheme_and_credentials(self):
        client = GuardedHttpClient(
            allowed_hosts={"example.com"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        )
        try:
            with self.assertRaises(UrlNotAllowedError):
                await client.get("http://example.com/data")
            with self.assertRaises(UrlNotAllowedError):
                await client.get("https://user:pass@example.com/data")
        finally:
            await client.aclose()

    async def test_rejects_private_dns_resolution(self):
        client = GuardedHttpClient(
            allowed_hosts={"example.com"},
            resolver=private_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        )
        try:
            with self.assertRaises(UnsafeAddressError):
                await client.get("https://example.com/data")
        finally:
            await client.aclose()

    async def test_redirect_target_is_revalidated(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                302,
                headers={"location": "https://evil.example/secret"},
                request=request,
            )

        client = GuardedHttpClient(
            allowed_hosts={"example.com"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(handler),
        )
        try:
            with self.assertRaises(UrlNotAllowedError):
                await client.get("https://example.com/start")
        finally:
            await client.aclose()

    async def test_response_size_is_bounded(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-length": "10"},
                content=b"0123456789",
                request=request,
            )
        )
        client = GuardedHttpClient(
            allowed_hosts={"example.com"},
            resolver=public_resolver,
            sleeper=no_sleep,
            max_response_bytes=8,
            transport=transport,
        )
        try:
            with self.assertRaises(ResponseTooLargeError):
                await client.get("https://example.com/data")
        finally:
            await client.aclose()

    async def test_retries_retryable_status(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, request=request)
            return httpx.Response(200, content=b"ok", request=request)

        client = GuardedHttpClient(
            allowed_hosts={"example.com"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(handler),
            retries=1,
        )
        try:
            response = await client.get("https://example.com/data")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(calls, 2)
        finally:
            await client.aclose()


if __name__ == "__main__":
    unittest.main()
