"""Local pricing changes preserve model routes and provider credentials."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import urllib.error

import pytest

spec = importlib.util.spec_from_file_location("local_test_models", Path(__file__).resolve().parents[2] / "scripts/local_test_models.py")
models_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models_helper)


@pytest.fixture
def native():
    models = [
        {
            "model_name": f"free-{number}",
            "model_info": {"id": str(number)},
            "litellm_params": {"model": f"openrouter/author/model{number}:free", "api_key": "synthetic-provider-secret"},
        }
        for number in (1, 2)
    ]
    updates = []

    def call(base, path, *, key=None, payload=None):
        if base == "https://openrouter.ai":
            assert path == "/api/v1/auth/key"
            return {"data": {}}
        if path.startswith("/v2/model/info"):
            return {"data": deepcopy(models)}
        assert path == "/model/update"
        updates.append(deepcopy(payload))
        target = next(model for model in models if model["model_info"]["id"] == payload["model_info"]["id"])
        target["model_info"].update(payload["model_info"])
        target["litellm_params"].update(payload["litellm_params"])
        return {}

    return models, updates, call


def test_pricing_changes_only_accounting_rates_and_verifies_them(native, capsys):
    models, updates, call = native
    models_helper.configure_pricing(call, "http://127.0.0.1:4000", "synthetic-master")
    assert [model["litellm_params"]["input_cost_per_token"] for model in models] == [0.1, 0.0001]
    assert all(set(update["litellm_params"]) == {"input_cost_per_token", "output_cost_per_token"} for update in updates)
    assert all(model["litellm_params"]["api_key"] == "synthetic-provider-secret" for model in models)
    assert "synthetic-provider-secret" not in capsys.readouterr().out


def test_key_refresh_preserves_existing_prices_and_routes(native, capsys):
    models, updates, call = native
    models_helper.configure_pricing(call, "http://127.0.0.1:4000", "synthetic-master")
    updates.clear()
    models_helper.refresh_key(call, "http://127.0.0.1:4000", "synthetic-master", "replacement-provider-secret")
    assert all(set(update["litellm_params"]) == {"api_key"} for update in updates)
    assert [model["litellm_params"]["input_cost_per_token"] for model in models] == [0.1, 0.0001]
    assert "replacement-provider-secret" not in capsys.readouterr().out


def test_paid_route_is_rejected_before_any_changes(native):
    models, updates, call = native
    models[1]["litellm_params"]["model"] = "openrouter/author/paid-model"
    with pytest.raises(RuntimeError, match="known free"):
        models_helper.configure_pricing(call, "http://127.0.0.1:4000", "synthetic-master")
    assert updates == []


def test_invalid_provider_credential_does_not_change_deployments(native):
    models, updates, call = native
    before = deepcopy(models)

    def reject_auth(base, path, **kwargs):
        if base == "https://openrouter.ai":
            raise urllib.error.HTTPError(base + path, 401, "Unauthorized", {}, None)
        return call(base, path, **kwargs)

    with pytest.raises(urllib.error.HTTPError):
        models_helper.refresh_key(reject_auth, "http://127.0.0.1:4000", "synthetic-master", "invalid-provider-secret")
    assert updates == []
    assert models == before


def test_key_refresh_detects_unexpected_route_changes(native):
    models, _, call = native

    def changing_call(base, path, **kwargs):
        result = call(base, path, **kwargs)
        if path == "/model/update":
            models[0]["litellm_params"]["model"] = "openrouter/author/other:free"
        return result

    with pytest.raises(RuntimeError, match="routes or prices changed"):
        models_helper.refresh_key(changing_call, "http://127.0.0.1:4000", "synthetic-master", "replacement-provider-secret")
