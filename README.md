# Fictor YT Downloader (yt-dlp)

Extensão para Chrome / Edge / Brave / Opera que adiciona um botão **Download** ao YouTube (à esquerda do Like) com 4 abas: **Video**, **Audio**, **Thumbnail** e **Subtitles**. Os downloads são feitos pelo **yt-dlp**, que corre num pequeno servidor Python local.

```
YouTube (content.js) → background.js → http://127.0.0.1:9614 (Flask + yt-dlp)
                                                ↓ ficheiro pronto
                                  chrome.downloads → pasta de downloads do browser
```

## 1. Servidor local

Requisitos: **Python 3.9+** e **ffmpeg** no PATH (necessário para juntar vídeo+áudio em resoluções altas, converter para MP3 e para SRT/ASS). Nas versões recentes, o yt-dlp também precisa de um runtime JavaScript para o YouTube — instala o [Deno](https://deno.com).

- **Windows:** duplo clique em `server/install_and_run.bat`
- **Linux / macOS:** `sh server/install_and_run.sh`

O script cria um ambiente virtual, instala/atualiza as dependências (incluindo o yt-dlp) e arranca o servidor em `http://127.0.0.1:9614`. Deixa a janela aberta enquanto usas a extensão. Podes confirmar em `http://127.0.0.1:9614/health`.

## 2. Extensão

1. Abre `chrome://extensions` e ativa o **Modo de programador**.
2. Clica em **Carregar sem pacote** e escolhe a pasta `extension/`.
3. Abre um vídeo no YouTube: o botão **Download** aparece junto aos botões Like/Share.

## Utilização

- **Video:** escolhe a resolução (ou *Best available*) → Download (MP4).
- **Audio:** *Best (original stream)* ou MP3 a 320 … 64 kbps.
- **Thumbnail:** descarrega a miniatura em máxima resolução.
- **Subtitles:** escolhe idioma (legendas manuais ou automáticas) e formato (SRT, VTT, ASS, TTML, JSON3).

O servidor guarda o ficheiro numa pasta temporária, a extensão entrega-o ao gestor de downloads do browser e os temporários são apagados ao fim de 15 minutos.

## Configuração

| O quê | Como |
|---|---|
| Mudar a porta | variável `YTDLP_PORT` + `SERVER` em `extension/background.js` + `host_permissions` em `extension/manifest.json` |
| Vídeos com restrição de idade / "confirm you're not a bot" | variável `YTDLP_COOKIES_BROWSER=chrome` (ou `firefox`, `edge`…) antes de arrancar o servidor |

## Problemas comuns

- **"Can't reach the local server"** — o servidor não está a correr; arranca-o e carrega em *Retry*.
- **Erros de extração / formatos em falta** — o YouTube muda com frequência; reinicia o script (atualiza o yt-dlp) e confirma que tens Deno e ffmpeg instalados.
- **Só aparecem resoluções baixas e não há MP3/SRT** — falta o ffmpeg.
- **Firefox** — não suportado tal como está (usa service worker MV3 e `chrome.*`).

## Segurança

O servidor só ouve em `127.0.0.1`, rejeita pedidos com `Host` diferente de localhost e pedidos cuja origem não seja uma extensão, e só aceita URLs do YouTube.

## Aviso

Usa esta ferramenta apenas para conteúdo que tenhas direito de descarregar (o teu, licenciado ou de domínio público). Descarregar vídeos pode violar os Termos de Serviço do YouTube e leis de direitos de autor do teu país.
