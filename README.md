# Tabeleão

O Tabeleão é uma aplicação local de apoio ao trabalho do tabelionato. Reúne consulta à base institucional, análise documental por processo, entendimentos humanos, revisões de respostas e formatação de exportações para ata notarial. As respostas da IA são auxiliares: a conferência dos documentos originais e a decisão sobre o ato pertencem ao profissional responsável.

## O que cada aba faz

| Aba | Uso atual |
| --- | --- |
| Consulta | Envia perguntas gerais ao Gemini File Search e pesquisa, em ordem, entendimentos publicados, respostas humanas de Revisões e documentos institucionais aprovados. Só mostra respostas com trechos citados e validados localmente; sem base suficiente, encaminha ao ADMIN. |
| Documentos | Cadastra e processa PDF, DOCX e TXT, inclusive OCR local de PDF digitalizado. O ADMIN classifica, revisa a extração, aprova, arquiva, revoga, reprocessa, baixa ou exclui documentos. Só conteúdo aprovado, íntegro e elegível alimenta a Consulta. |
| Novos entendimentos | O ADMIN redige entendimentos internos. Eles passam por processamento e publicação administrativa antes de integrar a Consulta. Usuários podem ler os publicados. |
| Análise | Mantém uma conversa privada por caso. O usuário descreve o processo, identifica o tipo e a parte relacionada a cada documento, envia PDF, DOCX, TXT, JPG ou PNG, e recebe uma triagem factual assistida. Pode complementar o caso na mesma conversa, conferir fatos e concluir ou reabrir. |
| Ata Notarial | Organiza em ordem cronológica a exportação ZIP/RAR de uma conversa do WhatsApp. Preserva as referências a fotos, vídeos, PDFs e stickers no texto; áudio é transcrito localmente quando as ferramentas estão configuradas. O resultado temporário pode ser concluído e apagado. |
| Histórico | Mostra as consultas do próprio usuário. O ADMIN pode filtrar e consultar o histórico de todos, para acompanhar os temas pesquisados. |
| Revisões | Recebe as respostas avaliadas como não úteis. O ADMIN registra uma correção humana e, quando ela puder ser generalizada, cria um entendimento interno para publicação na base. |
| Configurações | Administração de usuários e acesso, disponível ao ADMIN. |

Existem os perfis `ADMIN` e `USUARIO`. Todos podem consultar e trabalhar em seus casos próprios ou atribuídos. O ADMIN gerencia a base institucional, as contas e as revisões, e pode acompanhar todos os casos. Os anexos de um caso da Análise são privados e **não** entram no corpus jurídico da Consulta. A2 organiza fatos extraídos, A1 aplica fontes institucionais após conferência e TAB registra a decisão humana; a conversa da IA não substitui essas etapas.

Uma avaliação negativa não altera automaticamente o conhecimento da IA. Uma resposta corrigida passa a servir de base somente depois de o ADMIN transformá-la em entendimento geral, conferir o processamento e publicá-la. Essa separação evita promover dados de um caso particular a regra geral.

## Instalação em uma máquina Windows

Instale previamente:

1. Python 3.12 ou mais recente e Node.js 20 ou mais recente.
2. Docker Desktop, para PostgreSQL com a extensão pgvector.
3. Ollama local, com modelos de embeddings e Análise configurados no `.env`. A Consulta usa o Gemini.
4. Para OCR: Poppler (`pdftoppm`) e Tesseract com os idiomas português (`por`) e inglês (`eng`). Ambos devem estar no `PATH` ou ter o caminho do executável indicado no `.env`.
5. Para áudio da Ata: FFmpeg/FFprobe, Whisper local e um modelo Whisper já armazenado na máquina. Para RAR, instale 7-Zip. ZIP não depende do 7-Zip.

Na raiz do projeto, copie a configuração de exemplo e altere pelo menos a chave secreta e as credenciais do banco. Para usar a Consulta, configure também uma chave Gemini de projeto sem faturamento ativo e confirme o nível gratuito no ambiente. Não compartilhe o arquivo `.env`.

```powershell
Copy-Item .env.example .env
docker compose up -d
ollama pull nomic-embed-text-v2-moe
ollama pull qwen3:8b
```

Confirme que o Ollama está em execução localmente. Em um terminal, instale o backend, aplique as migrações e inicie a API:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python backend/scripts/download_whisper_model.py
Set-Location backend
python -m alembic upgrade head
python -m scripts.create_admin
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

`create_admin` é necessário apenas para o primeiro administrador de uma instalação nova. O segundo fator TOTP é controlado por `MFA_ENABLED` (ativado por padrão); pode ser temporariamente desativado no ambiente local de testes definindo `MFA_ENABLED=false`, sem remover os fluxos ou os dados cadastrados. Em outro terminal, inicie a interface:

```powershell
Set-Location frontend
npm ci
npm run dev
```

A interface fica em `http://localhost:3000`; a API, em `http://localhost:8000`; a documentação da API, em `http://localhost:8000/docs`. Com `MFA_ENABLED=true`, no primeiro acesso configure o segundo fator TOTP em um aplicativo autenticador compatível. A recuperação de conta é feita localmente no servidor por `python -m scripts.recover_account`, com conferência administrativa.

Para instalar em outra máquina, repita a instalação dos programas, copie o código sem dados operacionais, crie um `.env` próprio e aplique as migrações. Se precisar manter usuários, documentos e histórico, transfira banco e arquivos operacionais por procedimento de backup/restore protegido; copiar apenas o código não transfere esses dados. Análise, OCR, embeddings e Ata permanecem locais. A Consulta envia ao Gemini somente perguntas gerais e conteúdo institucional público ou sintético liberado individualmente pelo ADMIN.

### Modelo local de transcrição da Ata

O backend usa Whisper `large-v3` em CPU para transcrever áudios em português. Os pesos são gratuitos, sob licença MIT, e são baixados separadamente do repositório; não envie o arquivo `.pt` ao GitHub. Com o ambiente virtual ativado, execute `python backend/scripts/download_whisper_model.py` na raiz do projeto. O script salva o checkpoint em `backend/models/large-v3.pt` e valida o SHA-256 antes de concluir. Em seguida, configure `WHISPER_MODEL_PATH=models/large-v3.pt` no `.env` usado pelo backend, considerando que a API é iniciada dentro da pasta `backend`, e reinicie a API.

O download ocupa aproximadamente 3 GB. O modelo Large exige muito mais memória do que o Small; o repositório oficial estima cerca de 10 GB de VRAM para a variante Large, e o uso em CPU consome memória RAM e pode ser significativamente mais lento. Para executar Ollama, API, banco e Whisper Large com concorrência, recomenda-se dimensionar a VM com pelo menos 32 GB de RAM e espaço livre suficiente para os pesos, dependências, banco e extração temporária dos arquivos da Ata. Os áudios de usuários continuam sendo processados localmente.

## Operação da base documental

O fluxo de cadastro é upload → extração/OCR → trechos e embeddings locais → status de processamento. O ADMIN confere categoria, origem, vigência, integridade, segurança e aprovação. Documentos em rascunho, erro, processamento, revogados ou arquivados não alimentam a Consulta. Para responder, o Gemini File Search percorre, em chamadas ordenadas, entendimentos, revisões humanas e documentos aprovados que tenham sido liberados individualmente pelo ADMIN. Cada chamada fica limitada à categoria consultada. A resposta só é exibida quando as citações retornadas pelo Gemini correspondem a trechos e versões ainda válidos no banco local; o histórico preserva snapshots das fontes citadas. A geração local com Ollama não é usada na Consulta. Se o Gemini não estiver configurado, não encontrar evidência suficiente ou não produzir citações verificáveis, o sistema informa a insuficiência e orienta o usuário a encaminhar a dúvida ao ADMIN ou à Revisão. As instruções de consulta aplicam os princípios de A1/A2/TAB: não inventar fatos ou regras, explicitar lacunas e conflitos, tratar os documentos como evidência e manter decisão e autorização exclusivamente humanas.

Os documentos de casos da Análise ficam segregados do acervo institucional. JPG e PNG são submetidos a OCR local; se a leitura não for suficientemente legível, a Análise pede uma cópia melhor ou a transcrição do trecho, sem fingir que o conteúdo foi conferido. Os arquivos de trabalho e os dados do banco não devem ser incluídos no Git. Anexos temporários devem ser mantidos apenas pelo tempo necessário ao ato.

## Consulta com Gemini

A aba Consulta usa diretamente o Gemini File Search; não existe geração local como fallback. A chave fica somente no ambiente do backend, sem acesso pelo navegador. O banco local mantém a governança, as permissões, o histórico, os snapshots e a validação das citações. Análise e Ata Notarial permanecem separadas e não enviam casos ao Gemini.

Para preparar o servidor, crie uma chave em um projeto Google sem faturamento ativo e configure `GEMINI_API_KEY`, `EXTERNAL_AI_ENABLED=true` e `EXTERNAL_AI_FREE_TIER_CONFIRMED=true` no `.env` do backend. As opções de segurança continuam desativadas no `.env.example`; o responsável pela implantação deve habilitá-las somente após conferir o projeto. O sistema não consegue verificar o plano nem impedir que alguém ative faturamento. Sem cota gratuita, a Consulta informa indisponibilidade ou falta de evidência e não troca para Ollama nem para um plano pago. Consulte os [termos da Gemini API](https://ai.google.dev/gemini-api/terms?hl=pt-br), a [documentação do File Search](https://ai.google.dev/gemini-api/docs/file-search) e as [cotas vigentes](https://ai.google.dev/gemini-api/docs/rate-limits).

Não há etapa para habilitar a Consulta na interface. O ADMIN continua liberando individualmente, na aba **Documentos** ou **Revisões**, as fontes públicas ou sintéticas autorizadas para sincronização. Documentos precisam estar aprovados, PRONTOS e liberados na revisão de segurança. O conteúdo é inspecionado localmente e enviado como texto extraído; o original não é enviado como arquivo. A fila registra sincronização, falhas e remoções. O status e o reprocessamento de falhas ficam disponíveis em **Configurações → Status da Consulta**.

O nível gratuito pode usar conteúdo enviado para melhoria do serviço ou revisão humana. Não libere dados pessoais, confidenciais ou sensíveis; marcar uma fonte como sintética é uma decisão administrativa e a inspeção automática não certifica anonimização. O conteúdo dos casos de Análise e da Ata continua local.

## Segurança e limites de uso

O login usa senha e bloqueio de tentativas; o segundo fator TOTP local pode ser controlado por `MFA_ENABLED` e deve permanecer ativado fora dos testes locais. A sessão é renovada durante a atividade e expira após o período configurado. O Ollama é restringido a loopback por padrão. Respostas e triagens devem ser conferidas nas fontes exibidas e nos documentos originais; a existência de uma fonte não significa, por si só, que ela resolve a pergunta ou autoriza a lavratura de uma escritura.

Para detalhes técnicos de A1/A2/TAB, consulte [a base funcional](docs/arquitetura/BASE_FUNCIONAL.md) e [o desenho da análise documental](docs/arquitetura/ANALISE_DOCUMENTAL_V2.md).
