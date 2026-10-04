"""Fail closed before collection: no network, dotenv, secret files or real DB."""

import os
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def blocked(*args, **kwargs):
    raise RuntimeError("Forbidden operation in offline tests.")


def install():
    os.environ.clear()
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    sys.dont_write_bytecode = True

    def audit(event, args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.posix_spawn"}:
            blocked()
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).absolute()
            name = path.name.lower()
            if (
                name.startswith(".env")
                or name in {"credentials", "secrets", "passwords", "tokens"}
                or path.suffix.lower() in {".pem", ".key", ".p12", ".duckdb", ".db", ".sqlite"}
                or path.is_relative_to(ROOT / "traces")
                or path.is_relative_to(ROOT / "models")
                or "traces" in path.parts
                or "models" in path.parts
                or ("evals" in path.parts and name == "results.json")
                or (
                    path.suffix in {".json", ".toml", ".yaml", ".yml", ".txt", ".ini", ".conf"}
                    and re.search(r"credential|password|secret|api[_-]?key|token", name)
                )
                or path == ROOT / "evals" / "results.json"
            ):
                blocked()

    sys.addaudithook(audit)
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = dotenv.dotenv_values = dotenv.find_dotenv = blocked
    sys.modules["dotenv"] = dotenv
    import psycopg
    import psycopg2
    from google import genai

    psycopg.connect = psycopg2.connect = genai.Client = blocked
