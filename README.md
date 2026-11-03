# Fictor YT Downloader (yt-dlp)

Extensão para Chrome / Edge / Brave / Opera. Ao clicar no **ícone da extensão**, num vídeo do YouTube, abre um menu **Download** com 4 abas: **Video**, **Audio**, **Thumbnail** e **Subtitles**. Os downloads são feitos pelo **yt-dlp**, que corre num pequeno servidor Python local.

```
Ícone da extensão → popup.html/popup.js ─┐
                                         ├→ background.js → http://127.0.0.1:9614 (Flask + yt-dlp)
              (progresso e ficheiro) ←───┘                          ↓ ficheiro pronto
                                          chrome.downloads → pasta de downloads do browser
```

## 1. Servidor local

Requisitos: **Python 3.9+**. O **ffmpeg** é instalado automaticamente (pacote `imageio-ffmpeg`) se não existir no PATH, e o **Deno** é recomendado (o yt-dlp precisa de um runtime JavaScript para o YouTube; sem ele podem faltar formatos).

- `server/install_and_update.bat` / `.sh` — instala/atualiza as dependências Python (incluindo o yt-dlp) e o Deno.
- `server/run_server.bat` / `.sh` — arranca o servidor em `http://127.0.0.1:9614`. Deixa a janela aberta enquanto usas a extensão.

**Diagnóstico:** abre `http://127.0.0.1:9614/health` — deve mostrar `"ffmpeg": true` e `"deno": true`. Se algum for `false`, é a causa mais provável de resoluções em falta ou de erros do tipo *"Requested format is not available"*.

## 2. Extensão

1. Abre `chrome://extensions` e ativa o **Modo de programador**.
2. Clica em **Carregar sem pacote** e escolhe a pasta `extension/`. (Se já a tinhas carregada, carrega em **Atualizar** ↻ — o botão que estava integrado no YouTube desaparece.)
3. Fixa o ícone na barra (menu de extensões ▸ 📌), abre um vídeo no YouTube e clica no ícone.

O popup funciona em `youtube.com/watch`, `youtube.com/shorts` e `youtu.be`. Noutras páginas mostra um aviso.

## Utilização

- **Video:** resolução (ou *Best available*) + formato **MP4** (máxima compatibilidade), **MKV** (melhor qualidade, qualquer codec) ou **WEBM**. Em 1440p/4K o YouTube só oferece VP9/AV1, por isso o MP4 resultante pode não abrir em leitores antigos — usa MKV.
- **Audio:** formato **Original** (sem conversão), **MP3**, **M4A**, **Opus**, **FLAC** ou **WAV**; nos formatos com perdas escolhes o bitrate (320 … 64 kbps).
- **Thumbnail:** descarrega a miniatura em máxima resolução.
- **Subtitles:** três grupos — manuais, geradas automaticamente (idioma original) e traduzidas automaticamente — e formato SRT, VTT, ASS, TTML ou JSON3.

**O popup fecha sempre que clicas fora dele — não faz mal.** O download continua em segundo plano e o ficheiro vai para a pasta de downloads do browser quando terminar. Enquanto decorre, o ícone mostra a percentagem (`42%`); se falhar, mostra `!` e a mensagem aparece ao reabrires o popup no mesmo vídeo.

### Sobre o erro 429 nas legendas

O YouTube bloqueia (HTTP 429) os pedidos de legendas **traduzidas automaticamente** (o grupo "Auto-translated"). As legendas manuais e as automáticas no idioma original não são afetadas. Se uma legenda normal falhar com 429, espera alguns minutos ou usa `YTDLP_COOKIES_BROWSER`.

## Configuração (variáveis de ambiente do servidor)

| Variável | Para quê |
|---|---|
| `YTDLP_PORT` | Mudar a porta (altera também `SERVER` em `extension/background.js` e `host_permissions` em `manifest.json`) |
| `YTDLP_COOKIES_BROWSER` | `chrome`, `firefox`, `edge`… — usa os cookies desse browser (idade restrita, "confirm you're not a bot", 429) |
| `FFMPEG_LOCATION` | Pasta (ou caminho) do teu ffmpeg |

## Problemas comuns

- **"Can't reach the local server"** — o servidor não está a correr; arranca-o e carrega em *Retry*.
- **Faltam resoluções / "Requested format is not available"** — vê `/health`; instala o Deno e atualiza o yt-dlp.
- **"No YouTube video here"** — o separador ativo não é um vídeo; abre um vídeo e clica no ícone outra vez.
- **Firefox** — não suportado tal como está (usa service worker MV3 e `chrome.*`).

## Segurança

O servidor só ouve em `127.0.0.1`, rejeita pedidos com `Host` diferente de localhost e pedidos cuja origem não seja uma extensão, e só aceita URLs do YouTube. A extensão já não injeta nada nas páginas do YouTube: só lê o URL do separador ativo quando clicas no ícone (permissão `activeTab`).

## Aviso

Usa esta ferramenta apenas para conteúdo que tenhas direito de descarregar (o teu, licenciado ou de domínio público). Descarregar vídeos pode violar os Termos de Serviço do YouTube e leis de direitos de autor do teu país.
