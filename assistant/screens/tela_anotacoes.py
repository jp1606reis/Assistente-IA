"""Tela de bloco de anotações com persistência em arquivos .txt."""

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from ..services import abrir_anotacao, salvar_anotacao


class TelaAnotacoes(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=20)
        self.app = app

        # Cabeçalho
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="📝 Bloco de Anotações", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(
            self,
            text="Por voz: diga “iniciar ditado”, dite o texto e diga “salvar anotação”.",
            foreground="gray",
        ).pack(anchor="w", pady=(0, 8))

        # Barra de ferramentas superior
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))

        ttk.Button(toolbar, text="💾 Salvar (.txt)", command=self.salvar).pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="📂 Abrir (.txt)", command=self.abrir).pack(side="left", padx=5)
        ttk.Button(toolbar, text="🧹 Limpar", command=self.limpar).pack(side="left", padx=5)
        ttk.Button(toolbar, text="⬅ Voltar", command=lambda: app.mostrar("inicial")).pack(side="right")

        # Área de texto com scrollbar
        text_container = ttk.Frame(self)
        text_container.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_container)
        scrollbar.pack(side="right", fill="y")

        self.texto = tk.Text(
            text_container,
            wrap="word",
            font=("Segoe UI", 11),
            yscrollcommand=scrollbar.set,
            undo=True,
        )
        self.texto.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.texto.yview)

        # Barra de status
        self.status = ttk.Label(self, text="Pronto para ditar ou digitar.", foreground="gray")
        self.status.pack(fill="x", pady=(8, 0))

    def ao_exibir(self):
        self.texto.focus_set()

    def salvar(self):
        conteudo = self.texto.get("1.0", tk.END).strip()
        if not conteudo:
            messagebox.showwarning("Aviso", "Não há texto para salvar.")
            return

        caminho = salvar_anotacao(conteudo)
        if caminho:
            self.status.config(text=f"Salvo em: {caminho}")
            messagebox.showinfo("Sucesso", "Anotação salva com sucesso!")

    def salvar_por_voz(self) -> str | None:
        """Salva o ditado em um arquivo .txt sem abrir diálogo de arquivo."""
        conteudo = self.texto.get("1.0", tk.END).strip()
        if not conteudo:
            return None

        pasta = Path.home() / "Documents" / "Anotacoes de Voz"
        pasta.mkdir(parents=True, exist_ok=True)
        nome = f"anotacao_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.txt"
        caminho = pasta / nome
        caminho.write_text(conteudo, encoding="utf-8")
        self.status.config(text=f"Salvo por voz em: {caminho}")
        return str(caminho)

    def abrir(self):
        resultado = abrir_anotacao()
        if resultado:
            caminho, conteudo = resultado
            self.texto.delete("1.0", tk.END)
            self.texto.insert("1.0", conteudo)
            self.status.config(text=f"Arquivo carregado: {caminho}")

    def limpar(self):
        if self.texto.get("1.0", tk.END).strip():
            if messagebox.askyesno("Confirmar", "Deseja realmente limpar o texto atual?"):
                self.texto.delete("1.0", tk.END)
                self.status.config(text="Área de anotações limpa.")
