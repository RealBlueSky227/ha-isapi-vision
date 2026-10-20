"""Read-only inventory and event probe; no Home Assistant installation required."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib
import json
import os
import sys
import types
from pathlib import Path

import aiohttp

# Load the protocol library without executing the integration's HA entry point.
package = types.ModuleType("isapi_vision_probe")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "isapi_vision")]
sys.modules[package.__name__] = package
api = importlib.import_module("isapi_vision_probe.api")
discovery = importlib.import_module("isapi_vision_probe.discovery")


async def probe(args, password: str) -> None:
    connector = aiohttp.TCPConnector(ssl=False) if args.insecure else None
    async with aiohttp.ClientSession(connector=connector) as session:
        client = api.IsapiVisionClient(session, args.host, args.username, password, args.port, args.https, args.channel)
        inventory = await client.inventory()
        result = {
            "model": inventory.device.get("model"),
            "firmware": inventory.device.get("firmwareVersion"),
            "endpoints": inventory.endpoints,
            "features": discovery.feature_report(inventory.features),
            "endpoint_probes": inventory.probes,
            "parameter_count": len(inventory.parameters),
            "parameters": inventory.parameters,
            "observed_events": [],
        }
        try:
            image = await client.snapshot()
            result["snapshot"] = {"jpeg": True, "bytes": len(image)}
        except api.CameraError:
            result["snapshot"] = {"jpeg": False}
        result["stream_connected"] = False

        def connected():
            result["stream_connected"] = True

        if args.events:
            try:
                async with asyncio.timeout(args.events):
                    async for event in client.events(connected):
                        summary = {
                            "event_type": event.event_type,
                            "state": event.state,
                            "channel": event.channel,
                            "targets": sorted(event.targets),
                        }
                        if summary not in result["observed_events"] and len(result["observed_events"]) < 100:
                            result["observed_events"].append(summary)
            except TimeoutError:
                pass
            except api.CameraError:
                result["stream_error"] = "stream_unavailable"
        output = Path(args.output)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key != "parameters"}, indent=2))
        print(f"Sanitized parameter inventory saved to {output.resolve()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--https", action="store_true")
    parser.add_argument("--insecure", action="store_true", help="Skip HTTPS certificate verification")
    parser.add_argument("--events", type=int, default=30, help="Observe events for this many seconds (0 disables)")
    parser.add_argument("--output", default="camera-inventory.json")
    parser.add_argument("--password-env", help="Optional environment variable containing the camera password")
    args = parser.parse_args()
    password = os.environ[args.password_env] if args.password_env else getpass.getpass("Camera password: ")
    try:
        asyncio.run(probe(args, password))
    except api.CameraError as err:
        parser.exit(1, f"Camera probe failed: {err}\n")


if __name__ == "__main__":
    main()
