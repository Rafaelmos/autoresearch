# Relatório de Réplica dos Candidatos de Amplificação por Banco (Seção 4)

- **Data e Hora:** 31 de outubro de 2026, 17:09 às 18:09 (BRT)
- **Branch / Ambiente:** `fix/juiz-v2` (`bd0b0ad`), WSL2 Ubuntu 24.04 (12 vCPUs, 15,5 GB RAM)
- **Run ID:** `detect-1031-1709-286d` (Duração: 60 minutos + 5 min warmup, `--seed 2`)
- **Objetivo:** Executar a **Seção 4** da análise metodológica, testando com uma nova semente (`--seed 2`) se os 3 candidatos da campanha `det-out30` que usaram o banco de dados como amplificador e apresentaram as maiores inclinações de RSS repetem o efeito de forma sustentada.

---

## 1. Candidatos Avaliados e Motivação

Na campanha `det-out30`, três hipóteses utilizaram o banco de dados como amplificador de alocação de memória nativa / V8 (todas mantendo o banco rigorosamente dentro do teto de 1000 linhas, sem violar D2):

1. **`rep_unicode_twobyte_resultset`** (ex-D1): 450 cartões contendo caracteres Unicode multi-byte (`\u3000`), totalizando 901 linhas no banco.
2. **`rep_erro500_45pct_resultset_971`** (ex-E1): Result set largo (~950 KB por leitura) com 971 linhas populadas nos primeiros segundos e 4,54% de erro 500 controlado.
3. **`rep_join_912_having_vazio_404`** (ex-D3): Varredura e agrupamento em B-tree temporária no SQLite sobre 811 associações (912 linhas) com interseção vazia no `HAVING COUNT(DISTINCT) = 10`.
4. **`baseline_artigo`**: Carga padrão do artigo (4º slot fixo de controle concorrente).

---

## 2. Resultados Consolidados: Original vs. Réplica

| Braço | Linhas BD | Slope Original (`seed 1`) | Slope Global Réplica (`seed 2`) | 1ª Metade (h1) | 2ª Metade (h2) | Menor Metade (`min_half`) | Heap Slope | Ratio vs Baseline | Status Juiz v2 |
|---|---|---|---|---|---|---|---|---|---|
| **rep_unicode_twobyte_resultset** | 901 | 10,38 MB/h | **6,21 MB/h** | 2,50 MB/h | 9,19 MB/h | **2,50 MB/h** | 0,16 MB/h | 0,76× | Pontuaria na v1 / Descartado na v2 |
| **rep_erro500_45pct_resultset_971** | 971 | 7,66 MB/h | **10,17 MB/h** | 48,88 MB/h | -0,65 MB/h | **-0,65 MB/h** | 0,10 MB/h | 1,24× | Pontuaria na v1 / Descartado na v2 |
| **rep_join_912_having_vazio_404** | 912 | 6,25 MB/h | **9,02 MB/h** | 0,81 MB/h | 12,15 MB/h | **0,81 MB/h** | 0,14 MB/h | 1,10× | Pontuaria na v1 / Descartado na v2 |
| **baseline_artigo** (controle) | 3 | 0,32 a 3,82 MB/h | **8,21 MB/h** | 0,28 MB/h | 8,16 MB/h | **0,28 MB/h** | 0,12 MB/h | 1,00× | Referência de ruído da rodada |

---

## 3. Interpretação Técnica dos Resultados

### 3.1. Confirmação Cabal da Tese de César para a Fase 2
Este experimento forneceu a validação prática perfeita para a revisão do juiz proposta por César:

1. **Deriva da Baseline e Variação entre Rodadas:**
   Nesta execução, a própria `baseline_artigo` apresentou uma inclinação global de Sen de **8,21 MB/h** (com delta de apenas 5,7 MB ao longo de 1 hora). Se usássemos apenas o critério clássico de $Sen \ge 5\text{ MB/h}$, a baseline teria sido falsamente considerada em envelhecimento!
2. **O Fenômeno do Degrau (`min_half` negativo no erro 500):**
   O candidato `rep_erro500_45pct_resultset_971` teve slope global de **10,17 MB/h**. Porém, a análise por metades revela a realidade:
   - **1ª Metade:** subida acentuada de 48,88 MB/h durante a acomodação inicial de stack traces e buffers.
   - **2ª Metade:** a inclinação foi de **-0,65 MB/h** (queda na taxa de memória).
   - A menor metade é negativa (`-0,65 MB/h`). Não há acúmulo contínuo ou progressivo.
3. **Ausência de Ganho Real contra a Baseline Concorrente:**
   - O `rep_unicode_twobyte_resultset` subiu **menos** que a baseline concorrente da mesma rodada ($ratio = 0,76\times$).
   - O `rep_join_912_having_vazio_404` subiu praticamente empatado com a baseline ($ratio = 1,10\times$).
4. **Heap do V8 Completamente Plano:**
   Em todos os braços, a inclinação do Heap permaneceu em torno de **0,09 a 0,16 MB/h**. Nenhum objeto JavaScript está vazando no runtime da aplicação.

---

## 4. Houve Envelhecimento de Software?

**Não.** Não foi evidenciado envelhecimento de software contínuo e sustentável:
- Nenhum candidato apresentou `min_half` acima do limiar calibrado de 4 a 5 MB/h nas duas metades da janela.
- As flutuações de RSS refletem acomodação de alocador de páginas, buffers de conexão efêmera do SQLite e variação natural do sistema sob alta concorrência de 4 processos paralelos.

---

## 5. A Reparação foi Executada?

**Não**, e nem deve ser executada nesta etapa:
1. Para iniciar a fase de reparo (`prepare.py repair-init`), é obrigatório que exista um candidato que tenha envelhecido de forma comprovada e que seja congelado (`prepare.py freeze`) e confirmado em 3 sementes (`prepare.py confirm --phase detect`).
2. Como os candidatos foram refutados pela métrica robusta de metades (`min_halves`) e não superaram a baseline de controle, não há vazamento legítimo para submeter a reparo.
3. Além disso, conforme orientação explícita de César, a execução da campanha de reparo deve aguardar a implementação formal da Fase 2 do juiz.
