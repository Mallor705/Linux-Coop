import json
from pathlib import Path
from typing import Optional, List, Dict

from pydantic import BaseModel, ConfigDict, Field, validator

from ..core.exceptions import ExecutableNotFoundError


class Game(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    """
    Represents a game in the user's library.

    This model stores high-level information about a game, such as its name
    and the path to its executable. This data is shared across all profiles
    associated with this game.

    Attributes:
        game_name (str): The name of the game.
        exe_path (Path): The path to the game's primary executable.
        app_id (Optional[str]): The Steam AppID of the game.
        game_args (Optional[str]): Command-line arguments to pass to the game.
        is_native (bool): Flag indicating if the game is a native Linux title.
        proton_version (Optional[str]): The Proton version to use for this game.
        apply_dxvk_vkd3d (bool): Whether to apply DXVK/VKD3D to prefixes for this game.
        winetricks_verbs (Optional[List[str]]): Winetricks verbs to run for this game.
        env_vars (Optional[Dict[str, str]]): Environment variables to set for this game.
    """
    game_name: str = Field(..., alias="GAME_NAME")
    exe_path: Path = Field(..., alias="EXE_PATH")
    app_id: Optional[str] = Field(default=None, alias="APP_ID")
    game_args: Optional[str] = Field(default=None, alias="GAME_ARGS")
    is_native: bool = Field(default=False, alias="IS_NATIVE")
    proton_version: Optional[str] = Field(default=None, alias="PROTON_VERSION")
    apply_dxvk_vkd3d: bool = Field(default=True, alias="APPLY_DXVK_VKD3D")
    winetricks_verbs: Optional[List[str]] = Field(default=None, alias="WINETRICKS_VERBS")
    env_vars: Optional[Dict[str, str]] = Field(default_factory=dict, alias="ENV_VARS")

    @validator('exe_path')
    def validate_exe_path(cls, v):
        """Validates that the executable path exists."""
        if v is None:
            return v
        path_v = Path(v)
        if not path_v.exists():
            raise ExecutableNotFoundError(f"Game executable not found: {path_v}")
        return path_v

    @validator('game_name')
    def sanitize_game_name(cls, v):
        """Sanitizes the game name."""
        return v.strip()

    @classmethod
    def load_from_file(cls, file_path: Path) -> "Game":
        """Loads a game from a JSON file."""
        if not file_path.exists():
            raise FileNotFoundError(f"Game file not found: {file_path}")
        with file_path.open('r', encoding='utf-8') as f:
            data = json.load(f)

        # Infer is_native if not present
        if 'IS_NATIVE' not in data:
            exe_path_str = data.get('EXE_PATH')
            data['IS_NATIVE'] = bool(exe_path_str and not exe_path_str.lower().endswith('.exe'))

        return cls.model_validate(data)

    def save_to_file(self, file_path: Path):
        """Saves the game to a JSON file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        json_data = self.model_dump_json(by_alias=True, indent=4)
        file_path.write_text(json_data, encoding='utf-8')