# Tabeleão

O Tabeleão é uma aplicação local de apoio ao trabalho do tabelionato. Reúne consulta à base institucional, análise documental por processo, entendimentos humanos, revisões de respostas e formatação de exportações para ata notarial. As respostas da IA são auxiliares: a conferência dos documentos originais e a decisão sobre o ato pertencem ao profissional responsável.

## O que cada aba faz

| Aba | Uso atual |
| --- | --- |
| Consulta | Recebe perguntas em português e pesquisa em camadas: primeiro entendimentos publicados pelo ADMIN, depois respostas de Revisões já respondidas pelo ADMIN e, por fim, documentos institucionais aprovados por busca híbrida de texto e embeddings. O entendimento mais pertinente é considerado em conjunto e sintetizado sem limite fixo de palavras, com fundamentação nas fontes citadas. |
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
3. Ollama local, com os modelos configurados no `.env`.
4. Para OCR: Poppler (`pdftoppm`) e Tesseract com os idiomas português (`por`) e inglês (`eng`). Ambos devem estar no `PATH` ou ter o caminho do executável indicado no `.env`.
5. Para áudio da Ata: FFmpeg/FFprobe, Whisper local e um modelo Whisper já armazenado na máquina. Para RAR, instale 7-Zip. ZIP não depende do 7-Zip.

Na raiz do projeto, copie a configuração de exemplo e altere pelo menos a chave secreta e as credenciais do banco. Não compartilhe o arquivo `.env`.

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

Para instalar em outra máquina, repita a instalação dos programas, copie o código sem dados operacionais, crie um `.env` próprio e aplique as migrações. Se precisar manter usuários, documentos e histórico, transfira banco e arquivos operacionais por procedimento de backup/restore protegido; copiar apenas o código não transfere esses dados. O processamento da IA permanece local quando `OLLAMA_LOCAL_ONLY=true` e a URL do Ollama aponta para `localhost`.

## Operação da base documental

O fluxo é upload → extração/OCR → trechos → embeddings → status de processamento. Após o processamento, o ADMIN deve conferir categoria, origem, vigência, integridade e situação de segurança antes de aprovar. Documentos em rascunho, erro, processamento, revogados ou arquivados não alimentam a Consulta. A busca seleciona entendimentos publicados pelas palavras relevantes da pergunta e pelo tema encontrado no título, na descrição e nos trechos; em PostgreSQL, restringe candidatos com o índice de texto completo em português antes de ranquear, em vez de carregar o acervo inteiro para a aplicação. O entendimento mais pertinente é enviado integralmente ao modelo, com controle de contexto, para sintetizar os itens aplicáveis, preservar condições, exceções e justificativas e fundamentar a resposta na fonte. Se o entendimento exceder o contexto seguro do modelo, o sistema avisa em vez de apresentar uma resposta parcial como completa. Respostas administrativas de Revisões podem ser recuperadas quando estiverem respondidas, ainda não tiverem sido encaminhadas para generalização e não contiverem identificadores pessoais evidentes; sua busca é filtrada pelos termos da pergunta e a pergunta original e o autor não são enviados como fonte ao modelo. Se uma fonte humana não sustentar resposta suficiente, a busca híbrida dos documentos aprovados complementa a recuperação. Os derivados de Revisões só entram como entendimentos gerais após processamento, aprovação e publicação.

Os documentos de casos da Análise ficam segregados do acervo institucional. JPG e PNG são submetidos a OCR local; se a leitura não for suficientemente legível, a Análise pede uma cópia melhor ou a transcrição do trecho, sem fingir que o conteúdo foi conferido. Os arquivos de trabalho e os dados do banco não devem ser incluídos no Git. Anexos temporários devem ser mantidos apenas pelo tempo necessário ao ato.

## Segurança e limites de uso

O login usa senha e bloqueio de tentativas; o segundo fator TOTP local pode ser controlado por `MFA_ENABLED` e deve permanecer ativado fora dos testes locais. A sessão é renovada durante a atividade e expira após o período configurado. O Ollama é restringido a loopback por padrão. Respostas e triagens devem ser conferidas nas fontes exibidas e nos documentos originais; a existência de uma fonte não significa, por si só, que ela resolve a pergunta ou autoriza a lavratura de uma escritura.

Para detalhes técnicos de A1/A2/TAB, consulte [a base funcional](docs/arquitetura/BASE_FUNCIONAL.md) e [o desenho da análise documental](docs/arquitetura/ANALISE_DOCUMENTAL_V2.md).
