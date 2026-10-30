"""Teste funcional público (adaptado de chas42/generated-software-llm/scripts/tests/test_credit_card_service.py).

O agente pode ler este arquivo. Ele não pode editá-lo.
"""

import http.client
import json
import sys


def post(port, path, body):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
    r = c.getresponse()
    data = r.read()
    c.close()
    try:
        return r.status, json.loads(data or b"null")
    except json.JSONDecodeError:
        return r.status, None


def associate(port, cc, phone):
    s, _ = post(port, "/associate_card", {"credit_card": cc, "phone": phone})
    return 200 <= s < 300


def retrieve(port, phones):
    s, j = post(port, "/retrieve_cards", {"phone_numbers": phones})
    if not 200 <= s < 300:
        return []
    return sorted((j or {}).get("card_numbers", []))


def run(port):
    """Retorna lista de falhas (vazia = passou)."""
    fails = []
    for cc, ph in [("4111111111111111", "+5511988887777"),
                   ("4111111111111111", "+1(800)123-4567"),
                   ("5500000000000004", "+1(800)123-4567")]:
        if not associate(port, cc, ph):
            fails.append(f"associate {cc} {ph}")
    checks = [
        (["+5511988887777"], ["4111111111111111"]),
        (["+5511988887777", "+1(800)123-4567"], ["4111111111111111"]),
        (["+5511988887777", "+1(800)123-4567", "+44 2079460958"], []),
        (["+1(800)123-4567"], ["4111111111111111", "5500000000000004"]),
    ]
    for phones, expected in checks:
        got = retrieve(port, phones)
        if got != expected:
            fails.append(f"retrieve {phones}: esperado {expected}, obtido {got}")
    return fails


if __name__ == "__main__":
    f = run(int(sys.argv[1]) if len(sys.argv) > 1 else 3000)
    print("OK" if not f else "FALHOU:\n" + "\n".join(f))
    sys.exit(1 if f else 0)
