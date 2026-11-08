"""Agente LLM usando Google AI Studio (Gemini) com Function Calling / Tool Calling.

Processa instruções em linguagem natural livre que não correspondem
aos comandos rápidos de similaridade (ex: "pesquisa receitas de bolo no youtube",
"anota no bloco que tenho dentista amanhã às 14h").
"""

import json
import os
from typing import Any, Callable, Dict, List, Optional

try:
    from google import genai
    from google.genai import types

    HAS_NEW_GENAI = True
except ImportError:
    HAS_NEW_GENAI = False

try:
    import google.generativeai as legacy_genai

    HAS_LEGACY_GENAI = True
except ImportError:
    HAS_LEGACY_GENAI = False


# Declaração das ferramentas disponíveis para o assistente
FERRAMENTAS_DECLARACOES = [
    {
        "name": "pesquisar_youtube",
        "description": "Realiza uma pesquisa de vídeos no YouTube e abre o navegador.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "termo": {
                    "type": "STRING",
                    "description": "Termo, assunto ou nome do vídeo/canal a ser pesquisado no YouTube.",
                }
            },
            "required": ["termo"],
        },
    },
    {
        "name": "adicionar_anotacao",
        "description": "Escreve ou dita um texto diretamente na área de anotações.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "texto": {
                    "type": "STRING",
                    "description": "O conteúdo da anotação ditada pelo usuário.",
                }
            },
            "required": ["texto"],
        },
    },
    {
        "name": "navegar_para",
        "description": "Muda a tela visível na interface do assistente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tela": {
                    "type": "STRING",
                    "description": "Nome da tela destino: 'inicial', 'youtube' ou 'anotacoes'.",
                }
            },
            "required": ["tela"],
        },
    },
    {
        "name": "abrir_ferramenta",
        "description": "Abre um utilitário do sistema operacional (calculadora, bloco de notas do windows).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "ferramenta": {
                    "type": "STRING",
                    "description": "Nome da ferramenta: 'calculadora' ou 'notepad'.",
                }
            },
            "required": ["ferramenta"],
        },
    },
]


SYSTEM_PROMPT = """Você é o cérebro interpretador de um assistente de voz para desktop com foco em acessibilidade motora.
O usuário se comunica por voz. Sua função principal é transformar o pedido falado em uma chamada de função (tool call).
Se o usuário pedir para pesquisar vídeos no YouTube, use a ferramenta respectiva extraindo o termo exato.
Se o usuário pedir para anotar, lembrar ou escrever algo, use 'adicionar_anotacao' com o texto limpo.
Se o usuário pedir para ver uma tela ou voltar, use 'navegar_para'.
Se não houver nenhuma ferramenta aplicável, responda de forma curta e cordial orientando o que é possível fazer."""


from ..config import carregar_api_key


class GeminiAgent:
    def __init__(
        self, api_key: Optional[str] = None, model_name: str = "gemini-3.8-flash-lite"
    ):
        self.api_key = api_key or carregar_api_key()
        self.model_name = model_name
        self.client_new = None
        self._inicializar_cliente()

    def _inicializar_cliente(self):
        if not self.api_key:
            return

        if HAS_NEW_GENAI:
            self.client_new = genai.Client(api_key=self.api_key)
        elif HAS_LEGACY_GENAI:
            legacy_genai.configure(api_key=self.api_key)

    def interpretar(self, texto_usuario: str) -> Dict[str, Any]:
        """Interpreta a instrução livre e retorna a ferramenta a chamar com os argumentos."""
        if not self.api_key:
            return {
                "sucesso": False,
                "erro": "GEMINI_API_KEY não configurada.",
            }

        modelos_tentativa = [self.model_name, "gemini-3.8-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        for mod in modelos_tentativa:
            try:
                if self.client_new:
                    # Usando SDK moderno google-genai
                    response = self.client_new.models.generate_content(
                        model=mod,
                        contents=texto_usuario,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            tools=[{"function_declarations": FERRAMENTAS_DECLARACOES}],
                            temperature=0.1,
                        ),
                    )

                    self.model_name = mod
                    if response.function_calls:
                        chamada = response.function_calls[0]
                        return {
                            "sucesso": True,
                            "tipo": "tool_call",
                            "ferramenta": chamada.name,
                            "argumentos": dict(chamada.args) if chamada.args else {},
                        }

                    return {
                        "sucesso": True,
                        "tipo": "mensagem",
                        "resposta": response.text or "",
                    }
                elif HAS_LEGACY_GENAI:
                    mod_formatado = mod if mod.startswith("models/") else f"models/{mod}"
                    modelo = legacy_genai.GenerativeModel(
                        model_name=mod_formatado,
                        system_instruction=SYSTEM_PROMPT,
                    )
                    resposta = modelo.generate_content(
                        f"Instrução do usuário: {texto_usuario}\n"
                        f"Decida qual ferramenta acionar dentre: pesquisar_youtube, adicionar_anotacao, navegar_para, abrir_ferramenta."
                        f" Responda estritamente em JSON no formato: {{\"ferramenta\": \"nome\", \"argumentos\": {{...}}}}"
                    )
                    texto = resposta.text.strip()
                    if "```json" in texto:
                        texto = texto.split("```json")[1].split("```")[0].strip()
                    elif "```" in texto:
                        texto = texto.split("```")[1].split("```")[0].strip()

                    dados = json.loads(texto)
                    self.model_name = mod
                    return {
                        "sucesso": True,
                        "tipo": "tool_call",
                        "ferramenta": dados.get("ferramenta"),
                        "argumentos": dados.get("argumentos", {}),
                    }
            except Exception as e:
                if "404" in str(e) or "not found" in str(e).lower() or "is no longer available" in str(e).lower():
                    continue
                return {"sucesso": False, "erro": str(e)}

        return {"sucesso": False, "erro": "Nenhum modelo do Gemini respondeu com sucesso."}
