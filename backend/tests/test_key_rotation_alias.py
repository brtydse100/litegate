from unittest.mock import AsyncMock, patch

import pytest

from app.models import CurrentUser
from app.rate_limit import _key_ops
from app.routers.keys import regenerate_key


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "rename", "generate", "delete"])
async def test_rotation_handles_unique_aliases_and_restores_old_name_on_failure(failure):
    _key_ops.clear()
    user = CurrentUser(user_id="owner", email="owner@example.com")
    records = {"sk-old": {"token": "sk-old", "key_alias": "owner's key", "spend": 7.25}}

    async def update(key, fields):
        assert all(key == other or info["key_alias"] != fields["key_alias"] for other, info in records.items())
        records[key].update(fields)
        if failure == "rename" and fields["key_alias"].startswith("litegate-rotation-"):
            raise RuntimeError("rename response failed")

    async def generate(user_id, email, team_id, *, initial_spend, key_alias):
        # The original credential must remain live until generation succeeds.
        assert "sk-old" in records
        assert all(info["key_alias"] != key_alias for info in records.values()), "LiteLLM requires unique key aliases"
        if failure == "generate":
            raise RuntimeError("generation failed")
        records["sk-new"] = {"key_alias": key_alias, "spend": initial_spend}
        return {"key": "sk-new"}

    async def delete(key):
        if key == "sk-old" and failure == "delete":
            raise RuntimeError("deletion failed")
        del records[key]

    with (
        patch("app.routers.keys.llm.list_user_keys", new=AsyncMock(return_value=[dict(records["sk-old"])])),
        patch("app.routers.keys.llm.update_key", new=AsyncMock(side_effect=update)),
        patch("app.routers.keys.llm.generate_key", new=AsyncMock(side_effect=generate)),
        patch("app.routers.keys.llm.delete_key", new=AsyncMock(side_effect=delete)),
    ):
        if failure:
            with pytest.raises(RuntimeError):
                await regenerate_key(user)
            assert records == {"sk-old": {"token": "sk-old", "key_alias": "owner's key", "spend": 7.25}}
        else:
            result = await regenerate_key(user)
            assert result.key == "sk-new"
            assert records == {"sk-new": {"key_alias": "owner's key", "spend": 7.25}}
