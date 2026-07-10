from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def services():
    return SimpleNamespace(
        catalog=Mock(),
        editor=Mock(),
        history=Mock(),
    )


@pytest.fixture
def app(services):
    from conf_edit.web.app import WebContainer, create_app
    from conf_edit.web.security import RequestSecurity

    security = RequestSecurity(
        port=8765,
        token="test-token",
        allowed_hosts={"localhost", "localhost:8765"},
    )
    app = create_app(
        WebContainer(
            catalog=services.catalog,
            editor=services.editor,
            history=services.history,
            security=security,
        )
    )
    app.config.update(TESTING=True)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mutation_headers():
    return {"X-Conf-Edit-Token": "test-token"}

