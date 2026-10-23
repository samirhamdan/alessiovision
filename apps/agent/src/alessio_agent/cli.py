"""Linha de comando do agente. Todas as opções também podem vir de variáveis de ambiente."""

import argparse
import logging
import os
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

from alessio_agent.runner import Agent, AgentSettings


def _parse_datetime(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise argparse.ArgumentTypeError("informe o fuso, ex.: 2026-10-23T23:00:00-03:00")
    return moment


def build_parser() -> argparse.ArgumentParser:
    env = os.environ.get
    parser = argparse.ArgumentParser(prog="alessio-agent", description=__doc__)
    parser.add_argument("--api-url", default=env("ALESSIO_API_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=env("ALESSIO_AGENT_TOKEN"), help="credencial do agente")
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path(env("ALESSIO_SOURCES_FILE", "sources.json")),
        help="JSON local {source_ref: uri}; as URIs nunca saem desta máquina",
    )
    parser.add_argument(
        "--state-dir", type=Path, default=Path(env("ALESSIO_STATE_DIR", ".alessio-agent"))
    )
    parser.add_argument(
        "--detector", choices=["hog", "ultralytics"], default=env("ALESSIO_DETECTOR", "hog")
    )
    parser.add_argument("--detector-model", default=env("ALESSIO_DETECTOR_MODEL"))
    parser.add_argument(
        "--replay-start",
        type=_parse_datetime,
        default=_parse_datetime(env("ALESSIO_REPLAY_START"))
        if env("ALESSIO_REPLAY_START")
        else None,
        help="horário simulado do primeiro quadro de arquivos de vídeo (padrão: agora)",
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        default=env("ALESSIO_REALTIME", "").lower() in ("1", "true", "yes"),
        help="reproduz arquivos no ritmo real em vez de o mais rápido possível",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("ALESSIO_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not args.token:
        print("erro: informe --token ou ALESSIO_AGENT_TOKEN", file=sys.stderr)
        return 2
    settings = AgentSettings(
        api_url=args.api_url,
        token=args.token,
        sources_file=args.sources,
        state_dir=args.state_dir,
        detector=args.detector,
        detector_model=args.detector_model,
        replay_start=args.replay_start,
        realtime=args.realtime,
    )
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    delivered = Agent(settings).run(stop)
    return 0 if delivered else 1


if __name__ == "__main__":
    sys.exit(main())
