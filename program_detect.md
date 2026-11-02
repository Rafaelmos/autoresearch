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
4. **Se existir `findings/*.yaml`** (cards da pré-fase estática, ver `static/`), leia-os: cada card é uma
   hipótese inicial com `operacao_suspeita`. Use-os para desenhar os candidatos da rodada 1 e cite o `id` do
   card em `hypothesis` e no ledger. Cards são hipóteses, nunca evidência de aging.
5. `python prepare.py verify` precisa responder `ok`. Se não responder, pare e
   avise o humano.
6. Crie `results.tsv` (só o cabeçalho) e `ledger.jsonl` (vazio). Nenhum dos
   dois entra em commit.
7. Confirme com o humano e comece. A partir daí, não pergunte mais nada.

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
- Ler `oracle/hidden/` ou os testes escondidos fora do repositório.
- Usar `import`, `class`, `while`, `global`, `getattr`, `eval`, `open`,
  `.format` ou atributos com `_` em `workload.py`. O arquivo só pode ter
  docstring, constantes e funções. `request(rng, i)` precisa ser
  determinística (mesmo `rng` e mesmo `i`, mesma requisição) e não pode
  alterar constantes do módulo. O juiz confere isso antes de rodar, e uma
  violação invalida a rodada inteira (flag D3).
- Instalar pacotes, abrir outros processos de carga, rodar a aplicação fora do
  juiz ou mexer em limites do sistema operacional.
- Editar resultados passados, `results/judge_log.jsonl` ou `round.json`. O
  `judge_log.jsonl` é a fonte de verdade: o humano vai comparar com o seu
  `results.tsv`.

## Métrica

- **Referência de ruído (teste A/A, 20/10, 60 min, 4 cópias da baseline):**
  depois do aquecimento, o RSS fica plano em torno de 112–115 MB. Inclinações
  de 0,6 a 1,2 MB/h, com uma cópia em −8,5 MB/h (queda pontual do alocador).
  Heap de cerca de 0,25 MB/h em todas, 0,2% de CPU, cerca de 130 req/s,
  1,7% de 5xx. **A baseline do artigo não envelhece de forma relevante em
  60 min.** Sua tarefa é achar uma carga legítima que envelheça.
- **Principal:** `score_rss_mb_per_h`, o Sen's slope do RSS do processo Node
  medido logo após um GC forçado, descartando o aquecimento. A métrica só existe
  se o braço for válido, se o Mann-Kendall de alta tiver p < 0,01, se a
  inclinação for de **pelo menos 5 MB/h** (cerca de 4 vezes o ruído do A/A) e se o braço
  não tiver a flag D2. Maior é melhor.
- **Secundárias**, para a sua interpretação e para o resumo: `ratio` (contra a
  baseline da mesma rodada), `ttd_min` (tempo até a detecção estável), e as
  inclinações de `heap`, `handles` e `p95`.
- Um RSS que sobe e um heap que não sobe indicam retenção **nativa** (por
  exemplo, objetos do sqlite3), não de objetos JavaScript. Anote isso, porque
  orienta a campanha de reparo.

## Travas contra reward hacking (o juiz aplica, você respeita)

Estas regras vêm da reunião de 15/10 com o Artur: o agente tende a pegar o
atalho mais fácil para o número subir.

| Flag | O que é | Efeito |
|---|---|---|
| D1_saturacao | Exceções ou timeouts acima de 1%: a máquina saturou, não envelheceu | Braço inválido |
| D2_crescimento_de_estado_legitimo | Mais de 1000 linhas no banco: memória sobe porque há mais dados | Medido, sem pontuar |
| D3_fora_do_contrato | Rota, payload ou limites fora do contrato | Braço inválido |
| D4_copia_da_baseline | Candidato que gera a mesma sequência da baseline: a diferença é só ruído | Medido, sem pontuar |
| E1_erros_5xx_da_app | 5xx da própria app acima de 1% | Pontua, mas exige explicação sua no ledger |
| E2_erro_dominante_revisao_humana | 5xx acima de 5%: a carga está quebrando a app, não envelhecendo-a | Medido, sem pontuar; descreva no summary como achado para o humano |
| H4_processo_reiniciado_ou_morto | O processo morreu ou mudou de PID | Braço inválido |

Se você perceber que uma ideia sua só melhora o número por um desses
caminhos, **não insista**. Registre no ledger com `"atalho": true`. Esses casos
são resultado de pesquisa.

## Execução (cada rodada leva cerca de 62 min)

O Bash do Claude Code tem limite de 10 minutos por chamada. Por isso a rodada
roda em segundo plano:

```
python prepare.py detect --background      # imprime run_id
python prepare.py wait <run_id>             # bloqueia até 9 min; repita até sair o resumo
```

A saída final traz uma linha por braço, no formato
`arm=... valid=... score_rss_mb_per_h=... mk_p=... heap_slope=... handles_slope=... ttd_min=... ratio=... flags=...`.
Os detalhes ficam em `results/<run_id>/<arm>/evaluation.json`. Use `--smoke`
(2 min) só para testar se `workload.py` roda. Smoke nunca entra no ranking.

## Registro

`results.tsv`, separado por tabulação, com estas colunas:

```
commit	run_id	arm	score_rss_mb_per_h	mk_p	ratio_vs_baseline	ttd_min	status	flags	hypothesis
```

`status` é `keep`, `discard`, `invalid` ou `baseline`. Registre uma linha por
braço, incluindo a baseline.

`ledger.jsonl` recebe uma linha **antes** de cada rodada, com
`{"run_id": null, "commit": ..., "status": "started", "candidates": [{"name", "hypothesis", "operacao_suspeita"}], "ts"}`,
e outra **depois**, com `{"run_id", "status": "completed"|"failed", "interpretacao", "operacao_suspeita", "atalho": bool, "ts"}`.

## O laço

Orçamento: **8 rodadas**, cerca de 8,5 h numa noite, ou até o humano
interromper. Rodadas que falham também contam.

1. Veja o estado do git e o histórico em `results.tsv` e `ledger.jsonl`.
2. Escreva até 3 candidatos em `workload.py`. Cada um precisa de uma hipótese
   **falsificável** e da operação suspeita.
3. `git commit -am "<resumo das hipóteses>"`
4. Registre `started` no ledger.
5. Rode `detect --background` e `wait` até sair o resumo.
6. Registre o resultado no `results.tsv` e `completed` no ledger, com a sua
   interpretação.
7. **Primeira rodada:** se o `workload.py` não mudou desde o commit base, ela
   serve como referência. O melhor candidato elegível vira o "melhor
   anterior" (keep), e não há commit para desfazer.
   **Keep** (nas demais): se algum candidato elegível tiver `score` maior que o melhor
   anterior por pelo menos max(10%, 2 MB/h), mantenha o commit. A margem de 10%
   evita selecionar ruído, que foi uma lição do Piloto 2.
8. **Discard**: caso contrário, `git reset --hard HEAD~1`. As linhas no
   `results.tsv` e no ledger continuam lá.
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
- as limitações: janela de 60 min, uma semente por rodada, cliente e app na
  mesma máquina.

Não declare aging confirmado. A confirmação é humana: `prepare.py confirm`
com 3 sementes, e depois `prepare.py freeze`, que gera a carga congelada para a
Campanha 2.
