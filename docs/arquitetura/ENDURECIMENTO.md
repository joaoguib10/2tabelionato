# Endurecimento arquitetural

Este documento registra o recorte de segurança e operação aplicado após a
revisão do MVP. O objetivo é tornar o piloto local mais previsível sem alterar
as regras jurídicas de A1, A2, TAB ou a separação dos casos privados.

## Aplicado

- PostgreSQL com timeout de conexão, pool configurável e reciclagem de conexões.
- Endpoint `/ready` para distinguir processo ativo de banco disponível.
- Headers de segurança e `X-Request-ID` em respostas da API.
- Diagnóstico detalhado do banco restrito ao ADMIN.
- Ollama local obrigatório por padrão (`OLLAMA_LOCAL_ONLY=true`).
- Sessão da interface usando cookie `HttpOnly`, `SameSite=Lax` e renovação por
  atividade; Bearer continua aceito para compatibilidade e Swagger.
- Logout que invalida o cookie da interface.
- Operações administrativas de usuários isoladas em `UsuarioRepository` como
  primeiro limite entre rotas e persistência.

## Operação recomendada

- Em uma implantação HTTPS, definir `AUTH_COOKIE_SECURE=true`.
- Manter `OLLAMA_BASE_URL` em `localhost`, `127.0.0.1` ou `::1`.
- Ajustar `DATABASE_POOL_SIZE` e `DATABASE_MAX_OVERFLOW` somente após teste de
  carga; o padrão atende o piloto local.
- Usar `/health` para processo e `/ready` para dependência do PostgreSQL.
- Não executar múltiplos workers da API enquanto não houver coordenação
  persistente das tarefas de OCR, embeddings e Ata Notarial.

## Próximos recortes necessários

1. Extrair gradualmente os demais agregados para services/repositories, sem
   misturar regras jurídicas com acesso ao banco.
2. Criar uma tabela de jobs e um worker persistente para que OCR, embeddings e
   análises possam ser retomados após reinício.
3. Adicionar métricas e auditoria de alterações administrativas, sem registrar
   CPF, conteúdo documental ou credenciais.
4. Executar testes de integração com PostgreSQL/pgvector, Ollama real e carga
   concorrente antes de ampliar o número de usuários.
5. Adotar proteção CSRF caso a interface seja publicada fora do mesmo site; a
   configuração atual usa `SameSite=Lax` para o piloto local.
