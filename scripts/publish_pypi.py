"""Build, check, and publish llm-observe-proxy distributions to PyPI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover - only hit outside the dev environment
    raise SystemExit(
        "python-dotenv is required. Install release dependencies with "
        "`python -m pip install -e .[dev]`."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build, validate, and publish llm-observe-proxy to PyPI."
    )
    parser.add_argument(
        "--repository",
        default="pypi",
        help="Twine repository name to publish to, such as pypi or testpypi.",
    )
    parser.add_argument(
        "--repository-url",
        help="Explicit repository URL. When provided, this overrides --repository.",
    )
    parser.add_argument(
        "--token-env",
        help=(
            "Environment variable containing the API token. Defaults to PYPI_TOKEN, "
            "or TEST_PYPI_TOKEN for testpypi."
        ),
    )
    parser.add_argument(
        "--env-file",
        default=str(ROOT / ".env"),
        help="dotenv file to load before reading token environment variables.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and run twine check, but do not upload or require a token.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Pass --skip-existing to twine upload.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep the existing dist directory before building.",
    )
    return parser.parse_args()


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    printable = " ".join(command)
    print(f"+ {printable}", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def clean_dist() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)


def load_env_file(env_file: str) -> None:
    path = Path(env_file)
    if not path.exists():
        return

    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8", "utf-8-sig", "utf-16"):
        try:
            load_dotenv(path, encoding=encoding)
            return
        except UnicodeDecodeError as exc:
            last_error = exc

    raise SystemExit(f"Unable to read dotenv file {path} as UTF-8 or UTF-16.") from last_error


def distribution_files() -> list[str]:
    if not DIST_DIR.exists():
        raise SystemExit("dist directory was not created by the build step.")
    files = sorted(str(path) for path in DIST_DIR.iterdir() if path.is_file())
    if not files:
        raise SystemExit("No distribution files found in dist.")
    return files


def default_token_env(repository: str) -> str:
    normalized = repository.lower().replace("-", "")
    if normalized == "testpypi":
        return "TEST_PYPI_TOKEN"
    return "PYPI_TOKEN"


def twine_environment(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    token_env = args.token_env or default_token_env(args.repository)
    token = env.get(token_env)

    if not token and env.get("TWINE_PASSWORD"):
        token = env["TWINE_PASSWORD"]

    if not token:
        raise SystemExit(
            f"Missing PyPI token. Set {token_env} in the environment or .env file."
        )

    env.setdefault("TWINE_USERNAME", "__token__")
    env["TWINE_PASSWORD"] = token
    return env


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)

    if not args.no_clean:
        clean_dist()

    run([sys.executable, "-m", "build"])
    files = distribution_files()
    run([sys.executable, "-m", "twine", "check", *files])

    if args.dry_run:
        print("Dry run complete. Skipping upload.")
        return 0

    upload_command = [sys.executable, "-m", "twine", "upload"]
    if args.repository_url:
        upload_command.extend(["--repository-url", args.repository_url])
    else:
        upload_command.extend(["--repository", args.repository])
    if args.skip_existing:
        upload_command.append("--skip-existing")
    upload_command.extend(files)

    run(upload_command, env=twine_environment(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
