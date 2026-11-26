import pytest

from app.security import limiter


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()
