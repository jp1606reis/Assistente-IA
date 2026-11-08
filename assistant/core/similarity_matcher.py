"""Módulo de similaridade semântica por embeddings com suporte resiliente a modelos de embedding:
- text-embedding-004
- embedding-001
- TF-IDF local (fallback offline instantâneo que não depende de API externa)
"""

import json
import math
import os
import re
from typing import Any, Dict, List, Optional
from ..config import carregar_api_key

try:
    from google import genai
    HAS_NEW_GENAI = True
except ImportError:
    HAS_NEW_GENAI = False

try:
    import google.generativeai as legacy_genai
    HAS_LEGACY_GENAI = True
except ImportError:
    HAS_LEGACY_GENAI = False


CATALOGO_COMANDOS = [
    {
        "id": "ir_inicio",
        "sensivel": False,
        "descricao": "Voltar para o menu principal",
        "exemplos": [
            "voltar para o início",
            "ir para o menu principal",
            "tela inicial",
            "página inicial",
            "voltar ao início",
            "menu principal",
            "menu",
            "início",
            "voltar",
        ],
    },
    {
        "id": "abrir_youtube",
        "sensivel": False,
        "descricao": "Abrir tela de pesquisa do YouTube",
        "exemplos": [
            "abrir youtube",
            "pesquisar vídeos",
            "ver vídeos no youtube",
            "abrir o youtube",
            "buscar no youtube",
            "youtube",
        ],
    },
    {
        "id": "confirmar_pesquisa",
        "sensivel": False,
        "descricao": "Executar a pesquisa que está digitada na tela atual",
        "exemplos": [
            "confirmar",
            "pesquisar",
            "pode pesquisar",
            "buscar",
            "executar busca",
            "vai",
        ],
    },
    {
        "id": "abrir_anotacoes",
        "sensivel": False,
        "descricao": "Abrir o bloco de anotações",
        "exemplos": [
            "abrir bloco de anotações",
            "ir para anotações",
            "fazer anotação",
            "escrever nota",
            "abrir anotações",
            "meu bloco de notas",
            "anotações",
            "notas",
        ],
    },
    {
        "id": "salvar_anotacao",
        "sensivel": False,
        "descricao": "Salvar texto atual em arquivo txt",
        "exemplos": [
            "salvar anotação",
            "salvar texto",
            "gravar arquivo",
            "salvar em txt",
            "salvar",
        ],
    },
    {
        "id": "limpar_anotacao",
        "sensivel": True,
        "mensagem_confirmacao": "Você tem certeza que deseja limpar todas as anotações da tela?",
        "descricao": "Limpar o texto da área de anotações",
        "exemplos": [
            "limpar anotações",
            "apagar tudo",
            "limpar o texto",
            "apagar o bloco de notas",
            "deletar anotação",
        ],
    },
    {
        "id": "fechar_aplicacao",
        "sensivel": True,
        "mensagem_confirmacao": "Você deseja realmente fechar o assistente?",
        "descricao": "Fechar e encerrar o programa",
        "exemplos": [
            "fechar o aplicativo",
            "fechar assistente",
            "sair do programa",
            "encerrar assistente",
            "fechar programa",
            "sair",
        ],
    },
]


def similaridade_cosseno(vetor_a: List[float], vetor_b: List[float]) -> float:
    if len(vetor_a) != len(vetor_b) or not vetor_a:
        return 0.0

    produto_escalar = sum(a * b for a, b in zip(vetor_a, vetor_b))
    norma_a = math.sqrt(sum(a * a for a in vetor_a))
    norma_b = math.sqrt(sum(b * b for b in vetor_b))

    if norma_a == 0.0 or norma_b == 0.0:
        return 0.0

    return produto_escalar / (norma_a * norma_b)


class SimilarityMatcher:
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_path: str = "embeddings_cache.json",
        limiar_similaridade: float = 0.70,
        catalogo: Optional[List[Dict[str, Any]]] = None,
    ):
        self.api_key = api_key or carregar_api_key()
        self.cache_path = cache_path
        self.limiar = limiar_similaridade
        self.catalogo = catalogo if catalogo is not None else CATALOGO_COMANDOS

        # Modelos candidatos suportados pela API do Gemini
        self.modelos_candidatos = [
            "text-embedding-004",
            "models/text-embedding-004",
            "embedding-001",
            "models/embedding-001",
        ]
        self.modelo_ativo: Optional[str] = None

        self.client_new = None
        self._inicializar_cliente()

        self.exemplos_embutidos: List[Dict[str, Any]] = []
        self._carregar_cache()

    def _carregar_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    exemplos = json.load(f)
                esperados = {
                    (item["id"], frase)
                    for item in self.catalogo
                    for frase in item["exemplos"]
                }
                encontrados = {
                    (item.get("id"), item.get("frase"))
                    for item in exemplos
                    if isinstance(item, dict)
                }
                if encontrados == esperados:
                    self.exemplos_embutidos = exemplos
            except Exception as e:
                print(f"[SimilarityMatcher] Erro ao ler cache: {e}")

    def _inicializar_cliente(self):
        if not self.api_key:
            return

        if HAS_NEW_GENAI:
            self.client_new = genai.Client(api_key=self.api_key)
        elif HAS_LEGACY_GENAI:
            legacy_genai.configure(api_key=self.api_key)

    def _tentar_embed_com_modelo(self, texto: str, modelo: str) -> Optional[List[float]]:
        """Tenta gerar embedding com um modelo específico."""
        try:
            if self.client_new:
                # Remove prefixo models/ se passado para o client_new
                mod_name = modelo.replace("models/", "")
                resposta = self.client_new.models.embed_content(
                    model=mod_name,
                    contents=texto,
                )
                if hasattr(resposta, "embedding") and hasattr(resposta.embedding, "values"):
                    return list(resposta.embedding.values)
                elif hasattr(resposta, "embeddings") and len(resposta.embeddings) > 0:
                    return list(resposta.embeddings[0].values)
            elif HAS_LEGACY_GENAI:
                mod_name = modelo if modelo.startswith("models/") else f"models/{modelo}"
                resposta = legacy_genai.embed_content(
                    model=mod_name,
                    content=texto,
                )
                if "embedding" in resposta:
                    return resposta["embedding"]
        except Exception:
            return None
        return None

    def gerar_embedding(self, texto: str) -> Optional[List[float]]:
        if not self.api_key:
            return None

        # Se já encontramos o modelo que funciona, usa ele diretamente
        if self.modelo_ativo:
            vetor = self._tentar_embed_com_modelo(texto, self.modelo_ativo)
            if vetor:
                return vetor

        # Caso contrário, descobre qual modelo está disponível para a chave
        for cand in self.modelos_candidatos:
            vetor = self._tentar_embed_com_modelo(texto, cand)
            if vetor:
                self.modelo_ativo = cand
                return vetor

        return None

    def _carregar_ou_gerar_catalogo(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    exemplos = json.load(f)
                esperados = {
                    (item["id"], frase)
                    for item in self.catalogo
                    for frase in item["exemplos"]
                }
                encontrados = {
                    (item.get("id"), item.get("frase"))
                    for item in exemplos
                    if isinstance(item, dict)
                }
                if encontrados == esperados and exemplos:
                    self.exemplos_embutidos = exemplos
                    return
            except Exception as e:
                print(f"[SimilarityMatcher] Erro ao ler cache: {e}")

        if self.api_key:
            self.reconstruir_cache()

    def reconstruir_cache(self):
        exemplos_processados = []
        for item in self.catalogo:
            cmd_id = item["id"]
            sensivel = item.get("sensivel", False)
            msg_confirmacao = item.get("mensagem_confirmacao")

            for frase in item["exemplos"]:
                vetor = self.gerar_embedding(frase)
                if vetor:
                    exemplos_processados.append({
                        "id": cmd_id,
                        "frase": frase,
                        "sensivel": sensivel,
                        "mensagem_confirmacao": msg_confirmacao,
                        "vetor": vetor,
                    })

        self.exemplos_embutidos = exemplos_processados
        if exemplos_processados:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.exemplos_embutidos, f, ensure_ascii=False, indent=2)

    def _match_direto_texto(
        self,
        texto_usuario: str,
        ids_permitidos: Optional[set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Correspondência textual direta como fast-path prioritário e sem custo de rede."""
        texto_norm = texto_usuario.lower().strip()
        texto_norm = re.sub(r"[^\w\s]", "", texto_norm)

        for item in self.catalogo:
            if ids_permitidos is not None and item["id"] not in ids_permitidos:
                continue
            for ex in item["exemplos"]:
                ex_norm = re.sub(r"[^\w\s]", "", ex.lower().strip())
                if texto_norm == ex_norm or texto_norm.startswith(ex_norm) or ex_norm in texto_norm:
                    return {
                        "comando_id": item["id"],
                        "frase_combinada": ex,
                        "score": 1.0,
                        "sensivel": item.get("sensivel", False),
                        "mensagem_confirmacao": item.get("mensagem_confirmacao"),
                    }
        return None

    def encontrar_comando(
        self,
        texto_usuario: str,
        ids_permitidos: Optional[set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not texto_usuario:
            return None

        # 1. Correspondência textual direta instantânea
        match_direto = self._match_direto_texto(texto_usuario, ids_permitidos)
        if match_direto:
            return match_direto

        # 2. Similaridade de Cosseno via Embeddings do Gemini (se gerado)
        if self.exemplos_embutidos:
            vetor_usuario = self.gerar_embedding(texto_usuario)
            if vetor_usuario:
                melhor_match = None
                maior_score = -1.0

                for item in self.exemplos_embutidos:
                    if ids_permitidos is not None and item["id"] not in ids_permitidos:
                        continue
                    score = similaridade_cosseno(vetor_usuario, item["vetor"])
                    if score > maior_score:
                        maior_score = score
                        melhor_match = item

                if melhor_match and maior_score >= self.limiar:
                    return {
                        "comando_id": melhor_match["id"],
                        "frase_combinada": melhor_match["frase"],
                        "score": round(maior_score, 4),
                        "sensivel": melhor_match["sensivel"],
                        "mensagem_confirmacao": melhor_match.get("mensagem_confirmacao"),
                    }

        return None
