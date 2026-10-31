# Relatório Técnico de Atualizações — AutoResearch-Aging (Piloto 3)

- **Data e Hora da Modificação do Modelo:** 30 de outubro de 2026 (`2026-10-30T20:45:04-03:00`, BRT)
- **Data e Hora da Atualização do Código:** 30 de outubro de 2026 (`2026-10-30T20:51:00-03:00` a `2026-10-30T21:21:00-03:00`, BRT)
- **Modelo Utilizado:** Gemini 4 Argon (Medium)
- **Repositório Atualizado:** `C:\Users\rafae\Documents\GitHub\autoresearch`
- **Referência da Revisão:** 9 pontos levantados por Cesar (Segurança do Juiz, Isolamento de Oráculos, Bugs de Permissão e Problemas de Método/Ruído)

---

## Sumário Executivo

Este relatório documenta a resolução completa dos **9 problemas técnicos e metodológicos** identificados por Cesar após a análise do código do Piloto 3 e dos resultados da campanha `det-out20` e do teste `A/A`. Todas as correções foram aplicadas diretamente nos arquivos do repositório principal (`prepare.py`, `harness/`, `.claude/`, `.gitignore`, `run_campaign.sh`, `program_detect.md`, `program_repair.md` e `README.md`).

| # | Categoria | Problema Levantado por Cesar | Solução Implementada | Arquivos Modificados |
|---|---|---|---|---|
| **1** | Segurança do Juiz | O agente pode mudar as regras da nota importando `harness.evaluate` dentro de `workload.py` | `workload.py` nunca mais é importado no processo do juiz (`prepare.py`); toda validação, geração de carga e replay rodam em subprocesso isolado (`python -m harness.load`), além de conferência em memória de `EXPECTED_CONSTANTS` antes e depois de cada rodada | `harness/load.py`, `harness/gates.py`, `prepare.py` |
| **2** | Segurança dos Oráculos | Os testes escondidos (`oracle/hidden/`) podem ser lidos via `grep`, `head`, `tail` ou `git show HEAD:...` | `oracle/hidden/` adicionado ao `.gitignore` e removido do índice do Git (`git rm --cached`); bloqueio explícito em `.claude/settings.{detect,repair}.json`; `chmod 700` automático em `setup` e `run_campaign.sh` + suporte a `AGENT_USER` e `AGING_HIDDEN_TESTS` | `.gitignore`, `.claude/settings.detect.json`, `.claude/settings.repair.json`, `harness/gates.py`, `prepare.py`, `run_campaign.sh`, `README.md` |
| **3** | Bug de Infraestrutura | O `chmod -R a-w` de `run_campaign.sh` em `apps/` faz `shutil.copytree` criar cópias sem escrita (`EACCES` no symlink e SQLite) | Criação de `copy_tree_writable` usando `shutil.copytree(..., copy_function=shutil.copyfile)` seguida de aplicação explícita de permissão de escrita do dono (`0o700` em diretórios e `0o600` em arquivos) em todas as cópias de instâncias e candidatos | `harness/instance.py`, `prepare.py` |
| **4** | Método (Ruído) | O limite de `5 MB/h` está dentro do ruído (`-8,5` a `+7,8 MB/h` nos braços nulos) | Limite recalibrado para `MIN_EFFECT_MB_PER_H = 10.0` MB/h (acima do P95 e máximo dos braços nulos) e introdução da **inclinação robusta a degraus** (`robust_slope_per_h = min(sen_slope_first_half_per_h, sen_slope_second_half_per_h)`) | `harness/stats.py`, `harness/evaluate.py`, `prepare.py`, `program_detect.md` |
| **5** | Método (Estatística) | O p-valor do Mann-Kendall não discrimina ($p \approx 0$ por autocorrelação) e distorce o `ttd_min` | `mk_p_upward` passa a ser puramente descritivo/informativo; elegibilidade e `time_to_detect` (`ttd_min`) decididos exclusivamente pelo tamanho do efeito global e robusto ($\ge 10{,}0$ MB/h) | `harness/evaluate.py`, `prepare.py`, `program_detect.md` |
| **6** | Método (Seleção) | A regra de `keep` não exige réplica (um resultado de sorte vira o "melhor anterior") | Exigência de **2 sementes distintas** (`MIN_KEEP_SEEDS = 2`) com `score_rss_mb_per_h >= 10.0` MB/h antes de habilitar `keep_eligible = True`; uma única semente recebe status `needs_replica` | `prepare.py`, `program_detect.md` |
| **7** | Anti-Reward Hacking | A checagem de cópia da baseline (`D4`) compara a sequência exata e é driblada invertendo leitura/escrita | Nova função `workload_signature` e `same_as_baseline` que comparam a **proporção de cada operação** ($\pm 5\%$), parâmetros (`threads`, `think_time_s`) e cardinalidade/tamanho de payloads, independentemente da ordem | `harness/load.py`, `prepare.py`, `program_detect.md` |
| **8** | Fase de Reparo | O reparo depende de um original que envelheça e não mede a `base` na rodada | `repair-init` e `repair` exigem confirmação prévia de 3 sementes (`aging_confirmed = True`) na detecção; `cmd_repair` passa a medir também `candidates/base` na mesma rodada e calcula `gain_vs_base` | `prepare.py`, `program_repair.md`, `README.md` |
| **9** | Registro de Dados | O `results.tsv` perde a inclinação (`NA`) quando o braço não pontua | `results.tsv`, `print_detect` e `judge_log.jsonl` passam a registrar sempre `rss_slope_mb_per_h` e `robust_slope_mb_per_h` numericamente em todos os braços, mesmo quando `score_rss_mb_per_h` é `NA` | `prepare.py`, `program_detect.md`, `program_repair.md` |

---

## Detalhamento das Soluções Implementadas

### 1. Isolamento do Processo do Juiz contra Adulteração das Regras da Nota
- **Problema:** `prepare.py` executava `load_module(ROOT / "workload.py", "workload")` dentro do próprio processo Python do juiz. Como `workload.py` é editado pelo agente e não faz parte do `.judge/manifest.json`, o agente poderia inserir `import harness.evaluate as e; e.MIN_EFFECT_MB_PER_H = 0` no topo de `workload.py`, zerando o limiar de pontuação em memória sem alterar nenhum arquivo fixo em disco.
- **Solução Implementada:**
  1. **Isolamento via Subprocesso (`python -m harness.load`):** `prepare.py` **nunca mais importa `workload.py` nem `frozen/workload_frozen.py`**. Toda interação com o código de carga ocorre em subprocessos separados que se comunicam exclusivamente via JSON validado:
     - `inspect_workload_subprocess()`: valida `CANDIDATES`, calcula a assinatura de cada candidato e devolve apenas metadados JSON (`name`, `hypothesis`, `threads`, `think_time_s`, `same_as_baseline`, `signature`).
     - `run_load_subprocess()`: executa o `LoadRun` de cada braço em um processo separado e grava o resumo das janelas (`load_summary.json`).
     - `build_trace_subprocess()`: gera a lista de requisições de replay para `harness/gates.py` em subprocesso separado.
  2. **Verificação Ativa de Constantes em Memória (`verify_constants()`):** `prepare.py` confere o dicionário `EXPECTED_CONSTANTS` antes e depois de `run_arms()`, abortando com a flag `H5_juiz_ou_oraculo_alterado` caso qualquer constante de `harness.evaluate` ou `harness.load` divirja do valor oficial.

---

### 2. Proteção Real dos Testes Escondidos (`oracle/hidden/`)
- **Problema:** As configurações do Claude Code negavam `Read(./oracle/hidden/**)`, mas permitiam `grep`, `head`, `tail`, `git diff` e `git log`. Como o setup fazia `git add -A`, `oracle/hidden/hidden_tests.py` entrava no histórico do Git e podia ser lido integralmente com `git show HEAD:oracle/hidden/hidden_tests.py`.
- **Solução Implementada:**
  1. `oracle/hidden/` foi adicionado ao `.gitignore` e removido do índice do Git (`git rm --cached oracle/hidden/hidden_tests.py`), mantendo o arquivo apenas no sistema de arquivos local.
  2. `.claude/settings.detect.json` e `.claude/settings.repair.json` receberam regras explícitas de bloqueio (`deny`) para `Bash(*oracle/hidden*)`, `Bash(*hidden_tests*)`, `Bash(git show:*)`, `Bash(git cat-file:*)`, `Bash(git grep:*)`, `Bash(grep:*oracle*)`, `Bash(head:*oracle*)`, `Bash(tail:*oracle*)`, `Bash(cat:*oracle/hidden*)` e `Bash(find:*oracle*)`.
  3. `cmd_setup` em `prepare.py` e `run_campaign.sh` aplicam `chmod 700` em `oracle/hidden` (e `0600` no arquivo), além de suportar `AGENT_USER` (para executar o agente sob outro usuário Linux via `sudo -u "$AGENT_USER"`) e a variável `AGING_HIDDEN_TESTS` em `harness/gates.py` para armazenar os testes escondidos fora da árvore do repositório.

---

### 3. Correção do Bug de Permissão (`chmod` / `EACCES`) na Cópia da Aplicação
- **Problema:** `run_campaign.sh` remove a permissão de escrita de `apps/` (`chmod -R a-w`). Como `shutil.copytree` usa `shutil.copy2` por padrão, as pastas copiadas para `workdir/app` herdavam os bits somente-leitura (`r-xr-xr-x`), impedindo a criação do symlink `node_modules` e do arquivo `uptime_db` do SQLite (causa do erro `Errno 13 / EACCES` na tentativa inicial da campanha `det-out20`).
- **Solução Implementada:**
  - Implementada a função `copy_tree_writable(src, dst, ignore=None)` em `harness/instance.py`, que utiliza `shutil.copytree(..., copy_function=shutil.copyfile)` (não copiando bits de bloqueio de modo) e aplica `_force_writable(dst)` (`0o700` para diretórios e `0o600` para arquivos).
  - Reutilizada em `copy_app()`, `cmd_setup()`, `cmd_repair_init()`, `cmd_promote()` e nos snapshots de `cmd_repair()`.

---

### 4. Recalibração do Limiar para `10,0 MB/h` e Métrica Robusta a Degraus
- **Problema:** Somando os 32 braços de `det-out20` e os 4 do teste `A/A`, braços que não deveriam crescer (incluindo a própria `baseline_artigo`, que atingiu `7,77 MB/h` na rodada 4) oscilaram entre `-8,5` e `+7,8 MB/h` devido a degraus de alocação nativa. O limiar de `5,0 MB/h` deixava passar ruído como se fosse achado.
- **Solução Implementada:**
  1. `MIN_EFFECT_MB_PER_H` foi elevado de `5.0` para **`10.0` MB/h** em `harness/evaluate.py` (acima do percentil 95 e do máximo observado em todos os braços nulos).
  2. Em `harness/stats.py` (`trend`), a série pós-aquecimento é dividida em duas metades temporais, calculando:
     - `sen_slope_first_half_per_h` (1ª metade, ~5 a 32,5 min);
     - `sen_slope_second_half_per_h` (2ª metade / últimos ~30 min);
     - `robust_slope_per_h = min(sen_slope_first_half_per_h, sen_slope_second_half_per_h)`.
  3. Para que um braço tenha `rss_upward_significant = True`, **tanto** `sen_slope_per_h` (global) **quanto** `robust_slope_per_h` devem ser $\ge 10{,}0$ MB/h, e a nota `score_rss_mb_per_h` passa a ser o `robust_slope_per_h`. Assim, degraus isolados do alocador em uma única metade da execução são neutralizados.

---

### 5. Desacoplamento do p-valor do Mann-Kendall da Decisão e do `ttd_min`
- **Problema:** Em séries temporais de ~660 amostras consecutivas de RSS, a forte autocorrelação faz o teste de Mann-Kendall resultar em $p \approx 0$ (ex.: $10^{-52}$ a $10^{-135}$) mesmo para variações residuais de `0,4 MB/h`. O cálculo de `time_to_detect` (`ttd_min`) herdava esse defeito.
- **Solução Implementada:**
  - `mk_p_upward` foi removido da condição booleana `rss_upward_significant` em `harness/evaluate.py`, permanecendo no JSON e nos logs apenas como estatística descritiva.
  - `time_to_detect(probe, warm, key="rss")` foi reescrito para identificar o primeiro checkpoint de 5 min a partir do qual **tanto** `sen_slope_per_h >= 10.0` **quanto** `robust_slope_per_h >= 10.0` e **assim permanecem** até o final da execução.

---

### 6. Exigência de Réplica em 2 Sementes para a Regra de `keep`
- **Problema:** Em `det-out20`, um único valor fortuito na rodada 3 (`retrieve_longo = 6,56 MB/h` na semente 1) virou o "melhor anterior" (`keep`), distorcendo toda a campanha subsequente mesmo após falhar na réplica (`0,50 MB/h`).
- **Solução Implementada:**
  - Definido `MIN_KEEP_SEEDS = 2` em `prepare.py`.
  - A função `_historical_confirmed_seeds()` cruza a assinatura canônica do candidato (`sig_hash`) e seu nome no `results/judge_log.jsonl` com a rodada atual e contabiliza em quantas **sementes distintas** (ex.: `--seed 1` e `--seed 2`) aquele candidato atingiu `score_rss_mb_per_h >= 10.0` MB/h.
  - Enquanto `len(confirmed_seeds) < 2`, o juiz marca `keep_eligible = False` (status `needs_replica`). Somente com $\ge 2$ sementes confirmadas o candidato recebe `keep_eligible = True` e `replicated_score_mb_per_h` (média das sementes confirmadas).

---

### 7. Detecção Robusta de Cópia da Baseline (`D4_copia_da_baseline`)
- **Problema:** `same_as_baseline` comparava `spec["request"](ra, i) != BASELINE["request"](rb, i)` índice por índice. Bastava trocar `i % 2 == 0` por `i % 2 == 1` (invertendo a ordem entre `/associate_card` e `/retrieve_cards`) para driblar a flag `D4`.
- **Solução Implementada:**
  - `workload_signature(spec)` e `same_as_baseline(spec)` em `harness/load.py` agora amostram 400 requisições por semente e comparam:
    1. `threads` e `think_time_s` ($\pm 0{,}002\text{ s}$);
    2. A **proporção de cada operação** (`op_ratios` para `/associate_card` e `/retrieve_cards` dentro de $\pm 5\%$ do mix 50/50 da baseline);
    3. A cardinalidade de cartões e telefones distintos ($\le 1$ cartão e $\le 1$ telefone) e o tamanho médio da requisição ($\pm 16$ bytes).
  - Inverter a ordem par/ímpar, embaralhar a sequência 50/50 ou trocar a literal do único cartão/telefone continua acionando `D4_copia_da_baseline`.

---

### 8. Pré-condição de Vazamento Confirmado para o Reparo e Medição da `base`
- **Problema:** `score_repair` exige que o `original` suba acima do limiar na mesma rodada (o que não ocorre sem uma carga que realmente envelheça a aplicação), e a regra de `keep` mandava comparar com a `base` sem que a `base` fosse medida na rodada.
- **Solução Implementada:**
  1. **Trava de Pré-condição:** `cmd_freeze` exige que o braço congelado tenha pontuação $\ge 10{,}0$ MB/h, e `cmd_confirm --phase detect` verifica se todas as 3 sementes (`11, 12, 13`) atingiram $\ge 10{,}0$ MB/h, gravando `FROZEN_CONFIRMED = True` em `frozen/workload_frozen.py` e `"aging_confirmed": true` no `judge_log.jsonl`. `cmd_repair_init` e `cmd_repair` abortam se a carga congelada não estiver confirmada (`require_confirmed=True`).
  2. **Medição da `base` na Rodada de Reparo:** Quando `candidates/base` difere de `original` (após um `promote`), `cmd_repair` inclui `base` como braço medido na rodada, calcula `base_reduction` na mesma janela temporal e reporta `gain_vs_base = score_reduction(vN) - score_reduction(base)` para cada candidato `v1..v3`.

---

### 9. Preservação Completa de `rss_slope` e `robust_slope` no `results.tsv` e `judge_log.jsonl`
- **Problema:** Quando um braço não pontuava (`score_rss_mb_per_h = NA`), o valor da inclinação de RSS era omitido no `results.tsv` e no resumo de `judge_log.jsonl`, prejudicando análises posteriores.
- **Solução Implementada:**
  - `prepare.py` (`cmd_detect`, `print_detect` e `log_judge`) e os guias `program_detect.md` e `program_repair.md` foram atualizados para registrar sempre `rss_slope_mb_per_h` e `robust_slope_mb_per_h` como colunas numéricas obrigatórias em todos os braços (inclusive `baseline`, `discard` e `E2`), reservando `NA` apenas para `score_rss_mb_per_h` quando o braço não é elegível.
