"""
Instance management module for the Twinverse application.

This module provides functionality to manage Steam instances, including launching,
terminating, and configuring them with isolated environments.
"""

import copy
import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Optional

from src.core import Config, Logger, Utils
from src.core.exceptions import DependencyError, TwinverseError, VirtualDeviceError
from src.models import PlayerInstanceConfig, Profile

from .kde_manager import KdeManager


class InstanceService:
    """Service responsible for managing Steam instances."""

    def __init__(self, logger: Logger, kde_manager: Optional[KdeManager] = None):
        """Initialize the instance service."""
        from .device_manager import DeviceManager
        from .virtual_device import VirtualDeviceService

        self.logger = logger
        self.virtual_device = VirtualDeviceService(logger)
        self.kde_manager = kde_manager
        self.device_manager = DeviceManager()
        self._virtual_joystick_path: Optional[str] = None
        self._virtual_joystick_checked: bool = False
        self.pids: dict[int, int] = {}
        self.pgids: dict[int, int] = {}
        self.processes: dict[int, subprocess.Popen] = {}
        self.termination_in_progress = False

    def _prepare_instance_launch(self, profile: Profile, instance_num: int) -> tuple[list[str], dict]:
        """Prepare and build the command for launching a single Steam instance."""
        home_path = Config.get_steam_home_path(instance_num)
        home_path.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Instance {instance_num}: Using isolated home path '{home_path}'")

        self._prepare_home(home_path)

        device_info = self._validate_input_devices(profile, instance_num, instance_num)
        instance_env = self._prepare_environment(profile, device_info, instance_num)

        from .cmd_builder import CommandBuilder

        cmd_builder = CommandBuilder(
            self.logger,
            profile,
            device_info,
            self.device_manager,
            instance_num,
            home_path,
            self._virtual_joystick_path,
        )
        return cmd_builder.build_command(), instance_env

    def _launch_single_instance(self, profile: Profile, instance_num: int) -> None:
        """Launch a single steam instance."""
        self.logger.info(f"Preparing instance {instance_num}...")

        base_command, instance_env = self._prepare_instance_launch(profile, instance_num)

        log_file = Config.LOG_DIR / f"steam_instance_{instance_num}.log"
        self.logger.info(f"Launching instance {instance_num} (Log: {log_file})")
        self.logger.debug(f"Instance {instance_num}: Environment: {dict(instance_env)}")

        try:
            if Utils.is_flatpak():
                self.logger.info(f"Instance {instance_num}: Launching in Flatpak environment")
                process, pgid = self._launch_in_flatpak(instance_num, base_command, instance_env)
            else:
                self.logger.info(f"Instance {instance_num}: Launching natively")
                process, pgid = self._launch_natively(instance_num, base_command, instance_env)

            self.pids[instance_num] = process.pid
            self.pgids[instance_num] = pgid
            self.processes[instance_num] = process

            self.logger.info(f"Instance {instance_num}: Successfully launched with PID {process.pid}")

        except TwinverseError:
            self.logger.error(f"Instance {instance_num}: TwinverseError during launch")
            raise
        except Exception as e:
            self.logger.error(f"Instance {instance_num}: Unexpected error during launch: {str(e)}")
            self.logger.exception(f"Instance {instance_num}: Exception details:")
            raise TwinverseError(f"Failed to launch instance {instance_num}: {str(e)}")

    def _launch_in_flatpak(
        self, instance_num: int, base_command: list[str], instance_env: dict
    ) -> tuple[subprocess.Popen, int]:
        """Launch a Steam instance within a Flatpak environment."""
        env_prefix_parts = [f"export {key}={shlex.quote(value)}" for key, value in instance_env.items()]
        env_prefix = "; ".join(env_prefix_parts) + "; " if env_prefix_parts else ""
        escaped_command = shlex.join(base_command)
        shell_command = f"{env_prefix}set -m; echo $$; exec {escaped_command}"

        self.logger.info(f"Instance {instance_num}: Launching on host via shell: {shell_command}")

        flatpak_env = os.environ.copy()
        flatpak_env.pop("PYTHONHOME", None)
        flatpak_env.pop("PYTHONPATH", None)

        try:
            process = Utils.flatpak_spawn_host(
                ["bash", "-c", shell_command],
                async_=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=flatpak_env,
                cwd=Path.home(),
            )
        except FileNotFoundError as e:
            self.logger.error(f"Instance {instance_num}: flatpak-spawn-host command not found: {e}")
            raise DependencyError(f"flatpak-spawn-host command not found: {e}")
        except PermissionError as e:
            self.logger.error(f"Instance {instance_num}: Permission denied when spawning host process: {e}")
            raise TwinverseError(f"Permission denied when launching instance {instance_num}: {e}")
        except Exception as e:
            self.logger.error(f"Instance {instance_num}: Unexpected error when spawning host process: {e}")
            raise TwinverseError(f"Unexpected error when launching instance {instance_num}: {e}")

        import time

        time.sleep(0.1)

        if process.poll() is not None:
            stdout_data, stderr_data = process.communicate()
            stdout_str = stdout_data.decode() if stdout_data else ""
            stderr_str = stderr_data.decode() if stderr_data else ""
            error_message = (
                f"STDOUT: {stdout_str}\nSTDERR: {stderr_str}" if (stdout_str or stderr_str) else "Unknown error"
            )
            self.logger.error(f"Instance {instance_num}: Process failed to start:\n{error_message}")
            raise DependencyError(f"Command failed to start: {base_command[0]} - {error_message}")

        pgid_str = process.stdout.readline().decode().strip() if process.stdout else ""
        if pgid_str.isdigit():
            pgid = int(pgid_str)
            self.logger.info(
                f"Instance {instance_num} started on host with PID {process.pid} " f"and captured host PGID: {pgid}"
            )
            return process, pgid

        self.logger.error(f"Instance {instance_num}: Failed to capture host PGID. Read: '{pgid_str}'")
        process.terminate()

        # Try to get error output if available
        stdout_data, stderr_data = process.communicate(timeout=1) if process.stdout else (None, None)
        stdout_str = stdout_data.decode() if stdout_data else ""
        stderr_str = stderr_data.decode() if stderr_data else ""
        error_message = (
            f"STDOUT: {stdout_str}\nSTDERR: {stderr_str}"
            if (stdout_str or stderr_str)
            else "Failed to capture host PGID"
        )

        raise TwinverseError(f"Failed to get host process group ID for instance {instance_num}: {error_message}")

    def _launch_natively(
        self, instance_num: int, base_command: list[str], instance_env: dict
    ) -> tuple[subprocess.Popen, int]:
        """Launch a Steam instance natively."""
        native_env = os.environ.copy()
        native_env.pop("PYTHONHOME", None)
        native_env.pop("PYTHONPATH", None)
        native_env.update(instance_env)

        self.logger.info(f"Instance {instance_num}: Full command: {shlex.join(base_command)}")

        # Log environment variables for debugging
        self.logger.debug(f"Instance {instance_num}: Environment variables: {list(instance_env.keys())}")

        # Check if required binaries exist before launching
        if not shutil.which(base_command[0]):
            error_msg = f"Command '{base_command[0]}' not found in PATH"
            self.logger.error(f"Instance {instance_num}: {error_msg}")
            raise DependencyError(error_msg)

        try:
            process = subprocess.Popen(
                base_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=native_env,
                cwd=Path.home(),
                preexec_fn=os.setpgrp,
            )
        except FileNotFoundError as e:
            self.logger.error(f"Instance {instance_num}: Command not found: {e}")
            raise DependencyError(f"Command not found: {e}")
        except PermissionError as e:
            self.logger.error(f"Instance {instance_num}: Permission denied: {e}")
            raise TwinverseError(f"Permission denied when launching instance {instance_num}: {e}")
        except OSError as e:
            self.logger.error(f"Instance {instance_num}: OS error when launching: {e}")
            raise TwinverseError(f"OS error when launching instance {instance_num}: {e}")

        import time

        time.sleep(0.1)

        if process.poll() is not None:
            stdout_data, stderr_data = process.communicate()
            stdout_str = stdout_data.decode() if stdout_data else ""
            stderr_str = stderr_data.decode() if stderr_data else ""
            error_message = (
                f"STDOUT: {stdout_str}\nSTDERR: {stderr_str}" if (stdout_str or stderr_str) else "Unknown error"
            )
            self.logger.error(f"Instance {instance_num}: Process failed to start:\n{error_message}")
            raise DependencyError(f"Command failed to start: {base_command[0]} - {error_message}")

        pgid = process.pid
        self.logger.info(f"Instance {instance_num} started with PID: {process.pid} and PGID: {pgid}")
        return process, pgid

    def launch_instance(
        self,
        profile: Profile,
        instance_num: int,
        use_gamescope_override: Optional[bool] = None,
    ) -> None:
        """Launch a single Steam instance."""
        if not self._virtual_joystick_checked:
            self._virtual_joystick_checked = True
            needs_virtual_joystick = False
            num_players = profile.effective_num_players()
            if num_players > 0:
                # Check player configs up to the number of players
                for i in range(num_players):
                    player_config = (
                        profile.player_configs[i]
                        if profile.player_configs and i < len(profile.player_configs)
                        else PlayerInstanceConfig()
                    )
                    if not player_config.physical_device_id:
                        needs_virtual_joystick = True
                        break

            if needs_virtual_joystick:
                self.logger.info("One or more instances lack a physical joystick. Creating a virtual one.")
                try:
                    self._virtual_joystick_path = self.virtual_device.create_virtual_joystick()
                except VirtualDeviceError as e:
                    self.logger.error(f"Halting launch due to virtual joystick creation failure: {str(e)}")
                    # Re-raise the exception to be caught by the UI layer
                    raise

        active_profile = profile
        if use_gamescope_override is not None:
            active_profile = copy.deepcopy(profile)
            active_profile.use_gamescope = use_gamescope_override

            # Also override ENABLE_GAMESCOPE_WSI when gamescope is disabled
            if use_gamescope_override is False:
                active_profile.enable_gamescope_wsi = False

        Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._launch_single_instance(active_profile, instance_num)

    def terminate_instance(self, instance_num: int) -> None:
        """Terminates a single Steam instance gracefully."""
        if instance_num not in self.processes:
            self.logger.warning(f"Attempted to terminate non-existent instance {instance_num}")
            return

        process = self.processes[instance_num]
        self.logger.info(f"Terminating instance {process.pid}...")

        if process.poll() is None:
            # Get the appropriate process/group ID for termination.
            # For Flatpak, this is the host PGID we captured.
            # For native, it's the PGID we created.
            pgid = self.pgids.get(instance_num)
            if pgid:
                if Utils.is_flatpak():
                    self.logger.info(f"Sending SIGTERM to host process group {pgid} for instance {instance_num}")
                    Utils.flatpak_spawn_host(["sh", "-c", f"kill -15 -{pgid}"])
                else:
                    try:
                        self.logger.info(f"Sending SIGTERM to process group {pgid} for instance {instance_num}")
                        os.killpg(pgid, signal.SIGTERM)
                    except ProcessLookupError:
                        self.logger.warning(f"Process group {pgid} not found for instance {instance_num}.")

                try:
                    process.wait(timeout=10)
                    self.logger.info(f"Instance {instance_num} terminated gracefully.")
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"Instance {instance_num} did not terminate after 10s. Sending SIGKILL.")
                    if Utils.is_flatpak():
                        try:
                            Utils.flatpak_spawn_host(["sh", "-c", f"kill -9 -{pgid}"])
                        except Exception as e:
                            self.logger.warning(f"Failed to send SIGKILL to host PGID {pgid}: {e}")

                        self.logger.info(f"Instance {instance_num} terminated with SIGKILL.")

                        # This is necessary as a temporary measure for the problem described in:
                        # https://github.com/ValveSoftware/gamescope/issues/1482
                        Utils.flatpak_spawn_host(["sh", "-c", "pkill -9 -f winedevice"])

                    else:
                        try:
                            os.killpg(pgid, signal.SIGKILL)
                        except ProcessLookupError:
                            self.logger.warning(
                                f"Process group {pgid} not found when sending SIGKILL for instance {instance_num}."
                            )
                        except PermissionError as e:
                            self.logger.error(f"Permission denied when sending SIGKILL to process group {pgid}: {e}")
                            raise TwinverseError(f"Permission denied when terminating instance {instance_num}: {e}")

                        self.logger.info(f"Instance {instance_num} terminated with SIGKILL.")

                        # This is necessary as a temporary measure for the problem described in:
                        # https://github.com/ValveSoftware/gamescope/issues/1482
                        subprocess.run(
                            ["pkill", "-9", "-f", "winedevice"],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
            else:
                self.logger.warning(f"No PGID found for instance {instance_num}, cannot send termination signal.")

        if process.poll() is None:
            process.wait()

        if instance_num in self.processes:
            del self.processes[instance_num]
        if instance_num in self.pids:
            del self.pids[instance_num]
        if instance_num in self.pgids:
            del self.pgids[instance_num]

    def _prepare_home(self, home_path: Path) -> None:
        """
        Prepare the isolated Steam directories for the instance.

        This involves creating the directory structure and copying app manifests
        to ensure games are recognized.
        """
        self.logger.info(f"Preparing isolated Steam directories for instance at {home_path}...")

        sdbx_steam_local = home_path / ".local/share/Steam"

        # Create essential Steam directories within the instance's isolated path
        try:
            (sdbx_steam_local / "steamapps").mkdir(parents=True, exist_ok=True)
            (sdbx_steam_local / "compatibilitytools.d").mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            self.logger.error(f"Permission denied when creating Steam directories: {e}")
            raise TwinverseError(f"Permission denied when creating Steam directories: {e}")
        except OSError as e:
            self.logger.error(f"OS error when creating Steam directories: {e}")
            raise TwinverseError(f"OS error when creating Steam directories: {e}")

        # Copy .acf (app manifest) files from the host to the instance.
        # This makes Steam recognize games as "installed" so it can find them
        # in the shared steamapps/common directory.
        host_steamapps = Path.home() / ".local/share/Steam/steamapps"
        dest_steamapps = sdbx_steam_local / "steamapps"

        if host_steamapps.exists():
            for acf_file in host_steamapps.glob("*.acf"):
                dest_file = dest_steamapps / acf_file.name
                if not dest_file.exists():
                    try:
                        shutil.copy(acf_file, dest_file)
                    except PermissionError as e:
                        self.logger.warning(f"Permission denied when copying {acf_file.name}: {e}")
                    except OSError as e:
                        self.logger.warning(f"OS error when copying {acf_file.name}: {e}")
        else:
            self.logger.warning(
                f"Host Steam directory '{host_steamapps}' not found. Game manifests will not be copied to the instance."
            )

        self.logger.info("Isolated Steam directories are ready.")

    def _prepare_environment(self, profile: Profile, device_info: dict, instance_num: int) -> dict:
        """Prepare a dictionary of environment variables for the Steam instance."""
        env = {}

        env["ENABLE_GAMESCOPE_WSI"] = "1" if profile.enable_gamescope_wsi else "0"

        # Handle audio device assignment
        if device_info.get("audio_device_id_for_instance"):
            env["PULSE_SINK"] = device_info["audio_device_id_for_instance"]
            self.logger.info(
                f"Instance {instance_num}: Setting PULSE_SINK to '{device_info['audio_device_id_for_instance']}'."
            )

        # Custom ENV variables from the profile are set via bwrap --setenv, so we don't handle them here.

        self.logger.info(f"Instance {instance_num}: Environment variables prepared.")
        return env

    def _validate_input_devices(self, profile: Profile, instance_num: int, instance_num_display: int) -> dict:
        """Validate input devices and return information about them."""
        # Get specific player config
        player_config = (
            profile.player_configs[instance_num]
            if profile.player_configs and 0 <= instance_num < len(profile.player_configs)
            else PlayerInstanceConfig()  # Default empty config
        )

        def _validate_device(path_str: Optional[str], device_type: str) -> Optional[str]:
            if not path_str or not path_str.strip():
                return None
            path_obj = Path(path_str)
            if path_obj.exists() and path_obj.is_char_device():
                self.logger.info(f"Instance {instance_num_display}: {device_type} device '{path_str}' assigned.")
                return str(path_obj.resolve())
            self.logger.warning(
                f"Instance {instance_num_display}: {device_type} device '{path_str}' not found or not a char device."
            )
            return None

        mouse_path = None
        keyboard_path = None
        joystick_path = _validate_device(player_config.physical_device_id, "Joystick")

        audio_id = player_config.audio_device_id
        if audio_id and audio_id.strip():
            self.logger.info(f"Instance {instance_num_display}: Audio device ID '{audio_id}' assigned.")

        return {
            "mouse_path_str_for_instance": mouse_path,
            "keyboard_path_str_for_instance": keyboard_path,
            "joystick_path_str_for_instance": joystick_path,
            "audio_device_id_for_instance": (audio_id if audio_id and audio_id.strip() else None),
            "should_add_grab_flags": player_config.grab_input_devices,
        }

    def terminate_all(self) -> None:
        """Terminate all managed steam instances."""
        if self.termination_in_progress:
            return
        try:
            self.termination_in_progress = True
            self.logger.info("Starting termination of all instances...")

            # Cleanup virtual joystick
            if self._virtual_joystick_path:
                self.virtual_device.destroy_virtual_joystick()
                self._virtual_joystick_path = None
                self.logger.info("Virtual joystick destroyed.")
            self._virtual_joystick_checked = False

            # Cleanup KDE-specific settings
            if self.kde_manager:
                self.kde_manager.stop_kwin_script()
                self.kde_manager.restore_panel_states()
                self.logger.info("KDE-specific cleanup complete.")

            for instance_num in list(self.processes.keys()):
                self.terminate_instance(instance_num)

            self.logger.info("Instance termination complete.")
            self.pids.clear()
            self.processes.clear()

        finally:
            self.termination_in_progress = False
