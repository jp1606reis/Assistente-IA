"""Módulo de compatibilidade/reexportação."""

from .services import pesquisar_youtube, salvar_anotacao, abrir_anotacao
from .screens.tela_inicial import TelaInicial
from .screens.tela_youtube import TelaYouTube
from .screens.tela_anotacoes import TelaAnotacoes
from .app import App

__all__ = [
    "pesquisar_youtube",
    "salvar_anotacao",
    "abrir_anotacao",
    "TelaInicial",
    "TelaYouTube",
    "TelaAnotacoes",
    "App",
]

if __name__ == "__main__":
    App().mainloop()
