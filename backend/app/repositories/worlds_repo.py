"""World persistence. Same contract as characters; the image column is `cover_asset_id`."""

from __future__ import annotations

from app.models.library import World
from app.repositories.characters_repo import SqlContentRepository, TargetKind


class SqlWorldRepository(SqlContentRepository):
    _model = World
    _asset_column = "cover_asset_id"
    _target_type: TargetKind = "world"
