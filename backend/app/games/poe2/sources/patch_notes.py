"""PoE 2 patch notes: official forum 2212 ('Early Access Patch Notes')."""

from app.knowledge.sources.ggg_forum import GggPatchNotesFetcher


def patch_notes_fetcher(limit: int = 10) -> GggPatchNotesFetcher:
    return GggPatchNotesFetcher(game="poe2", forum="2212", limit=limit)
