"""
Base adapter class — HTTP retry logic shared by all adapters.

All data adapters inherit from BaseAdapter to get:
- Exponential backoff retry on HTTP failures
- Consistent logging with SOURCE_NAME prefix
- Session management
"""
import logging
import time
from abc import ABC
from typing import Optional

import requests

logger = logging.getLogger('adapters')


class AdapterError(Exception):
    """Raised when an adapter cannot fetch data after all retries."""
    pass


class DataUnavailableError(Exception):
    """Raised by DataSourceRegistry when all fallbacks fail."""
    pass


class BaseAdapter(ABC):
    """
    Abstract base for all data adapters.

    Subclasses must set SOURCE_NAME.
    Use _get_with_retry() for all HTTP GET requests.
    """
    SOURCE_NAME: str = 'base'
    RATE_LIMIT_DELAY: float = 0.5    # seconds between requests (default; override in subclass)

    def _get_with_retry(
        self,
        url: str,
        session: Optional[requests.Session] = None,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        timeout: int = 15,
        **kwargs,
    ) -> requests.Response:
        """
        HTTP GET with exponential backoff retry.

        Args:
            url: Full URL to fetch
            session: Optional existing requests.Session (pass for cookie-persistent sessions)
            max_retries: Number of attempts before raising
            backoff_factor: Multiplier for delay between retries
            timeout: Request timeout in seconds
            **kwargs: Passed to requests.get()

        Returns:
            requests.Response (guaranteed status 2xx)

        Raises:
            AdapterError: After all retries are exhausted
        """
        s     = session or requests.Session()
        delay = self.RATE_LIMIT_DELAY

        for attempt in range(1, max_retries + 1):
            try:
                response = s.get(url, timeout=timeout, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response else 0
                # Don't retry client errors (4xx) except 429 (rate limit)
                if status and 400 <= status < 500 and status != 429:
                    raise AdapterError(f"[{self.SOURCE_NAME}] HTTP {status} for {url}") from e
                logger.warning(
                    f"[{self.SOURCE_NAME}] Attempt {attempt}/{max_retries} failed "
                    f"(HTTP {status}): {url}"
                )
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ConnectTimeout,
            ) as e:
                # Connection refused / DNS failure / server dropped connection.
                # These are not transient — retrying immediately won't help.
                # Log and raise right away so callers can move to the next fallback.
                logger.warning(
                    f"[{self.SOURCE_NAME}] Attempt {attempt}/{max_retries} failed "
                    f"(HTTP 0): {url}"
                )
                if attempt >= max_retries:
                    raise AdapterError(
                        f"[{self.SOURCE_NAME}] All {max_retries} retries failed for {url}"
                    ) from e
                # One brief pause before the next attempt (server may be briefly busy)
                logger.debug(f"[{self.SOURCE_NAME}] Retrying in {min(delay, 2.0):.1f}s...")
                time.sleep(min(delay, 2.0))  # cap at 2s; no point in long waits
                delay *= backoff_factor
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"[{self.SOURCE_NAME}] Attempt {attempt}/{max_retries} failed: {e} | {url}"
                )

            if attempt < max_retries:
                logger.debug(f"[{self.SOURCE_NAME}] Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= backoff_factor

        raise AdapterError(
            f"[{self.SOURCE_NAME}] All {max_retries} retries failed for {url}"
        )

    def _make_session(self, headers: Optional[dict] = None) -> requests.Session:
        """Create a new requests.Session with optional default headers."""
        s = requests.Session()
        if headers:
            s.headers.update(headers)
        return s
