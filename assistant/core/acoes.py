"""Declaração única das ações do assistente.

Cada Acao alimenta, a partir de um só lugar:
  - o reconhecimento local (frases exatas),
  - o filtro de intenção (catálogo do SimilarityMatcher),
  - as ferramentas do LLM (function calling),
  - a execução (a mesma função que o botão da tela chama).
"""

import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos nem pontuação, espaços únicos."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    limpo = "".join(c if c.isalnum() or c.isspace() else " " for c in sem_acento)
    return " ".join(limpo.split())


@dataclass
class Acao:
    id: str
    descricao: str
    funcao: Callable[..., Optional[str]]          # retorna a mensagem de feedback
    frases: List[str] = field(default_factory=list)
    params: Dict[str, str] = field(default_factory=dict)   # nome -> descrição
    pergunta: str = ""                            # feita quando faltar um parâmetro
    preparar: Optional[Callable[[], None]] = None  # roda ao aguardar o parâmetro
    telas: Optional[Set[str]] = None              # None = disponível em qualquer tela

    def __post_init__(self):
        self.frases_norm = [normalizar(f) for f in self.frases]

    def disponivel(self, tela: Optional[str]) -> bool:
        return self.telas is None or tela in self.telas