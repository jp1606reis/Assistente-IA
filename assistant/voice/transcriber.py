"""Captura áudio com PyAudio e encaminha transcrições do Gemini Live (versão enxuta)."""

import array
import asyncio
import queue
import threading
import time
from typing import Callable, Optional

import pyaudio
from google import genai
from google.genai import types

from ..config import carregar_api_key

CHUNK = 1024
RATE = 16000
MODEL = "gemini-3.5-transcribe-live"


class GeminiLiveTranscriber:
    def __init__(
        self,
        fila_transcricoes: queue.Queue,
        callback_status: Optional[Callable[[str], None]] = None,
    ):
        self.fila = fila_transcricoes
        self.callback_status = callback_status or (lambda _s: None)
        self.api_key = carregar_api_key()
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

        self.ativo = False
        self.thread: Optional[threading.Thread] = None
        self._fila_audio: queue.Queue = queue.Queue()

        # Diagnóstico mínimo: leia de qualquer lugar com self.stats
        self.stats = {"capturados": 0, "enviados": 0, "textos": 0, "pico": 0}

    def _notificar(self, status: str):
        print(f"[Gemini] {status}")
        self.callback_status(status)

    def tem_dependencias_completas(self) -> bool:
        return self.client is not None

    def diagnostico(self) -> str:
        if not self.api_key:
            return "Microfone inativo: configure GEMINI_API_KEY no arquivo .env."
        return "Transcrição Gemini Live pronta."

    def esta_rodando(self) -> bool:
        return self.ativo and self.thread is not None and self.thread.is_alive()

    def iniciar(self):
        if self.esta_rodando():
            return
        self._fila_audio = queue.Queue()
        self.stats = {"capturados": 0, "enviados": 0, "textos": 0, "pico": 0}
        self.ativo = True
        self.thread = threading.Thread(target=self._executar, daemon=True)
        self.thread.start()

    def parar(self):
        self.ativo = False
        self._fila_audio.put(None)

    def _callback_pyaudio(self, in_data, _frames, _time, _status):
        if self.ativo and in_data:
            self._fila_audio.put(in_data)
            self.stats["capturados"] += 1
            # pico de amplitude do chunk: ~0 = silêncio, milhares = voz
            amostras = array.array("h", in_data)
            self.stats["pico"] = max(map(abs, amostras)) if amostras else 0
        return None, pyaudio.paContinue

    def _executar(self):
        try:
            asyncio.run(self._executar_async())
        except Exception as erro:
            self._notificar(f"Erro no microfone Gemini: {erro}")
        finally:
            self.ativo = False

    async def _executar_async(self):
        if not self.client:
            self._notificar(self.diagnostico())
            return

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16, channels=1, rate=RATE, input=True,
            frames_per_buffer=CHUNK, stream_callback=self._callback_pyaudio,
        )
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            input_audio_transcription=types.AudioTranscriptionConfig(
                language_codes=["pt-BR"]
            ),
        )
        try:
            stream.start_stream()
            async with self.client.aio.live.connect(model=MODEL, config=config) as session:
                self._notificar("🎤 Microfone ativo: Gemini Live ouvindo...")
                tarefas = [
                    asyncio.create_task(self._enviar(session)),
                    asyncio.create_task(self._receber(session)),
                    asyncio.create_task(self._avisar_se_mudo()),
                ]
                feitas, pendentes = await asyncio.wait(
                    tarefas, return_when=asyncio.FIRST_COMPLETED
                )
                for t in pendentes:
                    t.cancel()
                for t in feitas:
                    t.result()  # propaga erro, se houver
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    async def _enviar(self, session):
        while self.ativo:
            dados = await asyncio.to_thread(self._fila_audio.get)
            if dados is None:
                return
            await session.send_realtime_input(
                media=types.Blob(data=dados, mime_type=f"audio/pcm;rate={RATE}")
            )
            self.stats["enviados"] += 1

    async def _receber(self, session):
        async for resposta in session.receive():
            conteudo = resposta.server_content
            transcricao = conteudo.input_transcription if conteudo else None
            if transcricao and transcricao.text:
                texto = transcricao.text.strip()
                if texto:
                    self.stats["textos"] += 1
                    self.fila.put(texto)

    async def _avisar_se_mudo(self):
        """Único watchdog: avisa se em 5s não chegou áudio ou só chegou silêncio."""
        await asyncio.sleep(5)
        if self.stats["capturados"] == 0:
            self._notificar("⚠️ Nenhum áudio chegando do microfone.")
        elif self.stats["pico"] < 50 and self.stats["textos"] == 0:
            self._notificar("⚠️ Só silêncio no microfone (mudo ou dispositivo errado?).")
        await asyncio.Event().wait()  # fica parado até ser cancelado