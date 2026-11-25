# Configurar a Ata Notarial

Este guia se aplica quando a instalação sair do modo `CONSULTA_ONLY_MODE=true`. No modo somente Consulta, a aba Ata e suas rotas permanecem indisponíveis.

## Dependências locais

1. Instale FFmpeg com os comandos `ffmpeg` e `ffprobe` acessíveis no `PATH`.
2. Instale 7-Zip e configure `RAR_TOOL_COMMAND` com o executável usado pela máquina. O backend precisa dele para abrir arquivos RAR.
3. Na raiz do repositório, instale `requirements-legacy.txt` no ambiente virtual do backend: `backend\.venv\Scripts\python.exe -m pip install -r requirements-legacy.txt`. Esse arquivo contém o leitor RAR e o Whisper local.
4. Disponibilize um checkpoint Whisper em arquivo `.pt` e defina o caminho em `WHISPER_MODEL_PATH`. O script `backend/scripts/download_whisper_model.py` baixa o checkpoint oficial `large-v3` e confere o SHA-256 antes de instalá-lo. Modelos maiores exigem mais memória e espaço.

O servidor lê a exportação ZIP/RAR localmente e usa Whisper para transcrever áudio. Imagens, vídeos, PDFs e outros anexos permanecem como referências no texto; os arquivos não são enviados ao Gemini. Trabalhos parciais permitem repetir o processamento local após corrigir a configuração ou a causa da falha.

## Organização opcional por Gemini

A organização externa é desligada por padrão. Para testá-la, configure no backend:

```dotenv
EXTERNAL_AI_ENABLED=true
EXTERNAL_AI_FREE_TIER_CONFIRMED=true
GEMINI_API_KEY=<chave guardada somente no .env>
ATA_GEMINI_ORGANIZATION_ENABLED=true
```

Ative esse fluxo somente depois de confirmar as condições do projeto Google e usar dados sintéticos ou públicos. Um ADMIN precisa confirmar essa classe de conteúdo para cada trabalho. O endpoint envia apenas as mensagens transcritas e seus metadados para que Gemini devolva IDs em ordem cronológica; o servidor monta a saída a partir dos textos originais. Áudio, anexos e transcrições reais/confidenciais ficam locais. Cada chamada é independente e não envia histórico anterior nem ID de interação; continuam valendo as regras de retenção do provedor. Falhas de rede, cota ou resposta inválida preservam a transcrição local.

O limite padrão é 50.000 caracteres e 1.500 mensagens. Trabalhos acima do limite permanecem disponíveis no resultado local.

## Homologação antes de liberar

Use [o roteiro de homologação sintética](../planejamento/HOMOLOGACAO_GEMINI_ATA.md). Os testes automatizados não substituem uma chamada real com texto sintético, uma avaliação humana da ordenação nem a medição de latência e cotas da VM.
