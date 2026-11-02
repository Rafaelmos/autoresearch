# Triagem - orquestrador (prepare.py + harness/)

Escopo: apenas prepare.py e harness/ (juiz/orquestrador, processo de vida curta). Nao ha reviews de IA. Todos os itens sao hipoteses para validacao em tempo de execucao, nao aging confirmado. Linhas verificadas no codigo real do repositorio.

## 1. Todos os candidatos

| id | fontes | veredito | motivo |
|---|---|---|---|
| orq-F1 | extra: harness/load.py:89,129 | conditional | listas de latencia por balde sem limite, so crescem ate summary(); relevante em janelas longas (48 h) |
| orq-F2 | semgrep-aging:aging-py-tempfile-without-cleanup (gates.py:158); extra: prepare.py:129,135,146,363 | conditional | tmp e results/ nunca removidos; acumulo apenas entre campanhas repetidas |
| orq-F3 | extra: instance.py:143-152 | conditional | stop() mata so o PID principal; orfaos so em queda do juiz ou app com filhos |
| orq-N1 | semgrep-aging:aging-js-interval-without-clear (gc_probe.js:27) | non-aging | um unico setInterval por processo, .unref(), vive e morre com o node; probe.jsonl cresce so durante a execucao |
| orq-N2 | semgrep-aging:aging-js-interval-without-clear (leak_inject.js:13) | non-aging | vazamento sintetico intencional (controle positivo, taxa conhecida); e o instrumento, nao defeito |
| orq-N3 | semgrep-aging:aging-py-open-without-close (instance.py:91) | non-aging | `log` e variavel local; em CPython e fechado na saida de start(); 1 fd por instancia, transitorio (o filho tem sua propria copia) |
| orq-N4 | semgrep-aging:aging-py-executor-per-call (instance.py:114) | non-aging | uma thread sampler daemon por instancia, termina com _stop e e joined em stop() |
| orq-N5 | semgrep-aging:aging-py-select-without-limit (instance.py:167-169) | non-aging | JOIN sem LIMIT executado uma vez ao fim do braco (db_state), custo transitorio, sem repeticao por requisicao |
| orq-N6 | semgrep-aging:aging-py-executor-per-call (load.py:136) | non-aging | 10 threads por LoadRun, criadas uma vez e joined; nao e por requisicao |
| orq-N7 | semgrep-aging:aging-py-subprocess-without-timeout (prepare.py:118-119) | non-aging | git rev-parse local, chamado poucas vezes por execucao, com except Exception; sem acumulo |
| orq-N8 | semgrep-aging:aging-py-subprocess-without-timeout (prepare.py:140) | non-aging | npm install no setup, one-off humano; sem timeout e risco de travar, mas nao acumula |
| orq-N9 | semgrep-aging:aging-py-executor-per-call (prepare.py:215) | non-aging | uma thread por braco em run_arms, todas joined (sem timeout, mas sem acumulo) |
| orq-N10 | extra: app.log sem limite (instance.py:63,91) | non-aging | cresce so enquanto a instancia roda e e determinado pelo log do app; limitado pela duracao da execucao. O acumulo entre execucoes esta coberto por orq-F2 |
| orq-N11 | extra: --background sem lock (prepare.py:230-236) | non-aging | run_id unico (uuid); execucoes concorrentes competem por CPU de forma constante e confundem a medicao, mas nao acumulam estado; sem lock apenas se --run-id for repetido |

Rejeitados por codigo inexistente: nenhum (todas as linhas citadas conferem). Nenhum item unsupported.

## 2. Contribuicao de fontes (por cartao)

| cartao | reviews de IA | ferramentas | extras do solicitante |
|---|---|---|---|
| orq-F1 | nenhuma | nenhuma | sim |
| orq-F2 | nenhuma | aging-py-tempfile-without-cleanup | sim (mkdtemp prepare.py) |
| orq-F3 | nenhuma | nenhuma | sim |

## 3. Divergencias

- IA x ferramentas: nao se aplica (sem reviews). As 10 regras da ferramenta foram, em sua maioria, falsos positivos para um processo de vida curta (regras assumem codigo por requisicao); apenas o tempfile (gates.py:158) sustenta um acumulo.
- Ferramenta x codigo: aging-py-open-without-close (instance.py:91) descreve vazamento ate o GC, mas o objeto e liberado por refcount ao sair de start().
- Extras que a regra nao pegou e viraram cartoes: latencias sem limite (F1) e Instance.stop (F3). mkdtemp de prepare.py foi fundido a F2 (mesmo recurso: disco temporario, mesma validacao).
- Nao foi inspecionado o codigo do app (fora das entradas); F3 depende de o app criar processos filhos.
