import sys
from pathlib import Path

class Config:
    """Global Linux-Coop configurations, including directories, commands, and Steam paths."""

    @staticmethod
    def _get_script_dir():
        """Get the script directory, handling PyInstaller frozen executable."""
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # PyInstaller bundle
            return Path(sys._MEIPASS)
        else:
            # Normal Python execution
            return Path(__file__).parent.parent.parent

    SCRIPT_DIR = _get_script_dir()
    PROFILE_DIR = Path.home() / ".config/linux-coop/profiles"
    LOG_DIR = Path.home() / ".cache/linux-coop/logs"
    PREFIX_BASE_DIR = Path.home() / "Games/linux-coop/prefixes/"

    STEAM_PATHS = [
        Path.home() / ".steam/root",
        Path.home() / ".local/share/Steam",
        Path.home() / ".steam/steam",
        Path.home() / ".steam/debian-installation",
        Path.home() / ".steam/steam/root",
        Path.home() / ".steam/steam/steamapps",
        Path.home() / ".local/share/Steam/steamapps",
        Path.home() / ".local/share/Steam/steamapps/common",
    ]

    REQUIRED_COMMANDS = ["bwrap"]  # gamescope is now optional, checked per-profile
    OPTIONAL_COMMANDS = ["gamescope"]

    # Timeout configurations (in seconds)
    PROCESS_START_TIMEOUT = 30
    PROCESS_TERMINATE_TIMEOUT = 10
    SUBPROCESS_TIMEOUT = 15
    FILE_IO_TIMEOUT = 5

    @staticmethod
    def migrate_legacy_paths() -> None:
        """
        Definitive migration for legacy paths. Renames prefix directories and profile
        .json files from using spaces or hyphens to underscores.
        """
        def _migrate_and_rename(path: Path):
            original_name = path.name
            # Standardize to underscores, cleaning up spaces and previous hyphen mistakes
            new_name = original_name.replace(" ", "_").replace("-", "_")

            if original_name == new_name:
                return  # No migration needed for this path

            new_path = path.parent / new_name
            if new_path.exists():
                print(f"Warning: Cannot migrate '{original_name}' because target '{new_name}' already exists. Skipping.", file=sys.stderr)
                return

            try:
                path.rename(new_path)
                print(f"Info: Migrated '{original_name}' to '{new_name}'.")
            except OSError as e:
                print(f"Error: Could not migrate '{original_name}'. Error: {e}", file=sys.stderr)

        # 1. Migrate Prefix Directories
        if Config.PREFIX_BASE_DIR.exists() and Config.PREFIX_BASE_DIR.is_dir():
            # list() creates a snapshot, as we modify the directory while iterating
            for path in list(Config.PREFIX_BASE_DIR.iterdir()):
                if path.is_dir():
                    _migrate_and_rename(path)

        # 2. Migrate Profile Filenames
        if Config.PROFILE_DIR.exists() and Config.PROFILE_DIR.is_dir():
            for path in list(Config.PROFILE_DIR.glob('*.json')):
                _migrate_and_rename(path)

    @staticmethod
    def get_prefix_base_dir(game_name: str) -> Path:
        """
        Returns the base prefix directory for a specific game, replacing spaces with underscores.
        """
        safe_game_name = game_name.replace(" ", "_")
        return Config.PREFIX_BASE_DIR / safe_game_name
