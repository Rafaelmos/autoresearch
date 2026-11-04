# Relatório de Calibração de 120 min (controle positivo + A/A)

- **Data:** 01/11/2026, 11:12 a 15:13 (BRT)
- **Ambiente:** WSL2 Ubuntu 24.04 (12 vCPUs, 15,5 GB), Python 3.12.3, Node 22; clone `~/pesquisa/autoresearch-juiz-v2`, branch `autoresearch/det-luna-2h-1031` @ `b29e7f4` (juiz inalterado; `verify: ok 26 arquivos fixos`)
- **Testes escondidos:** `hidden_tests.py` enviado em 01/11. É byte a byte idêntico ao já instalado em `~/.aging-hidden` (SHA-256 `66c7c3e7…`). Só afeta os portões do reparo, que **não foram exercitados** aqui.
- **Não foi executado** `run_campaign.sh` (nenhum agente, nenhuma hipótese de carga, nenhum reparo).

| Rodada | run_id | Semente | Duração | Braços |
|---|---|---|---|---|
| Controle positivo | `control-1101-120` | 2 | 120 min + 5 de aquecimento | baseline + vazamento de 0; 2,5; 5; 10 MiB/h |
| Teste A/A | `aa-1101-120` | 102 | 120 min + 5 de aquecimento | 4 cópias idênticas da baseline |

Sementes diferentes das calibrações anteriores (1 e 100): esta é uma réplica independente.

## 1. Controle positivo

| Injetado (MiB/h) | Slope RSS | 1ª metade | 2ª metade | Menor metade | Heap | Detectado (juiz atual) | ttd (min) |
|---|---|---|---|---|---|---|---|
| 0 | −0,17 | 0,27 | −0,27 | −0,27 | 0,04 | não | — |
| 2,5 | 2,71 | 2,84 | 2,63 | 2,63 | 0,16 | não | 25 |
| 5 | 5,55 | 6,38 | 5,10 | 5,10 | 0,17 | **sim** | 10 |
| 10 | 10,03 | 9,61 | 10,32 | 9,61 | 0,18 | **sim** | 10 |

Unidades: MB/h. Nos 4 braços: `valid=True`, ~135 req/s, p95 mediano 74–75 ms, 1,6% de 5xx (`E1`).

- A injeção é fiel (slope ≈ taxa injetada, heap parado). Com 120 min o slope da janela deixa de superestimar a taxa (antes, em 60 min, errava até +3,7).
- **Piso de detecção em 120 min: cerca de 5 MiB/h.** Com 5 MiB/h a menor metade fica em 5,10, só 0,10 acima do limiar de 5. Detecção marginal, não folgada. 2,5 MiB/h continua indetectável.

## 2. Teste A/A

| Braço | Slope RSS | 1ª metade | 2ª metade | Menor metade | RSS início → fim (MB) | Heap | req/s | 5xx |
|---|---|---|---|---|---|---|---|---|
| baseline_artigo | −0,19 | 0,58 | 0,22 | 0,22 | 107,8 → 113,3 | 0,08 | 137,8 | 1,60% |
| aa_copia_1 | 3,09 | 5,39 | 1,08 | 1,08 | 108,9 → 114,2 | −0,51 | 138,1 | 1,59% |
| aa_copia_2 | 3,25 | 5,49 | 1,04 | 1,04 | 107,8 → 112,6 | 0,05 | 136,8 | 1,63% |
| aa_copia_3 | 2,84 | 5,77 | 0,47 | 0,47 | 108,8 → 113,8 | −0,50 | 136,9 | 1,62% |

Média do slope da janela: 2,25 (dp 1,69); máximo 3,25. Menor metade: máximo 1,08. Handles com slope 0, p95 sem tendência, sem processo filho. As três cópias receberam `D4_copia_da_baseline`, como esperado.

- **Nenhum falso positivo.** Máximo de 3,25 MB/h na janela, contra limiar de 5. Margem de 1,75 MB/h (em 60 min era de apenas 0,8).
- **Padrão de degrau:** 3 de 4 braços sobem ~5,5 MB/h na 1ª metade e ficam planos (0,5–1,1) na 2ª, enquanto a quarta (`baseline_artigo`) fica plana nas duas. Mesma carga, mesma semente: a diferença é do alocador/slot, não da app. O Mann-Kendall dá p≈0 mesmo nas cópias, ou seja, **MK não discrimina; só o tamanho do efeito e a menor metade discriminam**.
- Ruído com 120 min (máx. 3,25) ficou **menor** que o de 60 min no mesmo clone (máx. 4,17).

## 3. Envelheceu?

**Não.** Na janela de 120 min não há aging acima do piso de ~5 MiB/h:

| Sinal | Resultado (braços sem vazamento) | Aging? |
|---|---|---|
| RSS pós-GC | Degrau de ~5 MB no início, depois platô; menor metade ≤ 1,1 MB/h | Não |
| Heap V8 | −0,5 a +0,08 MB/h | Não |
| Memória externa | ≈ 0 | Não |
| Handles | slope 0 | Não |
| p95 / throughput | sem tendência | Não |
| 5xx | ~1,6% constante (`SQLITE_BUSY` sob concorrência) | Defeito funcional, não aging |

O artigo relata ~1,5 GB em 50 h (~30 MB/h); aqui a app fica 1–2 ordens de grandeza abaixo.

## 4. Passou de `program_detect` para `program_repair`?

**Não, e não deve passar.** `program_repair.md` exige alvo confirmado em 3 sementes (≥ 5 MB/h nas duas metades e ganho ≥ 25% sobre a baseline concorrente) com carga congelada. Não existe carga assim: esta calibração não testa cargas, e as campanhas anteriores (`det-out30`, réplicas Luna) também não produziram braço com nota. Os vazamentos do controle são sintéticos, sem defeito de código a corrigir. Pelo próprio `program_repair.md`, o resultado correto seria `summary_repair.md` registrando a fase como **bloqueada**.

## 5. Limitações

1. Uma réplica de cada rodada, uma semente por rodada, uma máquina.
2. A 5 MiB/h a detecção passa por 0,10 MB/h; o limiar está no limite do que o juiz resolve.
3. O degrau inicial de ~5 MB aparece em 3 de 4 slots e não em um: o juiz ainda não tem explicação para isso.
4. Cliente e app na mesma máquina; JMX do artigo (1 thread) × texto (10 threads) ainda em aberto.
5. Os portões de reparo (H1–H7) e o `hidden_tests.py` não foram exercitados.

## 6. Recomendações

1. **Adotar a menor metade (≥ 5 MB/h) como critério de nota**, já descrito em `program_detect.md`. Ela separa vazamento de ruído melhor que o slope da janela (A/A: 1,08 contra 3,25; controle 5 MiB/h: 5,10).
2. **Aceitar ~5 MiB/h como o piso de detecção e dizê-lo em todo relatório.** Para enxergar menos, é preciso janelas maiores (≥ 6 h) ou limiar menor com mais réplicas; hoje 2,5 MiB/h é invisível.
3. **Investigar o degrau inicial** (A/A: 3 de 4 braços). Hipótese: acomodação do alocador/SQLite. Testar com aquecimento de 10–15 min ou excluindo os primeiros 30 min do ajuste, e repetir o A/A com outra semente e horário.
4. **Não iniciar a campanha de reparo.** Se rodar nova campanha de detecção, que seja com cargas que ataquem a divergência do artigo (10 threads × 1 thread, tempo de execução maior, cliente em máquina separada), pois com a carga atual a app não envelhece de forma mensurável.
5. **Resolver a pendência do JMX com o Cesar** (qual configuração rodou nas 50 h): é a explicação mais barata para a diferença de 1–2 ordens de grandeza.
6. **Tratar o `SQLITE_BUSY` (~1,6% de 5xx) como achado separado** de concorrência, fora da métrica de aging.
7. **Revisar o `hidden_tests.py` com o Cesar antes da campanha real** (o próprio arquivo pede revisão humana) e trocar a versão antiga que continua no histórico do git (`31ac544`).
8. Rodar o smoke dos portões de reparo (patch com `Map` em memória deve cair em H2) para validar o `hidden_tests.py` quando houver tempo, já que esta calibração não o exercita.

## 7. Arquivos

```
results/calibracao-120min-2026-11-01/
├─ RELATORIO_CALIBRACAO_120MIN.md
├─ calibracao-120min.log        # saída dos comandos
├─ judge_log.jsonl              # registros do juiz das duas rodadas
├─ control-1101-120/            # round.json + leak_0|2.5|5|10/
└─ aa-1101-120/                 # round.json + baseline_artigo, aa_copia_1..3/
```
