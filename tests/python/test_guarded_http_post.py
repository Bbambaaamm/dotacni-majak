import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "source-sdk" / "src"))

from dotacni_majak_source_sdk.http import (
    GuardedHttpClient,
    RequestTooLargeError,
    UrlNotAllowedError,
)


async def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_: float) -> None:
    return None


class SafeReadonlyPostTest(unittest.IsolatedAsyncioTestCase):
    async def test_post_requires_explicit_path_allowlist(self):
        client = GuardedHttpClient(
            allowed_hosts={"api.example.com"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, request=request)
            ),
        )
        try:
            with self.assertRaises(UrlNotAllowedError):
                await client.post_multipart(
                    "https://api.example.com/search",
                    json_parts={"query": {"bool": {"must": []}}},
                )
        finally:
            await client.aclose()

    async def test_multipart_json_post_uses_post_and_expected_parts(self):
        observed = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            observed["method"] = request.method
            observed["content_type"] = request.headers.get("content-type", "")
            observed["body"] = body
            return httpx.Response(
                200,
                json={"results": []},
                request=request,
            )

        client = GuardedHttpClient(
            allowed_hosts={"api.example.com"},
            allowed_post_paths={"/search"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(handler),
        )
        try:
            response = await client.post_multipart(
                "https://api.example.com/search?page=1",
                json_parts={
                    "query": {"bool": {"must": []}},
                    "languages": ["en"],
                },
                text_parts={"displayLanguage": "en"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(observed["method"], "POST")
            self.assertIn("multipart/form-data", observed["content_type"])
            self.assertIn(b'name="query"', observed["body"])
            self.assertIn(b"application/json", observed["body"])
            self.assertIn(b'name="displayLanguage"', observed["body"])
        finally:
            await client.aclose()

    async def test_request_body_is_bounded(self):
        client = GuardedHttpClient(
            allowed_hosts={"api.example.com"},
            allowed_post_paths={"/search"},
            max_request_body_bytes=16,
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, request=request)
            ),
        )
        try:
            with self.assertRaises(RequestTooLargeError):
                await client.post_multipart(
                    "https://api.example.com/search",
                    json_parts={"query": {"large": "x" * 100}},
                )
        finally:
            await client.aclose()

    async def test_post_redirect_target_is_revalidated(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                307,
                headers={"location": "https://evil.example/search"},
                request=request,
            )

        client = GuardedHttpClient(
            allowed_hosts={"api.example.com"},
            allowed_post_paths={"/search"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(handler),
        )
        try:
            with self.assertRaises(UrlNotAllowedError):
                await client.post_multipart(
                    "https://api.example.com/search",
                    json_parts={"query": {}},
                )
        finally:
            await client.aclose()

    async def test_arbitrary_post_is_still_rejected_by_request_api(self):
        client = GuardedHttpClient(
            allowed_hosts={"api.example.com"},
            allowed_post_paths={"/search"},
            resolver=public_resolver,
            sleeper=no_sleep,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, request=request)
            ),
        )
        try:
            with self.assertRaises(UrlNotAllowedError):
                await client.request(
                    "POST",
                    "https://api.example.com/search",
                )
        finally:
            await client.aclose()


if __name__ == "__main__":
    unittest.main()
