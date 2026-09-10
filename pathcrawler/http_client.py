"""HTTP client implemented with Python standard-library modules."""

from __future__ import annotations

import logging
import socket
import ssl
import time
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pathcrawler.logger import mask_headers
from pathcrawler.models import HTTPResponse


class NoRedirectHandler(HTTPRedirectHandler):
    """Redirect handler that returns redirect responses instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def validate_base_url(url: str) -> str:
    """Validate and normalize the base URL."""

    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise ValueError("Invalid URL.") from exc

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid URL. Use http:// or https:// with a host.")

    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def build_url(base_url: str, path: str) -> str:
    """Combine a base URL and enumeration path without unsafe string concatenation."""

    parsed = urlsplit(validate_base_url(base_url))
    base_path = parsed.path or "/"
    clean_path = "/" + path.strip().split("?", 1)[0].strip("/")

    if base_path == "/":
        combined_path = clean_path
    else:
        combined_path = base_path.rstrip("/") + clean_path

    quoted_path = quote(combined_path, safe="/%:@")
    return urlunsplit((parsed.scheme, parsed.netloc, quoted_path, parsed.query, ""))


class HTTPClient:
    """Small GET-only HTTP client for path enumeration."""

    def __init__(
        self,
        timeout: float,
        user_agent: str,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
        max_redirects: int = 5,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self.headers = headers or {}
        self.follow_redirects = follow_redirects
        self.max_redirects = max_redirects
        self._no_redirect_opener = build_opener(NoRedirectHandler)

    def get(self, url: str, include_body: bool = False) -> HTTPResponse:
        """Perform an HTTP GET request and return normalized response metadata."""

        start = time.perf_counter()
        current_url = url
        redirect_chain: list[str] = []
        original_status: Optional[int] = None
        first_redirect: Optional[str] = None

        for _ in range(self.max_redirects + 1):
            request = self._build_request(current_url)
            logging.debug("GET %s headers=%s", current_url, mask_headers(dict(request.header_items())))
            try:
                response = self._no_redirect_opener.open(request, timeout=self.timeout)
                with response:
                    body = response.read() if include_body else b""
                    headers = dict(response.headers.items())
                    elapsed = time.perf_counter() - start
                    return HTTPResponse(
                        url=url,
                        status_code=response.status,
                        headers=headers,
                        content_length=_content_length(headers, body),
                        content_type=headers.get("Content-Type", ""),
                        body=body,
                        response_time=elapsed,
                        final_url=response.geturl(),
                        redirect_location=first_redirect,
                        original_status_code=original_status,
                        redirect_chain=redirect_chain,
                    )
            except HTTPError as exc:
                headers = dict(exc.headers.items()) if exc.headers else {}
                status = exc.code
                location = headers.get("Location")
                is_redirect = 300 <= status < 400 and location
                if is_redirect:
                    if original_status is None:
                        original_status = status
                        first_redirect = location
                    redirect_chain.append(location)
                    if self.follow_redirects and len(redirect_chain) <= self.max_redirects:
                        current_url = _absolute_redirect(current_url, location)
                        exc.close()
                        continue

                body = b""
                if include_body:
                    try:
                        body = exc.read()
                    except OSError:
                        body = b""
                elapsed = time.perf_counter() - start
                result = HTTPResponse(
                    url=url,
                    status_code=status,
                    headers=headers,
                    content_length=_content_length(headers, body),
                    content_type=headers.get("Content-Type", ""),
                    body=body,
                    response_time=elapsed,
                    final_url=current_url,
                    redirect_location=first_redirect or location,
                    original_status_code=original_status,
                    redirect_chain=redirect_chain,
                )
                exc.close()
                return result
            except TimeoutError as exc:
                return _error_response(url, start, "Request timed out.", exc, timed_out=True)
            except socket.timeout as exc:
                return _error_response(url, start, "Request timed out.", exc, timed_out=True)
            except ssl.SSLError as exc:
                return _error_response(url, start, "SSL error while connecting.", exc)
            except URLError as exc:
                return _error_response(url, start, _url_error_message(exc), exc)
            except OSError as exc:
                return _error_response(url, start, "Connection error.", exc)

        elapsed = time.perf_counter() - start
        return HTTPResponse(
            url=url,
            status_code=original_status,
            response_time=elapsed,
            redirect_location=first_redirect,
            original_status_code=original_status,
            error="Too many redirects.",
            redirect_chain=redirect_chain,
        )

    def _build_request(self, url: str) -> Request:
        headers = {"User-Agent": self.user_agent}
        headers.update(self.headers)
        return Request(url, headers=headers, method="GET")


def _content_length(headers: Dict[str, str], body: bytes) -> int:
    value = headers.get("Content-Length")
    if value:
        try:
            return int(value)
        except ValueError:
            pass
    return len(body)


def _absolute_redirect(current_url: str, location: str) -> str:
    from urllib.parse import urljoin

    return urljoin(current_url, location)


def _url_error_message(exc: URLError) -> str:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, socket.gaierror):
        return "Could not resolve target host."
    if isinstance(reason, ConnectionRefusedError):
        return "Could not connect to target."
    if isinstance(reason, TimeoutError):
        return "Request timed out."
    text = str(reason)
    if "timed out" in text.lower():
        return "Request timed out."
    return "Could not connect to target."


def _error_response(
    url: str,
    start: float,
    message: str,
    exc: BaseException,
    timed_out: bool = False,
) -> HTTPResponse:
    logging.debug("%s %s", message, exc, exc_info=True)
    return HTTPResponse(
        url=url,
        status_code=None,
        response_time=time.perf_counter() - start,
        error=message,
        timed_out=timed_out,
    )
