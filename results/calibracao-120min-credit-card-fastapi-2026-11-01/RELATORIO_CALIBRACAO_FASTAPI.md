# Relatório de Calibração de 120 min — credit-card-fastapi (nova app)

- **Data:** 01/11/2026 23:29 a 02/11/2026 03:30 (BRT)
- **App alvo:** `credit-card-fastapi` (BaxBench, FastAPI + SQLite), de `chas42/llm-aging-detection-agents`, `apps/credit-card-fastapi/original`. A app Node anterior foi descartada (movida para `~/pesquisa/_descartado/`).
- **Ambiente:** WSL2 Ubuntu 24.04 (12 vCPUs, 15,5 GB), Python 3.12.3, FastAPI 0.115.6, uvicorn 0.34.0 (um processo, log de acesso ligado como em `python app.py`)
- **Juiz:** branch `feat/credit-card-fastapi` @ `7c2efff` (clone WSL). Sonda Python (`harness/py_probe/sitecustomize.py`) no lugar da sonda Node. `verify: ok 16 arquivos fixos`.
- **Não executado:** campanha com agente, reparo.

| Rodada | run_id | Semente | Duração |
|---|---|---|---|
| Controle positivo | `control-fastapi-1101-120` | 1 | 120 min + 5 de aquecimento |
| Teste A/A | `aa-fastapi-1101-120` | 100 | 120 min + 5 de aquecimento |

## 1. O que mudou no juiz (e o que isso implica)

- **RSS** vem de `/proc/self/statm` logo após `gc.collect()`, a cada 5 s. O limiar de 5 MB/h e o restante do avaliador não mudaram.
- **"heap"** é uma **aproximação**: blocos vivos do pymalloc × 64 B. **"external"** é o **resíduo** `rss − heap` (alocador, sqlite3, libs nativas). Não são equivalentes ao heap e ao external do V8; servem para separar "objetos Python" de "resto".
- **Vazamento sintético:** `bytes` retidos em thread da sonda (valor não nulo, páginas tocadas).
- A app responde ~460 req/s (o Node respondia ~135), 404 para busca vazia (conta como 4xx, não 5xx) e 400 para entrada inválida.

## 2. Controle positivo

| Injetado (MiB/h) | Slope RSS | 1ª metade | 2ª metade | Menor metade | "External" | Heap | Detectado (limiar 5) |
|---|---|---|---|---|---|---|---|
| 0 | 0,13 | 0,06 | 0,12 | 0,06 | 0,11 | 0,02 | não |
| 2,5 | 2,62 | 2,56 | 2,59 | 2,56 | 2,56 | 0,06 | não |
| 5 | 5,10 | 5,06 | 5,09 | 5,06 | 5,03 | 0,06 | **sim** |
| 10 | 10,11 | 9,92 | 10,17 | 9,92 | 10,05 | 0,06 | **sim** |

Em todos: `valid=True`, ~460 req/s, p95 mediano 28,5 ms, 0,007% de 5xx, sem flags.

- A medida acompanha a taxa injetada com erro de **0,1 MB/h** (no Node era de 0,9 a 3,7 em 60 min e 0,5 a 0,8 em 120 min).
- O 5 MiB/h passou do limiar por **0,10 MB/h**: a detecção é "sim" só porque o limiar está colado em 5. Quem mede 2,5 MiB/h com precisão é o juiz; quem não o detecta é o limiar.

## 3. Teste A/A

| Braço | Slope RSS | 1ª metade | 2ª metade | Menor metade | RSS início → fim (MB) | Heap | req/s | 5xx |
|---|---|---|---|---|---|---|---|---|
| baseline_artigo | 0,14 | 0,11 | 0,13 | 0,11 | 58,9 → 59,4 | 0,015 | 471,6 | 0,009% |
| aa_copia_1 | 0,10 | 0,15 | 0,11 | 0,11 | 58,7 → 59,3 | 0,018 | 471,7 | 0,008% |
| aa_copia_2 | 0,13 | 0,19 | 0,05 | 0,05 | 58,8 → 59,4 | 0,021 | 471,6 | 0,008% |
| aa_copia_3 | 0,10 | 0,12 | 0,10 | 0,10 | 58,9 → 59,4 | 0,017 | 471,6 | 0,008% |

Média 0,12 MB/h, dp 0,02, máximo 0,14. Handles com slope 0, p95 com slope de +0,17 a +0,39 ms/h (<2% da latência), sem filhos. As 3 cópias recebem `D4_copia_da_baseline`, como esperado.

- **Ruído ~30 vezes menor que na app Node** (máx. 3,25 a 4,17 MB/h) e **sem o degrau inicial** de ~5 MB que aparecia na app Node. Esse degrau era, então, característica daquela app/runtime e não do juiz.
- Folga contra falso positivo: 4,86 MB/h até o limiar de 5.

## 4. Envelheceu?

**Não de forma relevante.** Na baseline do artigo, o RSS vai de 58,9 a 59,4 MB em 2 h: ~0,13 MB/h, com MK p≈0 (significativo, porque n é grande, mas tamanho de efeito mínimo). Extrapolando linearmente, são ~6,5 MB em 50 h, contra os ~1,5 GB que o artigo relata para a app equivalente em Node. Heap, handles, p95 e vazão: sem tendência relevante. Erros 5xx: praticamente zero (no Node eram 1,6% de `SQLITE_BUSY`; aqui o SQLite em WAL com `INSERT OR IGNORE` não gerou conflito).

**A baseline NÃO é o cenário que o achado F1 do repo descreve.** O card (`findings/bax-fastapi-credit-card-F1.yaml`) diz que o aging aparece com **pares (cartão, telefone) distintos** crescendo o banco e leituras sem `LIMIT`. A baseline do artigo usa sempre o mesmo par, então o banco fica com **1 linha** e o mecanismo nunca é acionado (mesma conclusão do repo para o Uptime: o JMX original não ativava o achado). Esse efeito é de **estado em disco/latência de `/retrieve_cards`**, não necessariamente de RSS.

## 5. Passou de `program_detect` para `program_repair`?

**Não.** Não há carga congelada que faça a app envelhecer, confirmada em 3 sementes. Além disso, a fase de reparo está **bloqueada por dois motivos técnicos**: (1) o `hidden_tests.py` falha 1 teste no original FastAPI (telefone `"12"` → 201, esperava 400), então precisa ser refeito para esta app; (2) os portões H1–H7 foram adaptados para Python mas **não foram testados**.

## 6. Limitações

1. Uma rodada de cada, uma semente cada, uma máquina; cliente e app na mesma máquina (o gerador Python compete por CPU com o servidor).
2. Heap e "external" do Python são aproximações, não métricas equivalentes às do V8.
3. Limiar de 5 MB/h e limites de carga (10 threads, 0,01 s, 2 KB, 10 telefones) continuam os do artigo/Node: não recalibrados para a nova app.
4. O contrato de carga de `load.py` cobre só `credit-card`; as outras apps do repo exigirão contratos próprios.
5. Os 120 min não exercitam o mecanismo F1 (crescimento do banco), por desenho da baseline.

## 7. Recomendações

1. **Baixar o limiar desta app para ~1 MB/h** (menor metade). O ruído máximo é 0,14 MB/h e o juiz mede 2,5 MiB/h com erro de 0,1; o limiar de 5 jogava fora essa sensibilidade. Fixar a decisão depois de uma segunda réplica A/A (outra semente/horário).
2. **Campanha de detecção com cargas que ativem F1:** pares distintos, telefones "quentes" com muitos cartões, retrieves sobre eles. É onde o repo prevê aging. Para isso, **relaxar D2 (>1000 linhas)** ou medir latência/tamanho de resposta como métrica primária, pois aqui o sintoma é crescimento de estado legítimo, que a regra atual marca como "não pontua".
3. **Adicionar métricas além de RSS** para esta app: p95 de `/retrieve_cards` por operação, tamanho do banco e tempo de resposta vs. número de linhas (o `db_bytes` já é coletado no `psutil.csv`).
4. **Refazer o `hidden_tests.py` para a app FastAPI** (e rever a pendência do 404 × 200 `[]`): sem isso o reparo continua bloqueado. Depois, testar os portões H1–H7 com patches sabotadores (Map em memória → H2).
5. **Registrar a diferença entre as duas apps** (Node: ruído alto, 135 req/s, `SQLITE_BUSY` 1,6%; FastAPI: ruído baixo, 460 req/s, sem erros) como achado; sugere que parte do que se via na app Node era efeito de concorrência/alocador, não aging.
6. **Próximas apps** (uptime-fastapi, image-converter-flask, monitor-flask): repetir o mesmo par de calibrações, cada uma com contrato de carga e oráculos próprios.
7. Se o artigo precisa de aging na baseline, investigar a configuração real dos 48 h (JMX com 1 thread × texto com 10 threads; máquinas separadas).

## 8. Arquivos

```
results/calibracao-120min-credit-card-fastapi-2026-11-01/
├─ RELATORIO_CALIBRACAO_FASTAPI.md
├─ calibracao.log
├─ judge_log.jsonl
├─ control-fastapi-1101-120/   # round.json + leak_0|2.5|5|10/
└─ aa-fastapi-1101-120/        # round.json + baseline_artigo, aa_copia_1..3/
```
