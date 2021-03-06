"""Validate manifests."""
import argparse
import pathlib
import sys
from time import monotonic

from . import (
    codeowners,
    config_flow,
    coverage,
    dependencies,
    manifest,
    services,
    ssdp,
    translations,
    zeroconf,
)
from .model import Config, Integration

INTEGRATION_PLUGINS = [
    codeowners,
    config_flow,
    dependencies,
    manifest,
    services,
    ssdp,
    translations,
    zeroconf,
]
HASS_PLUGINS = [
    coverage,
]


def valid_integration_path(integration_path):
    """Test if it's a valid integration."""
    path = pathlib.Path(integration_path)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"{integration_path} is not a directory.")

    return path


def get_config() -> Config:
    """Return config."""
    parser = argparse.ArgumentParser(description="Hassfest")
    parser.add_argument(
        "--action", type=str, choices=["validate", "generate"], default=None
    )
    parser.add_argument(
        "--integration-path",
        action="append",
        type=valid_integration_path,
        help="Validate a single integration",
    )
    parsed = parser.parse_args()

    if parsed.action is None:
        parsed.action = "validate" if parsed.integration_path else "generate"

    if parsed.action == "generate" and parsed.integration_path:
        raise RuntimeError(
            "Generate is not allowed when limiting to specific integrations"
        )

    if (
        not parsed.integration_path
        and not pathlib.Path("requirements_all.txt").is_file()
    ):
        raise RuntimeError("Run from Home Assistant root")

    return Config(
        root=pathlib.Path(".").absolute(),
        specific_integrations=parsed.integration_path,
        action=parsed.action,
    )


def main():
    """Validate manifests."""
    try:
        config = get_config()
    except RuntimeError as err:
        print(err)
        return 1

    plugins = INTEGRATION_PLUGINS

    if config.specific_integrations:
        integrations = {}

        for int_path in config.specific_integrations:
            integration = Integration(int_path)
            integration.load_manifest()
            integrations[integration.domain] = integration

    else:
        integrations = Integration.load_dir(pathlib.Path("homeassistant/components"))
        plugins += HASS_PLUGINS

    for plugin in plugins:
        try:
            start = monotonic()
            print(f"Validating {plugin.__name__.split('.')[-1]}...", end="", flush=True)
            plugin.validate(integrations, config)
            print(" done in {:.2f}s".format(monotonic() - start))
        except RuntimeError as err:
            print()
            print()
            print("Error!")
            print(err)
            return 1

    # When we generate, all errors that are fixable will be ignored,
    # as generating them will be fixed.
    if config.action == "generate":
        general_errors = [err for err in config.errors if not err.fixable]
        invalid_itg = [
            itg
            for itg in integrations.values()
            if any(not error.fixable for error in itg.errors)
        ]
    else:
        # action == validate
        general_errors = config.errors
        invalid_itg = [itg for itg in integrations.values() if itg.errors]

    print()
    print("Integrations:", len(integrations))
    print("Invalid integrations:", len(invalid_itg))

    if not invalid_itg and not general_errors:
        if config.action == "generate":
            for plugin in plugins:
                if hasattr(plugin, "generate"):
                    plugin.generate(integrations, config)
        return 0

    print()
    if config.action == "generate":
        print("Found errors. Generating files canceled.")
        print()

    if general_errors:
        print("General errors:")
        for error in general_errors:
            print("*", error)
        print()

    for integration in sorted(invalid_itg, key=lambda itg: itg.domain):
        extra = f" - {integration.path}" if config.specific_integrations else ""
        print(f"Integration {integration.domain}{extra}:")
        for error in integration.errors:
            print("*", error)
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
