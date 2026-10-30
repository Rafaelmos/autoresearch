# Campanha 1 (detecção): resumo, tag det-out20

Ramificação `autoresearch/det-out20`, `credit-card`, 8 rodadas reais de 60 min (20/10/2026, de 13:49 a cerca de 21:55). Fonte de verdade: `results/judge_log.jsonl`. Houve também uma tentativa anterior (`detect-1020-1344-1613`) que falhou antes de qualquer carga por permissão de escrita (Errno 13 no symlink de `node_modules`); foi corrigida com `chmod -R u+w apps results` e não conta como rodada.

## Conclusão

**Não encontrei carga que envelheça a memória de forma reproduzível em 60 min, e não há operação suspeita sustentada.** Cinco braços candidatos (e uma baseline) passaram do piso de 5 MB/h, mas nenhum se repetiu quando foi replicado. Não declaro aging confirmado nem causa.

## Tabela das rodadas

RSS = Sen's slope do RSS pós-GC (MB/h); `*` = passou do piso de 5 MB/h. A baseline não é pontuada (`score = NA`); mostro o RSS dela como referência da rodada.

| # | run_id | Braços (RSS MB/h) | Baseline | Resultado |
|---|---|---|---|---|
| 1 | detect-1020-1349-7f38 | so_associate 0,64 (91% de 5xx, E2) · so_retrieve 0,61 · so_invalidas 0,48 | 1,34 | nenhum elegível |
| 2 | detect-1020-1451-ca03 | mix_variado 0,56 · retrieve_10 1,16 · leitura_pesada 0,44 | 0,53 | nenhum elegível |
| 3 | detect-1020-1551-7e50 | mix_longo 0,12 · **retrieve_longo 6,56\*** · tipo_invalido 0,44 (100% 5xx, E2) | 0,41 | keep (retrieve_longo) |
| 4 | detect-1020-1652-5a60 | retrieve_meio 1,77 · retrieve_max 1,15 · retrieve_1_longo 0,81 | **7,77** | nenhum elegível |
| 5 | detect-1020-1753-0e0e | retrieve_longo_replica 0,50 · **mix_1_thread 6,13\*** · mix_3_threads 3,12 | 1,37 | discard (6,13 < 6,56 × 1,1) |
| 6 | detect-1020-1854-1de0 | mix_1_thread_replica 1,19 · associate_1_thread 0,53 · retrieve_1_thread 0,82 | 0,49 | nenhum elegível |
| 7 | detect-1020-1954-b1b1 | densa_1_thread **5,93\*** · densa_10_threads **8,29\*** · leitura_densa **8,46\*** | −0,33 | discard (8,46 < 6,56 + 2) |
| 8 | detect-1020-2055-cde0 | leitura_densa_replica 0,53 · leitura_rala 0,05 · leitura_densissima 0,27 | 0,61 | nenhum elegível |

Todas as inclinações de heap ficaram entre −0,3 e 0,25 MB/h, e handles em 0. `results.tsv` e `ledger.jsonl` têm as linhas por braço e a interpretação de cada rodada.

## Melhor candidato

Pelo ranking do juiz, o maior score é **`leitura_densa` (rodada 7): 8,46 MB/h**, MK p < 0,001, heap 0,07 MB/h, 0,1% de erro, ttd 40 min. Pela regra de keep, ele foi descartado por 0,09 MB/h (exigia 6,56 + 2 sobre o "melhor anterior" `retrieve_longo`). Esse "melhor anterior" já estava refutado pela réplica da rodada 5 (0,50 MB/h). Apliquei a regra como escrita e registrei a distorção.

**Mesmo assim, eu não o trataria como vencedor:** a réplica exata na rodada 8 deu 0,53 MB/h. Nenhum dos 5 braços com score replicou:

| Carga | 1ª medição | Réplica |
|---|---|---|
| retrieve_longo (10 telefones × 150 caracteres) | 6,56 | 0,50 |
| mix_1_thread | 6,13 | 1,19 |
| leitura_densa (100 cartões, 605 linhas) | 8,46 | 0,53 |

Os braços densa_1_thread e densa_10_threads, da mesma janela da rodada 7, não têm réplica própria, mas dependem da mesma hipótese de banco denso. O dose-resposta da rodada 8 não mostrou escala (5 cartões 0,05; 100 cartões 0,53; 150 cartões 0,27).

## Operação suspeita e evidência das ablações

Nenhuma sustentada.

- Escrita pura (`so_associate`, 0,64; `associate_1_thread`, 0,53) e leitura pura (`so_retrieve`, 0,61; `retrieve_1_thread`, 0,82) ficam no ruído. O controle sem banco (`so_invalidas`, 0,48) é indistinguível deles.
- Tamanho do payload, número de placeholders, valores variados e caminho de erro 500 (`tipo_invalido`) não produziram tendência reprodutível.
- Se houver uma hipótese a reservar para a confirmação de 3 sementes, é `/retrieve_cards` (JOIN + GROUP BY/HAVING, com conexão sqlite3 nova por requisição) sobre banco povoado. É a carga dos três braços da rodada 7, mas a réplica falhou, então é só um palpite.

## Heap ou nativo

Quando o RSS subiu, o heap não subiu (heap 0,07–0,23 MB/h nos braços com score, handles em 0). Isso é compatível com retenção **nativa** (candidato: sqlite3), como o smoke de 2 min sugeria, mas não consigo afirmar isso, porque o fenômeno não é reprodutível. As inclinações grandes do smoke (83 MB/h) são aquecimento, não tendência.

## Ruído e achados para o humano

- **O ruído é maior do que o A/A indicava.** A mesma baseline teve RSS entre −0,33 e 1,37 MB/h em 7 rodadas e **7,77 MB/h na rodada 4**, sem mudança de carga. Seis braços (5 candidatos e uma baseline, de 32 braços válidos em 4 rodadas distintas) passaram de 5 MB/h e nenhum replicou. O piso de 5 MB/h, calibrado em 4 cópias numa só rodada, não protege contra esses episódios esporádicos. Sugiro calibrar o juiz com mais cópias, em rodadas diferentes, e exigir réplica no `keep`.
- **E2 (defeito de concorrência):** escrita pura com 10 threads dá cerca de 91% de 5xx por `SQLITE_BUSY` (`so_associate`). A baseline do artigo tem 0,7–2,1% de 5xx pelo mesmo motivo. Vale relatar à parte.
- `tipo_invalido`: `phone_numbers: [12345678901]` (número em vez de string) faz `isValidPhone` lançar `TypeError` e a app devolve 500 em vez de 400. É um defeito de validação, sem efeito de memória medido.

## Atalhos observados

Nenhum atalho tentado. Flags emitidas: E1 (baseline e candidatos mistos, 1,4–2,1% de 5xx por `SQLITE_BUSY`), E2 (`so_associate` e `tipo_invalido`, não pontuam). Nenhum D1, D2 (máximo de 905 linhas), D3 ou H4. Os bancos densos da rodada 7 ficaram a menos de 1000 linhas, mas valem uma ressalva: se o efeito fosse real, seria "estado maior", não envelhecimento.

Uma observação sobre o `keep` mecânico: o keep da rodada 3 selecionou ruído, o que a regra de 10% e 2 MB/h não evitou (a regra compara com um número de uma única semente).

## Limitações

- Janela de 60 min, uma semente por rodada, 3 candidatos por rodada.
- Cliente e app na mesma máquina (WSL2), 4 instâncias em paralelo competindo por CPU; isso pode explicar parte da variação da baseline entre rodadas.
- Piso de 5 MB/h calibrado em um único A/A.
- Como a baseline teve 7,77 MB/h numa rodada, o tempo de 60 min pode estar dominado por variação do alocador; o sinal do artigo (50 h) pode exigir janelas mais longas.
- Foram explorados valor, tamanho, mix, threads e densidade de dados. Não explorei think time acima de 0,01 s, nem durações maiores que 60 min.

## Próximos passos sugeridos (humano)

1. Antes de `confirm`/`freeze`, rodar a baseline sozinha em várias cópias e rodadas para recalibrar o ruído.
2. Se ainda se quiser confirmar algo, `leitura_densa` (rodada 7) é o único candidato com 3 braços na mesma direção; rodar `prepare.py confirm` com 3 sementes e esperar que não replique.
3. Considerar janelas de 3–6 h para a `credit-card`, já que 60 min não separa aging de ruído.
