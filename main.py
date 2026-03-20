from dna.config import get_default_config
from dna.gui.config_launcher import run_persistent_launcher
from dna.settings import load_settings_overrides


def main():
    config = get_default_config()
    persisted = load_settings_overrides(config)
    config.update(persisted)
    run_persistent_launcher(config)


if __name__ == "__main__":
    main()
