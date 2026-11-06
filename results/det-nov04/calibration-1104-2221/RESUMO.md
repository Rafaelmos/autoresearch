# Controle positivo — calibração de 120 min (`calibration-1104-2221`)

Rodada 0, feita pelo humano antes da campanha `det-nov04`, com `calibration/positive_control.py --minutes 120` (semente 1).
Quatro instâncias com a carga da baseline e vazamento nativo injetado de 0, 10, 20 e 40 MB/h, avaliadas pelo mesmo juiz.
Números copiados de `calibration_summary.json`.

| Injetado (MB/h) | Global (MB/h) | Robusto (MB/h) | Recuperação robusta | Detectado | Flags |
|---|---|---|---|---|---|
| 0 | 0,31 | 0,16 | – | não | E1 |
| 10 | 13,13 | 12,67 | 126,7% | sim | E1 |
| 20 | 23,56 | 23,64 | 118,2% | sim | E1 |
| 40 | 39,69 | 39,07 | 97,7% | sim | E1 |

**Leitura:** o controle de 0 MB/h ficou limpo e os de 10, 20 e 40 MB/h foram detectados. Para vazamento nativo, o detector não é cego nesta janela e com esta carga. Um braço plano é, portanto, evidência de ausência de aging naquela carga, e não só falta de sensibilidade.

## Tentativas anteriores (não valem como controle)
- `calibration-1104-2156-smoke` e `calibration-1104-2157-smoke`: smoke de 2 min. No de `2157`, o braço de 0 MB/h apareceu como detectado (global 55,5; robusto 19,7), porque 2 min é curto demais.
- `calibration-1104-2205`: a execução de 120 min iniciada às 22:05 morreu sem gerar `calibration_summary.json`, e foi refeita às 22:21.

## Limitações
Semente única, 4 instâncias em paralelo, cliente e app na mesma máquina, vazamento injetado (nativo e linear), que pode não representar o aging real da app.
