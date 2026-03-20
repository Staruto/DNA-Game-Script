from dna.config import get_default_config
from dna.gui.config_launcher import open_config_launcher
from dna.runtime.app import DNAApp
from dna.settings import load_settings_overrides, save_settings_overrides


def main():
    config = get_default_config()
    persisted = load_settings_overrides(config)
    config.update(persisted)

    selected = open_config_launcher(config)
    if selected is None:
        print("[INFO] Launch cancelled by user.")
        return

    config.update(selected)
    saved_path = save_settings_overrides(selected, get_default_config())
    print(f"[INFO] Settings saved to {saved_path.name}.")

    app = DNAApp(config)
    app.run()


if __name__ == "__main__":
    main()
