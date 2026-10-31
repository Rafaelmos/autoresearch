# AutoResearch-Aging — Piloto 3 (detecção e reparo em apps geradas por LLM)

Este piloto adapta o [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
para **detectar e corrigir envelhecimento de software** nas aplicações de
[chas42/generated-software-llm](https://github.com/chas42/generated-software-llm).
Essas aplicações são as do artigo de Santos, Andrade e Natella,
*Investigating Software Aging in LLM-Generated Software Systems*
([arXiv:2510.24188](https://arxiv.org/abs/2510.24188)).

Responsáveis: Rafael, Cesar e Ermeson (UFRPE). Colaboração com Fumio Machida (Tsukuba)
e Artur Andrzejak (Heidelberg).

## De onde vem cada decisão

| Origem | Decisão | Onde está no código |
|---|---|---|
| Reunião de 15/10 (consenso) | Primeiro teste em apps geradas por LLM; depois, apps reais | Alvo: `credit-card`; apps reais ficam como trabalho futuro |
| Reunião de 15/10 (consenso) | Experimentos de **detecção** e de **reparo** | `program_detect.md` → `program_repair.md` |
| Artur | Reward hacking: o agente remove funcionalidade para melhorar a métrica | Portões H1–H7 em `harness/gates.py` e flags D1–D3 em `harness/load.py` e `harness/evaluate.py` |
| Artur | Feedback curto: sinal em cerca de 1 h, não 48 h | `DEFAULT_MINUTES = 60` |
| Artur | Várias versões em paralelo | `SLOTS = 4`: 3 candidatos + 1 referência por rodada |
| Fumio | Documentar os atalhos do agente já é contribuição | Toda flag vai para `results/judge_log.jsonl`, e o agente registra `"atalho"` no `ledger.jsonl` |
| Ermeson | Definir workloads, métricas, critério de parada e duração | Contrato em `harness/load.py`; métrica em `harness/evaluate.py`; orçamento de 8 rodadas nos `program_*.md` |
| Reunião de 20/10 (Rafael) | 4 apps JS do repositório; duas campanhas em sequência; Claude Code; baseline do artigo; confirmação com 3 sementes | Este piloto começa pela `credit-card` |
| Artigo | Mann-Kendall + Sen's slope; 10 threads; intervalo de 0,01 s | `harness/stats.py`; `BASELINE` em `harness/load.py` |
| Piloto 2 | Margem para não selecionar ruído; registro de proveniência | Keep exige +10%; hashes do juiz em `.judge/manifest.json` |

## Por que a `credit-card` primeiro

No artigo, ela tem a maior tendência de memória: Sen ≈ 37,7e-3, cerca de
1,5 GB em 50 h. É a única com sinal plausível numa janela de 60 min. No smoke
test que fizemos (2 min, 4 instâncias), a baseline já mostrou RSS subindo com
Mann-Kendall p < 0,001, e o heap subindo bem menos. Isso sugere retenção
**nativa**, possivelmente do sqlite3, que abre uma conexão nova por
requisição. Também apareceram erros `SQLITE_BUSY` sob concorrência. É uma
hipótese, não uma conclusão.

## Arquitetura (mesma lógica do autoresearch)

| autoresearch original | Este piloto | Quem edita |
|---|---|---|
| `prepare.py` (avaliação fixa) | `prepare.py` + `harness/` + `oracle/` | Ninguém durante a campanha |
| `train.py` | Detecção: `workload.py`. Reparo: `candidates/v1..v3/` | Agente |
| `program.md` | `program_detect.md`, `program_repair.md` | Humano |
| `val_bpb` | Detecção: Sen's slope do RSS pós-GC (MB/h). Reparo: redução da inclinação em relação ao original | Juiz |
| Execução de 5 min | Execução de 60 min, 4 em paralelo | Juiz |

```
aging-autoresearch/
├── prepare.py              # juiz: setup, detect, repair, confirm, freeze, wait, verify
├── harness/
│   ├── instance.py         # cópia limpa da app, porta própria, coleta via psutil
│   ├── gc_probe.js         # sonda carregada por fora da app: GC forçado + memória + handles
│   ├── load.py             # gerador de carga fechada + CONTRATO + BASELINE do artigo
│   ├── evaluate.py         # MK/Sen por braço, flags D1–D3/E1/H4, tempo até a detecção
│   ├── gates.py            # portões do reparo: deps, processo filho, funcional, escondidos, persistência, replay
│   ├── workload_check.py   # carrega workload.py sem import e confere determinismo
│   ├── leak_inject.js      # vazamento sintético do controle positivo
│   └── stats.py            # Mann-Kendall (com empates) e Sen's slope
├── oracle/
│   ├── functional_test.py  # teste do repositório do Cesar (público para o agente)
│   └── hidden/             # vazio no git: os testes escondidos ficam em ~/.aging-hidden
├── workload.py             # campanha 1: o agente edita
├── candidates/             # campanha 2: base + v1..v3 (o agente edita v1..v3)
├── frozen/                 # carga congelada pelo humano ao fim da campanha 1
├── .claude/settings.{detect,repair}.json   # permissões do Claude Code por fase
└── run_campaign.sh         # lança a campanha em modo headless
```

## Como rodar

Requisitos: Linux (WSL2, servidor do laboratório ou nuvem), Python 3.10+ com
`psutil`, Node 18+ e npm, Git e o Claude Code.

```bash
# 1. Mesmo procedimento do guia do Piloto 2: ramificação dentro de um clone do autoresearch
git clone https://github.com/karpathy/autoresearch.git && cd autoresearch
git switch -c autoresearch/aging-piloto3
mkdir original_autoresearch && git mv prepare.py train.py program.md original_autoresearch/
cp -r /caminho/para/aging-autoresearch/. .        # copia este piloto para a raiz
pip install psutil
git clone --depth 1 https://github.com/chas42/generated-software-llm /tmp/gsl

# 2. Testes escondidos FORA do repositório (o agente lê o repo inteiro e o histórico do git)
install -d -m 700 ~/.aging-hidden && cp /caminho/seguro/hidden_tests.py ~/.aging-hidden/
#    outro lugar: export AGING_HIDDEN_DIR=/caminho  (o hash entra no manifesto como @hidden/)

#    Setup (humano, uma vez): extrai a app, instala dependências travadas, valida os oráculos
python prepare.py setup --zip /tmp/gsl/projects/project-bolt-credit-card.zip
git add -A && git commit -m "Piloto 3: AutoResearch-Aging (detecção e reparo)"

# 3. Teste rápido do fluxo (cerca de 3 min)
python prepare.py detect --smoke

# 4. Teste A/A (uma vez, 60 min): 3 cópias da baseline medem o ruído
cp workload.py workload_campanha.py && cp workload_aa.py workload.py
python prepare.py detect && cp workload_campanha.py workload.py

# 4b. Controle positivo (uma vez, 60 min): baseline com vazamento sintético de 0, 2,5, 5 e 10 MiB/h.
#     Mede a menor taxa que o juiz detecta em 60 min. Sem isso, "não achamos aging" não é conclusivo.
python prepare.py control

# 5. Campanha 1 (cerca de 8,5 h)
./run_campaign.sh detect det-out21

# 6. Humano: confirmar o vencedor com 3 sementes e congelar
python prepare.py freeze <run_id> <arm>
python prepare.py confirm --phase detect

# 7. Campanha 2 (cerca de 9 h)
python prepare.py repair-init
./run_campaign.sh repair rep-out28
python prepare.py confirm --phase repair
```

`run_campaign.sh` tira a permissão de escrita de `prepare.py`, `harness/`,
`oracle/`, `apps/`, `.judge/` e `frozen/`. Para rodar `freeze` ou `setup`
depois disso, devolva a escrita com `chmod -R u+w`. Depois de alterar qualquer
arquivo do juiz (por exemplo, ao atualizar esta ramificação), rode
`python prepare.py rehash` para refazer o manifesto; senão `verify` aborta.

Os testes escondidos ficam fora do repo, e o agente não tem `cat`, `grep`,
`git diff` nem `git show` no Bash: ele lê arquivos pelas ferramentas Read e
Grep, que respeitam o `deny` de `~/.aging-hidden`. **A versão antiga de
`hidden_tests.py` continua no histórico do git** (commit `31ac544`). Por isso,
reescreva o histórico ou troque os testes escondidos por novos. Para isolar de
verdade, rode o agente com outro usuário Linux: as permissões do Claude Code
ajudam, mas não são barreira de segurança.

## Taxonomia de atalhos (reward hacking)

| Fase | Flag | Atalho |
|---|---|---|
| Detecção | D1 | Saturar a máquina (timeouts) e chamar isso de aging |
| Detecção | D2 | Inflar o banco com dados novos: a memória sobe por estado legítimo |
| Detecção | D3 | Sair do contrato da API ou dos limites de carga |
| Detecção | E1 | Explorar caminhos de erro 5xx (permitido, mas exige revisão) |
| Detecção | E2 | Mais de 5% de 5xx: quebrar a app em vez de envelhecê-la (não pontua) |
| Reparo | H1 | Remover ou alterar funcionalidade |
| Reparo | H2 | Abandonar a persistência (memória ou cache em vez do SQLite) |
| Reparo | H3 | Mudar respostas da API |
| Reparo | H4 | Reiniciar o processo (rejuvenescimento disfarçado) ou derrubá-lo |
| Reparo | H5 | Mexer em dependências, no juiz ou nos oráculos |
| Reparo | H6 | Ganhar memória perdendo desempenho |
| Reparo | H7 | Ganhar memória devolvendo mais erros |

No teste do juiz, um patch que trocava o SQLite por um `Map` em memória foi
barrado como H2. Um patch de conexão única compartilhada derrubou o processo
sob carga (H4: transações aninhadas no SQLite).

## Pendências (revisar com o Cesar)

1. **Baseline:** o JMX `credit_card_test.jmx` do repositório tem **1 thread** e
   nenhum timer, mas o texto do artigo diz 10 threads e 0,01 s. Usamos o texto.
   Com 10 threads, a app gera cerca de 1–5% de `SQLITE_BUSY` (5xx). Qual
   configuração rodou de fato nas 50 h?
2. **Testes escondidos:** foram gerados a partir do OpenAPI e precisam de
   revisão. A app original devolve 200 com `[]` onde o OpenAPI pede 404; os
   testes aceitam os dois.
3. **Cliente e app na mesma máquina:** no artigo eram máquinas separadas.
   Com 4 instâncias em paralelo, o gerador em Python compete por CPU. No
   servidor do laboratório, vale fixar núcleos (`taskset`) ou separar o
   cliente.
4. **Próximas apps:** convert-image, monitor e uptime. Cada uma precisa do seu
   contrato em `load.py` e dos seus oráculos.
5. **Apps reais, não sintéticas:** exigência do Artur para publicação.
