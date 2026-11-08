"""Tela de pesquisa do YouTube."""

import io
import threading
import tkinter as tk
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from tkinter import ttk
from PIL import Image, ImageTk, ImageOps
from ..services import (
    ResultadoPesquisa,
    RespostaPesquisa,
    baixar_thumbnail,
    pesquisar_youtube,
)
from ..player.youtube_player_bridge import PlayerYouTube


class TelaYouTube(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=(20, 12))
        self.app = app
        self._imagem: ImageTk.PhotoImage | None = None
        self._capa_pil: Image.Image | None = None   # original, para reajustar ao redimensionar
        self._alvo_capa: tuple[int, int] | None = None
        self._job_redimensionar: str | None = None
        self._busca_id = 0
        self.resultados: list[ResultadoPesquisa] = []
        self.indice_atual = 0
        self._player_aberto = False
        self._player = PlayerYouTube(
            Path(__file__).resolve().parents[1] / "player" / "youtube_player.html"
        )

        self._definir_estilos()

        # Cabeçalho: título à esquerda, Voltar à direita
        topo = ttk.Frame(self)
        topo.pack(fill="x", pady=(0, 10))
        ttk.Label(topo, text="📺 Pesquisar no YouTube", style="YT.Titulo.TLabel").pack(side="left")
        ttk.Button(
            topo, text="⬅ Voltar", style="YT.TButton",
            command=lambda: app.mostrar("inicial"),
        ).pack(side="right")
        ttk.Button(
            topo, text="Home do YouTube", style="YT.TButton", command=self.abrir_home
        ).pack(side="right", padx=(0, 8))

        # Busca: campo + botão na mesma linha
        busca = ttk.Frame(self)
        busca.pack(fill="x")
        self.termo = tk.StringVar()
        self.entrada = ttk.Entry(busca, textvariable=self.termo, font=("Segoe UI", 14))
        self.entrada.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 10))
        self.entrada.bind("<Return>", lambda _e: self.pesquisar())
        self.btn_pesquisar = ttk.Button(
            busca, text="🔍 Pesquisar", style="YT.Destaque.TButton", command=self.pesquisar
        )
        self.btn_pesquisar.pack(side="right")

        # Status em linha própria, com a largura toda
        self.status = ttk.Label(self, text="", style="YT.Status.TLabel", justify="left", wraplength=600)
        self.status.pack(fill="x", pady=(6, 8))

        # Navegação ancorada no rodapé: empacotada antes do cartão para nunca sair da tela
        navegacao = ttk.Frame(self)
        navegacao.pack(side="bottom", fill="x", pady=(8, 0))
        navegacao.columnconfigure(1, weight=1)
        self.btn_anterior = ttk.Button(
            navegacao, text="◀ Anterior", style="YT.TButton", command=self.anterior, state="disabled"
        )
        self.btn_anterior.grid(row=0, column=0, sticky="w")
        self.btn_selecionar = ttk.Button(
            navegacao, text="▶ Selecionar vídeo", style="YT.Destaque.TButton",
            command=self.selecionar, state="disabled",
        )
        self.btn_selecionar.grid(row=0, column=1)
        self.btn_proximo = ttk.Button(
            navegacao, text="Próximo ▶", style="YT.TButton", command=self.proximo, state="disabled"
        )
        self.btn_proximo.grid(row=0, column=2, sticky="e")
        controles = ttk.Frame(navegacao)
        controles.grid(row=1, column=0, columnspan=3, pady=(8, 0))
        ttk.Button(
            controles, text="▶ Reproduzir", style="YT.TButton",
            command=self.reproduzir,
        ).pack(side="left", padx=4)
        ttk.Button(
            controles, text="⏸ Pausar", style="YT.TButton",
            command=self.pausar,
        ).pack(side="left", padx=4)
        ttk.Button(
            controles, text="🔊 Ativar som", style="YT.TButton",
            command=self.ativar_som,
        ).pack(side="left", padx=4)
        ttk.Button(
            controles, text="🔇 Silenciar", style="YT.TButton",
            command=self.desativar_som,
        ).pack(side="left", padx=4)
        ttk.Button(
            controles, text="⏪ Voltar 10 s", style="YT.TButton",
            command=self.retroceder,
        ).pack(side="left", padx=4)
        ttk.Button(
            controles, text="Avançar 10 s ⏩", style="YT.TButton",
            command=self.adiantar,
        ).pack(side="left", padx=4)

        # Cartão do vídeo
        cartao = ttk.Frame(self, style="YT.Cartao.TFrame", padding=10)
        cartao.pack(fill="both", expand=True)

        self.pagina = ttk.Label(cartao, text="", style="YT.Pagina.TLabel")
        self.pagina.pack(side="top", anchor="e", pady=(0, 4))

        # Texto empacotado primeiro (embaixo): a capa ocupa só o espaço que sobrar
        self.descricao_video = ttk.Label(
            cartao, text="", style="YT.Descricao.TLabel", wraplength=500, justify="left"
        )
        self.descricao_video.pack(side="bottom", fill="x")
        self.titulo_video = ttk.Label(
            cartao, text="", style="YT.TituloVideo.TLabel", wraplength=500, justify="left"
        )
        self.titulo_video.pack(side="bottom", fill="x", pady=(8, 3))

        self.moldura = ttk.Frame(cartao, style="YT.Capa.TFrame", height=110)
        self.moldura.pack(fill="both", expand=True)
        self.moldura.pack_propagate(False)
        self.capa = ttk.Label(
            self.moldura,
            text="Faça uma pesquisa para ver os vídeos.",
            style="YT.Capa.TLabel",
            anchor="center",
        )
        self.capa.pack(expand=True)

        self.moldura.bind("<Configure>", self._ao_redimensionar_capa)
        cartao.bind("<Configure>", self._ajustar_quebra_de_linha)

    def _definir_estilos(self):
        estilo = ttk.Style(self)
        fundo_cartao, fundo_capa = "#f3f5f8", "#1e1e1e"
        estilo.configure("YT.Titulo.TLabel", font=("Segoe UI", 18, "bold"))
        estilo.configure("YT.Status.TLabel", font=("Segoe UI", 11), foreground="#555555")
        estilo.configure("YT.TButton", font=("Segoe UI", 11), padding=(14, 8))
        estilo.configure("YT.Destaque.TButton", font=("Segoe UI", 12, "bold"), padding=(18, 10))
        estilo.configure("YT.Cartao.TFrame", background=fundo_cartao, relief="solid", borderwidth=1)
        estilo.configure("YT.Pagina.TLabel", background=fundo_cartao, foreground="#666666", font=("Segoe UI", 10))
        estilo.configure("YT.TituloVideo.TLabel", background=fundo_cartao, font=("Segoe UI", 15, "bold"))
        estilo.configure("YT.Descricao.TLabel", background=fundo_cartao, foreground="#444444", font=("Segoe UI", 11))
        estilo.configure("YT.Capa.TFrame", background=fundo_capa)
        estilo.configure("YT.Capa.TLabel", background=fundo_capa, foreground="#dddddd", font=("Segoe UI", 12))

    # ---- apenas aparência: ajustes responsivos ----
    def _ajustar_quebra_de_linha(self, evento):
        largura = max(evento.width - 40, 200)
        self.titulo_video.config(wraplength=largura)
        self.descricao_video.config(wraplength=largura)
        self.status.config(wraplength=max(evento.width - 20, 200))
        
    def _extrair_video_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")

        if host == "youtu.be":
            return parsed.path.strip("/").split("/")[0]

        if host in ("youtube.com", "m.youtube.com"):
            if parsed.path == "/watch":
                return parse_qs(parsed.query).get("v", [None])[0]

            partes = parsed.path.strip("/").split("/")

            if len(partes) >= 2 and partes[0] in ("embed", "shorts"):
                return partes[1]

        return None


    def _ao_redimensionar_capa(self, _evento):
        if self._job_redimensionar:
            self.after_cancel(self._job_redimensionar)
        self._job_redimensionar = self.after(80, self._renderizar_capa)

    def _tamanho_alvo_capa(self) -> tuple[int, int]:
        largura = max(self.moldura.winfo_width() - 4, 160)
        altura = max(self.moldura.winfo_height() - 4, 90)
        largura = min(largura, int(altura * 16 / 9))
        return largura, int(largura * 9 / 16)

    def _renderizar_capa(self):
        self._job_redimensionar = None
        if self._capa_pil is None or not self.capa.winfo_exists():
            return
        alvo = self._tamanho_alvo_capa()
        if alvo == self._alvo_capa and self._imagem is not None:
            return
        foto = ImageTk.PhotoImage(
            ImageOps.fit(self._capa_pil, alvo, method=Image.Resampling.LANCZOS)
        )
        self._alvo_capa = alvo
        self._imagem = foto
        self.capa.config(image=foto, text="")

    def ao_exibir(self):
        """Chamado sempre que a tela aparece."""
        if not self.termo.get().strip():
            self.status.config(text="")
        self.entrada.focus_set()

    def pesquisar(self):
        termo = self.termo.get().strip()
        if not termo:
            self.status.config(text="Digite o que deseja assistir no YouTube.")
            return "Digite o que deseja assistir no YouTube."

        self._limpar_resultados()
        self.status.config(text="Pesquisando vídeos no YouTube...")
        self.btn_pesquisar.config(state="disabled")
        self._busca_id += 1
        busca_id = self._busca_id
        threading.Thread(
            target=self._buscar_em_segundo_plano,
            args=(termo, busca_id),
            daemon=True,
        ).start()
        return "Buscando vídeos no YouTube."

    def _buscar_em_segundo_plano(self, termo: str, busca_id: int):
        try:
            resposta = pesquisar_youtube(termo)
        except (OSError, RuntimeError, ValueError) as erro:
            self.after(0, lambda erro=erro: self._mostrar_erro(erro, busca_id))
            return
        self.after(0, lambda: self._mostrar_resultados(resposta, busca_id))

    def _mostrar_erro(self, erro: Exception, busca_id: int):
        if busca_id != self._busca_id:
            return
        self.btn_pesquisar.config(state="normal")
        self.status.config(text=f"Erro na pesquisa: {erro}")

    def _mostrar_resultados(self, resposta: RespostaPesquisa, busca_id: int):
        if busca_id != self._busca_id:
            return
        self.btn_pesquisar.config(state="normal")
        self.resultados = resposta.resultados
        self.indice_atual = 0
        if self.resultados:
            self._mostrar_video_atual(busca_id)
            self.status.config(
                text=f"{len(self.resultados)} vídeo(s) encontrado(s). "
                "Use os comandos Próximo, Anterior e Selecionar vídeo."
            )
        else:
            self._limpar_video_atual()
            self.status.config(text="Nenhum vídeo encontrado. Tente outro termo.")

    def _limpar_resultados(self):
        self._busca_id += 1
        self.resultados = []
        self.indice_atual = 0
        self._limpar_video_atual()

    def _limpar_video_atual(self):
        if not self.capa.winfo_manager():
            self.capa.pack(expand=True)
        self._imagem = None
        self._capa_pil = None
        self._alvo_capa = None
        self.capa.config(image="", text="Nenhum vídeo selecionado.")
        self.pagina.config(text="")
        self.titulo_video.config(text="")
        self.descricao_video.config(text="")
        self.btn_anterior.config(state="disabled")
        self.btn_proximo.config(state="disabled")
        self.btn_selecionar.config(state="disabled")

    def _mostrar_video_atual(self, busca_id: int):
        if not self.capa.winfo_manager():
            self.capa.pack(expand=True)
        
        resultado = self.resultados[self.indice_atual]
        self._imagem = None
        self._capa_pil = None
        self._alvo_capa = None
        self.capa.config(image="", text="Carregando capa...")
        self.pagina.config(
            text=f"Vídeo {self.indice_atual + 1} de {len(self.resultados)}"
        )
        self.titulo_video.config(text=resultado.titulo)
        self.descricao_video.config(
            text=resultado.descricao or "Sem descrição disponível."
        )
        self.btn_anterior.config(
            state="normal" if self.indice_atual > 0 else "disabled"
        )
        self.btn_proximo.config(
            state="normal"
            if self.indice_atual < len(self.resultados) - 1
            else "disabled"
        )
        self.btn_selecionar.config(state="normal")
        if resultado.thumbnail_url:
            threading.Thread(
                target=self._baixar_capa,
                args=(resultado, busca_id),
                daemon=True,
            ).start()
        else:
            self.capa.config(text="Capa indisponível")

    def _baixar_capa(self, resultado: ResultadoPesquisa, busca_id: int):
        try:
            dados = baixar_thumbnail(resultado.thumbnail_url)
        except (OSError, RuntimeError, ValueError):
            self.after(
                0,
                lambda: self._definir_capa_indisponivel(resultado, busca_id),
            )
            return
        self.after(0, lambda: self._mostrar_capa(resultado, dados, busca_id))

    def _mostrar_capa(self, resultado: ResultadoPesquisa, dados: bytes, busca_id: int):
        if (
            busca_id != self._busca_id
            or not self.resultados
            or self.resultados[self.indice_atual] is not resultado
            or not self.capa.winfo_exists()
        ):
            return
        try:
            with Image.open(io.BytesIO(dados)) as imagem:
                original = imagem.convert("RGB")
        except (OSError, ValueError):
            self._definir_capa_indisponivel(resultado, busca_id)
            return
        self._capa_pil = original
        self._alvo_capa = None
        self._renderizar_capa()
        
    
    
    
    def _definir_capa_indisponivel(self, resultado: ResultadoPesquisa, busca_id: int):
        if (
            busca_id == self._busca_id
            and self.resultados
            and self.resultados[self.indice_atual] is resultado
            and self.capa.winfo_exists()
        ):
            self._imagem = None
            self._capa_pil = None
            self.capa.config(image="", text="Capa indisponível")

    def proximo(self):
        if self.indice_atual >= len(self.resultados) - 1:
            return "Você já está no último vídeo."
        self.indice_atual += 1
        self._mostrar_video_atual(self._busca_id)
        return f"Vídeo {self.indice_atual + 1} de {len(self.resultados)}."

    def anterior(self):
        if self.indice_atual <= 0 or not self.resultados:
            return "Você já está no primeiro vídeo."
        self.indice_atual -= 1
        self._mostrar_video_atual(self._busca_id)
        return f"Vídeo {self.indice_atual + 1} de {len(self.resultados)}."

    def selecionar(self):
        if not self.resultados:
            self.status.config(
                text="Faça uma pesquisa antes de selecionar um vídeo."
            )
            return "Não há vídeos para selecionar."

        resultado = self.resultados[self.indice_atual]
        video_id = self._extrair_video_id(resultado.url)
        if not video_id:
            mensagem = "Não foi possível obter o identificador do vídeo selecionado."
            self.status.config(text=mensagem)
            return mensagem
        try:
            self._player.abrir(video_id, resultado.titulo)
        except (OSError, RuntimeError, ValueError) as erro:
            self.status.config(text=f"Erro ao abrir vídeo: {erro}")
            return f"Erro ao abrir vídeo: {erro}"
        self._player_aberto = True
        self.status.config(text=f"Player aberto no navegador: {resultado.titulo}")
        return f"Abrindo no player: {resultado.titulo}"

    def _enviar_comando_player(self, comando: str, descricao: str) -> str:
        if not self._player_aberto:
            mensagem = "Selecione um vídeo antes de controlar o player."
            self.status.config(text=mensagem)
            return mensagem
        try:
            self._player.enviar_comando(comando)
        except (RuntimeError, ValueError) as erro:
            self.status.config(text=f"Erro ao controlar o player: {erro}")
            return f"Erro ao controlar o player: {erro}"
        if comando == "play":
            mensagem = (
                "Comando de reprodução enviado ao navegador. Se não iniciar, "
                "permita autoplay para este site nas configurações do navegador."
            )
        else:
            mensagem = f"Comando enviado ao player: {descricao}."
        self.status.config(text=mensagem)
        return mensagem

    def reproduzir(self):
        return self._enviar_comando_player("play", "reproduzir")

    def pausar(self):
        return self._enviar_comando_player("pause", "pausar")

    def ativar_som(self):
        return self._enviar_comando_player("unmute", "ativar som")

    def desativar_som(self):
        return self._enviar_comando_player("mute", "desativar som")

    def retroceder(self):
        return self._enviar_comando_player("rewind", "retroceder 10 segundos")

    def adiantar(self):
        return self._enviar_comando_player("forward", "avançar 10 segundos")

    def fechar(self):
        self._player.fechar()
        self._player_aberto = False

    def abrir_home(self):
        try:
            pesquisar_youtube("")
        except RuntimeError as erro:
            self.status.config(text=f"Erro ao abrir o YouTube: {erro}")
            return
        self.status.config(text="Abrindo YouTube...")