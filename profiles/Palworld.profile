# Nome do Jogo
GAME_NAME="Palworld"

# Caminho do Executável
EXE_PATH="/mnt/games/messi/Games/Steam/steamapps/common/Palworld/Palworld.exe"

# Versão do Proton
PROTON_VERSION="GE-Proton10-3"
USE_STEAM_RUNTIME="true"

# Número de jogadores/instâncias
NUM_PLAYERS=2

# Resolução por instância
INSTANCE_WIDTH=1920
INSTANCE_HEIGHT=1080

# Joystick
PLAYER_PHYSICAL_DEVICE_IDS=(
    "" # Jogador 1 /dev/input/by-id/usb-8BitDo_8BitDo_Ultimate_wireless_Controller_for_PC_4057CAD817E4-event-joystick
    "/dev/input/by-id/usb-045e_Gamesir-T4w_1.39-event-joystick" # Jogador 2 /dev/input/by-id/usb-045e_Gamesir-T4w_1.39-event-joystick
)

# Mouse
PLAYER_MOUSE_EVENT_PATHS=(
    "/dev/input/by-id/usb-Rapoo_Rapoo_Gaming_Device-event-mouse" # Jogador 1
    "/dev/input/by-id/usb-04d9_USB_Gaming_Mouse-event-mouse" # Jogador 2
)

# Teclado
PLAYER_KEYBOARD_EVENT_PATHS=(
    "/dev/input/by-id/usb-0416_NA87-if01-event-kbd" # Jogador 1
    "/dev/input/by-id/usb-Evision_RGB_Keyboard-event-kbd" # Jogador 2
)

# Garanta que a ordem aqui corresponda à ordem dos jogadores

# (Opcional) Argumentos do jogo
GAME_ARGS="-dx12"

# Adicionado AppID do Palworld
APP_ID="1623730"

PLAYERS=
      {
        "account_name": "Jogador1",
        "language": "brazilian",
        "listen_port": "47584",
        "user_steam_id": "76561198000000001"
      },
      {
        "account_name": "Jogador2",
        "language": "brazilian",
        "listen_port": "47584",
        "user_steam_id": "76561198000000002"
      }