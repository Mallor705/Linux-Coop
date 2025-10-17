import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from pydantic import (BaseModel, ConfigDict, Field, ValidationError,
                      validator)

from ..core.config import Config
from ..core.exceptions import ProfileNotFoundError
from ..core.logger import Logger
from .game import Game


class PlayerInstanceConfig(BaseModel):
    """
    Defines the specific configuration for a single player's game instance.
    """
    model_config = ConfigDict(populate_by_name=True)

    ACCOUNT_NAME: Optional[str] = Field(default=None, alias="ACCOUNT_NAME")
    LANGUAGE: Optional[str] = Field(default=None, alias="LANGUAGE")
    LISTEN_PORT: Optional[str] = Field(default=None, alias="LISTEN_PORT")
    USER_STEAM_ID: Optional[str] = Field(default=None, alias="USER_STEAM_ID")
    PHYSICAL_DEVICE_ID: Optional[str] = Field(default=None, alias="PHYSICAL_DEVICE_ID")
    MOUSE_EVENT_PATH: Optional[str] = Field(default=None, alias="MOUSE_EVENT_PATH")
    KEYBOARD_EVENT_PATH: Optional[str] = Field(default=None, alias="KEYBOARD_EVENT_PATH")
    AUDIO_DEVICE_ID: Optional[str] = Field(default=None, alias="AUDIO_DEVICE_ID")
    monitor_id: Optional[str] = Field(default=None, alias="MONITOR_ID")


class SplitscreenConfig(BaseModel):
    """
    Configuration for splitscreen mode.
    """
    model_config = ConfigDict(populate_by_name=True)
    orientation: str = Field(alias="ORIENTATION")

    @validator('orientation')
    def validate_orientation(cls, v):
        if v not in ["horizontal", "vertical"]:
            raise ValueError("Orientation must be 'horizontal' or 'vertical'.")
        return v


class Profile(BaseModel):
    """
    A profile for launching a game with a specific configuration.

    This model holds settings that can vary between different playthroughs
    of the same game, such as player counts, Proton versions, and device configs.
    """
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    profile_name: str = Field(..., alias="PROFILE_NAME")
    num_players: int = Field(..., alias="NUM_PLAYERS")
    instance_width: int = Field(..., alias="INSTANCE_WIDTH")
    instance_height: int = Field(..., alias="INSTANCE_HEIGHT")
    mode: Optional[str] = Field(default=None, alias="MODE")
    splitscreen: Optional[SplitscreenConfig] = Field(default=None, alias="SPLITSCREEN")
    player_configs: Optional[List[PlayerInstanceConfig]] = Field(default=None, alias="PLAYERS")
    selected_players: Optional[List[int]] = Field(default=None, alias="selected_players")
    sidecar_executable: Optional[str] = Field(default=None, alias="SIDECAR_EXECUTABLE")
    sidecar_args: Optional[str] = Field(default=None, alias="SIDECAR_ARGS")
    sidecar_width: Optional[int] = Field(default=None, alias="SIDECAR_WIDTH")
    sidecar_height: Optional[int] = Field(default=None, alias="SIDECAR_HEIGHT")

    @validator('num_players')
    def validate_num_players(cls, v):
        if not (1 <= v <= 4):
            raise ValueError("The number of players must be between 1 and 4.")
        return v

    @classmethod
    def load_from_file(cls, profile_path: Path) -> "Profile":
        """Loads a profile from a JSON file."""
        if not profile_path.exists():
            raise ProfileNotFoundError(f"Profile not found: {profile_path}")

        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            raise ValueError(f"Error reading profile file {profile_path}: {e}")

        # Ensure profile_name is set from filename if not present
        if 'PROFILE_NAME' not in data:
            data['PROFILE_NAME'] = profile_path.stem

        if 'NUM_PLAYERS' not in data and 'PLAYERS' in data:
            data['NUM_PLAYERS'] = len(data['PLAYERS'])

        try:
            profile = cls(**data)
        except ValidationError as e:
            Logger("LinuxCoop", Config.LOG_DIR).error(f"Pydantic Validation Error for {profile_path}: {e.errors()}")
            raise ValueError(f"Profile data validation failed: {e}")
        return profile

    def save_to_file(self, profile_path: Path):
        """Saves the profile to a JSON file."""
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        json_data = self.model_dump_json(by_alias=True, indent=4)
        profile_path.write_text(json_data, encoding='utf-8')

    @property
    def is_splitscreen_mode(self) -> bool:
        """Checks if the profile is configured for splitscreen mode."""
        return self.mode == "splitscreen"

class GameProfile:
    """
    A dynamic, unified view of a Game and a Profile.

    This class acts as a read-only proxy, combining the attributes of a Game
    object and a Profile object. It provides a consistent interface for the
    rest of the application, especially the InstanceService, which expects
    a single profile object.
    """
    def __init__(self, game: Game, profile: Profile):
        self._game = game
        self._profile = profile

    def __getattr__(self, name: str) -> Any:
        """Dynamically retrieves attributes from the Profile or Game."""
        # Prioritize profile attributes
        if hasattr(self._profile, name):
            return getattr(self._profile, name)
        # Fallback to game attributes
        if hasattr(self._game, name):
            return getattr(self._game, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @property
    def is_splitscreen_mode(self) -> bool:
        return self._profile.mode == "splitscreen"

    def effective_num_players(self) -> int:
        if self._profile.selected_players:
            return len(self._profile.selected_players)
        return len(self._profile.player_configs) if self._profile.player_configs else 0

    @property
    def players_to_launch(self) -> List[PlayerInstanceConfig]:
        return self._profile.player_configs if self._profile.player_configs else []

    def get_instance_dimensions(self, instance_num: int) -> Tuple[int, int]:
        """Calculates instance dimensions, accounting for splitscreen."""
        if not self.is_splitscreen_mode or not self._profile.splitscreen:
            return self._profile.instance_width, self._profile.instance_height

        orientation = self._profile.splitscreen.orientation
        num_players = self.effective_num_players()

        if num_players < 1:
            return self._profile.instance_width, self._profile.instance_height

        if num_players == 1:
            return self._profile.instance_width, self._profile.instance_height
        elif num_players == 2:
            if orientation == "horizontal":
                return self._profile.instance_width // 2, self._profile.instance_height
            else:
                return self._profile.instance_width, self._profile.instance_height // 2
        elif num_players == 3:
            if orientation == "horizontal":
                if instance_num == 1:
                    return self._profile.instance_width, self._profile.instance_height // 2
                else:
                    return self._profile.instance_width // 2, self._profile.instance_height // 2
            else:
                if instance_num == 1:
                    return self._profile.instance_width // 2, self._profile.instance_height
                else:
                    return self._profile.instance_width // 2, self._profile.instance_height // 2
        elif num_players == 4:
            return self._profile.instance_width // 2, self._profile.instance_height // 2
        else:
            if orientation == "horizontal":
                return self._profile.instance_width, self._profile.instance_height // num_players
            else:
                return self._profile.instance_width // num_players, self._profile.instance_height