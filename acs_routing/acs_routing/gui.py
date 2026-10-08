"""Small local Tkinter interface for multi-agent family planning."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .desktop_app import format_plan, process_csv


class RoutingApp:
    """Present CSV selection, employee count, and formatted route results."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Planejamento de visitas — ACS")
        self.root.geometry("900x650")
        self.root.minsize(680, 480)

        self.csv_path = tk.StringVar()
        self.agents = tk.StringVar(value="1")
        self.shift_minutes = tk.StringVar(value="360")
        self.status = tk.StringVar(value="Selecione um arquivo CSV para começar.")

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="Arquivo de famílias (CSV):").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Entry(frame, textvariable=self.csv_path, state="readonly").grid(
            row=0, column=1, sticky="ew", pady=6
        )
        ttk.Button(frame, text="Escolher CSV", command=self.choose_csv).grid(
            row=0, column=2, padx=(8, 0), pady=6
        )

        ttk.Label(frame, text="Funcionários por dia:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Spinbox(frame, from_=1, to=100, textvariable=self.agents, width=8).grid(
            row=1, column=1, sticky="w", pady=6
        )

        ttk.Label(frame, text="Tempo ativo por funcionário (minutos):").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Spinbox(
            frame,
            from_=1,
            to=1440,
            increment=30,
            textvariable=self.shift_minutes,
            width=8,
        ).grid(row=2, column=1, sticky="w", pady=6)

        self.process_button = ttk.Button(
            frame,
            text="Processar e gerar rotas",
            command=self.start_processing,
        )
        self.process_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(frame, textvariable=self.status).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        self.output = ScrolledText(frame, wrap=tk.WORD, font=("Consolas", 10))
        self.output.grid(row=5, column=0, columnspan=3, sticky="nsew")

    def choose_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecione o CSV de famílias",
            filetypes=[("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self.csv_path.set(path)
            self.status.set(f"Selecionado: {Path(path).name}")

    def start_processing(self) -> None:
        path = self.csv_path.get()
        if not path:
            messagebox.showwarning("CSV obrigatório", "Selecione um arquivo CSV.")
            return
        try:
            agents = int(self.agents.get())
            shift_minutes = int(self.shift_minutes.get())
            if agents <= 0:
                raise ValueError
            if shift_minutes <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Valor inválido",
                "Informe números maiores que zero para funcionários e tempo ativo.",
            )
            return
        self.process_button.configure(state=tk.DISABLED)
        self.status.set("Processando famílias e calculando rotas...")
        self.output.delete("1.0", tk.END)
        threading.Thread(
            target=self._process,
            args=(path, agents, shift_minutes),
            daemon=True,
        ).start()

    def _process(self, path: str, agents: int, shift_minutes: int) -> None:
        try:
            families, state = process_csv(path, agents, shift_minutes)
            result = format_plan(families, state, agents)
        except Exception as error:  # surfaced in the UI with the original message
            self.root.after(0, self._show_error, str(error))
            return
        self.root.after(0, self._show_result, result)

    def _show_result(self, result: str) -> None:
        self.output.insert("1.0", result)
        self.status.set("Rotas geradas com sucesso.")
        self.process_button.configure(state=tk.NORMAL)

    def _show_error(self, message: str) -> None:
        self.status.set("Não foi possível gerar as rotas.")
        self.process_button.configure(state=tk.NORMAL)
        messagebox.showerror("Erro no processamento", message)


def main() -> None:
    """Start the local desktop application."""
    root = tk.Tk()
    RoutingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
