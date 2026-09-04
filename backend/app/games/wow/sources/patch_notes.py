"""World of Warcraft (Retail): official Blizzard hotfixes and content update notes."""

from app.knowledge.sources.blizzard_news import BlizzardNewsFetcher


def patch_notes_fetcher(limit: int = 10) -> BlizzardNewsFetcher:
    return BlizzardNewsFetcher(game="wow", limit=limit)
