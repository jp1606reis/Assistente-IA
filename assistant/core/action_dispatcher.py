"""Despachante de ações e gerenciador de segurança / confirmação.

Responsável por conectar a intenção reconhecida (seja do SimilarityMatcher
ou do GeminiAgent) à interface do Tkinter e ao sistema operacional.
Interrompe e solicita confirmação por voz quando a ação for considerada sensível.
"""

from typing import Any, Callable, Dict, Optional
import subprocess


class ActionDispatcher:
    def __init__(self, app):
        """
        Args:
            app: Instância do App (Tkinter) para controlar as telas e componentes.
        """
        self.app = app

        # Estado para ações sensíveis pendentes de confirmação
        self.acao_pendente: Optional[Dict[str, Any]] = None

        # Palavras afirmativas e negativas para confirmação
        self.palavras_sim = {"sim", "confirmo", "pode", "isso", "confirmar", "com certeza", "ok", "claro"}
        self.palavras_nao = {"não", "cancela", "cancelar", "deixa", "esquece", "parar", "não quero"}

    def esta_aguardando_confirmacao(self) -> bool:
        """Indica se o sistema está travado aguardando 'Sim' ou 'Não' do usuário."""
        return self.acao_pendente is not None

    def processar_resposta_confirmacao(self, texto: str) -> Dict[str, Any]:
        """Processa a resposta do usuário quando uma ação sensível está pendente."""
        texto_limpo = texto.lower().strip()

        # Verificar confirmação
        if any(p in texto_limpo for p in self.palavras_sim):
            acao = self.acao_pendente
            self.acao_pendente = None
            resultado = self._executar_acao_direta(acao["comando"], acao.get("argumentos", {}))
            return {
                "executado": True,
                "mensagem": f"Confirmado: {resultado.get('mensagem', 'Ação executada.')}",
            }

        # Verificar cancelamento
        if any(p in texto_limpo for p in self.palavras_nao):
            self.acao_pendente = None
            return {
                "executado": False,
                "mensagem": "Ação cancelada com segurança.",
            }

        return {
            "executado": False,
            "mensagem": "Não compreendi. Por favor diga 'Sim' para confirmar ou 'Não' para cancelar.",
            "aguardando": True,
        }

    def despachar(self, comando: str, argumentos: Optional[Dict[str, Any]] = None, sensivel: bool = False, msg_confirmacao: Optional[str] = None) -> Dict[str, Any]:
        """Ponto de entrada para despachar uma ação.

        Se for sensível, guarda a ação e devolve a mensagem de confirmação.
        Se for segura, executa de imediato.
        """
        argumentos = argumentos or {}

        if sensivel:
            self.acao_pendente = {
                "comando": comando,
                "argumentos": argumentos,
            }
            mensagem = msg_confirmacao or "Esta ação pode alterar ou apagar dados. Deseja confirmar? (Diga 'Sim' ou 'Não')"
            return {
                "executado": False,
                "aguardando_confirmacao": True,
                "mensagem": mensagem,
            }

        return self._executar_acao_direta(comando, argumentos)

    def _executar_acao_direta(self, comando: str, argumentos: Dict[str, Any]) -> Dict[str, Any]:
        """Executa a ação correspondente no app ou sistema operacional."""

        try:
            # 1. Navegação de Telas
            if comando in ("ir_inicio", "navegar_para") and argumentos.get("tela") in ("inicial", "menu"):
                self.app.mostrar("inicial")
                return {"executado": True, "mensagem": "Exibindo tela inicial."}

            if comando == "abrir_youtube" or (comando == "navegar_para" and argumentos.get("tela") == "youtube"):
                self.app.mostrar("youtube")
                return {"executado": True, "mensagem": "Tela do YouTube aberta."}

            if comando == "abrir_anotacoes" or (comando == "navegar_para" and argumentos.get("tela") == "anotacoes"):
                self.app.mostrar("anotacoes")
                return {"executado": True, "mensagem": "Bloco de anotações aberto."}

            # 2. Pesquisas com argumentos (Preenche o campo na tela para permitir conferência/correção)
            if comando == "pesquisar_youtube":
                termo = argumentos.get("termo", "")
                self.app.mostrar("youtube")
                tela_yt = self.app.telas.get("youtube")
                if tela_yt:
                    tela_yt.termo.set(termo)
                    tela_yt.status.config(
                        text=f"Termo inserido: '{termo}'. Pressione Enter, clique em Pesquisar ou diga 'confirmar'."
                    )
                    tela_yt.entrada.focus_set()
                    tela_yt.entrada.icursor("end")
                return {
                    "executado": True,
                    "mensagem": f"Vídeo preparado: '{termo}'. Confira e confirme para pesquisar.",
                }

            if comando == "confirmar_pesquisa":
                tela_yt = self.app.telas.get("youtube")
                if self.app.tela_atual == "youtube" and tela_yt:
                    tela_yt.pesquisar()
                    return {"executado": True, "mensagem": "Pesquisa do YouTube executada."}
                if tela_yt and tela_yt.termo.get().strip():
                    tela_yt.pesquisar()
                    return {"executado": True, "mensagem": "Pesquisa do YouTube executada."}
                return {"executado": False, "mensagem": "Nenhum termo para pesquisar."}

            # 3. Anotações
            if comando == "adicionar_anotacao":
                texto = argumentos.get("texto", "")
                self.app.mostrar("anotacoes")
                tela_anot = self.app.telas.get("anotacoes")
                if tela_anot:
                    # Adiciona nova linha com o texto ditado
                    import tkinter as tk
                    tela_anot.texto.insert(tk.END, f"\n{texto}".strip() + "\n")
                    tela_anot.status.config(text="Texto adicionado por voz.")
                return {"executado": True, "mensagem": "Anotação adicionada."}

            if comando == "salvar_anotacao":
                self.app.mostrar("anotacoes")
                tela_anot = self.app.telas.get("anotacoes")
                if tela_anot:
                    tela_anot.salvar()
                return {"executado": True, "mensagem": "Abrindo diálogo para salvar."}

            if comando == "limpar_anotacao":
                tela_anot = self.app.telas.get("anotacoes")
                if tela_anot:
                    import tkinter as tk
                    tela_anot.texto.delete("1.0", tk.END)
                    tela_anot.status.config(text="Anotações limpas com sucesso.")
                return {"executado": True, "mensagem": "Anotações apagadas."}

            # 4. Utilitários do Sistema
            if comando in ("abrir_calculadora", "abrir_ferramenta") and (comando == "abrir_calculadora" or argumentos.get("ferramenta") == "calculadora"):
                subprocess.Popen("calc.exe")
                return {"executado": True, "mensagem": "Calculadora iniciada."}

            if comando in ("abrir_notepad", "abrir_ferramenta") and (comando == "abrir_notepad" or argumentos.get("ferramenta") == "notepad"):
                subprocess.Popen("notepad.exe")
                return {"executado": True, "mensagem": "Bloco de Notas nativo iniciado."}

            # 5. Ações Sensíveis de Aplicação
            if comando == "fechar_aplicacao":
                self.app.after(500, self.app.destroy)
                return {"executado": True, "mensagem": "Encerrando assistente..."}

        except Exception as e:
            return {"executado": False, "mensagem": f"Erro ao executar ação: {e}"}

        return {"executado": False, "mensagem": f"Comando '{comando}' não reconhecido."}
