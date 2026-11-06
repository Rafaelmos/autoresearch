# Campanha de detecção `det-nov04` — resumo parcial

Branch `autoresearch/det-nov04`. Rodadas de 120 min, semente 1. Nenhum braço chegou a 10,0 MB/h (global e robusto), então não houve `score`, `keep` ou operação suspeita. Controle positivo: ver `calibration-1104-2221/RESUMO.md` (0 MB/h limpo; 10, 20 e 40 MB/h detectados).

## Problema de infraestrutura
Braços com 2 ou mais threads (e a baseline de 10 threads) estouraram o timeout de 7300 s do subprocesso `harness.load run`, em todas as 5 execuções. Braços de 1 thread sempre terminaram a carga. A app estava saudável nos braços que travaram. O `dmesg` do WSL mostra `Time jumped backwards`, suspeita de causa que não foi confirmada. `harness/` e `prepare.py` não foram editados. Consequência: não há baseline pareada nem carga de 10 threads em nenhuma rodada de 120 min.

## Rodadas (MB/h; todos os `score` = NA)

| Rodada | run_id | Braço | Global | Robusto | Obs. |
|---|---|---|---|---|---|
| 1 (1ª) | detect-1105-0910-b8cc | escrita_serial_120 (1t) | 2,67 | 1,00 | h1=7,5 |
| | | leitura_10t_120, misto_diverso_4t, baseline | – | – | timeout |
| 1 (repetição) | detect-1105-1109-e938 | todos | – | – | timeout; 1t terminou a carga mas não apareceu no resumo |
| 2 | detect-1105-1353-0ea3 | leitura_serial_120 (1t) | 0,14 | −0,03 | |
| | | misto_serial_diverso_120 (1t) | 0,51 | 0,37 | |
| | | leitura_larga_serial_120 (1t) | 0,17 | 0,12 | |
| | | baseline | – | – | timeout |
| 3 | detect-1105-1548-154d | escrita_diversa_serial (1t) | 3,78 | 0,24 | h1=19,0 (degrau) |
| | | leitura_inexistente_serial (1t) | 1,16 | 0,59 | |
| | | misto_com_5xx_serial (1t) | 1,24 | 0,04 | E1 (3,07% de 5xx, esperado) |
| | | baseline | – | – | timeout |
| 4 | detect-1105-1758-c376 | corpo_grande_misto_serial (1t) | 1,11 | 0,005 | h1=10,9 (degrau) |
| | | formatos_variados_serial (1t) | 1,99 | −0,27 | D2 (3320 linhas; erro de desenho) |
| | | misto_diverso_2t | – | – | timeout |
| | | baseline | – | – | timeout |

Fonte de verdade: `judge_log.jsonl`. Linhas completas em `results.tsv` e `ledger.jsonl`.

## Conclusões
- Heap ≤ 0,16 MB/h e handles 0 em todos os braços válidos. Operação suspeita: nenhuma identificada.
- Os degraus de alocador na 1ª metade (h1 de 10 a 19 MB/h) são filtrados pela regra robusta.
- O caminho 5xx via `errorHandler` (TypeError com `credit_card` numérico) e o corpo grande (`body-parser`) não acumulam memória.
- Atalhos: nenhum marcado. Só E1 explicado e D2 por erro de desenho.

## Limitações
Só cargas de 1 thread foram medidas (o contrato do artigo usa 10), uma semente por candidato, sem baseline pareada, janela de 120 min, 4 instâncias em paralelo, cliente e app na mesma máquina.

## Próximos passos (decisão do humano)
Rodadas de 8 h foram sugeridas. Antes disso, é preciso resolver o timeout do harness (constante de 7200 s + 100 s de margem) e o relógio do WSL.
