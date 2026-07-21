"""Capture real desktop/mobile Chrome screenshots and report horizontal overflow."""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from websockets.asyncio.client import connect


ROOT = Path(__file__).resolve().parents[1]
CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


def wait_for(url: str, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"Server did not become ready: {url}")


async def cdp_call(ws, call_id: int, method: str, params: dict | None = None) -> dict:
    await ws.send(json.dumps({"id": call_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(await ws.recv())
        if message.get("id") == call_id:
            if "error" in message:
                raise RuntimeError(message["error"])
            return message.get("result", {})


async def capture(
    chrome: Path,
    url: str,
    output: Path,
    width: int,
    height: int,
    mobile: bool,
    port: int,
    action: str | None = None,
) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    # Chrome on Windows can briefly keep Cache/Journal locked after exit.
    with tempfile.TemporaryDirectory(
        dir=output.parent,
        ignore_cleanup_errors=True,
    ) as profile:
        browser = subprocess.Popen(
            [
                str(chrome),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            version_url = f"http://127.0.0.1:{port}/json/version"
            wait_for(version_url)
            new_tab = Request(
                f"http://127.0.0.1:{port}/json/new?{quote('about:blank', safe=':')}",
                method="PUT",
            )
            with urlopen(new_tab, timeout=5) as response:
                target = json.load(response)
            async with connect(target["webSocketDebuggerUrl"], origin="http://localhost") as ws:
                call_id = 1
                await cdp_call(ws, call_id, "Page.enable")
                call_id += 1
                await cdp_call(
                    ws,
                    call_id,
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": mobile,
                    },
                )
                call_id += 1
                await cdp_call(ws, call_id, "Page.navigate", {"url": url})
                await asyncio.sleep(4)
                if action:
                    call_id += 1
                    action_result = await cdp_call(
                        ws,
                        call_id,
                        "Runtime.evaluate",
                        {
                            "expression": action,
                            "awaitPromise": True,
                            "returnByValue": True,
                        },
                    )
                    if action_result.get("exceptionDetails"):
                        details = action_result["exceptionDetails"]
                        raise RuntimeError(
                            details.get("exception", {}).get("description")
                            or details.get("text")
                            or "Chrome action failed"
                        )
                    await asyncio.sleep(3)
                call_id += 1
                await cdp_call(
                    ws,
                    call_id,
                    "Runtime.evaluate",
                    {"expression": "window.scrollTo(0, 0)"},
                )
                await asyncio.sleep(0.25)
                call_id += 1
                metrics_result = await cdp_call(
                    ws,
                    call_id,
                    "Runtime.evaluate",
                    {
                        "returnByValue": True,
                        "expression": """
                            (() => {
                              const root = document.documentElement;
                              const visible = el => Boolean(
                                el && !el.hidden && getComputedStyle(el).display !== 'none'
                              );
                              const overflow = [...document.querySelectorAll('body *')]
                                .map(el => ({el, r: el.getBoundingClientRect()}))
                                .filter(x => x.r.right > innerWidth + 1 || x.r.left < -1)
                                .slice(0, 12)
                                .map(x => ({
                                  tag: x.el.tagName,
                                  cls: x.el.className || '',
                                  left: Math.round(x.r.left),
                                  right: Math.round(x.r.right)
                                }));
                              return {
                                scrollY,
                                innerWidth,
                                clientWidth: root.clientWidth,
                                scrollWidth: root.scrollWidth,
                                visibleHeroes: [...document.querySelectorAll('.doc-hero')]
                                  .filter(el => !el.hidden).length,
                                visibleLayouts: [...document.querySelectorAll('.doc-layout')]
                                  .filter(el => !el.hidden).length,
                                soloSetupVisible: visible(document.getElementById('solo-setup')),
                                soloActiveVisible: visible(document.getElementById('solo-active-filter')),
                                soloLeagueOptions: document.querySelectorAll('#solo-league-select option').length,
                                recognitionButtons: document.querySelectorAll('#recognition-selector button').length,
                                timelineItems: document.querySelectorAll('#quiz-area .timeline-item').length,
                                resultModalVisible: visible(document.querySelector('.solo-result-modal')),
                                resultQuickFacts: document.querySelectorAll(
                                  '.solo-result-modal .rm-quick-facts > *'
                                ).length,
                                resultPoolLines: document.querySelectorAll(
                                  '.solo-result-modal .rm-pool-line'
                                ).length,
                                overflow
                              };
                            })()
                        """,
                    },
                )
                call_id += 1
                image_result = await cdp_call(
                    ws,
                    call_id,
                    "Page.captureScreenshot",
                    {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
                )
                output.write_bytes(base64.b64decode(image_result["data"]))
                return metrics_result["result"]["value"]
        finally:
            browser.terminate()
            try:
                browser.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser.kill()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(".tmp-adsense-qa"))
    parser.add_argument("--port", type=int, default=9003)
    parser.add_argument("--db", type=Path, default=Path("data/football_quiz_v2.db"))
    parser.add_argument("--only", action="append", help="Capture only the named job; repeat as needed.")
    args = parser.parse_args()
    chrome = next((path for path in CHROME_CANDIDATES if path.exists()), None)
    if chrome is None:
        raise RuntimeError("Chrome executable not found")

    server_env = os.environ.copy()
    server_env["APP_DB_PATH"] = str(args.db)
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.realtime.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--workers",
            "1",
        ],
        cwd=ROOT,
        env=server_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{args.port}"
        try:
            wait_for(f"{base}/api/health")
        except RuntimeError as exc:
            if server.poll() is not None and server.stderr:
                details = server.stderr.read().strip()
                if details:
                    raise RuntimeError(f"{exc}\n{details}") from exc
            raise
        pages = (
            ("about", "/about"),
            ("methodology", "/methodology"),
            ("contact", "/contact"),
            ("privacy", "/privacy"),
            ("terms", "/terms"),
        )
        jobs = []
        debug_port = 9331
        for name, path in pages:
            jobs.append((f"{name}-desktop", f"{base}{path}", 1440, 1100, False, debug_port, None, "doc"))
            debug_port += 1
            jobs.append((f"{name}-mobile", f"{base}{path}", 390, 844, True, debug_port, None, "doc"))
            debug_port += 1
        jobs.extend((
            (
                "about-light-desktop",
                f"{base}/about",
                1440,
                900,
                False,
                debug_port,
                """
                (() => {
                  document.documentElement.dataset.theme = 'light';
                  localStorage.setItem('theme', 'light');
                })()
                """,
                "doc",
            ),
            (
                "solo-setup-desktop",
                f"{base}/#/solo",
                1440,
                1100,
                False,
                debug_port + 1,
                None,
                "solo-setup",
            ),
            (
                "solo-run-mobile",
                f"{base}/#/solo",
                390,
                844,
                True,
                debug_port + 2,
                """
                (async () => {
                  const select = document.getElementById('solo-league-select');
                  select.value = 'TR1';
                  setQuizLeague('TR1');
                  const button = document.querySelector(
                    '#recognition-selector [data-recognition="known"]'
                  );
                  setRecognition('known', button);
                  await startSelectedRun();
                })()
                """,
                "solo-run",
            ),
            (
                "result-correct-desktop",
                f"{base}/#/solo",
                1440,
                900,
                False,
                debug_port + 3,
                """
                (async () => {
                  const select = document.getElementById('solo-league-select');
                  select.value = 'TR1';
                  setQuizLeague('TR1');
                  const button = document.querySelector(
                    '#recognition-selector [data-recognition="known"]'
                  );
                  setRecognition('known', button);
                  await startSelectedRun();
                  showQuizResult(true, recordCorrectAnswer());
                })()
                """,
                "result",
            ),
            (
                "result-skipped-mobile",
                f"{base}/#/solo",
                390,
                844,
                True,
                debug_port + 4,
                """
                (async () => {
                  const select = document.getElementById('solo-league-select');
                  select.value = 'TR1';
                  setQuizLeague('TR1');
                  const button = document.querySelector(
                    '#recognition-selector [data-recognition="known"]'
                  );
                  setRecognition('known', button);
                  await startSelectedRun();
                  passQuiz();
                })()
                """,
                "result",
            ),
        ))
        results = {}
        kinds = {}
        if args.only:
            selected_jobs = set(args.only)
            jobs = [job for job in jobs if job[0] in selected_jobs]
            missing_jobs = selected_jobs.difference(job[0] for job in jobs)
            if missing_jobs:
                raise ValueError(f"Unknown visual QA jobs: {', '.join(sorted(missing_jobs))}")
        for name, url, width, height, mobile, debug_port, action, kind in jobs:
            results[name] = await capture(
                chrome,
                url,
                args.output_dir / f"{name}.png",
                width,
                height,
                mobile,
                debug_port,
                action,
            )
            kinds[name] = kind
        print(json.dumps(results, ensure_ascii=True, indent=2))
        for name, result in results.items():
            if result["scrollWidth"] > result["clientWidth"]:
                return 1
            if kinds[name] != "result" and result["scrollY"] != 0:
                return 1
            if kinds[name] == "doc" and (
                result["visibleHeroes"] != 1 or result["visibleLayouts"] != 1
            ):
                return 1
            if kinds[name] == "solo-setup" and (
                not result["soloSetupVisible"]
                or result["soloActiveVisible"]
                or result["soloLeagueOptions"] < 14
                or result["recognitionButtons"] != 3
            ):
                return 1
            if kinds[name] == "solo-run" and (
                result["soloSetupVisible"]
                or not result["soloActiveVisible"]
                or result["timelineItems"] < 2
            ):
                return 1
            if kinds[name] == "result" and (
                not result["resultModalVisible"]
                or result["resultQuickFacts"] != 3
                or result["resultPoolLines"] != 1
            ):
                return 1
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
