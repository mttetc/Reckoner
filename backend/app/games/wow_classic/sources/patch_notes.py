"""World of Warcraft Classic: the Classic sections of Blizzard's official hotfixes and notes."""

from app.knowledge.sources.blizzard_news import BlizzardNewsFetcher


def patch_notes_fetcher(limit: int = 10) -> BlizzardNewsFetcher:
    return BlizzardNewsFetcher(game="wow_classic", limit=limit)
