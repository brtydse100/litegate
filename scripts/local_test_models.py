"""Manage provider credentials and artificial accounting rates in the local test proxy."""

import argparse
import getpass
import os
import urllib.error

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def local_models(call, proxy, master):
    return call(proxy, "/v2/model/info?page=1&size=100", key=master).get("data", [])


def free_deployment(model):
    params = model.get("litellm_params", {})
    upstream = params.get("model", "")
    native = (
        upstream.startswith("openrouter/")
        and params.get("api_base") in (None, OPENROUTER_BASE)
        and params.get("custom_llm_provider") in (None, "openrouter")
    )
    compatible = (
        upstream.startswith("openai/")
        and params.get("api_base") == OPENROUTER_BASE
        and params.get("custom_llm_provider") == "openai"
    )
    return (native or compatible) and (
        upstream.split("/", 1)[1] == "openrouter/free" or upstream.endswith(":free")
    )


def accounting_route(model):
    return {
        "model": "openai/" + model["litellm_params"]["model"].split("/", 1)[1],
        "api_base": OPENROUTER_BASE,
        "custom_llm_provider": "openai",
    }


def configure_pricing(call, proxy, master):
    rates = {"free-1": 0.1, "free-2": 0.0001}
    models = [
        model
        for model in local_models(call, proxy, master)
        if model.get("model_name") in rates
    ]
    if {model["model_name"] for model in models} != set(rates):
        raise RuntimeError(
            "Run local_test.py providers first; both free-1 and free-2 must exist."
        )
    if any(
        not free_deployment(model) or not model.get("model_info", {}).get("id")
        for model in models
    ):
        raise RuntimeError(
            "Refusing to change a deployment that is not a known free OpenRouter route."
        )
    for model in models:
        rate = rates[model["model_name"]]
        prices = {"input_cost_per_token": rate, "output_cost_per_token": rate}
        call(
            proxy,
            "/model/update",
            key=master,
            payload={
                "model_info": {"id": model["model_info"]["id"], **prices},
                "litellm_params": {**accounting_route(model), **prices},
            },
        )
    verified = local_models(call, proxy, master)
    for model in models:
        actual = next(
            (
                item
                for item in verified
                if item.get("model_info", {}).get("id") == model["model_info"]["id"]
            ),
            None,
        )
        rate = rates[model["model_name"]]
        expected = {
            **accounting_route(model),
            "input_cost_per_token": rate,
            "output_cost_per_token": rate,
            "api_key": model["litellm_params"].get("api_key"),
        }
        if not actual or any(
            actual.get("litellm_params", {}).get(field) != value
            for field, value in expected.items()
        ):
            raise RuntimeError(
                "Could not verify the saved test prices; inspect the local model settings."
            )
        print(
            f"{model['model_name']}: local accounting ${rate}/token for input and output (provider route remains free)."
        )


def refresh_key(call, proxy, master, provider_key):
    if not provider_key:
        raise ValueError("An OpenRouter API key is required")
    call("https://openrouter.ai", "/api/v1/auth/key", key=provider_key)
    models = [
        model
        for model in local_models(call, proxy, master)
        if model.get("model_name") in {"free-router", "free-1", "free-2"}
    ]
    if not models or any(
        not free_deployment(model) or not model.get("model_info", {}).get("id")
        for model in models
    ):
        raise RuntimeError(
            "No safe existing free deployments to refresh; run local_test.py providers first."
        )
    for model in models:
        call(
            proxy,
            "/model/update",
            key=master,
            payload={
                "model_info": {"id": model["model_info"]["id"]},
                "litellm_params": {"api_key": provider_key},
            },
        )
    verified = local_models(call, proxy, master)
    preserved = (
        "model",
        "api_base",
        "custom_llm_provider",
        "input_cost_per_token",
        "output_cost_per_token",
    )
    for model in models:
        actual = next(
            (
                item
                for item in verified
                if item.get("model_info", {}).get("id") == model["model_info"]["id"]
            ),
            None,
        )
        if not actual or any(
            actual.get("litellm_params", {}).get(field)
            != model["litellm_params"].get(field)
            for field in preserved
        ):
            raise RuntimeError(
                "Credential update completed but model routes or prices changed; inspect local model settings."
            )
    print(
        "Refreshed local OpenRouter credentials. Model routes and accounting prices were preserved."
    )


def main():
    from local_test import MASTER, PROXY, call

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pricing", "refresh-key"])
    args = parser.parse_args()
    try:
        if args.action == "pricing":
            configure_pricing(call, PROXY, MASTER)
        else:
            key = os.environ.get("OPENROUTER_API_KEY") or getpass.getpass(
                "Valid OpenRouter API key (hidden): "
            )
            refresh_key(call, PROXY, MASTER, key)
    except urllib.error.HTTPError as exc:
        print(
            f"Credential or model update rejected: HTTP {exc.code}. Check the OpenRouter key and the local proxy; no credential was printed."
        )
        raise SystemExit(1) from None
    except (RuntimeError, ValueError) as exc:
        print(str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print(
            f"Local model configuration failed: {type(exc).__name__}. No provider credential was printed."
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
