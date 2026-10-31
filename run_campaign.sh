#!/usr/bin/env bash
# Lança uma campanha com o Claude Code em modo headless.
# Uso: ./run_campaign.sh detect <tag>    |    ./run_campaign.sh repair <tag>
set -euo pipefail
PHASE="${1:?detect|repair}"; TAG="${2:?tag da campanha}"
cd "$(dirname "$0")"
python prepare.py verify
cp ".claude/settings.${PHASE}.json" .claude/settings.json
# Barreira real (além das permissões do Claude Code): juiz e oráculos sem escrita,
# e oracle/hidden restrito (chmod 700) para impedir leitura caso o agente rode com outro usuário Linux.
chmod -R a-w prepare.py harness oracle apps .judge 2>/dev/null || true
[ -d oracle/hidden ] && chmod 700 oracle/hidden 2>/dev/null || true
[ -d frozen ] && chmod -R a-w frozen || true
mkdir -p logs results
PROMPT="Leia program_${PHASE}.md e execute a campanha com a tag '${TAG}'. O humano já confirmou o setup: não pergunte nada, siga o laço até o orçamento acabar e escreva o summary."
if [ -n "${AGENT_USER:-}" ]; then
  sudo -u "$AGENT_USER" claude -p "$PROMPT" --output-format stream-json --verbose \
    > "logs/${PHASE}-${TAG}-$(date +%Y%m%d-%H%M).jsonl" 2>&1
else
  claude -p "$PROMPT" --output-format stream-json --verbose \
    > "logs/${PHASE}-${TAG}-$(date +%Y%m%d-%H%M).jsonl" 2>&1
fi
echo "Campanha encerrada. Compare results.tsv com results/judge_log.jsonl."
