"""Load protocol modules without requiring Home Assistant on this machine."""

import importlib
import sys
import types
from pathlib import Path

package = types.ModuleType("isapi_vision_test")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "isapi_vision")]
sys.modules.setdefault("isapi_vision_test", package)
protocol = importlib.import_module("isapi_vision_test.protocol")
api = importlib.import_module("isapi_vision_test.api")
