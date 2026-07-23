"""Manual player headshot overrides.

Add entries here; they are written into ``players.photo_url`` on every boot.
Keys may be football-data player ids (int) or exact player names (str).
Ids are preferred when names collide.

Example:
    PLAYER_PHOTO_URLS = {
        3160: "https://r2.thesportsdb.com/images/media/player/cutout/orawu51724929691.png",
        "Jamie Leweling": "https://example.com/leweling.png",
    }
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PLAYER_PHOTO_URLS: dict[int | str, str] = {
    # Fill in as needed — ids from /api/players or /api/admin/players/missing-photos
}


def apply_manual_player_photos(*, only_missing: bool = False) -> dict:
    """Apply ``PLAYER_PHOTO_URLS`` into the database.

    Returns counts of updated / skipped / missing keys.
    """
    from app import db
    from app.models import Player

    updated = 0
    skipped = 0
    missing_keys: list[str] = []

    for key, url in PLAYER_PHOTO_URLS.items():
        url = (url or "").strip()
        if not url:
            skipped += 1
            continue

        player = None
        if isinstance(key, int) or (isinstance(key, str) and str(key).isdigit()):
            player = db.session.get(Player, int(key))
        else:
            matches = Player.query.filter(Player.name.ilike(str(key).strip())).all()
            if len(matches) == 1:
                player = matches[0]
            elif len(matches) > 1:
                missing_keys.append(f"{key} (ambiguous x{len(matches)})")
                continue

        if not player:
            missing_keys.append(str(key))
            continue

        if only_missing and player.photo_url and player.photo_url not in ("", "-"):
            skipped += 1
            continue

        if player.photo_url == url:
            skipped += 1
            continue

        player.photo_url = url
        updated += 1

    if updated:
        db.session.commit()

    result = {
        "updated": updated,
        "skipped": skipped,
        "missing_keys": missing_keys,
        "configured": len(PLAYER_PHOTO_URLS),
    }
    if missing_keys:
        logger.warning("Manual photo map: unresolved keys: %s", missing_keys[:20])
    return result
