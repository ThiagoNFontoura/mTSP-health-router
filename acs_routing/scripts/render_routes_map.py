"""Render persisted weekly routes as an interactive Leaflet map."""

from __future__ import annotations

import argparse
import html
import json
from urllib.parse import urlencode
from urllib.request import urlopen
from pathlib import Path
from typing import Any


DAY_NAMES = ("segunda", "terça", "quarta", "quinta", "sexta")
COLORS = (
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#be123c",
    "#4f46e5",
)


def _parse_ubs(value: str) -> tuple[float, float]:
    """Parse a UBS coordinate in latitude,longitude format."""
    try:
        latitude, longitude = (float(part) for part in value.split(","))
    except ValueError as error:
        raise ValueError("--ubs deve estar no formato latitude,longitude") from error
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("as coordenadas da UBS estão fora dos limites válidos")
    return latitude, longitude


def _load_state(path: str | Path) -> tuple[dict[int, tuple[float, float]], list[dict[str, Any]]]:
    """Load family coordinates and routes from a persisted planner state."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    families = {
        int(item["id"]): (float(item["lat"]), float(item["lon"]))
        for item in payload.get("families", [])
    }
    routes = payload.get("routes", [])
    if not isinstance(routes, list):
        raise ValueError("o state JSON deve conter uma lista em 'routes'")
    return families, routes


def _route_label(route: dict[str, Any], index: int) -> str:
    """Create a stable label even for routes without day/agent metadata."""
    day = route.get("day") or index + 1
    agent = route.get("agent")
    if agent is None:
        return f"Dia {day}"
    day_name = DAY_NAMES[day - 1] if 1 <= day <= len(DAY_NAMES) else f"dia {day}"
    return f"{day_name} — agente {agent}"


def _fetch_osrm_geometry(
    sequence: list[int],
    families: dict[int, tuple[float, float]],
    ubs: tuple[float, float],
    base_url: str,
    profile: str,
    timeout: float,
) -> list[tuple[float, float]]:
    """Fetch one route geometry from OSRM and return latitude/longitude points."""
    coordinates = [ubs if family_id == 0 else families[family_id] for family_id in sequence]
    coordinate_text = ";".join(
        f"{longitude},{latitude}" for latitude, longitude in coordinates
    )
    query = urlencode({"overview": "full", "geometries": "geojson", "steps": "false"})
    url = f"{base_url.rstrip('/')}/route/v1/{profile}/{coordinate_text}?{query}"
    with urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RuntimeError(
            f"OSRM não conseguiu calcular a rota: {payload.get('message', payload.get('code'))}"
        )
    geometry = payload["routes"][0].get("geometry", {}).get("coordinates", [])
    if not geometry:
        raise RuntimeError("OSRM retornou uma rota sem geometria")
    return [(float(latitude), float(longitude)) for longitude, latitude in geometry]


def render_map_html(
    families: dict[int, tuple[float, float]],
    routes: list[dict[str, Any]],
    ubs: tuple[float, float],
    *,
    margin_fraction: float = 0.08,
    osrm_url: str,
    osrm_profile: str = "foot",
    osrm_timeout: float = 30.0,
) -> str:
    """Render OSRM road geometries to a standalone HTML document."""
    if not 0 < margin_fraction < 1:
        raise ValueError("margin_fraction deve estar entre 0 e 1")
    if not osrm_url.strip():
        raise ValueError("a URL do OSRM é obrigatória para renderizar as rotas")

    coordinates = list(families.values()) + [ubs]
    if not coordinates:
        raise ValueError("não há coordenadas para renderizar")
    latitudes = [latitude for latitude, _ in coordinates]
    longitudes = [longitude for _, longitude in coordinates]
    min_latitude, max_latitude = min(latitudes), max(latitudes)
    min_longitude, max_longitude = min(longitudes), max(longitudes)
    latitude_span = max(max_latitude - min_latitude, 1e-9)
    longitude_span = max(max_longitude - min_longitude, 1e-9)
    min_latitude -= latitude_span * margin_fraction
    max_latitude += latitude_span * margin_fraction
    min_longitude -= longitude_span * margin_fraction
    max_longitude += longitude_span * margin_fraction

    width, height = 1200, 760
    padding = 70

    def point(latitude: float, longitude: float) -> tuple[float, float]:
        x = padding + (longitude - min_longitude) / (max_longitude - min_longitude) * (
            width - 2 * padding
        )
        y = padding + (max_latitude - latitude) / (max_latitude - min_latitude) * (
            height - 2 * padding
        )
        return x, y

    svg: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Mapa das rotas semanais">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
    ]
    map_routes: list[dict[str, Any]] = []
    for route_index, route in enumerate(routes):
        sequence = [int(family_id) for family_id in route.get("sequence", [])]
        geographic_points = _fetch_osrm_geometry(
            sequence,
            families,
            ubs,
            osrm_url,
            osrm_profile,
            osrm_timeout,
        )
        route_points = [point(latitude, longitude) for latitude, longitude in geographic_points]
        if len(route_points) < 2:
            continue
        color = COLORS[route_index % len(COLORS)]
        route_label = _route_label(route, route_index)
        map_routes.append(
            {
                "index": route_index,
                "day": route.get("day") or route_index + 1,
                "agent": route.get("agent") or 1,
                "label": route_label,
                "color": color,
                "points": geographic_points,
            }
        )
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in route_points)
        label = html.escape(route_label)
        svg.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" '
            f'stroke-width="3" stroke-linejoin="round" stroke-linecap="round">'
            f"<title>{label}</title></polyline>"
        )

    for family_id, (latitude, longitude) in families.items():
        x, y = point(latitude, longitude)
        svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="#334155" '
            f'stroke="#ffffff" stroke-width="2"><title>Família {family_id}</title></circle>'
        )
        svg.append(
            f'<text x="{x + 9:.2f}" y="{y - 9:.2f}" class="label">'
            f"{html.escape(str(family_id))}</text>"
        )

    ubs_x, ubs_y = point(*ubs)
    svg.extend(
        [
            f'<rect x="{ubs_x - 8:.2f}" y="{ubs_y - 8:.2f}" width="16" height="16" '
            'fill="#111827" stroke="#ffffff" stroke-width="2"><title>UBS</title></rect>',
            f'<text x="{ubs_x + 12:.2f}" y="{ubs_y + 5:.2f}" class="label">UBS</text>',
            "</svg>",
        ]
    )

    map_routes_json = json.dumps(map_routes, ensure_ascii=False)
    agents_json = json.dumps(
        sorted({int(route["agent"]) for route in map_routes}),
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rotas semanais</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; padding: 24px; background: #e2e8f0; color: #0f172a; }}
    main {{ max-width: 1200px; margin: auto; background: white; padding: 20px;
            border-radius: 12px; box-shadow: 0 8px 24px #0f172a22; }}
    #map {{ height: min(78vh, 760px); min-height: 520px; border: 1px solid #cbd5e1;
            border-radius: 8px;
            background: transparent; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 12px 18px; align-items: end;
                 margin: 12px 0 16px; }}
    .controls label {{ display: grid; gap: 4px; font-weight: 600; }}
    select {{ min-width: 180px; padding: 7px 9px; border: 1px solid #94a3b8;
              border-radius: 6px; background: white; font: inherit; }}
    .label {{ font-size: 13px; fill: #0f172a; paint-order: stroke;
              stroke: white; stroke-width: 4px; stroke-linejoin: round; }}
    ul {{ display: flex; flex-wrap: wrap; gap: 12px 24px; padding: 0; list-style: none; }}
    li {{ display: flex; align-items: center; gap: 6px; }}
    .swatch {{ width: 18px; height: 4px; display: inline-block; }}
    #download-map {{ padding: 7px 12px; border: 1px solid #2563eb;
                     border-radius: 6px; background: #2563eb; color: white;
                     font: inherit; cursor: pointer; }}
    #download-map:disabled {{ opacity: 0.65; cursor: wait; }}
    #download-status {{ color: #475569; font-weight: 400; }}
  </style>
</head>
<body>
  <main>
    <h1>Rotas semanais</h1>
    <div class="controls">
      <label>Agente
        <select id="agent-filter">
          <option value="all">Todos os agentes</option>
        </select>
      </label>
      <label>Dia
        <select id="day-filter">
          <option value="all">Todos os dias</option>
          <option value="1">Segunda</option>
          <option value="2">Terça</option>
          <option value="3">Quarta</option>
          <option value="4">Quinta</option>
          <option value="5">Sexta</option>
        </select>
      </label>
      <button id="download-map" type="button">Baixar imagem atual</button>
      <span id="download-status" role="status" aria-live="polite"></span>
    </div>
    <div id="map" role="img" aria-label="Mapa interativo das rotas semanais"></div>
  </main>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          ></script>
  <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"
          ></script>
  <script>
    const routeData = {map_routes_json};
    const agentData = {agents_json};
    const dayNames = ["", "segunda", "terça", "quarta", "quinta", "sexta"];
    const allPoints = routeData.flatMap(route => route.points);
    const rawBounds = L.latLngBounds(allPoints);
    const bounds = rawBounds.pad(0.08);
    const map = L.map("map", {{
      zoomControl: true,
      maxBounds: bounds,
      maxBoundsViscosity: 1.0,
      maxZoom: 18
    }});
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}",
      {{ maxZoom: 18, opacity: 0.42, attribution: "&copy; Esri" }}
    ).addTo(map);
    const routeLayers = [];

    function routeVisible(route) {{
      const agent = document.getElementById("agent-filter").value;
      const day = document.getElementById("day-filter").value;
      return (agent === "all" || String(route.agent) === agent)
        && (day === "all" || String(route.day) === day);
    }}

    function updateRoutes() {{
      routeLayers.forEach(item => {{
        if (routeVisible(item.route)) {{
          item.layer.addTo(map);
        }} else {{
          map.removeLayer(item.layer);
        }}
      }});
    }}

    routeData.forEach(route => {{
      const layer = L.polyline(route.points, {{
        color: route.color, weight: 5, opacity: 0.9
      }}).bindTooltip(route.label);
      routeLayers.push({{ route, layer }});
    }});
    agentData.forEach(agent => {{
      const option = document.createElement("option");
      option.value = agent;
      option.textContent = "Agente " + agent;
      document.getElementById("agent-filter").appendChild(option);
    }});
    document.getElementById("agent-filter").addEventListener("change", updateRoutes);
    document.getElementById("day-filter").addEventListener("change", updateRoutes);
    document.getElementById("download-map").addEventListener("click", async () => {{
      const button = document.getElementById("download-map");
      const status = document.getElementById("download-status");
      const agent = document.getElementById("agent-filter").value;
      const day = document.getElementById("day-filter").value;
      button.disabled = true;
      status.textContent = "Capturando...";
      try {{
        const canvas = await html2canvas(document.getElementById("map"), {{
          useCORS: true,
          allowTaint: false,
          backgroundColor: "#f8fafc",
          logging: false
        }});
        const link = document.createElement("a");
        const agentLabel = agent === "all" ? "todos-agentes" : "agente-" + agent;
        const dayLabel = day === "all" ? "todos-dias" : dayNames[Number(day)];
        link.download = "rotas-" + agentLabel + "-" + dayLabel + ".png";
        link.href = canvas.toDataURL("image/png");
        link.click();
        status.textContent = "Imagem baixada.";
      }} catch (error) {{
        console.error(error);
        status.textContent = "Não foi possível capturar o mapa.";
      }} finally {{
        button.disabled = false;
      }}
    }});
    map.fitBounds(bounds, {{ padding: [45, 45], maxZoom: 16 }});
    const minimumZoom = map.getBoundsZoom(bounds, false);
    map.setMinZoom(minimumZoom);
    map.on("zoomend", () => {{
      if (map.getZoom() < minimumZoom) {{
        map.setZoom(minimumZoom, {{ animate: false }});
      }}
    }});
    map.on("moveend", () => {{
      map.panInsideBounds(bounds, {{ animate: false }});
    }});
    updateRoutes();
  </script>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    """Build the map-rendering CLI."""
    parser = argparse.ArgumentParser(description="Renderizar rotas semanais em um mapa HTML")
    parser.add_argument("--state-file", required=True, help="JSON salvo pelo planejador")
    parser.add_argument("--ubs", required=True, help="coordenadas da UBS: latitude,longitude")
    parser.add_argument("--output", default="routes_map.html", help="HTML de saída")
    parser.add_argument(
        "--osrm-url",
        required=True,
        help="URL base do OSRM usado para obter a geometria viária real",
    )
    parser.add_argument(
        "--osrm-profile",
        default="foot",
        help="perfil do OSRM usado no endpoint route (padrão: foot)",
    )
    parser.add_argument(
        "--osrm-timeout",
        type=float,
        default=30.0,
        help="timeout, em segundos, de cada consulta ao OSRM",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=0.08,
        help="margem proporcional adicionada a cada lado (padrão: 0.08)",
    )
    return parser


def main() -> None:
    """Load a state file and write the rendered map."""
    args = build_parser().parse_args()
    families, routes = _load_state(args.state_file)
    document = render_map_html(
        families,
        routes,
        _parse_ubs(args.ubs),
        margin_fraction=args.margin,
        osrm_url=args.osrm_url,
        osrm_profile=args.osrm_profile,
        osrm_timeout=args.osrm_timeout,
    )
    output = Path(args.output)
    output.write_text(document, encoding="utf-8")
    print(f"Mapa salvo em: {output}")


if __name__ == "__main__":
    main()
