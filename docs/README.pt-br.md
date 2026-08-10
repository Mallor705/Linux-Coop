<p align="right">
  <a href="https://github.com/mall0r/Twinverse/blob/main/README.md"><img src="https://img.shields.io/badge/en-US-darkblue.svg" alt="English"/></a>
  <a href="https://github.com/mall0r/Twinverse/blob/main/docs/README.pt-br.md"><img src="https://img.shields.io/badge/pt-BR-darkgreen.svg" alt="Portuguese"/></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mall0r/Twinverse/v1.0.0/share/icons/hicolor/scalable/apps/io.github.mall0r.Twinverse.svg" alt="Twinverse Logo" width="176" height="176">
</p>

<p align="center">
  <a href="https://github.com/mall0r/Twinverse/releases"><img src="https://img.shields.io/badge/Version-1.0.0-blue.svg" alt="Version"/></a>
  <a href="https://github.com/mall0r/Twinverse/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-green.svg" alt="License"/></a>
  <a href="https://www.gtk.org/"><img src="https://img.shields.io/badge/GTK-4.0+-orange.svg" alt="GTK Version"/></a>
  <a href="https://gnome.pages.gitlab.gnome.org/libadwaita/"><img src="https://img.shields.io/badge/libadwaita-1.0+-purple.svg" alt="libadwaita Version"/></a>
</p>

<p align="center">
  <a href="https://www.python.org" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/></a>
  <a href="https://www.gnu.org/software/bash/" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Shell-4EAA25?style=for-the-badge&logo=gnu-bash&logoColor=white" alt="Shell"/></a>
  <a href="https://www.javascript.com/" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" alt="JavaScript"/></a>
  <a href="https://www.w3.org/Style/CSS/" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/CSS3-66309A?style=for-the-badge&logo=css3&logoColor=white" alt="CSS"/></a>
</p>

# O que é o Twinverse?

O **Twinverse** é uma ferramenta para Linux/SteamOS que permite criar e gerenciar múltiplas instâncias do `Steam Big Picture` simultaneamente. Isso possibilita que vários jogadores aproveitem sua biblioteca de jogos em um único computador, seja em tela dividida ou cada um com sua própria tela, além de saída de áudio e dispositivos de entrada dedicados.

<p align="center">
  <img alt="twinverse_ui" src="https://raw.githubusercontent.com/mall0r/Twinverse/v1.0.0/share/screenshots/twinverse-ui.png" />
</p>

> [!WARNING]
> Este projeto não apoia a pirataria; todos os jogadores devem possuir o jogo em suas bibliotecas Steam para poderem jogá-lo

## ✨ Principais Funcionalidades

> [!NOTE]
> Mouse/Teclado só podem ser atribuídos a uma instância por vez

O Twinverse foi projetado para ser uma solução flexível para jogar em tela dividida no Linux. Aqui estão algumas de suas principais funcionalidades:

1.  **Múltiplas Instâncias:** Execute várias instâncias do Cliente Steam simultaneamente

2.  **Atribuição de Dispositivos:** Atribua mouse, teclado e controle específicos para cada instância dos jogos

3.  **Canais de Áudio Dedicados:** Direcione o áudio de cada instância para um dispositivo de saída de áudio separado

4.  **Diretório Home Dedicado:** O Twinverse permite que você tenha um diretório home dedicado para cada instância, possibilitando a personalização individual de configurações e arquivos

5.  **Pasta de Jogos Compartilhada:** Compartilha o diretório de jogos steam entre várias instâncias, para que não seja necessário baixar o jogo novamente para cada instância, economizando espaço em disco.

6.  **Use Qualquer Proton:** Twinverse permite que você use qualquer versão do Proton para executar seus jogos, incluindo protons personalizados como o [ProtonGE](https://github.com/GloriousEggroll/proton-ge-custom)

7.  **Jogue o Que Quiser** A instâncias não precisam se limitar a jogar o mesmo jogo; cada instância pode jogar o jogo que quiser

8.  **Modos de tela flexíveis:** Escolha entre tela dividida (até 4 instâncias por monitor) ou tela cheia (1 instância por monitor)

---

[1920x1080-RX_6600_XT-demo](https://github.com/user-attachments/assets/e0ca4937-fd38-48cf-b56c-1c825b047572)

---

## 📦 Requisitos

Para usar o Twinverse sem problemas, certifique-se de que os seguintes requisitos sejam atendidos:

É necessário ter instalados os pacotes `gamescope` e `steam` *nativos* de sua distro.

Para que o Gamescope funcione corretamente, de acordo com sua GPU, será necessário:

  - **AMD:** Mesa 20.3 ou mais recente
  - **Intel:** Mesa 21.2 ou mais recente
  - **NVIDIA:** Drivers proprietários 515.43.04 ou mais recente, ou drivers NVIDIA de Módulo de Kernel Aberto (NVIDIA Open Kernel Module)

> [!NOTE]
> *SteamOS* (AMD) e *Bazzite* geralmente têm todas as dependências incluídas por padrão.

## 📦 Instalação

### Flatpak

A maneira recomendada de instalar o Twinverse é via Flatpak, que oferece um ambiente em sandbox e atualizações mais fáceis.

<!--**Opção 1: Instalar do Flathub (Em Breve)**
Assim que o Twinverse estiver disponível no Flathub, você poderá instalá-lo usando os seguintes comandos:
```bash
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub io.github.mall0r.Twinverse
```-->

**Instalar de um arquivo .flatpak**
1. **Baixe o último arquivo .flatpak:**
   Acesse a página de [**Releases**](https://github.com/mall0r/Twinverse/releases) e baixe o último arquivo `.flatpak`.

2. **Instale o Flatpak:**
   Você pode instalar o Flatpak com o seguinte comando:
   ```bash
   flatpak install --user Twinverse-*.flatpak
   ```

### AppImage

> [!NOTE]
> Garanta que tenha instalado o pacote `bubblewrap`.

Alternativamente, você pode usar a versão AppImage. Este arquivo único funciona na maioria das distribuições Linux modernas sem a necessidade de instalação no sistema.

1.  **Baixe o AppImage mais recente:**
    Acesse a página de [**Releases**](https://github.com/mall0r/Twinverse/releases) e baixe o arquivo `.AppImage` mais recente.

2.  **Torne-o Executável:**
    Após o download, clique com o botão direito no arquivo, vá para "Propriedades" e marque a caixa "Permitir a execução do arquivo como programa". Alternativamente, você pode usar o terminal:
    ```bash
    chmod +x Twinverse-*.AppImage
    ```

3.  **Execute o Aplicativo:**
    Execute o appimage e aproveite. É isso!

#### Integração de AppImage (Opcional)

Para uma melhor integração com o sistema (por exemplo, adicionar uma entrada no menu de aplicativos), você pode usar uma ferramenta como o **[Gear Lever](https://github.com/mijorus/gearlever)** para gerenciar seu AppImage.

### Executando a Partir do Código-Fonte

O script `run.sh` oferece uma maneira rápida de configurar um ambiente local e executar o aplicativo. Ele criará automaticamente um ambiente virtual e instalará as dependências necessárias.

```bash
# Clone o repositório
git clone https://github.com/mall0r/Twinverse.git
cd Twinverse

# Execute o script de execução
./run.sh
```

## 📖 Como Usar?

Acesse nosso [Guide](https://github.com/mall0r/Twinverse/blob/main/docs/GUIDE.pt-br.md) para mais informações sobre como usar o Twinverse.

---

## ⚙️ Como Funciona

O Twinverse utiliza **Gamescope** (cria o ambiente de jogo e gerencia a composição) e o **Bubblewrap** (bwrap - ferramenta para a construção de ambientes sandbox), para isolar cada instância do Cliente Steam. O `bwrap` nesse projeto, é utilizado com uma camada extra de isolamento ao redor do gamescope, fornecendo um isolamento mais robusto e permitindo um controle granular sobre o que deve ou não ser exposto ou mascarado dentro do contêiner, permitindo ignorar dispositivos desnecessários para aquela sessão ou recriar um diretório *home* dedicado por instância. Isso permite que cada Steam seja executado em seu próprio ambiente estereo e independente. Assim, a instância não pode interferir com sua área de trabalho e sua área de trabalho não pode interferir com ela.

A linha de comando final é montada dinamicamente com base nas configurações do usuário, seguindo uma estrutura de encapsulamento onde o **`bwrap`** é a camada mais externa, que executa o **Gamescope**, o qual, por sua vez, inicia o **Steam** dentro do sandbox.

---

## 🛠️ Para Desenvolvedores

Se você deseja contribuir com o Twinverse, por favor consulte o [CONTRIBUTING](../CONTRIBUTING.md) para obter instruções detalhadas sobre como começar, fluxos de trabalho de desenvolvimento e padrões de código.

---

## 📜 Licença

Este projeto está licenciado sob a **Licença Pública Geral GNU v3.0 (GPL-3.0)**. Para mais detalhes, consulte o [LICENSE](../LICENSE).

> [!NOTE]
> ## Aviso Legal
>
> O Twinverse é um projeto independente de código aberto e não é afiliado, endossado por, ou de qualquer forma oficialmente conectado à Valve Corporation ou ao Steam.
>
> Esta ferramenta atua como uma camada de orquestração que aproveita tecnologias de sandboxing para executar múltiplas instâncias isoladas do cliente oficial do Steam. O Twinverse **não modifica, aplica patches, faz engenharia reversa ou altera** quaisquer arquivos do Steam ou seu funcionamento normal. Todas as instâncias do Steam iniciadas por esta ferramenta são as versões oficiais e não modificadas fornecidas pela Valve.
>
> Os usuários são os únicos responsáveis por cumprir os termos do Acordo de Assinante do Steam.

---

## 🙏 Créditos

Este projeto foi inspirado pelo trabalho de:

-   [NaviVani-dev](https://github.com/NaviVani-dev) e seu script [dualscope.sh](https://gist.github.com/NaviVani-dev/9a8a704a31313fd5ed5fa68babf7bc3a).
-   [Tau5](https://github.com/Tau5) e seu projeto [Co-op-on-Linux](https://github.com/Tau5/Co-op-on-Linux).
-   [wunnr](https://github.com/wunnr) e seu projeto [Partydeck](https://github.com/wunnr/partydeck) (Recomendo usa-lo caso você esteja procurando uma abordagem mais próxima ao [Nucleus Co-op](https://github.com/SplitScreen-Me/splitscreenme-nucleus)).
