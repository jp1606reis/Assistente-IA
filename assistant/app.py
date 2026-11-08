"""Aplicação principal: voz -> ação. Botões e voz executam as mesmas funções."""

import os
import queue
import subprocess
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from pathlib import Path
from tkinter import ttk
from typing import Callable, Dict, Optional

from .config import carregar_api_key
from .core.acoes import Acao, normalizar
from .core.roteador import Roteador
from .core.similarity_matcher import SimilarityMatcher
from .screens.tela_anotacoes import TelaAnotacoes
from .screens.tela_inicial import TelaInicial
from .screens.tela_youtube import TelaYouTube
from .voice.transcriber import GeminiLiveTranscriber

PAUSA_FRASE_S = 0.8            # silêncio que fecha uma frase (junta fragmentos)
TIMEOUT_CONFIRMACAO_S = 20     # confirmação nunca fica pendurada
TIMEOUT_PARAMETRO_S = 15       # espera pelo termo ("o que deseja pesquisar?")
PALAVRAS_SIM = {"sim", "confirmo", "confirmar", "pode", "isso", "ok", "claro", "positivo"}
PALAVRAS_NAO = {"nao", "cancela", "cancelar", "deixa", "esquece", "negativo"}
CANCELAR = {"cancelar", "cancela"}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        api_key = carregar_api_key()

        self.title("Assistente Desktop por Voz & Acessibilidade")
        self.geometry("680x600")
        self.minsize(560, 520)
        self._tela_cheia = True
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", self._sair_tela_cheia)
        self.bind("<F11>", self._alternar_tela_cheia)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        self._encerrando = False
        self.tela_atual: Optional[str] = None
        self.acoes: Dict[str, Acao] = {}
        self._ditando_anotacao = False

        # Estado conversacional (sempre com expiração)
        self._pendente: Optional[dict] = None      # aguardando sim/não
        self._aguardando: Optional[dict] = None    # aguardando o valor de um parâmetro

        # Threads -> interface: somente por filas, lidas no _tick
        self._ui_q: queue.Queue = queue.Queue()
        self.fila_voz: queue.Queue = queue.Queue()
        self._buf_voz: list = []
        self._buf_ts = 0.0

        # Microfone com supervisão (reconecta sozinho)
        self.listener = GeminiLiveTranscriber(
            fila_transcricoes=self.fila_voz,
            callback_status=lambda msg: self._ui_q.put(("status", msg)),
        )
        self._mic_desejado = True
        self._falhas_mic = 0
        self._prox_reinicio = 0.0

        self._construir_painel_voz()

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)
        self.telas = {
            "inicial": TelaInicial(self.container, self),
            "youtube": TelaYouTube(self.container, self),
            "anotacoes": TelaAnotacoes(self.container, self),
        }
        for tela in self.telas.values():
            tela.grid(row=0, column=0, sticky="nsew")

        self._registrar_acoes()
        self.matcher = self._criar_matcher()
        self.roteador = Roteador(self.acoes, self.matcher, api_key)

        self.mostrar("inicial")
        self.after(100, self._tick)

    def _alternar_tela_cheia(self, _evento=None):
        self._tela_cheia = not self._tela_cheia
        self.attributes("-fullscreen", self._tela_cheia)
        if not self._tela_cheia:
            self.geometry("1100x800")
        return "break"

    def _sair_tela_cheia(self, _evento=None):
        if self._tela_cheia:
            self._tela_cheia = False
            self.attributes("-fullscreen", False)
            self.geometry("1100x800")
            return "break"

    # ================================================================ painel
    def _construir_painel_voz(self):
        painel = ttk.LabelFrame(self, text="🎙️ Controle de Voz & Acessibilidade", padding=12)
        painel.pack(fill="x", side="bottom", padx=12, pady=10)
        negrito = ("Segoe UI", 9, "bold")

        sup = ttk.Frame(painel)
        sup.pack(fill="x", pady=(0, 6))
        self.btn_mic = ttk.Button(sup, text="⏹ Parar Microfone", command=self.alternar_microfone)
        self.btn_mic.pack(side="left", padx=(0, 10))
        self.lbl_status = ttk.Label(sup, text="Iniciando sistema de voz...", foreground="#333333")
        self.lbl_status.pack(side="left")

        teste = ttk.Frame(painel)
        teste.pack(fill="x", pady=(2, 4))
        ttk.Label(teste, text="Comando rápido:").pack(side="left", padx=(0, 6))
        self.ent_teste = ttk.Entry(teste)
        self.ent_teste.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.ent_teste.bind("<Return>", lambda _e: self._enviar_teste())
        ttk.Button(teste, text="Enviar", command=self._enviar_teste).pack(side="right")

        self.lbl_ouvido = ttk.Label(painel, text="", foreground="gray", wraplength=600)
        self.lbl_ouvido.pack(fill="x", pady=(4, 0))
        self.lbl_feedback = ttk.Label(
            painel, text="Aguardando comando...", foreground="#0055aa",
            font=negrito, wraplength=600,
        )
        self.lbl_feedback.pack(fill="x", pady=(2, 0))

        # Confirmação: botões + voz, mesma função
        self.frm_conf = ttk.Frame(painel)
        self.lbl_conf = ttk.Label(self.frm_conf, foreground="#aa3300", font=negrito, wraplength=420)
        self.lbl_conf.pack(side="left", padx=(0, 10))
        ttk.Button(self.frm_conf, text="Sim", command=lambda: self._responder_confirmacao(True)).pack(side="left", padx=2)
        ttk.Button(self.frm_conf, text="Não", command=lambda: self._responder_confirmacao(False)).pack(side="left", padx=2)

    # ============================================================== ações
    def _registrar_acoes(self):
        t = self.telas

        def ir(nome: str, msg: str) -> Callable[[], str]:
            def _f():
                self.mostrar(nome)
                return msg
            return _f

        def preparar_busca(nome_tela: str, rotulo: str) -> Callable[[str], str]:
            def _f(termo: str):
                self.mostrar(nome_tela)
                tela = t[nome_tela]
                tela.termo.set(termo.strip())
                tela.status.config(text=f"Termo inserido: '{termo.strip()}'. Diga 'confirmar' para pesquisar.")
                tela.entrada.icursor("end")
                return f"{rotulo}: '{termo.strip()}' inserido. Diga 'confirmar' para pesquisar."
            return _f

        def confirmar_pesquisa():
            tela = t["youtube"]
            if not tela.termo.get().strip():
                return "Nada digitado ainda. Diga o que deseja pesquisar."
            return tela.pesquisar()

        def abrir_site(nome: str, url: str) -> Callable[[], str]:
            def _f():
                if not webbrowser.open(url):
                    raise RuntimeError(f"Não foi possível abrir {nome} no navegador.")
                return f"{nome} aberto no navegador."
            return _f

        def abrir_programa(comando: str, nome: str) -> Callable[[], str]:
            def _f():
                subprocess.Popen(comando)
                return f"{nome} aberto."
            return _f

        def abrir_pasta_projeto():
            os.startfile(str(Path(__file__).resolve().parents[1]))
            return "Pasta do projeto aberta."

        def adicionar_anotacao(texto: str):
            self.mostrar("anotacoes")
            tela = t["anotacoes"]
            tela.texto.insert("end", texto.strip() + "\n")
            tela.status.config(text="Texto adicionado por voz.")
            return "Anotação adicionada."

        def iniciar_ditado_anotacao():
            self.mostrar("anotacoes")
            self._ditando_anotacao = True
            mensagem = "Ditado ativo. Dite o texto; diga 'salvar anotação' para criar o arquivo."
            t["anotacoes"].status.config(text=mensagem)
            return mensagem

        def desfazer_anotacao():
            try:
                t["anotacoes"].texto.edit_undo()
            except tk.TclError:
                return "Não há nada para desfazer."
            return "Desfeito."

        def salvar_anotacao():
            self.mostrar("anotacoes")
            t["anotacoes"].salvar()
            return None

        def limpar_anotacao():
            tela = t["anotacoes"]
            tela.limpar()  # pede confirmação via app.pedir_confirmacao
            return None if self._pendente else tela.status.cget("text")

        def fechar():
            self.pedir_confirmacao("Deseja realmente fechar o assistente?", self._ao_fechar)

        def reg(acao: Acao):
            self.acoes[acao.id] = acao

        reg(Acao("ir_inicio", "Voltar para o menu principal", ir("inicial", "Menu principal."),
                 ["voltar para o início", "ir para o menu principal", "tela inicial", "página inicial",
                  "voltar ao início", "menu principal", "menu", "início", "voltar"]))

        reg(Acao("abrir_youtube", "Abrir a tela de pesquisa do YouTube", ir("youtube", "Tela do YouTube."),
                 ["abrir youtube", "abrir o youtube", "ver vídeos no youtube", "youtube"]))
        reg(Acao("pesquisar_youtube", "Preencher a barra de pesquisa do YouTube com um termo",
                 preparar_busca("youtube", "YouTube"),
                 ["pesquisar no youtube", "buscar no youtube", "pesquisar vídeos"],
                 params={"termo": "Assunto, vídeo ou canal a pesquisar no YouTube"},
                 pergunta="O que deseja pesquisar no YouTube?",
                 preparar=lambda: self.mostrar("youtube")))
        reg(Acao("abrir_home_youtube", "Abrir a página inicial do YouTube no navegador",
                 lambda: (t["youtube"].abrir_home(), "YouTube aberto no navegador.")[1],
                 ["abrir home do youtube", "home do youtube", "página inicial do youtube"],
                 telas={"youtube"}))
        reg(Acao("proximo_video_youtube", "Exibir o próximo vídeo nos resultados do YouTube",
                 t["youtube"].proximo,
                 ["próximo", "próximo vídeo", "vídeo seguinte"],
                 telas={"youtube"}))
        reg(Acao("video_anterior_youtube", "Exibir o vídeo anterior nos resultados do YouTube",
                 t["youtube"].anterior,
                 ["anterior", "vídeo anterior", "voltar vídeo", "vídeo passado"],
                 telas={"youtube"}))
        reg(Acao("selecionar_video_youtube", "Abrir o vídeo atualmente exibido",
                 t["youtube"].selecionar,
                 ["selecionar", "selecionar vídeo", "abrir vídeo", "abrir vídeo selecionado"],
                 telas={"youtube"}))
        reg(Acao("reproduzir_video_youtube", "Reproduzir o vídeo no navegador",
                 t["youtube"].reproduzir,
                 ["reproduzir vídeo", "tocar vídeo", "dar play", "iniciar o vídeo",
                  "quero assistir", "começar a reprodução", "retomar o vídeo",
                  "continuar assistindo", "colocar o vídeo para tocar"],
                 telas={"youtube"}))
        reg(Acao("pausar_video_youtube", "Pausar o vídeo no navegador",
                 t["youtube"].pausar,
                 ["pausar vídeo", "pausar reprodução", "dar pausa", "parar a reprodução",
                  "interromper o vídeo", "quero pausar", "pausa no vídeo"],
                 telas={"youtube"}))
        reg(Acao("ativar_som_youtube", "Ativar o som do vídeo no navegador",
                 t["youtube"].ativar_som,
                 ["ativar som", "ligar som", "tirar do mudo", "aumentar o volume do vídeo",
                  "quero ouvir", "habilitar áudio", "desmutar"],
                 telas={"youtube"}))
        reg(Acao("desativar_som_youtube", "Desativar o som do vídeo no navegador",
                 t["youtube"].desativar_som,
                 ["desativar som", "silenciar vídeo", "tirar o som", "deixar no mudo",
                  "mutar", "quero silêncio", "desligar áudio"],
                 telas={"youtube"}))
        reg(Acao("retroceder_video_youtube", "Retroceder o vídeo em 10 segundos",
                 t["youtube"].retroceder,
                 ["retroceder vídeo", "voltar 10 segundos", "rebobinar o vídeo",
                  "voltar um pouco", "voltar alguns segundos", "pular para trás",
                  "retornar o vídeo", "voltar no vídeo"],
                 telas={"youtube"}))
        reg(Acao("adiantar_video_youtube", "Avançar o vídeo em 10 segundos",
                 t["youtube"].adiantar,
                 ["adiantar vídeo", "avançar 10 segundos", "pular para frente",
                  "avançar um pouco", "pular alguns segundos", "ir para frente no vídeo",
                  "avançar na reprodução", "saltar um trecho"],
                 telas={"youtube"}))
        reg(Acao("confirmar_pesquisa", "Executar a pesquisa digitada na tela atual", confirmar_pesquisa,
                 ["confirmar", "pesquisar", "pode pesquisar", "buscar", "executar busca", "vai"],
                 telas={"youtube"}))

        reg(Acao("abrir_anotacoes", "Abrir o bloco de anotações", ir("anotacoes", "Bloco de anotações."),
                 ["abrir bloco de anotações", "ir para anotações", "fazer anotação", "escrever nota",
                  "abrir anotações", "meu bloco de notas", "anotações", "notas"]))
        reg(Acao("iniciar_ditado_anotacao", "Iniciar ditado por voz no bloco de anotações",
                 iniciar_ditado_anotacao,
                 ["começar ditado", "iniciar ditado", "começar a ditar", "ditar uma anotação",
                  "criar anotação por voz"]))
        reg(Acao("adicionar_anotacao", "Escrever um texto no bloco de anotações", adicionar_anotacao,
                 ["anotar", "adicionar anotação"],
                 params={"texto": "Conteúdo da anotação, como foi ditado"},
                 pergunta="O que deseja anotar?",
                 preparar=lambda: self.mostrar("anotacoes")))
        reg(Acao("salvar_anotacao", "Salvar o texto atual em arquivo .txt", salvar_anotacao,
                 ["salvar anotação", "salvar texto", "gravar arquivo", "salvar em txt", "salvar"],
                 telas={"anotacoes"}))
        reg(Acao("limpar_anotacao", "Limpar todo o texto do bloco de anotações", limpar_anotacao,
                 ["limpar anotações", "apagar tudo", "limpar o texto", "apagar o bloco de notas",
                  "deletar anotação", "limpar"],
                 telas={"anotacoes"}))
        reg(Acao("desfazer_anotacao", "Desfazer a última alteração no bloco de anotações", desfazer_anotacao,
                 ["desfazer", "desfazer anotação"], telas={"anotacoes"}))

        reg(Acao("abrir_calculadora", "Abrir a calculadora do Windows",
                 abrir_programa("calc.exe", "Calculadora"),
                 ["abrir calculadora", "iniciar calculadora", "calculadora"]))
        reg(Acao("abrir_notepad", "Abrir o Bloco de Notas do Windows",
                 abrir_programa("notepad.exe", "Bloco de Notas"),
                 ["abrir bloco de notas do windows", "iniciar notepad", "abrir bloco de notas nativo", "notepad"]))
        reg(Acao("abrir_chatgpt", "Abrir o ChatGPT no navegador",
                 abrir_site("ChatGPT", "https://chatgpt.com"),
                 ["abrir chatgpt", "abrir o chat gpt", "chatgpt"]))
        reg(Acao("abrir_github", "Abrir o GitHub no navegador",
                 abrir_site("GitHub", "https://github.com"),
                 ["abrir github", "abrir o github", "github"]))
        reg(Acao("abrir_gmail", "Abrir o Gmail no navegador",
                 abrir_site("Gmail", "https://mail.google.com"),
                 ["abrir gmail", "abrir email", "abrir e-mail", "gmail"]))
        reg(Acao("abrir_pasta_projeto", "Abrir a pasta do projeto no Explorer",
                 abrir_pasta_projeto,
                 ["abrir pasta do projeto", "pasta do projeto"]))

        reg(Acao("fechar_aplicacao", "Fechar o assistente", fechar,
                 ["fechar o aplicativo", "fechar assistente", "sair do programa",
                  "encerrar assistente", "fechar programa", "sair"]))

    def _criar_matcher(self):
        """Filtro semântico opcional. Se falhar, o roteador segue só com gatilhos lexicais."""
        catalogo = [
            {"id": a.id, "descricao": a.descricao, "exemplos": a.frases, "sensivel": False}
            for a in self.acoes.values()
        ]
        try:
            matcher = SimilarityMatcher(catalogo=catalogo)
        except Exception as erro:
            print(f"[App] Filtro semântico desativado ({erro}).")
            return None
        if not matcher.exemplos_embutidos and matcher.api_key:
            threading.Thread(target=matcher.reconstruir_cache, daemon=True).start()
        return matcher

    # ======================================================== API para telas
    def mostrar(self, nome: str):
        tela = self.telas.get(nome)
        if tela:
            self.tela_atual = nome
            tela.tkraise()
            if hasattr(tela, "ao_exibir"):
                tela.ao_exibir()

    def pedir_confirmacao(self, mensagem: str, ao_confirmar: Callable[[], None]):
        """Substitui messagebox.askyesno: funciona por botão e por voz, com timeout."""
        self._pendente = {"ao_confirmar": ao_confirmar, "expira": time.monotonic() + TIMEOUT_CONFIRMACAO_S}
        self.lbl_conf.config(text=f"{mensagem} Diga sim ou não.")
        self.frm_conf.pack(fill="x", pady=(6, 0))
        self._feedback(f"{mensagem} Diga sim ou não.")

    # ============================================================ microfone
    def alternar_microfone(self):
        if self._mic_desejado:
            self._mic_desejado = False
            self.listener.parar()
        else:
            self._mic_desejado = True
            self._falhas_mic = 0
            self._prox_reinicio = 0.0
        self._status_padrao()

    def _status_padrao(self):
        if self.listener.ativo:
            self.lbl_status.config(text="🎤 Microfone ativo: ouvindo...")
        elif self._mic_desejado:
            self.lbl_status.config(text="Reconectando microfone...")
        else:
            self.lbl_status.config(text="Microfone desligado.")
        self.btn_mic.config(text="⏹ Parar Microfone" if self._mic_desejado else "🎤 Ligar Microfone")

    def _supervisionar_microfone(self, agora: float):
        if self._mic_desejado and not self.listener.ativo and agora >= self._prox_reinicio:
            self.listener.iniciar()
            self._falhas_mic += 1
            self._prox_reinicio = agora + min(2 ** self._falhas_mic, 30)

    # ============================================================ laço central
    def _tick(self):
        try:
            agora = time.monotonic()

            # 1. Voz: junta fragmentos e fecha a frase após uma pausa
            try:
                while True:
                    self._buf_voz.append(self.fila_voz.get_nowait())
                    self._buf_ts = agora
                    self._falhas_mic = 0
            except queue.Empty:
                pass
            if self._buf_voz and agora - self._buf_ts > PAUSA_FRASE_S:
                texto = " ".join(p.strip() for p in self._buf_voz).strip()
                self._buf_voz.clear()
                self._ao_ouvir(texto)

            # 2. Resultados vindos de threads
            try:
                while True:
                    item = self._ui_q.get_nowait()
                    if item[0] == "status":
                        self.lbl_status.config(text=item[1])
                    elif item[0] == "llm":
                        self._tratar_resultado_llm(item[1], item[2])
            except queue.Empty:
                pass

            # 3. Expirações: nenhum estado fica pendurado
            if self._pendente and agora > self._pendente["expira"]:
                self._responder_confirmacao(False, "Tempo esgotado. Ação cancelada.")
            if self._aguardando and agora > self._aguardando["expira"]:
                self._aguardando = None
                self._feedback("Tempo esgotado. Pedido cancelado.")

            self._supervisionar_microfone(agora)
        except Exception:
            traceback.print_exc()
        finally:
            if not self._encerrando:
                self.after(100, self._tick)

    # ============================================================ fala -> ação
    def _enviar_teste(self):
        texto = self.ent_teste.get().strip()
        if texto:
            self.ent_teste.delete(0, tk.END)
            self._ao_ouvir(texto)

    def _ao_ouvir(self, texto: str):
        n = normalizar(texto)
        if not n:
            return
        self.lbl_ouvido.config(text=f'Ouvido: "{texto.strip()}"')
        palavras = set(n.split())

        # 1. Confirmação pendente: só sim/não
        if self._pendente:
            if palavras & PALAVRAS_NAO:
                self._responder_confirmacao(False)
            elif palavras & PALAVRAS_SIM:
                self._responder_confirmacao(True)
            else:
                self._feedback("Diga sim para confirmar ou não para cancelar.")
            return

        # 2. Cancelar sempre funciona
        if n in CANCELAR:
            self._cancelar_tudo()
            return

        if self._ditando_anotacao:
            if n in {"salvar", "salvar anotacao", "salvar texto", "gravar arquivo", "salvar em txt"}:
                self._ditando_anotacao = False
                try:
                    caminho = self.telas["anotacoes"].salvar_por_voz()
                except OSError as erro:
                    traceback.print_exc()
                    self._feedback(f"Não foi possível salvar a anotação: {erro}")
                    return
                self._feedback(
                    f"Anotação salva em: {caminho}"
                    if caminho else "Não há texto para salvar."
                )
                return

            if n in {"parar ditado", "parar de ditar", "encerrar ditado", "terminar ditado"}:
                self._ditando_anotacao = False
                self.telas["anotacoes"].status.config(text="Ditado encerrado. Diga 'iniciar ditado' para continuar.")
                self._feedback("Ditado encerrado.")
                return

            tela_anotacoes = self.telas["anotacoes"]
            if self.tela_atual != "anotacoes":
                self.mostrar("anotacoes")
            tela_anotacoes.texto.insert("end", texto.strip() + "\n")
            tela_anotacoes.texto.see("end")
            tela_anotacoes.status.config(text="Texto recebido por voz. Diga 'salvar anotação' para criar o arquivo.")
            self._feedback("Texto adicionado à anotação.")
            return

        # 3. Aguardando o valor de um parâmetro: a fala é o valor (exceto 'voltar')
        if self._aguardando:
            ag = self._aguardando
            escape = self.roteador.exato(texto, self.tela_atual)
            self._aguardando = None
            if escape and escape.id == "ir_inicio":
                self._executar(escape, {})
            else:
                self._executar(ag["acao"], {**ag["args"], ag["param"]: texto.strip()})
            return

        # 4. Comando curto e exato: local, sem rede
        acao = self.roteador.exato(texto, self.tela_atual)
        if acao:
            self._executar(acao, {})
            return

        # 5. Resto: triagem + LLM em thread (a interface nunca bloqueia)
        self.lbl_status.config(text="Interpretando...")
        threading.Thread(target=self._trabalho_llm, args=(texto, self.tela_atual), daemon=True).start()

    def _trabalho_llm(self, texto: str, tela: Optional[str]):
        try:
            correspondencia = self.roteador.encontrar_acao_similar(texto, tela)
            if correspondencia:
                comando_id = correspondencia["comando_id"]
                acao = self.acoes.get(comando_id)
                if acao and (
                    acao.params or comando_id == "confirmar_pesquisa"
                ):
                    if self.roteador.client:
                        resultado = self.roteador.interpretar(texto, tela)
                    elif acao.params:
                        resultado = {
                            "chamadas": [(acao.id, {})],
                        }
                    else:
                        resultado = {
                            "erro": "A pesquisa por voz precisa do interpretador. "
                            "Use 'Pesquisar no YouTube' e informe o termo, ou "
                            "digite-o na tela e pressione 'Pesquisar'."
                        }
                else:
                    resultado = {
                        "chamadas": [(comando_id, {})],
                    }
            elif self.roteador.parece_comando(
                texto, tela, consultar_matcher=False
            ):
                resultado = self.roteador.interpretar(texto, tela)
            else:
                resultado = {"ignorar": True}
        except Exception as erro:
            resultado = {"erro": str(erro)}
        self._ui_q.put(("llm", texto, resultado))

    def _tratar_resultado_llm(self, texto: str, res: dict):
        self._status_padrao()
        if res.get("ignorar"):
            return
        if res.get("erro"):
            print(f"[App] LLM: {res['erro']}")
            self._feedback("Não consegui interpretar agora. Tente um comando curto, como 'abrir youtube'.")
            return
        chamadas = res.get("chamadas")
        if not chamadas:
            self._feedback(res.get("mensagem") or "Não entendi o comando.")
            return
        for id_acao, args in chamadas:
            if not self._executar(self.acoes[id_acao], args):
                break

    # =========================================================== execução
    def _executar(self, acao: Acao, args: dict) -> bool:
        """True se concluiu; False se pausou (parâmetro/confirmação) ou falhou."""
        if not acao.disponivel(self.tela_atual):
            self._feedback(f"'{acao.descricao}' não está disponível nesta tela.")
            return False

        faltando = [p for p in acao.params if not str(args.get(p, "")).strip()]
        if faltando:
            self._aguardar(acao, faltando[0], args)
            return False

        try:
            msg = acao.funcao(**{p: args[p] for p in acao.params})
        except Exception as erro:
            traceback.print_exc()
            self._feedback(f"Erro ao executar: {erro}")
            return False

        if self._pendente is None:
            self._feedback(msg or f"{acao.descricao}.")
        return self._pendente is None

    def _aguardar(self, acao: Acao, param: str, args: dict):
        if acao.preparar:
            acao.preparar()
        self._aguardando = {
            "acao": acao, "param": param, "args": dict(args),
            "expira": time.monotonic() + TIMEOUT_PARAMETRO_S,
        }
        self._feedback(acao.pergunta or f"Diga: {acao.params[param]}.")

    def _responder_confirmacao(self, sim: bool, motivo: Optional[str] = None):
        pend, self._pendente = self._pendente, None
        self.frm_conf.pack_forget()
        if not pend:
            return
        if sim:
            try:
                pend["ao_confirmar"]()
            except Exception as erro:
                traceback.print_exc()
                self._feedback(f"Erro ao executar: {erro}")
        else:
            self._feedback(motivo or "Cancelado.")

    def _cancelar_tudo(self):
        self._pendente = None
        self._aguardando = None
        self.frm_conf.pack_forget()
        self._feedback("Cancelado.")

    def _feedback(self, msg: str):
        self.lbl_feedback.config(text=msg)

    def _ao_fechar(self):
        self._encerrando = True
        self._ditando_anotacao = False
        self._mic_desejado = False
        try:
            self.telas["youtube"].fechar()
        finally:
            try:
                self.listener.parar()
            finally:
                self.destroy()


if __name__ == "__main__":
    App().mainloop()