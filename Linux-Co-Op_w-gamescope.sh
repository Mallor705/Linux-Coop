#!/bin/bash

# Edite esse caminho para o arquivo de perfil do seu jogo
PROFILE_FILE="/home/mallor/Documentos/GitHub/Linux-Coop/profiles/profile"

# Verificar se o arquivo de perfil existe
if [ ! -f "$PROFILE_FILE" ]; then
  echo "Erro: O arquivo de perfil ($PROFILE_FILE) não foi encontrado. Execute o Create_new_profile.sh primeiro."
  exit 1
fi

# Carregar as configurações do arquivo de perfil
source "$PROFILE_FILE"

# Verificar se as variáveis obrigatórias foram definidas
if [ -z "$EXE_PATH" ] || [ -z "$PROTON_VERSION" ] || [ -z "$WIDTH" ] || [ -z "$HEIGHT" ]; then
  echo "Erro: As configurações obrigatórias não foram definidas corretamente no arquivo de perfil."
  exit 1
fi

# Verificar se o arquivo executável existe
if [ ! -f "$EXE_PATH" ]; then
  echo "Erro: O arquivo executável não existe: $EXE_PATH"
  exit 1
fi

# Extrair o nome do executável sem o caminho para usar como identificador
EXE_NAME=$(basename "$EXE_PATH")

# Verificar se o gamescope está instalado
if ! command -v gamescope &> /dev/null; then
  echo "Erro: Gamescope não está instalado. Por favor, instale-o primeiro."
  exit 1
fi

# Verificar se o Steam está em execução (necessário para usar o Proton)
if ! pgrep -x "steam" > /dev/null; then
  echo "Aviso: Steam não parece estar em execução. Iniciando o Steam..."
  steam &
  sleep 5
fi

# Verificar se o Bubblewrap está instalado 
if ! command -v bwrap &> /dev/null; then
  echo "Erro: Bubblewrap (bwrap) não está instalado. Instale com: sudo apt install bubblewrap"
  exit 1
fi

# Descobrir o caminho do Proton
find_proton_path() {
  local version=$1
  local proton_path=""

  # Verificar nas possíveis localizações do Steam
  for steam_path in "$HOME/.steam/steam" "$HOME/.local/share/Steam" "$HOME/.steam/debian-installation" "/var/mnt/games/messi/Games/Steam"; do
    if [ -d "$steam_path" ]; then
      # Primeiro, tenta encontrar o Proton Experimental
      if [[ "$version" == "Experimental" ]]; then
        potential_path=$(find "$steam_path/steamapps/common/" -maxdepth 1 -type d -name "Proton - Experimental" 2>/dev/null | head -n 1)
        if [ -n "$potential_path" ]; then
          proton_path="$potential_path/proton"
          break
        fi
      fi

      # Procurar por versões específicas do Proton
      potential_path=$(find "$steam_path/steamapps/common/" -maxdepth 1 -type d -name "Proton $version" 2>/dev/null | head -n 1)
      if [ -n "$potential_path" ]; then
        proton_path="$potential_path/proton"
        break
      fi

      # Procurar por versões do GE-Proton
      if [[ "$version" == GE-Proton* ]]; then
        potential_path=$(find "$steam_path/compatibilitytools.d/" -maxdepth 1 -type d -name "$version" 2>/dev/null | head -n 1)
        if [ -n "$potential_path" ]; then
          proton_path="$potential_path/proton"
          break
        fi
      fi
    fi
  done

  echo "$proton_path"
}

PROTON_PATH=$(find_proton_path "$PROTON_VERSION")

if [ -z "$PROTON_PATH" ]; then
  echo "Erro: Não foi possível encontrar o Proton $PROTON_VERSION. Verifique se ele está instalado pela Steam."
  exit 1
fi

echo "Usando Proton em: $PROTON_PATH"
echo "Executando jogo: $EXE_PATH"

# Definir o diretório de configuração de controladores
DIR_CO_OP_CONT="./controller_config/"
mkdir -p "$DIR_CO_OP_CONT"



# Função para executar uma instância do jogo
launch_game_instance() {
  local instance_num=$1
  local joy_device_file=$2

  # Ler o conteúdo do arquivo e atribuí-lo ao joy_device
  local joy_device=$(cat "$joy_device_file")

  echo "$(date '+%Y-%m-%d %H:%M:%S') - Iniciando instância $instance_num de $EXE_NAME com Proton $PROTON_VERSION no monitor $monitor..."

  # Criar um prefixo Wine único para cada instância
  local prefix_dir="$HOME/.proton_prefixes/${EXE_NAME}_instance_${instance_num}"
  mkdir -p "$prefix_dir" || { echo "Erro ao criar o diretório do prefixo: $prefix_dir"; exit 1; }

  # Configurar variáveis de ambiente para Proton
  export STEAM_COMPAT_CLIENT_INSTALL_PATH="$HOME/.steam/steam"
  export STEAM_COMPAT_DATA_PATH="$prefix_dir"
  export WINEPREFIX="$prefix_dir/pfx"
  export DXVK_ASYNC=1 # Habilita a compilação assíncrona de shaders no DXVK
  export SDL_JOYSTICK_DEVICE="$joy_device" # Forçar o SDL a usar apenas o dispositivo virtual correspondente
  export PROTON_LOG=1 # Habilitar logs do Proton

  echo "DEBUG: Caminho do Proton: $PROTON_PATH"
  echo "DEBUG: STEAM_COMPAT_CLIENT_INSTALL_PATH=$STEAM_COMPAT_CLIENT_INSTALL_PATH"
  echo "DEBUG: STEAM_COMPAT_DATA_PATH=$STEAM_COMPAT_DATA_PATH"
  echo "DEBUG: WINEPREFIX=$WINEPREFIX"
  # export SDL_GAMECONTROLLERCONFIG="$joy_device"
  echo "Dispositivo de joystick configurado: $SDL_JOYSTICK_DEVICE"
  # Executar com gamescope e redirecionar a saída para um arquivo de log
  gamescope \
    -w $WIDTH \
    -h $HEIGHT \
    -f \
    -- \
    "$PROTON_PATH" run "$EXE_PATH" > "$HOME/.proton_prefixes/${EXE_NAME}_instance_${instance_num}.log" 2>&1 &
  
  # ID do processo para rastreamento
  local pid=$!
  echo "Processo da instância $instance_num: $pid"
  echo $pid
}

# Limpar possíveis instâncias anteriores
pkill -f "gamescope.*-- '$PROTON_PATH' run '$EXE_PATH'" || true

echo "Iniciando a primeira instância..."
PID1=$(launch_game_instance 1 "$DIR_CO_OP_CONT/Player1_Controller")
sleep 2  # Pequeno atraso para evitar problemas de inicialização simultânea

echo "Iniciando a segunda instância..."
PID2=$(launch_game_instance 2 "$DIR_CO_OP_CONT/Player2_Controller")

echo "Ambas as instâncias foram iniciadas."
echo "Instância 1 PID: $PID1"
echo "Instância 2 PID: $PID2"
echo "Pressione CTRL+C neste terminal para tentar encerrar as instâncias."

# Aguarda a conclusão dos processos
wait