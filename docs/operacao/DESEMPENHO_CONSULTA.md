# Desempenho da Consulta local

## Diagnóstico atual

A Consulta usa dois modelos locais: um para embeddings e outro para geração. Se o Ollama mantiver somente um modelo residente, cada pergunta pode provocar a troca dos modelos e acrescentar dezenas de segundos ao tempo total.

O backend mantém os modelos solicitados por 30 minutos e conserva, somente em memória, até 256 vetores de perguntas repetidas. A chave do cache é um hash; o texto da pergunta não é armazenado nesse cache. O cache desaparece ao reiniciar a API.

O código agora registra tempos de cada etapa sem registrar pergunta, documento ou
conteúdo: artigos e corpus, embedding, consulta vetorial, consulta textual, número
de candidatos/fontes, e, na geração Ollama, carregamento do modelo, prefill do
prompt, decodificação dos tokens e duração total. Para encontrar o gargalo de uma
consulta específica, compare os registros `RAG busca concluída`, `Geração Ollama
concluída` e `Consulta concluída` no terminal do backend. Não use o conteúdo dos
prompts como telemetria.

Na inspeção de 01/10/2026, `ollama ps` não mostrava modelo residente naquele
instante. Isso não prova que todas as consultas façam cold start, mas indica que a
primeira após período ocioso pode pagar o carregamento; o padrão solicitado pela
aplicação é `OLLAMA_KEEP_ALIVE=30m`. A latência deve ser separada em carga, prefill
e geração antes de decidir se o ajuste correto é retenção do modelo, contexto,
recuperação ou hardware.

## Configuração inicial da VM

Configure o serviço do Ollama para manter dois modelos carregados:

```powershell
setx OLLAMA_MAX_LOADED_MODELS 2
setx OLLAMA_NUM_PARALLEL 1
setx OLLAMA_NO_CLOUD true
setx OLLAMA_NOHISTORY true
```

Feche e reinicie completamente o Ollama depois de alterar essas variáveis. Em seguida, confirme durante uma consulta:

```powershell
ollama ps
```

O objetivo é manter simultaneamente o modelo de embeddings na CPU e o modelo de Consulta prioritariamente na GPU. Na máquina de desenvolvimento, `OLLAMA_EMBED_NUM_GPU=0` permitiu manter os dois residentes. A memória de 24 GB é adequada como ponto de partida, mas o tempo de geração dependerá principalmente da GPU, da VRAM e da quantidade de camadas descarregadas para CPU.

`OLLAMA_NO_CLOUD=true` desativa os recursos de nuvem do Ollama e `OLLAMA_NOHISTORY=true` desativa seu histórico local de prompts. O serviço deve permanecer vinculado a `127.0.0.1`; não o exponha diretamente na rede. O frontend e o backend podem ser publicados na rede local, mas o acesso ao Ollama deve continuar intermediado pelo backend e protegido pelas permissões da aplicação.

Não aumente `OLLAMA_NUM_PARALLEL` sem teste de carga. Comece com 1, simule 5–10 usuários e acompanhe RAM, VRAM, fila e tempo de resposta. O valor 2 consumiu memória demais na máquina de desenvolvimento de 16 GB.

## Variáveis da aplicação

- `OLLAMA_KEEP_ALIVE`: permanência solicitada ao Ollama; padrão `30m`.
- `OLLAMA_EMBED_NUM_GPU`: mantém embeddings na CPU; padrão `0`.
- `OLLAMA_CONSULTA_MAX_TOKENS`: limite de saída; padrão atual `350`.
- `OLLAMA_CONSULTA_MODEL`: modelo específico da Consulta; candidato atual `qwen3:4b-instruct`, separado do `OLLAMA_GENERATION_MODEL` (`qwen3:8b`) usado nas análises profundas e no chat dos casos.
- `OLLAMA_CONSULTA_CONTEXT_TOKENS`: contexto máximo da Consulta; no piloto está em `3072`.
- `RAG_QUERY_EMBEDDING_CACHE_SIZE`: quantidade de vetores mantidos em memória; padrão `256`.

O `qwen3:4b-instruct` foi mantido como melhor compromisso de latência entre as opções efetivamente testadas no fluxo local. A comparação adicional de 01/10/2026 com `qwen3.5:4b` encontrou resposta igualmente aproveitável para uma pergunta objetiva sobre o art. 1.277, mas maior latência: `qwen3:4b-instruct` levou 16,1 s na chamada fria após troca de modelo e 10,2 s aquecido; `qwen3.5:4b` levou 50,8 s frio e 11,3 s aquecido. Ambos passaram a validação de citação nessa pergunta. Em uma pergunta ampla, ambos foram recusados por falta de respaldo verificável; a tentativa com Qwen 3.5 somou cerca de 15,9 s, dos quais 4,82 s foram recuperação. Assim, o modelo mais novo não foi promovido: falha o alvo de até 30 s em cold start e não demonstrou ganho suficiente para compensar. Esta é uma comparação local pequena, não uma prova de qualidade jurídica. Revalidar na VM e com casos revisados por humanos.

### Leitura do gargalo e próximos ajustes

- O gargalo estrutural tende a ser a geração local, não a busca, quando os logs
  mostrarem `geração` muito maior que `recuperação`. O endpoint espera a resposta
  completa porque as citações são verificadas antes de serem apresentadas.
- A busca vetorial foi alinhada ao operador que permite ao PostgreSQL considerar o
  índice HNSW: ordenação por distância cosseno crescente; o valor de similaridade
  continua sendo usado no reranking híbrido. Confirmar com
  `EXPLAIN (ANALYZE, BUFFERS)` que o plano realmente usa o índice. Como HNSW é uma
  busca aproximada, os candidatos podem diferir de uma ordenação exata; comparar
  recall e citações nos casos jurídicos avaliados antes de tratar o ganho como
  aceito. A busca textual já possui índice GIN.
- O modelo dedicado `qwen3:4b-instruct`, limite de saída de 350 tokens e cache de
  embeddings são as otimizações aplicadas à Consulta. Diminuir mais `num_predict` reduz tempo, mas pode
  truncar fundamentação e ressalvas; diminuir contexto pode retirar exceções ou
  fontes relevantes. Não reduzir esses limites sem comparação jurídica.
- Manter o modelo aquecido pode reduzir somente a parcela `carga`; prolongar
  `OLLAMA_KEEP_ALIVE` aumenta uso persistente de RAM/VRAM. Como a GPU de
  desenvolvimento é uma RTX 3050 Ti de notebook, não fixar todos os modelos na
  GPU sem observar VRAM e offload. O modelo de embeddings está configurado para
  CPU como forma de reduzir disputa com o gerador.
- Com `OLLAMA_NUM_PARALLEL=1`, chamadas simultâneas aguardam em fila. Isso protege
  memória, mas pode elevar o tempo percebido por 5–10 pessoas; mais paralelismo
  só deve ser escolhido após carga real na VM e medida de RAM/VRAM.
- As medições de 10,2 s aquecido e 16,1 s após troca de modelo foram uma consulta
  sintética objetiva; não são garantia para toda consulta nem para a VM. Perguntas amplas podem levar
  mais tempo na recuperação ou ser recusadas quando as fontes não sustentam a
  resposta. A validação atual de citações é heurística lexical, não prova de
  implicação semântica; casos jurídicos continuam exigindo revisão humana.

## Configuração validada na máquina de desenvolvimento

Em 09/09/2026, o Ollama foi reiniciado e confirmou:

- escuta somente em `127.0.0.1:11434`;
- até dois modelos carregados;
- uma requisição em paralelo;
- nuvem desativada;
- histórico de prompts desativado.

A configuração foi persistida no ambiente do usuário do Windows. Uma nova conta de serviço ou uma nova VM precisará receber as mesmas variáveis e reiniciar o Ollama.
