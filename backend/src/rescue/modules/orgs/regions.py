"""Region boundaries: load the seeded GeoJSON into core.regions (blueprint 11.1, 15.2).

A region is the shard key of the whole system — every operational row carries a
`region_id`. Boundaries come from OpenStreetMap through Nominatim and live in
`backend/seeds/regions/*.geojson`, one GeoJSON Feature each, so a fresh clone
seeds offline and every boundary change is a reviewable diff.

Run it from `backend/`:  uv run python -m rescue.modules.orgs.regions
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rescue.platform.db import dispose_engine, get_engine

# backend/src/rescue/modules/orgs/regions.py → backend/seeds/regions
SEEDS_DIR = Path(__file__).parents[4] / "seeds" / "regions"

# ST_MakeValid: OSM boundaries sometimes self-intersect. ST_Multi: the column is
# MultiPolygon, while Nominatim hands back a single Polygon.
UPSERT = text("""
    insert into core.regions (id, name, timezone, boundary)
    values (
        :id, :name, :timezone,
        st_multi(st_makevalid(st_setsrid(st_geomfromgeojson(:geometry), 4326)))::geography
    )
    on conflict (id) do update
    set name = excluded.name, timezone = excluded.timezone, boundary = excluded.boundary
""")


async def seed_regions(engine: AsyncEngine, seeds_dir: Path = SEEDS_DIR) -> list[str]:
    """Upsert every region file. Idempotent: a second run changes no row count."""
    files = sorted(seeds_dir.glob("*.geojson"))
    if not files:
        raise FileNotFoundError(f"no region seed files in {seeds_dir}")

    seeded: list[str] = []
    async with engine.begin() as conn:  # one transaction: every region or none
        for path in files:
            feature = json.loads(path.read_text())
            properties = feature["properties"]
            await conn.execute(
                UPSERT,
                {
                    "id": properties["id"],
                    "name": properties["name"],
                    "timezone": properties["timezone"],
                    "geometry": json.dumps(feature["geometry"]),
                },
            )
            seeded.append(properties["id"])
    return seeded


async def _main() -> None:
    seeded = await seed_regions(get_engine())
    print(f"seeded {len(seeded)} region(s): {', '.join(seeded)}")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
