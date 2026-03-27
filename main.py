import ctypes
import sys

from dna.config import get_default_config
from dna.gui.config_launcher import run_persistent_launcher
from dna.settings import load_settings_overrides


def _configure_windows_dpi_awareness():
    """Set process DPI awareness before creating Tk root to avoid late rescale/shrink."""
    if sys.platform != "win32":
        return
    try:
        awareness_context_per_monitor_v2 = ctypes.c_void_p(-4)
        set_thread_dpi = getattr(ctypes.windll.user32, "SetThreadDpiAwarenessContext", None)
        if set_thread_dpi is not None:
            set_thread_dpi(awareness_context_per_monitor_v2)
    except Exception:
        pass
    try:
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    _configure_windows_dpi_awareness()
    config = get_default_config()
    persisted = load_settings_overrides(config)
    config.update(persisted)
    run_persistent_launcher(config)


if __name__ == "__main__":
    main()
