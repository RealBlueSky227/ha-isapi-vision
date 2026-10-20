"""Inspect status and sanitized XML of explicitly listed read-only ISAPI paths."""

import argparse
import asyncio
import getpass
import importlib
import json
import os

import aiohttp
from probe import api

protocol = importlib.import_module("isapi_vision_probe.protocol")


async def inspect(args, password):
    result = {}
    async with aiohttp.ClientSession() as session:
        client = api.IsapiVisionClient(session, args.host, args.username, password)
        for path in args.path:
            if not path.startswith("/ISAPI/") or "?" in path:
                raise ValueError("Only explicit ISAPI paths without queries are accepted")
            async with client._request(path) as response:
                body = await response.content.read(1048576)
                item = {
                    "status": response.status,
                    "content_type": response.headers.get("Content-Type"),
                    "bytes": len(body),
                }
                if not body.startswith(b"\xff\xd8"):
                    try:
                        item["parameters"] = protocol.flatten(
                            protocol.parse_xml(body), (password, args.username, args.host)
                        )
                    except ValueError:
                        item["parameters"] = "not_xml"
                result[path] = item
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password-env")
    parser.add_argument("--path", action="append", required=True)
    args = parser.parse_args()
    password = os.environ[args.password_env] if args.password_env else getpass.getpass("Camera password: ")
    asyncio.run(inspect(args, password))
