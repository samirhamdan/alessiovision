"""Linha de comando do agente.

    alessio-agent enroll --api-url https://painel.exemplo.com.br --code K7QX-M2PA-9TRD-H4WN
    alessio-agent run --sources sources.json

``run`` é o padrão quando nenhum subcomando é informado. As opções também podem
vir de variáveis de ambiente (ALESSIO_*).
"""

import argparse
import logging
import os
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

from alessio_agent.cloud import AuthError
from alessio_agent.enrollment import EnrollmentError, enroll, load_credentials
from alessio_agent.runner import Agent, AgentSettings

COMMANDS = {"enroll", "run"}


def _parse_datetime(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise argparse.ArgumentTypeError("informe o fuso, ex.: 2026-10-23T23:00:00-03:00")
    return moment


def build_parser() -> argparse.ArgumentParser:
    env = os.environ.get
    parser = argparse.ArgumentParser(
        prog="alessio-agent",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--api-url", default=env("ALESSIO_API_URL"))
    common.add_argument(
        "--state-dir", type=Path, default=Path(env("ALESSIO_STATE_DIR", ".alessio-agent"))
    )

    enroll_cmd = commands.add_parser(
        "enroll", parents=[common], help="ativa o agente com o código do painel"
    )
    enroll_cmd.add_argument("--code", required=True, help="código de ativação exibido no painel")

    run = commands.add_parser("run", parents=[common], help="analisa as câmeras (padrão)")
    run.add_argument(
        "--token",
        default=env("ALESSIO_AGENT_TOKEN"),
        help="credencial do agente; sem ela, usa a salva por 'enroll'",
    )
    run.add_argument(
        "--sources",
        type=Path,
        default=Path(env("ALESSIO_SOURCES_FILE", "sources.json")),
        help="JSON local {source_ref: uri}; as URIs nunca saem desta máquina",
    )
    run.add_argument(
        "--detector", choices=["hog", "ultralytics"], default=env("ALESSIO_DETECTOR", "hog")
    )
    run.add_argument("--detector-model", default=env("ALESSIO_DETECTOR_MODEL"))
    run.add_argument(
        "--replay-start",
        type=_parse_datetime,
        default=_parse_datetime(env("ALESSIO_REPLAY_START"))
        if env("ALESSIO_REPLAY_START")
        else None,
        help="horário simulado do primeiro quadro de arquivos de vídeo (padrão: agora)",
    )
    run.add_argument(
        "--realtime",
        action="store_true",
        default=env("ALESSIO_REALTIME", "").lower() in ("1", "true", "yes"),
        help="reproduz arquivos no ritmo real em vez de o mais rápido possível",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help")):
        argv.insert(0, "run")
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("ALESSIO_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.command == "enroll":
        return _enroll(args)
    return _run(args)


def _enroll(args: argparse.Namespace) -> int:
    if not args.api_url:
        print("erro: informe --api-url ou ALESSIO_API_URL", file=sys.stderr)
        return 2
    try:
        result = enroll(args.api_url, args.code, args.state_dir)
    except EnrollmentError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"Agente '{result.agent_name}' ativado para {result.organization_name}.")
    print(f"Credencial salva em {args.state_dir / 'credentials.json'}.")
    return 0


def _run(args: argparse.Namespace) -> int:
    saved = load_credentials(args.state_dir) or {}
    token = args.token or saved.get("token")
    api_url = args.api_url or saved.get("api_url") or "http://localhost:8000"
    if not token:
        print(
            "erro: agente não ativado. Rode 'alessio-agent enroll --code <código do painel>' "
            "ou informe --token.",
            file=sys.stderr,
        )
        return 2
    settings = AgentSettings(
        api_url=api_url,
        token=token,
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
    try:
        delivered = Agent(settings).run(stop)
    except AuthError:
        print(
            "erro: a plataforma recusou a credencial deste agente (revogada ou substituída). "
            "Gere um novo código em Agentes, no painel, e rode 'alessio-agent enroll' de novo.",
            file=sys.stderr,
        )
        return 3
    return 0 if delivered else 1


if __name__ == "__main__":
    sys.exit(main())
