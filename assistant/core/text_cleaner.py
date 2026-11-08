"""Módulo de limpeza de texto e remoção de disfluências de fala.

Trata ruídos fonéticos (alongamentos como 'éeeeee', 'hummm'),
repetições imediatas (gaguejos como 'abre abre') e marcadores de hesitação
(fillers como 'tipo assim', 'é...', 'então...') para preparar o texto
tanto para classificação de comandos quanto para ditado em anotações.
"""

import re


class TextCleaner:
    def __init__(self):
        # Apenas reduz se houver 3 ou mais caracteres repetidos consecutivamente
        # Isso preserva palavras legítimas com letras duplas (ex: 'assunto', 'passo', 'google')
        self.padrao_alongamentos = re.compile(r"([^\W\d_])\1{2,}", re.IGNORECASE | re.UNICODE)

        # Disfluências e hesitações típicas da língua portuguesa falada
        # Nota: Usamos ordenação por tamanho decrescente para que expressões compostas
        # sejam testadas antes de termos curtos
        self.fillers = [
            r"tipo assim",
            r"olha só",
            r"pera aí",
            r"por favor",
            r"então",
            r"sabe",
            r"digo",
            r"tipo",
            r"pera",
            r"hein",
            r"hum[m]*",
            r"hã[a]*",
            r"ah[a]*",
            r"ã[a]*",
            r"é[e]*",
            r"né",
        ]

        # Regex para palavras idênticas repetidas consecutivamente ("abre abre", "eu eu")
        self.padrao_gaguejo = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.IGNORECASE)

    def normalizar_alongamentos(self, texto: str) -> str:
        """Reduz caracteres repetidos 3 ou mais vezes para 1 única letra.
        Exemplos: 'éeeeee' -> 'é', 'hãaaa' -> 'hã', mas mantém 'assim' e 'google'.
        """
        return self.padrao_alongamentos.sub(r"\1", texto)

    def remover_repeticoes_palavras(self, texto: str) -> str:
        """Remove repetições de palavras consecutivas (gaguejo/hesitação).
        Exemplo: 'abre abre o youtube' -> 'abre o youtube'.
        """
        return self.padrao_gaguejo.sub(r"\1", texto)

    def remover_fillers_inicio(self, texto: str) -> str:
        """Remove marcadores de hesitação no início da frase de forma iterativa."""
        texto_limpo = texto.strip()
        modificado = True

        while modificado:
            modificado = False
            # Remove pontuações e espaços no início
            texto_limpo = re.sub(r"^[\s,;.:\-\?!]+", "", texto_limpo).strip()

            for filler in self.fillers:
                padrao = re.compile(r"^" + filler + r"(?:[\s,;.:\-\?!]+|$)", re.IGNORECASE)
                match = padrao.match(texto_limpo)
                if match:
                    texto_limpo = texto_limpo[match.end():].strip()
                    modificado = True
                    break

        return texto_limpo

    def limpar_espacos_pontuacao(self, texto: str) -> str:
        """Remove pontuações soltas no início e normaliza múltiplos espaços."""
        texto = re.sub(r"^[\s,;.:\-\?!]+", "", texto)
        texto = re.sub(r"\s+", " ", texto)
        return texto.strip()

    def limpar(self, texto: str, modo: str = "comando") -> str:
        """Executa o pipeline completo de higienização.

        Args:
            texto: Texto transcrito pelo Whisper.
            modo: 'comando' (mais agressivo com fillers no início)
                  ou 'ditado' (preserva o sentido em anotações).

        Returns:
            Texto higienizado pronto para uso.
        """
        if not texto or not texto.strip():
            return ""

        # 1. Normalizar alongamentos (ex: 'éeeeee' -> 'é', mantendo 'assim')
        resultado = self.normalizar_alongamentos(texto)

        # 2. Remover gaguejos e repetições imediatas (ex: 'pesquisa pesquisa' -> 'pesquisa')
        resultado = self.remover_repeticoes_palavras(resultado)

        # 3. Tratamento de fillers
        if modo == "comando":
            resultado = self.remover_fillers_inicio(resultado)

        # 4. Limpeza final de pontuações flutuantes e espaços
        resultado = self.limpar_espacos_pontuacao(resultado)

        return resultado


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    cleaner = TextCleaner()

    testes = [
        ("Éeeee... hum, abre o youtube", "comando"),
        ("Tipo assim, pesquisa pesquisa no google receitas de bolo", "comando"),
        ("Hãaaa... então, abre a calculadora", "comando"),
        ("Hoje eu preciso comprar pão pão e leite.", "ditado"),
        ("Pera aí... anota anota reunião amanhã às 10 horas", "comando"),
    ]

    print("=== Testes do TextCleaner ===")
    for entrada, modo in testes:
        saida = cleaner.limpar(entrada, modo=modo)
        print(f"[{modo.upper()}] Entrada: '{entrada}'")
        print(f"[{modo.upper()}] Saída:   '{saida}'\n")
