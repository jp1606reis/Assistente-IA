"""Roteador de intenção.

Três caminhos, do mais barato ao mais caro:
  1. exato(): a fala é exatamente uma frase de uma ação disponível na tela
     -> executa local, sem rede (comandos curtos e fixos).
  2. parece_comando(): a fala contém um gatilho (ou o SimilarityMatcher a
     considera próxima de um comando) -> vale a pena chamar o LLM.
  3. Caso contrário a fala é ignorada (conversa no ambiente).

O LLM só interpreta e devolve chamadas de ações; quem executa é o App.
"""

from typing import Any, Dict, List, Optional

from .acoes import Acao, normalizar

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

MODELO_LLM = "gemini-3.5-flash-lite"
MODELO_LLM_RESERVA = "gemini-3.8-flash"

PROMPT = """Você interpreta comandos de voz para um assistente de desktop usado por pessoas \
que não conseguem usar mouse e teclado. Receberá a tela atual e a fala transcrita.
- Se a fala for um pedido ao assistente, chame uma ou mais ferramentas, na ordem em que \
devem ocorrer, extraindo os argumentos exatamente como foram falados.
- Use somente as ferramentas fornecidas (são as que existem na tela atual).
- Se a fala parecer conversa com outra pessoa ou não for um pedido ao assistente, \
não chame ferramenta e responda apenas: IGNORAR
- Se for um pedido que nenhuma ferramenta atende, responda em uma frase curta \
dizendo o que é possível fazer nesta tela."""


class Roteador:
    def __init__(
        self,
        acoes: Dict[str, Acao],
        matcher: Any = None,
        api_key: Optional[str] = None,
        modelo: str = MODELO_LLM,
        timeout_s: float = 10.0,
    ):
        self.acoes = acoes            # referência viva ao registro do App
        self.matcher = matcher
        self.modelo = modelo
        self.client = None
        if api_key and HAS_GENAI:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
            )

    def disponiveis(self, tela: Optional[str]) -> List[Acao]:
        return [a for a in self.acoes.values() if a.disponivel(tela)]

    # ------------------------------------------------------------- caminho 1
    def exato(self, texto: str, tela: Optional[str]) -> Optional[Acao]:
        """Sem rede, seguro para a thread da interface."""
        n = normalizar(texto)
        for acao in self.disponiveis(tela):
            if n in acao.frases_norm:
                return acao
        return None

    # ------------------------------------------------------------- caminho 2
    def parece_comando(
        self,
        texto: str,
        tela: Optional[str] = None,
        consultar_matcher: bool = True,
    ) -> bool:
        """Bloqueante: pode usar rede (embeddings). Rodar em thread."""
        n = f" {normalizar(texto)} "
        for acao in self.disponiveis(tela):
            if any(f" {frase} " in n for frase in acao.frases_norm):
                return True
        return (
            consultar_matcher
            and self.encontrar_acao_similar(texto, tela) is not None
        )

    def encontrar_acao_similar(
        self,
        texto: str,
        tela: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Retorna uma ação semelhante, limitada às ações disponíveis na tela."""
        if self.matcher is None:
            return None
        ids_permitidos = {
            acao.id for acao in self.disponiveis(tela)
        }
        if not ids_permitidos:
            return None
        try:
            resultado = self.matcher.encontrar_comando(
                texto,
                ids_permitidos=ids_permitidos,
            )
        except Exception as erro:
            print(f"[Roteador] matcher falhou: {erro}")
            return None
        if resultado and resultado.get("comando_id") in ids_permitidos:
            return resultado
        return None

    def interpretar(self, texto: str, tela: Optional[str]) -> Dict[str, Any]:
        """Bloqueante. Devolve {'chamadas': [(id, args)], 'mensagem': str|None, 'erro': str|None}."""
        if not self.client:
            return {"erro": "LLM indisponível (sem chave ou sem biblioteca)."}

        validas = {a.id: a for a in self.disponiveis(tela)}
        declaracoes = []
        for a in validas.values():
            d: Dict[str, Any] = {"name": a.id, "description": a.descricao}
            if a.params:
                d["parameters"] = {
                    "type": "OBJECT",
                    "properties": {
                        nome: {"type": "STRING", "description": desc}
                        for nome, desc in a.params.items()
                    },
                    "required": list(a.params),
                }
            declaracoes.append(d)

        contents = f"Tela atual: {tela}\nFala do usuário: {texto}"
        config = types.GenerateContentConfig(
            system_instruction=PROMPT,
            tools=[{"function_declarations": declaracoes}],
            temperature=0.0,
        )
        try:
            resp = self.client.models.generate_content(
                model=self.modelo,
                contents=contents,
                config=config,
            )
        except Exception as erro:
            if getattr(erro, "code", None) != 503 or self.modelo == MODELO_LLM_RESERVA:
                return {"erro": str(erro)}

            try:
                resp = self.client.models.generate_content(
                    model=MODELO_LLM_RESERVA,
                    contents=contents,
                    config=config,
                )
                self.modelo = MODELO_LLM_RESERVA
                print(f"[Roteador] Modelo principal indisponível; usando {self.modelo}.")
            except Exception as erro_reserva:
                return {"erro": f"Modelo principal indisponível: {erro}; reserva também falhou: {erro_reserva}"}

        chamadas = []
        for c in resp.function_calls or []:
            acao = validas.get(c.name)
            if acao:
                args = {k: v for k, v in dict(c.args or {}).items() if k in acao.params}
                chamadas.append((c.name, args))
        if chamadas:
            return {"chamadas": chamadas}

        texto_resp = (resp.text or "").strip()
        if not texto_resp or "IGNORAR" in texto_resp.upper():
            return {"ignorar": True}
        return {"mensagem": texto_resp}