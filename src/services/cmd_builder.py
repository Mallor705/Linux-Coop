"""
Command builder module for the Twinverse application.

This module provides functionality to build complex command strings for launching
Steam instances with various configurations, including gamescope and bwrap sandboxing.
"""

from pathlib import Path
from typing import Dict, List, Optional

from src.core import Logger
from src.models import Profile
from src.services.device_manager import DeviceManager


class CommandBuilder:
    """Builds command strings for launching Steam instances with various configurations."""

    def __init__(
        self,
        logger: Logger,
        profile: Profile,
        device_info: Dict,
        device_manager: DeviceManager,
        instance_num: int,
        home_path: Path,
        virtual_joystick_path: Optional[str],
    ):
        """Initialize the CommandBuilder with necessary parameters."""
        self.logger = logger
        self.profile = profile
        self.device_info = device_info
        self.device_manager = device_manager
        self.instance_num = instance_num
        self.home_path = home_path
        self.virtual_joystick_path = virtual_joystick_path

    def build_command(self) -> List[str]:
        """
        Build the final command array in the correct order.

        [gamescope] -> [bwrap] -> [steam]  (when gamescope is enabled)
        [bwrap] -> [steam]                  (when gamescope is disabled)
        """
        # 1. Build the innermost steam command
        steam_cmd = self._build_base_steam_command()

        # 2. Build the bwrap command, which will wrap the steam command
        bwrap_cmd = self._build_bwrap_command(self.instance_num)

        # 3. Prepend bwrap to the steam command
        final_cmd = bwrap_cmd + steam_cmd

        # 4. Build the Gamescope command and prepend it (if enabled)
        if self.profile.use_gamescope:
            should_add_grab_flags = self.device_info.get("should_add_grab_flags", False)
            gamescope_cmd = self._build_gamescope_command(should_add_grab_flags)

            # Add the '--' separator before the command Gamescope will run
            final_cmd = gamescope_cmd + ["--"] + final_cmd
            self.logger.info(f"Instance {self.instance_num}: Launching with Gamescope")
        else:
            self.logger.info(f"Instance {self.instance_num}: Launching without Gamescope (bwrap only)")

        return final_cmd

    def _build_gamescope_command(self, should_add_grab_flags: bool) -> List[str]:
        """Build the Gamescope command."""
        width, height = self.device_manager.get_instance_dimensions(self.profile, self.instance_num)
        if not width or not height:
            self.logger.error(f"Instance {self.instance_num}: Invalid dimensions. Aborting launch.")
            return []

        # Get refresh rate for the specific instance
        refresh_rate = 60  # Default
        if self.profile.player_configs and 0 <= self.instance_num < len(self.profile.player_configs):
            refresh_rate = self.profile.player_configs[self.instance_num].refresh_rate
        else:
            self.logger.warning(
                f"Instance {self.instance_num}: Could not find player config, defaulting refresh rate to 60Hz."
            )

        refresh_rate_str = str(refresh_rate)

        # fmt: off
        cmd = [
            "gamescope",
            "-e",
            "-W", str(width),
            "-H", str(height),
            "-w", str(width),
            "-h", str(height),
            "-o", refresh_rate_str,
            "-r", refresh_rate_str,
            "--adaptive-sync",
        ]
        # fmt: on

        if self.profile.use_steamdeck_tag:
            cmd.append("--mangoapp")

        if not self.profile.is_splitscreen_mode:
            cmd.append("-f")
        else:
            cmd.append("-b")

        if should_add_grab_flags:
            self.logger.info(f"Instance {self.instance_num}: Using dedicated mouse. Grabbing input.")
            cmd.append("--force-grab-cursor")

        return cmd

    def _build_base_steam_command(self) -> List[str]:
        """Build the base steam command."""
        cmd = ["steam"]

        if self.profile.use_steamdeck_tag:
            cmd.append("-steamdeck")

        if self.profile.use_gamescope:
            self.logger.info(f"Instance {self.instance_num}: Using Steam command with Gamescope flags.")
            cmd.extend(["-gamepadui", "-steamos3"])
        else:
            self.logger.info(f"Instance {self.instance_num}: Using plain Steam command.")

        return cmd

    def _build_bwrap_command(self, instance_idx: int) -> List[str]:
        """
        Build the bwrap command for sandboxing.

        This strategy uses the real user's home directory but mounts instance-specific
        Steam directories over the real ones to achieve isolation.
        """
        orig_home = Path.home()
        orig_local = orig_home / ".local"

        # fmt: off
        cmd = [
            "bwrap",
            "--dev-bind", "/", "/",
            "--dev-bind", "/dev", "/dev",
            "--tmpfs", "/dev/shm",
            "--proc", "/proc",
            "--die-with-parent",
            "--tmpfs", "/tmp",
            "--bind", "/tmp/.X11-unix", "/tmp/.X11-unix",
        ]
        # fmt: on

        # --- Device Isolation ---

        cmd.extend(["--tmpfs", "/dev/input"])

        joystick_path = self.device_info.get("joystick_path_str_for_instance")
        # If the instance has no physical joystick, assign the virtual one if it exists
        if not joystick_path and self.virtual_joystick_path:
            self.logger.info(
                f"Instance {self.instance_num}: Assigning virtual joystick '{self.virtual_joystick_path}'."
            )
            joystick_path = self.virtual_joystick_path

        device_paths_to_bind = [
            self.device_info.get("mouse_path_str_for_instance"),
            self.device_info.get("keyboard_path_str_for_instance"),
            joystick_path,
        ]
        for device_path in device_paths_to_bind:
            if device_path:
                self.logger.info(f"Instance {self.instance_num}: Exposing device '{device_path}' to sandbox.")
                cmd.extend(["--dev-bind", device_path, device_path])

        if Path("/dev/uinput").exists():
            cmd.extend(["--dev-bind", "/dev/uinput", "/dev/uinput"])
        if Path("/dev/input/mice").exists():
            cmd.extend(["--dev-bind", "/dev/input/mice", "/dev/input/mice"])
        # --- End Device Isolation ---

        # --- Home Directory Isolation ---
        # Mount the instance-specific directories over the real Steam locations
        # fmt: off

        cmd.extend(["--bind", str(self.home_path), str(orig_home)])

        # fmt: on
        # Mount host's common games and compatibility tools into the sandboxed Steam directory
        host_steam_path = orig_local / "share/Steam"
        sandbox_steam_path = orig_local / "share/Steam"  # Same path, but it's now a mount point

        # Share games
        sandbox_common = Path(sandbox_steam_path) / "steamapps/common"
        host_common = Path(host_steam_path) / "steamapps/common"
        if host_common.exists():
            for folder in host_common.iterdir():
                if folder.is_dir():
                    cmd.extend(["--bind", str(folder), str(sandbox_common / folder.name)])

        # Share compatibilitytools
        host_compat = Path(host_steam_path) / "compatibilitytools.d"
        sandbox_compat = Path(sandbox_steam_path) / "compatibilitytools.d"
        if host_compat.exists():
            ignore = {"LegacyRuntime"}
            for folder in host_compat.iterdir():
                if folder.is_dir() and folder.name not in ignore:
                    cmd.extend(["--bind", str(folder), str(sandbox_compat / folder.name)])
        # --- End Home Directory Isolation ---

        # Ensure custom ENV variables reach Steam inside the sandbox
        try:
            extra_env = (
                self.profile.get_env_for_instance(instance_idx) if hasattr(self.profile, "get_env_for_instance") else {}
            )
            for k, v in (extra_env or {}).items():
                if v is None:
                    v = ""
                cmd.extend(["--setenv", str(k), str(v)])
            if extra_env:
                self.logger.info(f"Instance {self.instance_num}: Added {len(extra_env)} --setenv entries to bwrap.")
        except Exception as e:
            self.logger.error(f"Instance {self.instance_num}: Failed to add --setenv entries: {e}")
        return cmd
