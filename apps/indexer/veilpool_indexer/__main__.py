"""Command-line entry point for the VeilPool local-chain indexer."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from pathlib import Path

from . import __version__
from .api import create_app
from .config import ConfigError, Settings
from .events import EventDecodeError
from .indexer import ChainIdError, Indexer, ReorgTooDeep, ScanError
from .rpc import RpcClient, RpcError
from .store import Store

LOGGER = logging.getLogger("veilpool_indexer")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veilpool-indexer",
        description=(
            "LOCAL CHAIN ONLY. Index VeilPool public events from Anvil and serve "
            "read-only chain facts. Set INDEXER_VERIFIER_KIND=mock (default) or "
            "groth16 to match the deployed verifier."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="sync once, print a JSON summary, and exit (no HTTP server)",
    )
    parser.add_argument(
        "--no-poll",
        action="store_true",
        help="serve the read API without starting the background poller",
    )
    parser.add_argument("--rpc-url", help="override ANVIL_RPC_URL")
    parser.add_argument("--contract", help="override VEILPOOL_ADDRESS")
    parser.add_argument("--db", help="override INDEXER_DB")
    parser.add_argument("--start-block", type=int, help="override INDEXER_START_BLOCK")
    parser.add_argument("--host", help="override INDEXER_HOST")
    parser.add_argument("--port", type=int, help="override INDEXER_PORT")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def _settings_from_args(args: argparse.Namespace) -> Settings:
    base = Settings.from_env(validate=False)
    overrides: dict[str, object] = {}
    if args.rpc_url:
        overrides["rpc_url"] = args.rpc_url
    if args.contract:
        overrides["contract_address"] = args.contract
    if args.db:
        overrides["database_path"] = Path(args.db)
    if args.start_block is not None:
        overrides["start_block"] = args.start_block
    if args.host:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    return base.with_overrides(**overrides)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        settings = _settings_from_args(args)
    except (ConfigError, ValueError) as exc:
        LOGGER.error("configuration error: %s", exc)
        return 2

    store = Store(settings.database_path)
    store.initialize()

    if args.once:
        rpc = RpcClient(
            settings.rpc_url,
            timeout=settings.rpc_timeout,
            retries=settings.rpc_retries,
        )
        try:
            indexer = Indexer(settings, rpc, store)
            result = indexer.sync_once()
            print(json.dumps(result.as_dict(), indent=2))
            return 0
        except (ChainIdError, ReorgTooDeep, ScanError, RpcError, EventDecodeError) as exc:
            store.set_meta("last_error", f"{type(exc).__name__}: {exc}")
            LOGGER.error("sync failed: %s", exc)
            return 2
        finally:
            rpc.close()

    if not args.no_poll:
        stop_event = threading.Event()

        def poll() -> None:
            rpc = RpcClient(
                settings.rpc_url,
                timeout=settings.rpc_timeout,
                retries=settings.rpc_retries,
            )
            indexer = Indexer(settings, rpc, store)
            try:
                indexer.sync_forever(stop_event)
            finally:
                rpc.close()

    app = create_app(settings, store)

    if not args.no_poll:
        thread = threading.Thread(target=poll, name="veilpool-poller", daemon=True)
        thread.start()

    import uvicorn

    LOGGER.info(
        "serving indexer API on http://%s:%s (contract=%s chain-allow-list=%s)",
        settings.host,
        settings.port,
        settings.contract_address,
        sorted(settings.allowed_chain_ids),
    )
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
