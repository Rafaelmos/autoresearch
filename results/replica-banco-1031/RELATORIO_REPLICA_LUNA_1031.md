# Réplica dos candidatos de amplificação por banco — análise com Luna

- **Data:** 31/10/2026
- **Branch/commit do executor:** `fix/juiz-v2` / `e59b1a9`
- **Ambiente:** WSL2 Ubuntu 24.04
- **Run ID:** `detect-luna-1031`
- **Semente:** 3
- **Duração:** 60 min de medição, após 5 min de aquecimento
- **Análise independente:** Luna (`gpt-6-luna`)

## Objetivo

Repetir os três candidatos de `det-out30` que haviam apresentado as maiores inclinações de RSS. A baseline do artigo ocupou o quarto braço, em paralelo. Os perfis de carga foram mantidos idênticos aos da réplica anterior; só a semente mudou para 3.

## Resultados

| Braço | Linhas no BD | RSS Sen (MB/h) | 1ª metade | 2ª metade | Heap (MB/h) | Razão vs baseline | Score do juiz | Flags |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `rep_unicode_twobyte_resultset` | 901 | 0,90 | 2,55 | 0,68 | 0,27 | — | — | — |
| `rep_join_912_having_vazio_404` | 912 | 8,50 | 3,72 | 0,31 | 0,21 | 0,91× | 8,50 | — |
| `rep_erro500_45pct_resultset_971` | 971 | 2,63 | 6,03 | 0,09 | 0,10 | — | — | E1 (4,54% de 5xx) |
| `baseline_artigo` | 3 | 9,32 | 2,30 | −0,03 | 0,19 | 1,00× | — | — |

Todos os braços foram válidos e ficaram abaixo do limite de 1000 linhas. O braço de erros 500 ficou abaixo do limite E2 de 5%, mas excedeu o limiar de 1% para revisão humana e recebeu E1. Os valores de `MK p` para alta foram significativos; isso, por si só, não demonstra um efeito relevante: com centenas de amostras, até inclinações pequenas podem ter `p` muito baixo.

## Comparação com a réplica anterior (seed 2)

| Braço | RSS seed 2 (MB/h) | Metades seed 2 | RSS seed 3 (MB/h) | Metades seed 3 |
|---|---:|---:|---:|---:|
| Unicode | 6,21 | 2,50 / 9,19 | 0,90 | 2,55 / 0,68 |
| Join | 9,02 | 0,81 / 12,15 | 8,50 | 3,72 / 0,31 |
| Erros 500 | 10,17 | 48,88 / −0,65 | 2,63 | 6,03 / 0,09 |
| Baseline | 8,21 | 0,28 / 8,16 | 9,32 | 2,30 / −0,03 |

## Interpretação

A baseline voltou a mostrar inclinação global alta (9,32 MB/h), enquanto a inclinação da segunda metade foi praticamente nula. Isso aponta para uma subida em degrau ou variação da execução, e mostra por que não basta olhar o Sen global.

O juiz atribuiu score global 8,50 MB/h ao candidato `join`, pois ele satisfaz a regra implementada de Mann–Kendall e inclinação mínima. Porém, o candidato ficou abaixo da baseline simultânea (razão 0,91×) e suas metades foram 3,72 e 0,31 MB/h. Portanto, o score oficial não constitui evidência de crescimento contínuo atribuível à carga.

O candidato Unicode caiu de 6,21 para 0,90 MB/h. O candidato de erros 500 caiu de 10,17 para 2,63 MB/h; nas duas sementes, a inclinação global foi dominada por uma metade, com a outra praticamente plana. As inclinações de heap ficaram entre 0,10 e 0,27 MB/h nos candidatos, sem sinal de acúmulo de heap JavaScript que acompanhe as oscilações de RSS.

**Conclusão:** esta terceira semente não confirma envelhecimento contínuo e específico de nenhum dos três candidatos. A baseline simultânea e a análise por metades indicam que as inclinações globais observadas são compatíveis com degraus ou ruído da execução. A leitura independente do Luna chega à mesma conclusão.

## Artefatos

Os dados brutos, avaliações individuais e `round.json` estão em [`detect-luna-1031`](./detect-luna-1031/). A réplica anterior de seed 2 está documentada em [`RELATORIO_REPLICA.md`](./RELATORIO_REPLICA.md).
