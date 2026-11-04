# Summary — Campanha 1 (DETECÇÃO), tag `det-nov03`

Ramificação `autoresearch/det-nov03`. 8 rodadas (orçamento completo), 7 com semente 1 e a 8ª com semente 2. Nenhuma falhou.

## Resultado em uma linha

**Nenhum braço, em nenhuma rodada, atingiu 10,0 MB/h de inclinação robusta. Nenhum `score_rss_mb_per_h` foi atribuído, nenhum `keep`, e a operação responsável não foi localizada.** Isso não demonstra ausência de aging: significa que ele não apareceu nesta janela de 60 min.

## Tabela de rodadas (`rss` = Sen global, `rob` = robusta, MB/h; todos os `score` = NA)

| Rodada | run_id | Braço | rss | rob | flags | Obs. |
|---|---|---|---|---|---|---|
| 1 (s1) | detect-1103-1349-1ee6 | so_associate (1 thr) | 7,10 | 0,97 | – | degrau h1=22,2 |
| | | so_retrieve | 1,40 | 0,56 | – | |
| | | so_invalidas | 0,27 | −0,53 | D4 | |
| | | baseline | 0,37 | 1,01 | E1 | |
| 2 (s1) | detect-1103-1450-59ca | valores_diversos | 7,86 | 1,02 | E1 | |
| | | leitura_10_telefones | 7,24 | 0,42 | – | |
| | | escrita_4_threads | 9,09 | 1,07 | E1 | |
| | | baseline | 0,00 | 0,00 | **inválida** (D1, H4) | app caiu, ver abaixo |
| 3 (s1) | detect-1103-1551-9be4 | payload_grande_invalido | 0,14 | 0,14 | – | |
| | | serial_misto | 3,46 | 0,20 | – | |
| | | leitura_serial_larga | 1,41 | 0,54 | – | |
| | | baseline | 0,53 | −0,05 | E1 | |
| 4 (s1) | detect-1103-1652-1d7c | strings_distintas | 0,83 | 1,07 | E1 | |
| | | um_cartao_muitos_telefones | 0,45 | −1,15 | – | |
| | | resultado_grande | 0,52 | −0,11 | – | |
| | | baseline | 0,05 | −0,22 | E1 | |
| 5 (s1) | detect-1103-1753-954e | associate_10_threads | 1,72 | 1,14 | E1, **E2** (91% 5xx) | |
| | | erros_intercalados | 8,39 | −0,43 | – | |
| | | meia_concorrencia (6 thr) | 7,44 | −0,95 | E1 | |
| | | baseline | 8,12 | 0,17 | E1 | degrau h1=4,2 |
| 6 (s1) | detect-1103-1854-4ea7 | corpo_extra_grande | 2,40 | 2,41 | – | maior robusto da campanha |
| | | telefones_duplicados | 0,95 | −0,10 | – | |
| | | taxa_baixa (think 1 s) | 1,06 | 1,01 | E1 | |
| | | baseline | 0,95 | 0,09 | E1 | |
| 7 (s1) | detect-1103-1954-3d18 | escrita_serial_corpo_grande | **12,09** | 1,99 | – | global > 10, robusto não |
| | | leitura_corpo_grande_10t | 3,12 | 0,15 | – | |
| | | leitura_corpo_aleatorio_10t | 1,16 | 0,34 | – | |
| | | baseline | 4,34 | 0,39 | E1 | degrau h1=16,4 |
| 8 (**s2**) | detect-1103-2055-6417 | corpo_extra_grande (réplica) | 1,42 | −0,01 | – | não replicou |
| | | escrita_serial_corpo_grande (réplica) | 1,51 | −0,24 | – | não replicou |
| | | corpo_extra_2t | 1,09 | −0,05 | – | |
| | | baseline | −0,29 | −0,52 | E1 | |

Fonte de verdade: `results/judge_log.jsonl`. `results.tsv` e `ledger.jsonl` ficam sem commit, como pede o programa.

## Melhor candidato

Não há. Os dois mais próximos de algo foram descartados por evidência:
- `escrita_serial_corpo_grande` (rodada 7): Sen global 12,09 MB/h, **acima do piso**, mas robusto 1,99 (h1=6,96; h2=1,99) — um degrau, o falso positivo que a regra robusta existe para barrar. Na réplica (semente 2): global 1,51, robusto −0,24.
- `corpo_extra_grande` (rodada 6): robusto 2,41, estável entre metades, mas 4× abaixo do piso; na réplica, −0,01.

## Operação suspeita e evidência das ablações

**Nenhuma identificada.** Ablações por operação (rodadas 1–4): escrita só (1 thread), leitura só, validação sem banco, escrita serial, leitura larga, resultados grandes, JOIN pesado, strings distintas — todas com inclinação robusta entre −1,2 e +1,1 MB/h, indistinguíveis da baseline na mesma rodada (−0,5 a +1,0). O controle sem banco (`payload_grande_invalido`, 0,14) ficou plano como esperado, mas como os braços com banco também ficaram planos, a comparação não discrimina nada.

## Heap ou nativo?

Não dá para dizer. O `heap_slope` ficou em ≈0–0,3 MB/h em todos os braços, e o RSS global só subiu por degraus no início (h1 ≫ h2 em praticamente todos), típicos de alocador nativo. Mas como não há crescimento sustentado, não há retenção a classificar. O palpite do README (retenção nativa do sqlite3) **não foi testado com sucesso**: nada cresceu.

## Atalhos observados

Nenhum marcado como `"atalho": true`. Observações sobre as travas:
- **E2 reproduzido de propósito** (`associate_10_threads`): 91,2% de 5xx por `SQLITE_BUSY` com 10 threads só escrevendo. Mede e não pontua.
- **D4** disparou em `so_invalidas` (rodada 1), sem efeito prático, pois o score já era NA. A assinatura (cardinalidade 1 de cartão/telefone, tamanho de payload) bateu com a da baseline mesmo com mix de operações diferente.
- **E1** (1–2,6% de 5xx) aparece em todas as baselines de 10 threads, por `SQLITE_BUSY`.

## Achados para o humano

1. **Crash da app sob a carga da baseline (rodada 2).** O Node morreu com `SQLITE_BUSY: database is locked` emitido como evento `error` em `Statement#run` sem handler (`models/card.js:18`, `INSERT OR IGNORE INTO credit_cards`). Todas as requisições seguintes viraram exceção (100% de erro, braço inválido por D1/H4/`sem_amostras`). Aconteceu 1 vez em 8 baselines. É defeito de concorrência da app, não aging, e invalidou a baseline pareada daquela rodada.
2. **O juiz tem um bug no caminho `--smoke`.** `python prepare.py detect --smoke` termina em `ValueError: not enough values to unpack` em `prepare.py:368`: `_historical_confirmed_seeds` devolve `[]` (uma lista) quando `smoke=True`, mas o chamador espera a tupla `(sementes, mapa)`. Rodadas normais não são afetadas. Não editei `prepare.py` (proibido); corrigir para `return [], {}`.
3. **Ruído da baseline maior que o esperado.** O Sen global da baseline variou de −0,29 a +8,12 MB/h entre rodadas (e o h1 chegou a 16,4), sempre por degraus. Só a regra robusta evitou falsos positivos perto do piso (`escrita_serial_corpo_grande` com 12,09 global).

## Limitações

- **Janela de 60 min** (50 h no artigo): se o aging for lento ou só aparecer com acúmulo prolongado, esta janela não o vê. A baseline do artigo (~30 MB/h implícitos em 1,5 GB/50 h) não se reproduziu aqui nem na baseline.
- **Uma semente por candidato**, exceto a réplica da rodada 8 (semente 2, só para 2 braços).
- **Cliente e app na mesma máquina**, 4 instâncias em paralelo, competindo por CPU.
- **Horários:** `date -Iseconds` foi negado pelo ambiente, então todos os `ts` do ledger são `null` (registrado em `ts_nota`). Não inventei horários; as horas aproximadas estão nos `run_id`.
- Todos os candidatos usam valores fixos ou de espaço pequeno por causa do limite de 1000 linhas (D2). Estado grande no banco ficou fora do que foi testado.

## O que sugiro ao humano

Não rodar `confirm`/`freeze`: não há vencedor. Antes de uma segunda campanha, vale (a) decidir se o aging do artigo exige janelas maiores que 60 min, (b) conferir o JMX (1 thread vs. 10, pendência 1 do README), pois com 10 threads a app cai por BUSY, e (c) corrigir o bug do `--smoke`.
