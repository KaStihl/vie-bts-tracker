"""
Shared HTTP helpers: one honest User-Agent and a requests.Session that retries
transient failures (429 / 5xx / connection errors) with exponential backoff and
honours Retry-After.

Before this module every scraper called requests.get() directly, so a single
429 from OpenSky or a 502 from an airport website failed the whole GitHub
Actions run.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Identifies the bot honestly and points at the project. bts.aero sits behind
# Cloudflare and challenges generic browser-less user agents, but accepts this
# "compatible; <Name>Bot" form (verified 2026-10).
USER_AGENT = "Mozilla/5.0 (compatible; FKsLabBot/1.0; +https://fkslab.com)"

RETRY_STATUSES = (429, 500, 502, 503, 504)


# OpenSky answers 429 when the DAILY credit budget is used up. Retrying that with
# backoff only wastes minutes (Retry-After can be hours), so OpenSky sessions
# retry on server errors only and callers handle 429 themselves.
RETRY_SERVER_ERRORS_ONLY = (500, 502, 503, 504)


def make_session(
    total_retries: int = 5,
    backoff_factor: float = 2.0,
    retry_statuses: tuple[int, ...] = RETRY_STATUSES,
) -> requests.Session:
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        status=total_retries,
        backoff_factor=backoff_factor,          # 0s, 4s, 8s, 16s, 32s ...
        status_forcelist=retry_statuses,
        allowed_methods=frozenset({"GET", "POST"}),  # OAuth token POST is idempotent
        respect_retry_after_header=True,
        raise_on_status=False,                  # let callers see the final response
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session
