"""Tela inicial do assistente com menu principal de ações."""

from tkinter import ttk


class TelaInicial(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=25)
        self.app = app

        ttk.Label(self, text="🤖 Central do Assistente", font=("Segoe UI", 20, "bold")).pack(pady=(5, 5))
        ttk.Label(
            self,
            text="Use os botões ou comande tudo por voz no painel inferior:",
            foreground="gray",
        ).pack(pady=(0, 20))

        menu_frame = ttk.Frame(self)
        menu_frame.pack(fill="x", padx=15)
        menu_frame.columnconfigure(0, weight=1)
        menu_frame.columnconfigure(1, weight=1)

        botoes = [
            ("📺  Pesquisar no YouTube", lambda: app.mostrar("youtube"), 0, 0),
            ("📝  Bloco de Anotações", lambda: app.mostrar("anotacoes"), 0, 1),
        ]

        for texto, comando, linha, coluna in botoes:
            ttk.Button(menu_frame, text=texto, command=comando).grid(
                row=linha, column=coluna, padx=6, pady=6, sticky="ew", ipady=10
            )
