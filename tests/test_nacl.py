import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nacl_sim  # noqa: E402

RULES = nacl_sim.load_rules(str(ROOT / "network" / "nacl.json"))


def packets(name):
    with open(ROOT / "network" / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pkt(direction, protocol, port, address):
    return {"direction": direction, "protocol": protocol, "port": port, "address": address}


class NaclTests(unittest.TestCase):
    def test_sample_packets_all_decided_as_expected(self):
        for p in packets("packets_sample.jsonl"):
            action, _ = nacl_sim.decide(RULES, p)
            self.assertEqual(action, p["expected"], p["id"])

    def test_own_packets_all_decided_as_expected(self):
        for p in packets("packets_extra.jsonl"):
            action, _ = nacl_sim.decide(RULES, p)
            self.assertEqual(action, p["expected"], p["id"])

    def test_blocked_range_is_denied_on_web_ports_by_the_lowest_rule(self):
        for port in (80, 443):
            action, rule = nacl_sim.decide(RULES, pkt("inbound", "tcp", port, "198.51.100.9"))
            self.assertEqual((action, rule), ("deny", 100))

    def test_ssh_only_from_management_subnet(self):
        self.assertEqual(nacl_sim.decide(RULES, pkt("inbound", "tcp", 22, "10.20.5.130"))[0], "allow")
        self.assertEqual(nacl_sim.decide(RULES, pkt("inbound", "tcp", 22, "203.0.113.7"))[0], "deny")

    def test_replies_need_their_own_rules(self):
        self.assertEqual(nacl_sim.decide(RULES, pkt("outbound", "tcp", 50000, "203.0.113.7"))[0], "allow")
        self.assertEqual(nacl_sim.decide(RULES, pkt("inbound", "tcp", 50000, "10.20.1.1"))[0], "allow")
        self.assertEqual(nacl_sim.decide(RULES, pkt("inbound", "tcp", 50000, "203.0.113.7"))[0], "deny")

    def test_unmatched_packet_is_denied(self):
        self.assertEqual(nacl_sim.decide(RULES, pkt("inbound", "udp", 53, "203.0.113.7")), ("deny", None))


if __name__ == "__main__":
    unittest.main()
