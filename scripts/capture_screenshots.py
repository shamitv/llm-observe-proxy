from __future__ import annotations

import argparse
import os
import socket
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

from llm_observe_proxy.app import create_app
from llm_observe_proxy.config import Settings

SCREENSHOTS = [
    ("requests.png", "/admin"),
    ("simple-request.png", "/admin/requests/1?mode=text"),
    ("tool-calls.png", "/admin/requests/2?mode=tool"),
    ("images.png", "/admin/requests/3?mode=auto"),
    ("streaming.png", "/admin/requests/4?mode=sse"),
    ("settings.png", "/admin/settings"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture admin UI screenshots.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", default=Path("docs/screenshots"), type=Path)
    parser.add_argument("--port", default=8091, type=int)
    args = parser.parse_args()

    _assert_port_available(args.port)
    args.output.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        database_url=f"sqlite:///{args.database.as_posix()}",
        upstream_url="http://localhost:8000/v1",
    )
    app = create_app(settings)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server(args.port)
    try:
        _capture(args.port, args.output)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _capture(port: int, output: Path) -> None:
    browser_path = _browser_executable()
    base_url = f"http://127.0.0.1:{port}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_path, headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        for filename, path in SCREENSHOTS:
            page.goto(base_url + path, wait_until="networkidle")
            page.screenshot(path=str(output / filename), full_page=True)
        browser.close()


def _browser_executable() -> str:
    candidates = [
        os.environ.get("LLM_OBSERVE_SCREENSHOT_BROWSER"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("No Chrome/Edge executable found for screenshot capture.")


def _wait_for_server(port: int) -> None:
    import httpx

    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=0.5)
            if response.status_code == 200:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(f"screenshot server did not start: {last_error}")


def _assert_port_available(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Port {port} is already in use.")


if __name__ == "__main__":
    main()
