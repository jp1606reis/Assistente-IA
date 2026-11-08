# Assistente de Voz

Aplicativo desktop para Windows que permite pesquisar vídeos no YouTube,
controlar a reprodução por voz, criar anotações e abrir alguns aplicativos e
sites. A interface oferece botões e um campo para testar comandos sem usar o
microfone.

## Requisitos

- Windows
- Python 3.13
- Acesso à internet para transcrição de voz, interpretação e pesquisa no YouTube
- Microfone para usar comandos falados
- Chaves de API para os serviços que deseja usar

## Instalação

Abra o PowerShell na pasta do projeto e execute:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Crie um arquivo `.env` na pasta do projeto para habilitar os recursos online:

```env
GEMINI_API_KEY=sua_chave_gemini
YOUTUBE_API_KEY=sua_chave_youtube
```

- `GEMINI_API_KEY`: transcrição do microfone e interpretação de comandos.
- `YOUTUBE_API_KEY`: pesquisa de vídeos e acesso aos resultados da YouTube Data
  API. A API precisa estar habilitada no projeto associado à chave.

Mantenha essas chaves privadas e não envie o arquivo `.env` para outras pessoas.

## Iniciar o aplicativo

No PowerShell, na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe main.py
```

A janela inicia em tela cheia. Pressione `F11` para alternar entre tela cheia e
janela; `Esc` sai da tela cheia.

O microfone inicia automaticamente. No painel inferior:

- **Parar Microfone / Ligar Microfone** alterna a captura de voz.
- **Comando rápido** executa o texto digitado como se fosse uma fala. Pressione
  `Enter` ou clique em **Enviar**.
- As mensagens **Ouvido** e o status mostram o que foi reconhecido e o
  resultado do comando.

## Pesquisar e reproduzir vídeos

1. Abra **Pesquisar no YouTube** pelo botão na tela inicial ou diga
   **“Abrir YouTube”**.
2. Digite um assunto na caixa de pesquisa e clique em **Pesquisar**; ou diga
   **“Pesquisar no YouTube”**, informe o assunto quando solicitado e depois
   diga **“Confirmar”**.
3. Use **Próximo** e **Anterior** para percorrer os resultados. A tela mostra
   um vídeo por vez, com título, descrição e capa.
4. Clique em **Selecionar vídeo** ou diga **“Selecionar vídeo”** para abrir o
   vídeo no navegador.
5. Com o aplicativo e a página do player abertos, use os comandos de voz ou os
   botões de controle na tela do YouTube.

Cada seleção abre uma nova aba. Os comandos seguintes são enviados ao player
mais recentemente aberto pelo aplicativo; abas anteriores não recebem novos
comandos.

Comandos de reprodução:

| Ação | Exemplos de fala |
| --- | --- |
| Reproduzir ou retomar | “Reproduzir vídeo”, “Dar play”, “Continuar assistindo” |
| Pausar | “Pausar vídeo”, “Dar pausa” |
| Ativar som | “Ativar som”, “Quero ouvir” |
| Silenciar | “Silenciar vídeo”, “Deixar no mudo” |
| Avançar 10 segundos | “Avançar 10 segundos”, “Pular para frente” |
| Voltar 10 segundos | “Voltar 10 segundos”, “Rebobinar o vídeo” |

O player tenta iniciar sem som. Alguns navegadores bloqueiam o início ou a
retomada automática. Para usar somente a voz, permita autoplay para o site nas
configurações do navegador. O aplicativo não consegue substituir essa
permissão.

## Usar anotações

1. Abra **Bloco de Anotações** na tela inicial.
2. Digite o texto ou diga **“Iniciar ditado”** e dite o conteúdo.
3. Diga **“Parar ditado”** para encerrar sem salvar, ou **“Salvar anotação”**
   para gravar diretamente em `Documents\Anotacoes de Voz`.

Também é possível usar os botões **Salvar (.txt)** e **Abrir (.txt)** para
escolher o arquivo e o local. **Limpar** pede confirmação antes de apagar o
texto atual.

## Outros comandos de voz

Os seguintes comandos podem ser falados sem abrir uma tela de atalhos:

- **Navegação:** “Voltar” retorna à tela inicial.
- **Aplicativos:** “Abrir calculadora” ou “Abrir Bloco de Notas”.
- **Sites:** “Abrir Gmail”, “Abrir GitHub” ou “Abrir ChatGPT”.
- **Pasta do projeto:** “Abrir pasta do projeto”.
- **Encerrar:** “Sair” ou “Fechar o aplicativo”; o app pede confirmação.
- **Cancelar:** “Cancelar” abandona uma pergunta ou ação pendente.

Os comandos também podem ser testados pelo campo **Comando rápido**, sem falar
ao microfone. Se uma frase alternativa não for reconhecida, tente primeiro os
exemplos listados acima.

## Solução de problemas

- **A pesquisa do YouTube falha:** confira `YOUTUBE_API_KEY`, a conexão com a
  internet e se a YouTube Data API está habilitada para a chave. O erro da
  pesquisa aparece na própria tela.
- **O microfone não transcreve:** confira `GEMINI_API_KEY`, a conexão, a
  permissão de microfone do Windows e se o dispositivo de entrada correto está
  selecionado.
- **O comando não é entendido:** confira se está na tela apropriada. Para
  testar o roteamento sem o microfone, digite a frase em **Comando rápido**.
- **O player não inicia ou não retoma:** confira a mensagem na página do player
  e as permissões de autoplay do navegador. Mantenha o aplicativo e a aba mais
  recente do player abertos.
- **A capa não aparece:** a pesquisa pode ter sido concluída mesmo se o download
  da miniatura falhar; tente novamente ou avance para outro resultado.

## Privacidade

O áudio do microfone é enviado ao Gemini para transcrição. A pesquisa e a chave
de API são usadas para consultar a YouTube Data API. As anotações são gravadas
localmente no computador. Não coloque informações confidenciais em comandos de
voz ou pesquisas.

## Estrutura do projeto

```text
.
├── assistant/
│   ├── core/       # Ações, roteamento e correspondência por similaridade
│   ├── player/     # Player HTML do YouTube e ponte para comandos de voz
│   ├── screens/    # Telas Tkinter
│   ├── voice/      # Captura e transcrição de áudio
│   ├── app.py      # Janela e fluxo principal do aplicativo
│   ├── config.py   # Leitura de credenciais
│   └── services.py # YouTube, miniaturas e arquivos de anotação
├── main.py         # Inicialização: python main.py
├── requirements.txt
└── .env            # Credenciais locais; não compartilhar
```
