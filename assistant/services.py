"""Serviços e integrações externas do assistente."""

import json
import os
import webbrowser
from datetime import datetime
from dataclasses import dataclass, field
from tkinter import filedialog
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .config import (
    carregar_youtube_access_token,
    carregar_youtube_api_key,
)


@dataclass
class ResultadoPesquisa:
    titulo: str
    url: str
    descricao: str = ""
    thumbnail_url: str = ""


@dataclass
class RespostaPesquisa:
    resultados: list[ResultadoPesquisa] = field(default_factory=list)


def abrir_resultado_pesquisa(url: str) -> bool:
    """Abre um link HTTP(S) selecionado nos resultados."""
    if not url.startswith(("https://", "http://")):
        raise ValueError("O link do resultado não é um endereço HTTP válido.")
    if not webbrowser.open(url):
        raise RuntimeError(f"Não foi possível abrir o link: {url}")
    return True


def baixar_thumbnail(url: str) -> bytes:
    """Baixa uma miniatura HTTPS de resultado do YouTube."""
    if not url.startswith("https://"):
        raise ValueError("A URL da miniatura não é HTTPS.")
    requisicao = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(requisicao, timeout=15) as resposta:
            dados = resposta.read(5_000_001)
    except (OSError, URLError) as erro:
        raise RuntimeError(f"Não foi possível carregar a capa do vídeo: {erro}") from erro
    if len(dados) > 5_000_000:
        raise RuntimeError("A imagem da capa excede o limite de tamanho.")
    return dados


def pesquisar_youtube(termo: str) -> RespostaPesquisa:
    """Pesquisa vídeos pela YouTube Data API e retorna os links."""
    termo = termo.strip()
    if not termo:
        if not webbrowser.open("https://www.youtube.com"):
            raise RuntimeError("Não foi possível abrir o YouTube no navegador.")
        return RespostaPesquisa()

    access_token = carregar_youtube_access_token()
    api_key = carregar_youtube_api_key() if not access_token else ""
    if not access_token and not api_key:
        raise RuntimeError(
            "Configure YOUTUBE_ACCESS_TOKEN (OAuth 2.0) ou YOUTUBE_API_KEY no .env."
        )

    parametros = {
        "part": "snippet",
        "type": "video",
        "maxResults": 10,
        "q": termo,
    }
    cabecalhos = {}
    if access_token:
        cabecalhos["Authorization"] = f"Bearer {access_token}"
    else:
        parametros["key"] = api_key
    requisicao = Request(
        f"https://www.googleapis.com/youtube/v3/search?{urlencode(parametros)}",
        headers=cabecalhos,
    )
    try:
        with urlopen(requisicao, timeout=20) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except HTTPError as erro:
        detalhe = erro.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"YouTube Data API retornou HTTP {erro.code}: {detalhe}") from erro
    except (OSError, URLError, json.JSONDecodeError) as erro:
        raise RuntimeError(f"Não foi possível consultar a YouTube Data API: {erro}") from erro

    resultados: list[ResultadoPesquisa] = []
    for item in dados.get("items", []):
        id_video = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})
        if id_video:
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = (
                thumbnails.get("high")
                or thumbnails.get("medium")
                or thumbnails.get("default")
                or {}
            )
            resultados.append(ResultadoPesquisa(
                titulo=snippet.get("title") or "Vídeo sem título",
                url=f"https://www.youtube.com/watch?v={id_video}",
                descricao=snippet.get("description", ""),
                thumbnail_url=thumbnail.get("url", ""),
            ))

    return RespostaPesquisa(resultados=resultados)


def salvar_anotacao(texto: str) -> str | None:
    """Abre diálogo para salvar texto em arquivo .txt. Retorna o caminho ou None se cancelado."""
    nome_padrao = f"anotacao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    caminho = filedialog.asksaveasfilename(
        defaultextension=".txt",
        initialfile=nome_padrao,
        filetypes=[("Arquivos de Texto", "*.txt"), ("Todos os Arquivos", "*.*")],
        title="Salvar Anotação",
    )
    if not caminho:
        return None

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return caminho


def abrir_anotacao() -> tuple[str, str] | None:
    """Abre diálogo para carregar um arquivo .txt. Retorna (caminho, conteudo) ou None."""
    caminho = filedialog.askopenfilename(
        filetypes=[("Arquivos de Texto", "*.txt"), ("Todos os Arquivos", "*.*")],
        title="Abrir Anotação",
    )
    if not caminho or not os.path.exists(caminho):
        return None

    with open(caminho, "r", encoding="utf-8") as f:
        conteudo = f.read()
    return caminho, conteudo
