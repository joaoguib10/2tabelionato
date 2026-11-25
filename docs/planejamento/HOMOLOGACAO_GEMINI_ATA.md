# Homologação sintética — Gemini na Ata Notarial

Atualizado em 24/11/2026. Este roteiro cobre somente a organização opcional do texto da Ata. A leitura de ZIP/RAR, a transcrição Whisper e a conservação dos arquivos continuam locais.

## Limites do fluxo

- Sinalizador `ATA_GEMINI_ORGANIZATION_ENABLED=false` por padrão.
- A API exige perfil ADMIN, transcrição local concluída e confirmação explícita de que todo o conteúdo é público ou sintético.
- Áudios, anexos, arquivos ZIP/RAR e resultados de trabalhos reais/confidenciais não são enviados.
- Gemini recebe mensagens sintéticas/públicas em JSON e devolve somente uma lista de IDs. O servidor valida que a lista contém todos os IDs uma vez e reconstrói a saída com os textos locais originais.
- O Gemini não resume, corrige, remove ou redige conteúdo da conversa. Cada chamada é independente, sem ID de interação ou histórico anterior; políticas de retenção do provedor continuam valendo. Não há fallback para Ollama nem outro provedor.
- O limite padrão é 50.000 caracteres e 1.500 mensagens. Falha de rede, cota, JSON incompleto ou ID inválido mantém a transcrição local.

## Verificações automatizadas

Os testes em `backend/tests/test_notarial_acts.py` cobrem a separação entre proprietário e ADMIN, a confirmação por trabalho, preservação do texto e transcrição locais, exclusão do arquivo de áudio da entrada do Gemini, resposta JSON e tratamento de timeout e resposta incompleta. O provedor é simulado nos testes; nenhuma informação é enviada ao Google.

Na execução de 24/11/2026, `pytest tests/test_migrations.py tests/test_notarial_acts.py -q` aprovou 26 testes. A build do frontend, TypeScript, ESLint global e Prettier da página da Ata também passaram. A suíte completa do backend ainda registra 20 falhas em testes de Análise e chat que simulam a interface Ollama anterior ou não usam a sessão de banco de teste no processamento em segundo plano. Portanto, esta execução não aprova o sistema inteiro.

## Verificação manual pendente antes de ativar na VM

1. Aplicar as migrations e habilitar o fluxo apenas num ambiente sintético separado.
2. Com uma chave válida do projeto de teste, ordenar uma transcrição sintética curta e revisar que autores, datas, conteúdo de cada mensagem e referências de anexos foram preservados.
3. Repetir com falha de rede, resposta 429, timeout, texto grande e resposta malformada; conferir que a transcrição local continua copiável e nenhum caminho alternativo envia conteúdo.
4. Testar com 1, 3 e 6 sessões sintéticas na VM. Medir p50/p95, fila e erros de cota; nenhuma chamada real ao provedor foi feita nesta atualização, portanto o desempenho do Gemini ainda não está homologado.
5. Conferir autorização e descarte: usuário comum não organiza via Gemini; o trabalho continua visível apenas ao usuário proprietário; **Concluir e apagar** remove exportação, extrações, transcrição local e resultado organizado.
6. Manter `CONSULTA_ONLY_MODE=true` até que a homologação de cada módulo e a revisão humana sejam concluídas. Não testar com transcrição real.

## Critério para liberar

Liberar a opção somente após revisão humana da ordenação sintética, confirmação de que a chave está no backend e sem faturamento ativo, medição de cota/desempenho na VM e validação do processo de descarte. Se algum critério falhar, manter a flag desligada; a saída local continua disponível.
