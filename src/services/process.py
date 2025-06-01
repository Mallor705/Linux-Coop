import os
import signal
import subprocess
import time
from pathlib import Path
from typing import List, Optional
import psutil
from ..core.logger import Logger

class ProcessService:
    """Serviço responsável por gerenciar processos das instâncias do jogo."""
    def __init__(self, logger: Logger):
        """Inicializa o serviço de processos com logger e lista de PIDs."""
        self.logger = logger
        self.pids: List[int] = []
    
    def cleanup_previous_instances(self, proton_path: Optional[Path], exe_path: Path) -> None:
        """Finaliza instâncias anteriores do jogo que estejam em execução."""
        self.logger.info(f"Terminating previous instances of '{exe_path.name}'...")
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                exe_in_cmdline = str(exe_path) in cmdline
                
                if proton_path is None:
                    # Native game - just check for executable
                    should_terminate = exe_in_cmdline
                else:
                    # Proton game - check for both proton and executable
                    should_terminate = str(proton_path) in cmdline and exe_in_cmdline
                
                if should_terminate:
                    proc.terminate()
                    time.sleep(1)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    
    def launch_instance(self, cmd: List[str], log_file: Path, env: dict) -> int:
        """Lança uma instância do jogo e retorna o PID do processo."""
        with open(log_file, 'w') as log:
            process = subprocess.Popen(
                cmd, 
                stdout=log, 
                stderr=subprocess.STDOUT,
                env=env,
                preexec_fn=os.setsid
            )
        
        self.pids.append(process.pid)
        return process.pid
    
    def terminate_all(self) -> None:
        """Finaliza todos os processos gerenciados."""
        if not self.pids:
            return
            
        self.logger.info(f"Terminating PIDs: {self.pids}")
        
        for pid in self.pids[:]:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                time.sleep(2)
                os.killpg(os.getpgid(pid), signal.SIGKILL)
                self.pids.remove(pid)
            except (ProcessLookupError, OSError):
                pass
    
    def monitor_processes(self) -> bool:
        """Verifica se ainda existem processos em execução."""
        alive_pids = []
        for pid in self.pids:
            try:
                os.kill(pid, 0)  # Check if process exists
                alive_pids.append(pid)
            except OSError:
                pass
        
        self.pids = alive_pids
        return len(alive_pids) > 0