"""Local HTTP bridge for voice commands sent to the YouTube player."""

import hmac
import ipaddress
import json
import secrets
import threading
import webbrowser
from collections import deque
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit


_COMANDOS_PERMITIDOS = {"play", "pause", "forward", "rewind", "mute", "unmute"}
_CARACTERES_ID_VIDEO = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


class PlayerYouTube:
    def __init__(self, html_path: Path):
        self._arquivo_html = html_path
        self._trava = threading.Lock()
        self._token = secrets.token_urlsafe(32)
        self._sessao = ""
        self._comandos: deque[dict[str, int | str]] = deque(maxlen=100)
        self._proximo_id = 0
        self._servidor: ThreadingHTTPServer | None = None
        self._thread_servidor: threading.Thread | None = None

    def abrir(self, video_id: str, titulo: str) -> None:
        self._validar_video_id(video_id)
        self._iniciar_servidor()

        with self._trava:
            self._sessao = secrets.token_urlsafe(18)
            self._comandos.clear()
            self._proximo_id = 0
            sessao = self._sessao

        servidor = self._servidor
        if servidor is None:
            raise RuntimeError("O servidor local do player não foi iniciado.")

        endereco, porta = servidor.server_address
        query = urlencode({
            "video_id": video_id,
            "title": titulo,
            "token": self._token,
            "session": sessao,
        })
        url_player = f"http://{endereco}:{porta}/player?{query}"
        if not webbrowser.open(url_player):
            with self._trava:
                self._sessao = ""
                self._comandos.clear()
            raise RuntimeError("Não foi possível abrir o player no navegador padrão.")

    def enviar_comando(self, comando: str) -> None:
        if comando not in _COMANDOS_PERMITIDOS:
            raise ValueError("Comando de reprodução desconhecido.")
        with self._trava:
            if not self._sessao:
                raise RuntimeError("Selecione um vídeo antes de enviar comandos.")
            self._adicionar_comando({"command": comando})

    def fechar(self) -> None:
        servidor = self._servidor
        if servidor is None:
            return

        self._servidor = None
        with self._trava:
            self._sessao = ""
            self._comandos.clear()

        servidor.shutdown()
        servidor.server_close()
        if self._thread_servidor is not None:
            self._thread_servidor.join(timeout=2)
            self._thread_servidor = None

    def _adicionar_comando(self, comando: dict[str, int | str]) -> None:
        self._proximo_id += 1
        self._comandos.append({"id": self._proximo_id, **comando})

    def _iniciar_servidor(self) -> None:
        if self._servidor is not None:
            return

        handler = partial(_AtendentePlayer, player=self)
        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._servidor.daemon_threads = True
        self._thread_servidor = threading.Thread(
            target=self._servidor.serve_forever,
            name="youtube-player-bridge",
            daemon=True,
        )
        self._thread_servidor.start()

    @staticmethod
    def _validar_video_id(video_id: str) -> None:
        if len(video_id) != 11 or any(
            char not in _CARACTERES_ID_VIDEO for char in video_id
        ):
            raise ValueError("O identificador do vídeo do YouTube é inválido.")

    def _atender_requisicao(self, handler: BaseHTTPRequestHandler) -> None:
        if not self._cliente_local(handler.client_address[0]):
            handler.send_error(403)
            return

        partes = urlsplit(handler.path)
        parametros = parse_qs(partes.query)
        if not self._autorizado(parametros):
            handler.send_error(403)
            return

        sessao = parametros.get("session", [""])[0]
        if not self._sessao_valida(sessao):
            handler.send_error(404)
            return

        if partes.path == "/player":
            self._servir_player(handler)
        elif partes.path == "/commands":
            self._servir_comandos(handler, parametros, sessao)
        else:
            handler.send_error(404)

    def _servir_player(self, handler: BaseHTTPRequestHandler) -> None:
        try:
            conteudo = self._arquivo_html.read_bytes()
        except OSError:
            handler.send_error(500, "Não foi possível carregar o player HTML.")
            return
        self._responder(handler, 200, conteudo, "text/html; charset=utf-8")

    def _servir_comandos(
        self,
        handler: BaseHTTPRequestHandler,
        parametros: dict[str, list[str]],
        sessao: str,
    ) -> None:
        try:
            depois_de = max(0, int(parametros.get("after", ["0"])[0]))
        except ValueError:
            handler.send_error(400, "Sequência de comando inválida.")
            return

        with self._trava:
            if sessao != self._sessao:
                handler.send_error(404)
                return
            comandos = [
                comando for comando in self._comandos
                if int(comando["id"]) > depois_de
            ]

        conteudo = json.dumps({"commands": comandos}).encode("utf-8")
        self._responder(
            handler, 200, conteudo, "application/json; charset=utf-8"
        )

    @staticmethod
    def _responder(
        handler: BaseHTTPRequestHandler,
        codigo: int,
        conteudo: bytes,
        tipo_conteudo: str,
    ) -> None:
        handler.send_response(codigo)
        handler.send_header("Content-Type", tipo_conteudo)
        handler.send_header("Content-Length", str(len(conteudo)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.end_headers()
        handler.wfile.write(conteudo)

    def _autorizado(self, parametros: dict[str, list[str]]) -> bool:
        recebido = parametros.get("token", [""])[0]
        return hmac.compare_digest(recebido, self._token)

    def _sessao_valida(self, sessao: str) -> bool:
        with self._trava:
            return bool(sessao) and sessao == self._sessao

    @staticmethod
    def _cliente_local(endereco: str) -> bool:
        try:
            return ipaddress.ip_address(endereco).is_loopback
        except ValueError:
            return False


class _AtendentePlayer(BaseHTTPRequestHandler):
    def __init__(self, *args, player: PlayerYouTube, **kwargs):
        self._player = player
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        self._player._atender_requisicao(self)

    def log_message(self, _format: str, *_args) -> None:
        del _format, _args
