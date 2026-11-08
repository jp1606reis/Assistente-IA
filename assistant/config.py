"""Função utilitária para obter a chave da API do Google AI Studio a partir do ambiente ou do arquivo .env."""

import os
from pathlib import Path


_ARQUIVO_ENV = Path(__file__).resolve().parent.parent / ".env"


def carregar_api_key() -> str:
    """Busca a chave da API no ambiente ou lê diretamente do arquivo .env."""
    variaveis = ("GEMINI_API_KEY", "GEMIN_API_KEY", "GOOGLE_API_KEY", "API_KEY")

    for var in variaveis:
        val = os.getenv(var)
        if val and val.strip():
            return val.strip()

    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_ARQUIVO_ENV, override=True)
        for var in variaveis:
            val = os.getenv(var)
            if val and val.strip():
                return val.strip()
    except ImportError:
        pass

    caminho_env = _ARQUIVO_ENV
    if caminho_env.exists():
        try:
            with open(caminho_env, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if not linha or linha.startswith("#"):
                        continue
                    if "=" in linha:
                        chave, valor = linha.split("=", 1)
                        chave = chave.strip()
                        valor = valor.strip().strip("'\"")
                        if chave in variaveis and valor:
                            os.environ["GEMINI_API_KEY"] = valor
                            os.environ["GOOGLE_API_KEY"] = valor
                            return valor
        except Exception as e:
            print(f"[config] Erro ao ler .env: {e}")

    return ""


def carregar_youtube_api_key() -> str:
    """Busca a chave da YouTube Data API no ambiente ou no arquivo .env."""
    chave = os.getenv("YOUTUBE_API_KEY")
    if chave and chave.strip():
        return chave.strip()

    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_ARQUIVO_ENV)
        chave = os.getenv("YOUTUBE_API_KEY")
        if chave and chave.strip():
            return chave.strip()
    except ImportError:
        pass

    caminho_env = _ARQUIVO_ENV
    if caminho_env.exists():
        try:
            with open(caminho_env, "r", encoding="utf-8") as arquivo:
                for linha in arquivo:
                    linha = linha.strip()
                    if linha and not linha.startswith("#") and "=" in linha:
                        nome, valor = linha.split("=", 1)
                        if nome.strip() == "YOUTUBE_API_KEY":
                            chave = valor.strip().strip("'\"")
                            if chave:
                                os.environ["YOUTUBE_API_KEY"] = chave
                                return chave
        except OSError as erro:
            print(f"[config] Erro ao ler a chave da YouTube API: {erro}")

    return ""


def carregar_youtube_access_token() -> str:
    """Busca o token OAuth da YouTube Data API no ambiente ou no arquivo .env."""
    nome_variavel = "YOUTUBE_ACCESS_TOKEN"
    token = os.getenv(nome_variavel)
    if token and token.strip():
        return token.strip()

    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_ARQUIVO_ENV)
        token = os.getenv(nome_variavel)
        if token and token.strip():
            return token.strip()
    except ImportError:
        pass

    caminho_env = _ARQUIVO_ENV
    if caminho_env.exists():
        try:
            with open(caminho_env, "r", encoding="utf-8") as arquivo:
                for linha in arquivo:
                    linha = linha.strip()
                    if linha and not linha.startswith("#") and "=" in linha:
                        nome, valor = linha.split("=", 1)
                        if nome.strip() == nome_variavel:
                            token = valor.strip().strip("'\"")
                            if token:
                                os.environ[nome_variavel] = token
                                return token
        except OSError as erro:
            print(f"[config] Erro ao ler o token OAuth do YouTube: {erro}")

    return ""
