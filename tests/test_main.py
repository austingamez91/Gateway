from __future__ import annotations

from pathlib import Path
from typing import Any

from gatewaykit import __main__


def test_main_starts_uvicorn_on_configured_port(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gateway.yaml"
    config_path.write_text(
        """
gateway:
  port: 8123
routes: []
""",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(__main__.uvicorn, "run", fake_run)

    exit_code = __main__.main([str(config_path)])

    assert exit_code == 0
    assert captured["kwargs"]["host"] == "0.0.0.0"
    assert captured["kwargs"]["port"] == 8123
    assert captured["app"].state.config.gateway.port == 8123
