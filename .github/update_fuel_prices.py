"""Refresca data/fuel-stations.json con la foto de precios del Ministerio.

Lo lanza `.github/workflows/fuel-prices.yml` en el repositorio publicado, varias veces al
día, sobre la web ya construida: no hay pipeline, ni geopandas, ni datos crudos. Solo la
biblioteca estándar. Escribe exactamente lo que escribe `web/export.py` (`_fuel_stations`) y
`tests/test_fuel_auto_update.py` comprueba que los dos coinciden sobre la misma foto.

El ámbito (`city` o `village`) sale de `data/districts.json`, que ya trae el de cada distrito;
una estación fuera de todo distrito es `village`, como en el export.

Uso: python .github/update_fuel_prices.py [raíz del sitio]
"""

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

URL = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes"
    "/EstacionesTerrestres/FiltroMunicipio/7214"
)
PRODUCTS = {"price_95": "Precio Gasolina 95 E5", "price_diesel": "Precio Gasoleo A"}
BRAND_FIXES = {"CARRREFOUR": "CARREFOUR"}
DECIMALS = 5


def _number(text: str) -> float | None:
    return float(text.replace(",", ".")) if text and text.strip() else None


def _inside(x: float, y: float, ring: list) -> bool:
    """Punto en anillo por cruce de rayos."""
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _scope(x: float, y: float, districts: dict) -> str:
    for feature in districts["features"]:
        geom = feature["geometry"]
        polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for outer, *holes in polygons:
            if _inside(x, y, outer) and not any(_inside(x, y, h) for h in holes):
                return feature["properties"]["scope"]
    return "village"


def build(body: dict, districts: dict) -> dict:
    """La FeatureCollection de `fuel-stations.json` a partir de la respuesta del Ministerio."""
    at = datetime.strptime(body["Fecha"], "%d/%m/%Y %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    features = []
    for s in body["ListaEESSPrecio"]:
        brand = s["Rótulo"].strip()
        x, y = _number(s["Longitud (WGS84)"]), _number(s["Latitud"])
        props = {
            "name": BRAND_FIXES.get(brand, brand),
            "note": s["Dirección"].strip(),
            **{col: _number(s[field]) for col, field in PRODUCTS.items()},
            "prices_at": at,
            "scope": _scope(x, y, districts),
        }
        features.append(
            {
                "type": "Feature",
                # Los nulos no viajan, como en el export
                "properties": {k: v for k, v in props.items() if v is not None},
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(x, DECIMALS), round(y, DECIMALS)],
                },
            }
        )
    # El export ordena por rótulo con un orden estable sobre el orden del Ministerio
    features.sort(key=lambda f: f["properties"]["name"])
    return {"type": "FeatureCollection", "features": features}


def dump(collection: dict) -> str:
    return json.dumps(collection, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(root: Path) -> None:
    request = urllib.request.Request(URL, headers={"User-Agent": "valenciadades.es"})
    with urllib.request.urlopen(request, timeout=90) as resp:
        body = json.load(resp)
    if body.get("ResultadoConsulta") != "OK" or not body.get("ListaEESSPrecio"):
        sys.exit(f"El Ministerio no devolvió estaciones: {body.get('ResultadoConsulta')}")
    districts = json.loads((root / "data" / "districts.json").read_text(encoding="utf-8"))
    out = root / "data" / "fuel-stations.json"
    out.write_text(dump(build(body, districts)), encoding="utf-8")
    print(f"{len(body['ListaEESSPrecio'])} estaciones, foto del {body['Fecha']}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
