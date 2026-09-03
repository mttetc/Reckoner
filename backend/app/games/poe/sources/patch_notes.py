"""PoE 1 patch notes: official forum 'patch-notes'."""

from app.knowledge.sources.ggg_forum import GggPatchNotesFetcher


def patch_notes_fetcher(limit: int = 10) -> GggPatchNotesFetcher:
    return GggPatchNotesFetcher(game="poe", forum="patch-notes", limit=limit)
