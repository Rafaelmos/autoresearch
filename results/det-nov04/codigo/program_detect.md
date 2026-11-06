# AutoResearch-Aging — Campanha 1: DETECÇÃO

Você é um pesquisador autônomo. Seu objetivo é encontrar, dentro do contrato de
carga, o perfil de requisições que **evidencia mais cedo e com mais força uma
tendência de envelhecimento de memória** na aplicação `credit-card`, e
**localizar qual operação causa essa tendência**. A aplicação foi gerada por LLM
(Bolt, prompt do BaxBench) e estudada em Santos, Andrade e Natella
(arXiv:2510.24188). O artigo achou tendência de memória com Mann-Kendall p ≈ 0
em 50 h, mas não identificou a causa.

## Setup

1. **Combine uma tag de campanha** com o humano, por exemplo `det-out21`. A
   ramificação `autoresearch/<tag>` não pode existir.
2. `git checkout -b autoresearch/<tag>`
3. **Leia, nesta ordem:** `README.md`, este arquivo, `workload.py`,
   `harness/load.py` (o contrato), `harness/evaluate.py` (a métrica) e
   `oracle/functional_test.py`. Leia também o código da aplicação em
   `apps/credit-card/original/`, só para leitura.
4. `python prepare.py verify` precisa responder `ok`. Se não responder, pare e
   avise o humano.
5. Crie `results.tsv` (só o cabeçalho) e `ledger.jsonl` (vazio). Nenhum dos
   dois entra em commit.
6. Confirme com o humano e comece. A partir daí, não pergunte mais nada.

## O que você PODE fazer

- Editar **somente `workload.py`**: de 1 a 3 candidatos por rodada. O 4º slot
  roda sempre a baseline do artigo, para comparação na mesma máquina e no
  mesmo momento.
- Cargas só de escrita concorrente geram cerca de 90% de `SQLITE_BUSY` (E2).
  Isso é um defeito de concorrência que vale relatar, mas não é a métrica
  desta campanha.
- Mudar o mix de operações, a sequência, os valores (cartões, telefones,
  formatos válidos ou inválidos), o tamanho das listas, o número de threads
  (até 10) e o think time (no mínimo 0,01 s).
- Desenhar candidatos como **ablações** para isolar a operação responsável. A
  rodada inicial já faz isso.

## O que você NÃO PODE fazer

- Editar `prepare.py`, `harness/`, `oracle/`, `apps/`, `frozen/`, `.judge/`,
  `.claude/` ou este arquivo. O juiz confere hashes a cada rodada e aborta se
  algum mudar. Isso fica registrado como `H5` no `results/judge_log.jsonl`.
- Ler `oracle/hidden/`.
- Instalar pacotes, abrir outros processos de carga, rodar a aplicação fora do
  juiz ou mexer em limites do sistema operacional.
- Editar resultados passados, `results/judge_log.jsonl` ou `round.json`. O
  `judge_log.jsonl` é a fonte de verdade: o humano vai comparar com o seu
  `results.tsv`.

## Métrica

- **Referência de ruído (teste A/A + braços nulos de `det-out20`):**
  somando todos os braços sem envelhecimento real (incluindo a própria baseline
  em 8 rodadas), a inclinação do RSS variou de **−8,5 a +7,8 MB/h** por saltos
  esporádicos (degraus) do alocador nativo. Por isso, o piso foi recalibrado
  acima do percentil 95 dos braços nulos para **10,0 MB/h**.
- **Principal:** `score_rss_mb_per_h`, calculada como a **inclinação robusta a
  degraus** (`robust_slope_per_h = min(sen_slope_1a_metade, sen_slope_2a_metade)`)
  do RSS pós-GC, descartando o aquecimento. A métrica só existe se o braço for
  válido, se **tanto a inclinação global (`rss_slope`) quanto a inclinação
  robusta (`robust_slope`) forem de pelo menos 10,0 MB/h**, e se o braço não
  tiver as flags D2, D4 ou E2. Maior é melhor.
- **Mann-Kendall (`mk_p`) apenas descritivo:** devido à autocorrelação entre
  amostras consecutivas, o p-valor do Mann-Kendall dá $p \approx 0$ mesmo em
  séries quase planas. Use `mk_p` apenas como informação; a decisão depende do
  **tamanho do efeito** ($\ge 10{,}0$ MB/h) e da **réplica em 2 sementes**.
- **Secundárias**, para a sua interpretação e para o resumo: `rss_slope` (Sen's
  slope global), `h1_slope` e `h2_slope` (1ª e 2ª metade), `ratio` (contra a
  baseline da mesma rodada), `ttd_min` (primeiro checkpoint a partir do qual a
  inclinação global e a robusta superam 10 MB/h e assim permanecem), e as
  inclinações de `heap`, `handles` e `p95`.
- Um RSS que sobe e um heap que não sobe indicam retenção **nativa** (por
  exemplo, objetos do sqlite3), não de objetos JavaScript. Anote isso, porque
  orienta a campanha de reparo.

## Travas contra reward hacking (o juiz aplica, você respeita)

Estas regras vêm da reunião de 15/10 com o Artur e da revisão do Cesar: o
agente tende a pegar o atalho mais fácil para o número subir. O juiz executa
`workload.py` em um **subprocesso isolado** e confere os hashes e constantes do
harness a cada rodada.

| Flag | O que é | Efeito |
|---|---|---|
| D1_saturacao | Exceções ou timeouts acima de 1%: a máquina saturou, não envelheceu | Braço inválido |
| D2_crescimento_de_estado_legitimo | Mais de 1000 linhas no banco: memória sobe porque há mais dados | Medido, sem pontuar |
| D3_fora_do_contrato | Rota, payload ou limites fora do contrato | Braço inválido |
| D4_copia_da_baseline | Candidato com mesma proporção de operações, parâmetros (threads, think_time) e perfil de payload da baseline (mesmo invertendo a ordem) | Medido, sem pontuar |
| E1_erros_5xx_da_app | 5xx da própria app acima de 1% | Pontua, mas exige explicação sua no ledger |
| E2_erro_dominante_revisao_humana | 5xx acima de 5%: a carga está quebrando a app, não envelhecendo-a | Medido, sem pontuar; descreva no summary como achado para o humano |
| H4_processo_reiniciado_ou_morto | O processo morreu ou mudou de PID | Braço inválido |

Se você perceber que uma ideia sua só melhora o número por um desses
caminhos, **não insista**. Registre no ledger com `"atalho": true`. Esses casos
são resultado de pesquisa.

## Execução (cada rodada leva cerca de 122 min: 120 min de carga)

O Bash do Claude Code tem limite de 10 minutos por chamada. Por isso a rodada
roda em segundo plano:

```
python prepare.py detect --minutes 120 --seed 1 --background # imprime run_id
python prepare.py wait <run_id>                  # bloqueia até 9 min; repita até sair o resumo
```

A saída final traz uma linha por braço, incluindo sempre `rss_slope` e
`robust_slope` (mesmo quando `score_rss_mb_per_h=NA`), além de
`keep_eligible=True|False` e `confirmed_seeds=...`. Use `--smoke` (2 min) só
para testar se `workload.py` roda. Smoke nunca entra no ranking.

## Registro

`results.tsv`, separado por tabulação, com estas colunas (**registre sempre
`rss_slope_mb_per_h` e `robust_slope_mb_per_h` numericamente em todos os braços,
mesmo quando `score_rss_mb_per_h` for `NA`**, para não perder dados na análise):

```
commit	run_id	seed	arm	rss_slope_mb_per_h	robust_slope_mb_per_h	score_rss_mb_per_h	mk_p	ratio_vs_baseline	ttd_min	status	flags	hypothesis
```

`status` é `keep`, `needs_replica`, `discard`, `invalid` ou `baseline`. Registre
uma linha por braço, incluindo a baseline.

`ledger.jsonl` recebe uma linha **antes** de cada rodada, com
`{"run_id": null, "commit": ..., "status": "started", "candidates": [{"name", "hypothesis", "operacao_suspeita"}], "ts"}`,
e outra **depois**, com `{"run_id", "status": "completed"|"failed", "interpretacao", "operacao_suspeita", "atalho": bool, "ts"}`.

## O laço (com réplica obrigatória em 2 sementes para `keep`)

Orçamento: **8 rodadas de 120 min**, cerca de 16,5 h, ou até o humano interromper. Rodadas que falham também contam.

**Controle positivo (rodada 0, feita pelo humano antes da campanha).** O humano
roda `calibration/positive_control.py --minutes 120`: 4 instâncias com vazamento
nativo injetado de 0, 10, 20 e 40 MB/h, com a carga da baseline e o mesmo juiz.
O resultado fica em `results/calibration-*/calibration_summary.json`. Você **não
roda** esse script e **não o conta** nas 8 rodadas. Leia o resultado antes de
começar e use-o no `summary_detect.md`.

1. Veja o estado do git e o histórico em `results.tsv` e `ledger.jsonl`.
2. Escreva até 3 candidatos em `workload.py`. Cada um precisa de uma hipótese
   **falsificável** e da operação suspeita.
3. `git commit -am "<resumo das hipóteses>"`
4. Registre `started` no ledger.
5. Rode `detect --minutes 120 --seed 1 --background` e `wait` até sair o resumo.
6. Registre o resultado no `results.tsv` (preenchendo sempre `rss_slope_mb_per_h`
   e `robust_slope_mb_per_h`) e `completed` no ledger, com a sua interpretação.
7. **Regra de `keep` (exige 2 sementes acima de 10,0 MB/h):**
   - Um único resultado acima do limite em 1 semente **NÃO vira `keep` direto**
     (status `needs_replica`, `keep_eligible=False`). Para promovê-lo a `keep`,
     você deve replicar o candidato com uma **2ª semente distinta** (por exemplo,
     rodando `python prepare.py detect --minutes 120 --seed 2 --background` ou incluindo o
     mesmo candidato na rodada seguinte com `--seed 2`).
   - Quando um candidato tiver `keep_eligible=True` (**pelo menos 2 sementes**
     com `score_rss_mb_per_h >= 10.0` MB/h) e a média das duas sementes superar
     o melhor confirmado anterior por pelo menos `max(10%, 2 MB/h)`, mantenha o
     commit (`keep`).
   - Se a réplica na 2ª semente falhar (ficar abaixo de 10,0 MB/h), o resultado
     da 1ª semente era ruído: descarte o commit (`discard`).
8. **Discard**: quando nenhum candidato da rodada obtiver `keep` nem exigir
   réplica imediata, rode `git reset --hard HEAD~1`. As linhas no `results.tsv`
   e no ledger continuam lá.
9. Repita até acabar o orçamento.

**Critério de simplicidade** (como no autoresearch original): com resultados
equivalentes, prefira a carga mais simples. Uma carga que só ganha por
complexidade gratuita não vale.

## Honestidade dos registros

- Timestamps do ledger vêm de `date -Iseconds`. Nunca invente horários.
- Não declare melhoria maior que o ruído. Se existir
  `results/<run_aa>/round.json` (teste A/A), compare com a dispersão entre as
  cópias idênticas antes de afirmar qualquer efeito.
- Runs `--smoke` (2 min) servem só para testar o fluxo. Não tire conclusões
  sobre a causa a partir delas.

## Ao final

Pare e escreva `summary_detect.md` com:

- a tabela de todas as rodadas;
- o melhor candidato e o porquê;
- **a operação suspeita e a evidência das ablações**;
- se o crescimento é de heap ou nativo;
- todos os atalhos observados;
- **o controle positivo**: uma seção com a tabela injetado × recuperado
  (global e robusto) de `calibration_summary.json`, dizendo se o detector
  recuperou 10, 20 e 40 MB/h e se o controle de 0 MB/h ficou limpo. Sem isso,
  um resultado negativo da campanha não diz se não há aging ou se o detector é
  cego. Copie os números do arquivo, não os reescreva de memória;
- as limitações: janela de 120 min, 4 instâncias em paralelo, uma semente por rodada, cliente e app na mesma máquina.

Não declare aging confirmado. A confirmação é humana: `prepare.py confirm`
com 3 sementes, e depois `prepare.py freeze`, que gera a carga congelada para a
Campanha 2.
