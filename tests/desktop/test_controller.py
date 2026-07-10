from pathlib import Path
from unittest.mock import Mock

import pytest

from conf_edit.desktop.controller import DesktopController, local_urls
from conf_edit.domain.models import FileKind


@pytest.fixture
def fake_server():
    return Mock()


def test_controller_transitions(fake_server, catalog_service) -> None:
    controller = DesktopController(fake_server, catalog_service, port=8765)

    controller.start()
    assert controller.state.status == "running"
    assert any(url.endswith(":8765") for url in controller.state.urls)
    controller.stop()
    assert controller.state.status == "stopped"


def test_controller_surfaces_port_error(fake_server, catalog_service) -> None:
    fake_server.start.side_effect = OSError("address in use")
    controller = DesktopController(fake_server, catalog_service, port=8765)

    controller.start()

    assert controller.state.status == "failed"
    assert "8765" in (controller.state.error or "")


def test_controller_adds_and_removes_local_files(
    fake_server, catalog_service, tmp_path: Path
) -> None:
    target = tmp_path / "models.json"
    target.write_text("[]", encoding="utf-8")
    controller = DesktopController(fake_server, catalog_service, port=8765)

    added = controller.add_file(target, FileKind.JSON, "模型")

    assert controller.state.files[0].id == added.id
    assert controller.state.files[0].path == target.resolve()
    controller.remove_file(added.id)
    assert controller.state.files == ()


def test_acknowledge_conflict_requires_explicit_confirmation(
    fake_server, catalog_service, allowed_json
) -> None:
    writer = Mock()
    controller = DesktopController(
        fake_server,
        catalog_service,
        port=8765,
        writer=writer,
    )

    assert controller.acknowledge_conflict(allowed_json.id, False) is False
    writer.acknowledge_current.assert_not_called()
    assert controller.acknowledge_conflict(allowed_json.id, True) is True
    writer.acknowledge_current.assert_called_once_with(allowed_json)


def test_local_urls_include_loopback_and_distinct_lan_addresses(monkeypatch) -> None:
    monkeypatch.setattr(
        "conf_edit.desktop.controller.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (None, None, None, None, ("192.168.1.20", 0)),
            (None, None, None, None, ("192.168.1.20", 0)),
            (None, None, None, None, ("127.0.0.1", 0)),
        ],
    )

    assert local_urls(8765) == (
        "http://127.0.0.1:8765",
        "http://192.168.1.20:8765",
    )


def test_port_can_change_only_while_stopped(fake_server, catalog_service) -> None:
    configure_port = Mock()
    controller = DesktopController(
        fake_server,
        catalog_service,
        port=8765,
        port_configurer=configure_port,
    )

    controller.set_port(9000)

    assert controller.port == 9000
    assert controller.state.urls[0] == "http://127.0.0.1:9000"
    configure_port.assert_called_once_with(9000)
    controller.start()
    with pytest.raises(RuntimeError):
        controller.set_port(9001)


def test_open_browser_uses_managed_url(fake_server, catalog_service) -> None:
    opener = Mock(return_value=True)
    controller = DesktopController(
        fake_server,
        catalog_service,
        port=8765,
        browser_opener=opener,
    )

    assert controller.open_browser() is True
    opener.assert_called_once_with("http://127.0.0.1:8765")
    with pytest.raises(ValueError):
        controller.open_browser("https://example.com")
