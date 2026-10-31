# Análise: o banco de dados pode ser usado para gerar aging sem violar as regras?

- **Data:** 31/10/2026
- **Branch:** `fix/juiz-v2` @ `bd0b0ad`
- **Base:** regras em `program_detect.md`, `harness/load.py` e `harness/evaluate.py`; código da app `credit-card`; os 24 braços da campanha `det-out30` (`results/det-out30/`). Nenhum experimento novo foi rodado.

## Resposta curta

Sim, é possível dentro das regras, mas com um teto apertado. A campanha `det-out30` já explorou bastante esse caminho e **não encontrou aging que se repetisse**.

## 1. O que as regras permitem com o banco

| Regra | Limite | Efeito no banco |
|---|---|---|
| D2 (estado legítimo) | No máximo 1000 linhas no fim da rodada | Acima disso o braço é medido mas não pontua: crescer porque "tem mais dados" não conta como aging |
| Contrato de carga | Body de até 2048 B, até 10 telefones, só `/associate_card` e `/retrieve_cards` | Cada linha guarda no máximo uns 2 KB |
| Validação da app | O cartão é checado depois de remover espaços e hífens, mas é **gravado cru** | Dá para gravar cartões de ~1960 B, preenchidos com espaços ou hífens, dentro do contrato |
| Ambiente | O banco começa vazio em cada braço (`instance.py` ignora `uptime_db`); a app não tem rota de DELETE | Não dá para burlar a contagem de linhas |
| E1/E2, D1, H4 | 5xx até 5%, sem saturar a máquina, sem matar o processo | Limita cargas de escrita concorrente por causa do `SQLITE_BUSY` |

**A conta que importa:** no máximo 1000 linhas × ~2 KB ≈ **2 MB de dados**. Para pontuar, o RSS precisa subir pelo menos 5 MB/h durante 60 min, ou seja, mais que o banco inteiro permitido. O volume de dados em si não gera aging. O banco só pode servir de **amplificador**: result sets grandes fazem cada requisição alocar muita memória nativa (sqlite3 e N-API), e é essa memória que pode ficar retida ou fragmentar. A app abre uma conexão nova por requisição, então o cache de páginas do SQLite é descartado a cada chamada.

Também é importante que o banco pare de crescer antes da janela medida, que começa depois de 300 s de aquecimento. Se ele continuar crescendo durante a medição, a subida de memória se confunde com dados novos.

## 2. O que a `det-out30` já testou

O agente já levou o banco para perto do limite em 14 dos 18 candidatos.

| Candidato | Linhas | Slope RSS (MB/h) | Observação |
|---|---|---|---|
| `unicode_twobyte_resultset` | 901 | **10,38** | Na combinação seguinte (`erro500_45pct_unicode_951`) caiu para 1,79 |
| `erro500_45pct_resultset_971` | 971 | 7,66 | Depende de 4,5% de 5xx (fica perto do E2) |
| `erro_500_controlado_4pct` | 601 | 6,25 | **Réplica com a semente 2 deu 1,19**: não se repetiu |
| `join_912_having_vazio_404` | 912 | 6,25 | Rodada só uma vez |
| `contencao_3w_7r` / `escrita_2_threads_longa` / `fragmentacao_resultset_misto` | 803 a 934 | 4,1 a 5,0 | Na faixa do ruído |
| `resultset_largo_961`, `join_having_10_fones`, `ablation_400_resultset_971` | 961 a 978 | −0,1 a 0,7 | Nada |

Para comparar: a baseline da rodada 4 deu 3,82 MB/h, e a pior cópia do A/A de 31/10 (`results/calibracao-juiz-v2/`) deu 4,17. Os "picos" de 6 a 10 MB/h ficam só 2 a 6 MB/h acima do ruído e **não se repetiram**. O heap ficou plano em todos (0,05 a 0,4 MB/h). Se existe alguma retenção, ela é nativa, mas não é estável.

> [!WARNING]
> Pelo critério da `fix/juiz-v2` (slope de pelo menos 5 MB/h na janela inteira), 4 desses braços teriam pontuado. Só que eles não se repetem e ficam colados no ruído. Isso reforça a proposta da Fase 2: usar a inclinação por metades e exigir réplica com outra semente antes de manter um candidato (keep).

## 3. Conclusão

- **É permitido?** Sim, até 1000 linhas, se o banco for preenchido durante o aquecimento e ficar estável durante a medição.
- **Pode gerar aging?** Só se cada requisição sobre o banco grande deixar memória retida. O banco é o amplificador, não a fonte.
- **Já foi demonstrado?** Não. As melhores tentativas não se repetiram.
- **Zona cinzenta, para anotar no ledger como possível atalho:**
  - cartões de ~1960 B preenchidos com espaços ou hífens;
  - Unicode `\u3000`, que passa no `\s` do regex.

  Os dois estão dentro do contrato, mas exploram a validação frouxa da app e são pouco realistas como carga de uso.
- **O que exigiria mudar as regras (decisão humana):** passar de 1000 linhas, janelas maiores que 60 min ou body maior que 2 KB. O aging do artigo (~1,5 GB em 50 h) pode só aparecer em horizontes longos, fora do alcance de 60 min.

## 4. Próximo passo sugerido (depois da Fase 2)

Uma rodada só de **réplicas**, com outra semente, dos três candidatos que mais subiram: `unicode_twobyte_resultset`, `join_912_having_vazio_404` e `erro500_45pct_resultset_971`. Todos com o banco preenchido nos primeiros minutos e congelado depois.
