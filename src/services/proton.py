from pathlib import Path
from typing import Tuple, Optional
from ..core.config import Config
from ..core.exceptions import ProtonNotFoundError
from ..core.logger import Logger

class ProtonService:
    """Serviço responsável por localizar e validar o Proton e diretórios do Steam."""
    def __init__(self, logger: Logger):
        """Inicializa o serviço de Proton com logger."""
        self.logger = logger
    
    def find_proton_path(self, version: str) -> Tuple[Path, Path]:
        """Procura o executável do Proton e o diretório raiz do Steam para a versão informada."""
        self.logger.info(f"Searching for Proton: {version}")
        
        for steam_path in Config.STEAM_PATHS:
            if not steam_path.exists():
                continue
                
            self.logger.info(f"Checking Steam directory: {steam_path}")
            proton_path = self._search_proton_in_steam(steam_path, version)
            
            if proton_path and proton_path.exists():
                self.logger.info(f"Proton found: {proton_path}")
                return proton_path, steam_path
        
        raise ProtonNotFoundError(f"Proton '{version}' not found")
    
    def _search_proton_in_steam(self, steam_path: Path, version: str) -> Optional[Path]:
        """Procura o Proton nos diretórios do Steam."""
        search_dirs = [
            steam_path / "steamapps/common",
            steam_path / "compatibilitytools.d"
        ]
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
                
            if version == "Experimental":
                proton_dir = search_dir / "Proton - Experimental"
            else:
                proton_dir = search_dir / f"Proton {version}"
                if not proton_dir.exists():
                    proton_dir = search_dir / version
            
            proton_script = proton_dir / "proton"
            if proton_script.exists():
                return proton_script
        
        return None