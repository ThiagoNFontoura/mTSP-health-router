"""Small local Tkinter interface for multi-agent family planning."""

from __future__ import annotations

import threading
import time
import tkinter as tk
import importlib.util
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .desktop_app import (
    _virtual_ubs,
    format_plan,
    process_csv,
    update_csv_last_visit_dates,
)
from .models import Family, WeekState
from .state import save_state


OSRM_URL = "https://router.project-osrm.org"
OSRM_PROFILE = "driving"


class RoutingApp:
    """Present CSV selection, agent count, and formatted route results."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Planejamento de visitas — ACS")
        self.root.geometry("900x650")
        self.root.minsize(680, 480)

        self.csv_path = tk.StringVar()
        self.agents = tk.StringVar(value="1")
        self.shift_minutes = tk.StringVar(value="360")
        self.weeks_ahead = tk.StringVar(value="0")
        self.status = tk.StringVar(value="Selecione um arquivo CSV para começar.")
        self.map_path: Path | None = None
        self._families: list[Family] | None = None
        self._state: WeekState | None = None

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)

        ttk.Label(frame, text="Arquivo de famílias (CSV):").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Entry(frame, textvariable=self.csv_path, state="readonly").grid(
            row=0, column=1, sticky="ew", pady=6
        )
        ttk.Button(frame, text="Escolher CSV", command=self.choose_csv).grid(
            row=0, column=2, padx=(8, 0), pady=6
        )

        ttk.Label(frame, text="Agentes de saúde por dia:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Spinbox(frame, from_=1, to=100, textvariable=self.agents, width=8).grid(
            row=1, column=1, sticky="w", pady=6
        )

        ttk.Label(frame, text="Tempo ativo por agente (minutos):").grid(
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

        ttk.Label(frame, text="Semanas para simulação (a partir de hoje):").grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Spinbox(
            frame,
            from_=0,
            to=520,
            textvariable=self.weeks_ahead,
            width=8,
        ).grid(row=3, column=1, sticky="w", pady=6)

        self.process_button = ttk.Button(
            frame,
            text="Processar e gerar rotas",
            command=self.start_processing,
        )
        self.process_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)

        self.map_button = ttk.Button(
            frame,
            text="Abrir mapa das rotas",
            command=self.open_map,
            state=tk.DISABLED,
        )
        self.map_button.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        ttk.Label(frame, textvariable=self.status).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        self.output = ScrolledText(frame, wrap=tk.WORD, font=("Consolas", 10))
        self.output.grid(row=7, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(7, weight=1)

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
            weeks_ahead = int(self.weeks_ahead.get())
            if agents <= 0 or weeks_ahead < 0:
                raise ValueError
            if shift_minutes <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Valor inválido",
                "Informe agentes e tempo ativo maiores que zero, "
                "e semanas de simulação maiores ou iguais a zero.",
            )
            return
        self.process_button.configure(state=tk.DISABLED)
        self.status.set("Processando famílias e calculando rotas...")
        self.output.delete("1.0", tk.END)
        self.map_path = None
        self._families = None
        self._state = None
        self.map_button.configure(state=tk.DISABLED)
        threading.Thread(
            target=self._process,
            args=(path, agents, shift_minutes, weeks_ahead),
            daemon=True,
        ).start()

    def _process(
        self,
        path: str,
        agents: int,
        shift_minutes: int,
        weeks_ahead: int,
    ) -> None:
        try:
            solver_started_at = time.perf_counter()
            families, state = process_csv(
                path,
                agents,
                shift_minutes,
                weeks_ahead=weeks_ahead,
            )
            solver_seconds = time.perf_counter() - solver_started_at
            result = format_plan(
                families,
                state,
                agents,
                execution_seconds=solver_seconds,
            )
            update_csv_last_visit_dates(path, state)
        except Exception as error:  # surfaced in the UI with the original message
            self.root.after(0, self._show_error, str(error))
            return
        self.root.after(0, self._show_result, result, families, state)

    def _show_result(
        self, result: str, families: list[Family], state: WeekState
    ) -> None:
        self.output.insert("1.0", result)
        self._families = families
        self._state = state
        self.status.set("Rotas geradas com sucesso.")
        self.process_button.configure(state=tk.NORMAL)
        self.map_button.configure(state=tk.NORMAL)

    def _render_map(self, families: list[Family], state: WeekState) -> Path:
        """Render the plan with real road geometries from OSRM."""
        output_dir = Path.home() / ".acs-routing" / "gui"
        output_dir.mkdir(parents=True, exist_ok=True)
        state_path = output_dir / "state.json"
        map_path = output_dir / "routes.html"
        save_state(state, state_path)
        renderer_path = Path(__file__).resolve().parents[1] / "scripts" / "render_routes_map.py"
        spec = importlib.util.spec_from_file_location("acs_route_map_renderer", renderer_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"não foi possível carregar o renderizador: {renderer_path}")
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        family_coordinates = {
            family.id: (family.lat, family.lon) for family in families
        }
        routes = [
            {
                "day": route.day,
                "agent": route.agent,
                "sequence": route.sequence,
            }
            for route in state.routes
        ]
        document = renderer.render_map_html(
            family_coordinates,
            routes,
            _virtual_ubs(families),
            osrm_url=OSRM_URL,
            osrm_profile=OSRM_PROFILE,
        )
        map_path.write_text(document, encoding="utf-8")
        return map_path

    def open_map(self) -> None:
        """Render with OSRM and open the latest plan in the default browser."""
        if self._families is None or self._state is None:
            return
        self.map_button.configure(state=tk.DISABLED)
        self.status.set("Consultando o OSRM e desenhando as rotas reais...")
        threading.Thread(target=self._generate_map, daemon=True).start()

    def _generate_map(self) -> None:
        if self._families is None or self._state is None:
            return
        try:
            self.map_path = self._render_map(self._families, self._state)
        except Exception as error:
            self.root.after(0, self._show_map_error, str(error))
            return
        self.root.after(0, self._open_rendered_map)

    def _open_rendered_map(self) -> None:
        if self.map_path is None:
            return
        self.status.set("Mapa com rotas reais do OSRM gerado.")
        self.map_button.configure(state=tk.NORMAL)
        webbrowser.open(self.map_path.resolve().as_uri())

    def _show_map_error(self, message: str) -> None:
        self.status.set("Rotas geradas; mapa aguardando o OSRM.")
        self.map_button.configure(state=tk.NORMAL)
        messagebox.showerror(
            "OSRM indisponível",
            "Não foi possível obter as rotas reais do OSRM.\n\n"
            f"{message}\n\n"
            "Verifique sua conexão com a internet e tente abrir o mapa novamente.",
        )

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
