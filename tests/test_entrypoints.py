"""Every entry point must at least import: a syntax error in scraper.main once reached GitHub Actions unnoticed."""
import importlib

import pytest


@pytest.mark.parametrize("module", ["scraper.main", "scraper.healthcheck", "scraper.eurostat_monthly", "scraper.eurostat_airfares", "scraper.draft_post"])
def test_entrypoint_imports(module):
    importlib.import_module(module)
