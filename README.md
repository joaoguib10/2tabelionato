# Tabeleão

Sistema de apoio à consulta de normas, procedimentos e entendimentos do tabelionato. O piloto usa busca textual no banco local para selecionar trechos de fontes institucionais aprovadas e liberadas; o Gemini Flash-Lite (`gemini-3.5-flash-lite`) sintetiza perguntas objetivas, enquanto o Gemini Flash (`gemini-3.5-flash`) atende consultas complexas, sempre com base nos trechos selecionados. Se a busca local não encontrar candidatos, o File Search externo continua como alternativa. A resposta é auxiliar: a conferência das fontes e a decisão sobre o ato cabem ao profissional responsável.

## Como funciona

1. O ADMIN cadastra documentos PDF, DOCX ou TXT e entendimentos internos. A extração do texto e o OCR de PDFs digitalizados ocorrem no servidor local.
2. Fontes institucionais de Consulta (normas, legislação, entendimentos, procedimentos e manuais) são aprovadas e colocadas automaticamente na fila do Gemini File Search quando a extração termina por completo e a inspeção de segurança é liberada. Uma fonte sinalizada para revisão, sem texto extraído ou revogada não é publicada. O arquivo original, os usuários e o histórico permanecem no armazenamento local.
3. Na aba **Consulta**, o usuário faz uma pergunta geral, sem informações de clientes ou processos. O backend recupera do banco local os trechos pertinentes que estão aprovados, liberados e sincronizados para consulta externa, incluindo normas, legislação, entendimentos e revisões autorizadas. Só os trechos selecionados e a pergunta seguem ao Gemini para síntese; o provedor não recebe acesso ao banco. A busca local preserva a prioridade das normas e usa entendimentos e procedimentos para complementar a aplicação prática.
4. A aplicação confere as citações da síntese contra os trechos e versões guardados localmente. Se a busca textual não encontrar candidatos, o File Search externo é usado como alternativa. Quando nenhuma evidência puder ser validada, a aplicação informa a limitação e orienta a pedir revisão humana.

O ADMIN administra a base documental, os usuários e as revisões. Cada usuário vê o próprio histórico; o ADMIN pode acompanhar o histórico geral. A interface oferece modo claro e escuro, com preferência salva no navegador. O piloto é iniciado com `CONSULTA_ONLY_MODE=true`; Análise, Minuta e Ata Notarial não aparecem nesse modo.

## O que instalar

Para executar o piloto no Windows:

- [Git](https://git-scm.com/download/win), se for clonar o repositório. Também é possível baixar o código como ZIP no GitHub.
- [Python 3.12](https://www.python.org/downloads/) ou mais recente e [Node.js 20.9](https://nodejs.org/) ou mais recente.
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) com WSL 2 ativo, para PostgreSQL 17 com pgvector. Em Linux, use Docker Engine e o plugin Compose.
- Uma chave da [Gemini API](https://aistudio.google.com/api-keys) em um projeto Google verificado no AI Studio. Para este piloto gratuito, confirme que o projeto está em **Free Tier**, sem faturamento ativo.
- Para ler PDFs digitalizados: [Poppler](https://poppler.freedesktop.org/) (`pdftoppm`) e [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) com os idiomas `por` e `eng`. Esses programas são opcionais quando os documentos já contêm texto selecionável.

O servidor precisa acessar a API do Google pela rede. Confira as [cotas e limites ativos](https://ai.google.dev/gemini-api/docs/rate-limits) no projeto do AI Studio; eles são compartilhados pelas chaves do mesmo projeto.

## Instalação local no Windows

Clone o repositório ou abra a pasta baixada. No PowerShell, a partir da raiz do projeto:

```powershell
git clone https://github.com/joaoguib10/2tabelionato.git
Set-Location 2tabelionato
Copy-Item .env.example .env
```

Se o código já estiver no computador, pule os dois primeiros comandos. Edite o `.env` local antes de iniciar os serviços:

- Substitua `TABELEAO_SECRET_KEY` por uma chave longa e aleatória.
- Troque `POSTGRES_PASSWORD` e atualize a mesma senha em `DATABASE_URL`.
- Coloque a chave do projeto em `GEMINI_API_KEY` e, depois de confirmar o Free Tier, defina `EXTERNAL_AI_ENABLED=true` e `EXTERNAL_AI_FREE_TIER_CONFIRMED=true`.
- Mantenha `CONSULTA_ONLY_MODE=true`. O segundo fator TOTP é controlado por `MFA_ENABLED` e vem ativado no exemplo.

Não publique o `.env` nem a chave Gemini no GitHub. Inicie o banco:

```powershell
docker compose -f docker-compose.yml -f compose.vm.yaml up -d
```

Em um terminal, instale e inicie o backend:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.create_admin
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

O comando `create_admin` é usado apenas na primeira instalação, para criar a conta administrativa. Em outro terminal, a partir da raiz do projeto, inicie a interface:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Abra <http://127.0.0.1:3000>. A API responde em <http://127.0.0.1:8000/health>. Quando o segundo fator estiver habilitado, configure um aplicativo autenticador no primeiro acesso.

Para uma instalação em outra máquina, configure um `.env` próprio e aplique as migrações. Copiar apenas o código não transfere usuários, documentos, arquivos enviados nem histórico; esses dados precisam de backup e restauração separados. Em uma VM acessada pela rede, publique a interface por um proxy HTTPS, configure `FRONTEND_ORIGINS` e `AUTH_COOKIE_SECURE=true` para o endereço usado e mantenha o banco restrito à máquina local.

## Dados e operação

O Google recebe as perguntas gerais e o texto extraído das fontes institucionais aprovadas; a aplicação não envia o arquivo original. O nível gratuito pode usar o conteúdo enviado para melhorar produtos. Não insira dados pessoais, confidenciais ou sensíveis na Consulta nem cadastre esse tipo de conteúdo como fonte pública. [Termos da Gemini API](https://ai.google.dev/gemini-api/terms?hl=pt-br).

A sincronização das fontes é feita por uma fila local, sem exigir uma segunda liberação manual para documentos institucionais aptos. Documentos extensos podem demorar até que todas as páginas com texto sejam indexadas; a Consulta só terá a fonte completa após a conclusão da fila. O consumo e os limites da API podem ser acompanhados no Google AI Studio. Para repetir uma medição sintética de uma ou cinco consultas simultâneas, consulte o [registro de capacidade](docs/operacao/TESTE_GEMINI_CAPACIDADE_2026-11-18.md).
