"""Manual player headshot overrides.

Add entries here; they are written into ``players.photo_url`` on boot / sync.
Keys may be football-data player ids (int) or exact player names (str).
Ids are preferred when names collide.

Example:
    PLAYER_PHOTO_URLS = {
        3160: "https://r2.thesportsdb.com/images/media/player/cutout/orawu51724929691.png",
        "Jamie Leweling": "https://example.com/leweling.png",
    }
"""

PLAYER_PHOTO_URLS: dict[int | str, str] = {
    # Fill in as needed — ids from /api/players or /api/admin/players/missing-photos
}
