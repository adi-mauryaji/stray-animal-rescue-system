"""The seeded boundaries are real geography, not just rows (blueprint 15.2).

Integration test: needs `docker compose up -d db`, the migration applied and
`backend/.env`, so run pytest from `backend/`. It seeds the dev database on
purpose — the regions are meant to be there, and the seed is idempotent.
"""

import asyncio

from sqlalchemy import text

from rescue.modules.orgs.regions import seed_regions
from rescue.platform.db import dispose_engine, get_engine

COVERS = text("""
    select id from core.regions
    where st_covers(boundary, st_point(:lon, :lat, 4326)::geography)
    order by id limit 1
""")

# lon, lat, the region that must contain the point
POINTS = [
    (77.2167, 28.6315, "in-dl-delhi"),  # Connaught Place, Delhi
    (77.5040, 28.4744, "in-up-gautam-buddha-nagar"),  # Greater Noida
    (72.8777, 19.0760, None),  # Mumbai: outside both pilot regions
]


async def _seed_twice_then_locate() -> tuple[list[str], int, list[str | None]]:
    engine = get_engine()
    try:
        await seed_regions(engine)
        seeded = await seed_regions(engine)  # second run must not duplicate
        async with engine.connect() as conn:
            count = (await conn.execute(text("select count(*) from core.regions"))).scalar_one()
            found = [
                (await conn.execute(COVERS, {"lon": lon, "lat": lat})).scalar_one_or_none()
                for lon, lat, _ in POINTS
            ]
        return seeded, count, found
    finally:
        await dispose_engine()


def test_regions_seed_is_idempotent_and_boundaries_contain_the_right_points() -> None:
    seeded, count, found = asyncio.run(_seed_twice_then_locate())

    assert sorted(seeded) == ["in-dl-delhi", "in-up-gautam-buddha-nagar"]
    assert count == 2, "the second seed run inserted duplicate regions"
    assert found == [expected for *_, expected in POINTS]
