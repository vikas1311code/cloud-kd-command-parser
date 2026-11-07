# Task 5: Subnetting and NACL

## 1. Subnets for 10.20.0.0/16

Rules used: usable hosts = 2^(32 - prefix) - 2. For each requirement I take the smallest prefix whose usable hosts are at least the hosts needed. Subnets are allocated from the largest requirement to the smallest, starting at 10.20.0.0, each one directly after the previous one.

| Subnet | Hosts needed | Prefix | Network address | Usable host range | Broadcast address | Usable hosts |
|---|---|---|---|---|---|---|
| app | 1,000 | /22 | 10.20.0.0 | 10.20.0.1 - 10.20.3.254 | 10.20.3.255 | 1,022 |
| public | 250 | /24 | 10.20.4.0 | 10.20.4.1 - 10.20.4.254 | 10.20.4.255 | 254 |
| data | 100 | /25 | 10.20.5.0 | 10.20.5.1 - 10.20.5.126 | 10.20.5.127 | 126 |
| management | 20 | /27 | 10.20.5.128 | 10.20.5.129 - 10.20.5.158 | 10.20.5.159 | 30 |

### Working

- app, 1,000 hosts: /23 gives 2^9 - 2 = 510 (too small), /22 gives 2^10 - 2 = 1,022 (enough). The block has 1,024 addresses, so it runs 10.20.0.0 to 10.20.3.255.
- public, 250 hosts: /25 gives 126 (too small), /24 gives 254 (enough). Block of 256 starts right after app at 10.20.4.0 and ends at 10.20.4.255.
- data, 100 hosts: /26 gives 62 (too small), /25 gives 126 (enough). Block of 128 starts at 10.20.5.0 and ends at 10.20.5.127.
- management, 20 hosts: /28 gives 14 (too small), /27 gives 30 (enough). Block of 32 starts at 10.20.5.128 and ends at 10.20.5.159.

Each network address is a multiple of its block size, so every subnet is correctly aligned. The next free address is 10.20.5.160. The table was cross-checked with Python's ipaddress module.

## 2. NACL for the public subnet (network/nacl.json)

| Direction | Rule | Action | Protocol and ports | CIDR | Purpose |
|---|---|---|---|---|---|
| inbound | 100 | deny | all | 198.51.100.0/24 | block the abusive range, even on web ports |
| inbound | 110 | allow | tcp 80 | 0.0.0.0/0 | HTTP |
| inbound | 120 | allow | tcp 443 | 0.0.0.0/0 | HTTPS |
| inbound | 130 | allow | tcp 22 | 10.20.5.128/27 | SSH from the management subnet only |
| inbound | 140 | allow | tcp 1024-65535 | 10.20.0.0/22 | replies coming back from the app subnet |
| outbound | 100 | allow | tcp 8000 | 10.20.0.0/22 | load balancer to app subnet |
| outbound | 110 | allow | tcp 1024-65535 | 0.0.0.0/0 | replies going back to clients (ephemeral ports) |

Everything else is denied by the default rule. Checked with tools/nacl_sim.py: network/packets_sample.jsonl gives 6 of 6 correct, and my own 20 packets in network/packets_extra.jsonl give 20 of 20 (the expectations of three of them are explained in their "note" field). Output is in results/nacl_check.txt.

## 3. Explanation

**Why replies need their own rules.** A NACL is stateless: it keeps no record of connections and judges every packet alone against the rules for its direction. A client connecting to port 443 is let in by inbound rule 120, but the reply leaves from port 443 towards the client's ephemeral port (1024-65535). The outbound rules cannot know that this packet is a reply, so it needs its own outbound rule (110). The same holds in the other direction: the request to the app subnet on port 8000 is allowed by outbound rule 100, and the app's reply returns to the load balancer's ephemeral port, so inbound rule 140 is needed. A stateful security group would allow both automatically.

**Why rule order matters for 198.51.100.0/24.** Rules are checked from the lowest number upward and the first match decides. The range 198.51.100.0/24 lies inside 0.0.0.0/0, so the allow rules for ports 80 and 443 also match its packets. The deny only works if its number is lower than those allow rules, which is why it is rule 100 and the allows are 110 and 120. With a deny numbered higher than 110 or 120, the allow would match first and abusive traffic would get through on the web ports.

**A limitation of this design.** Because replies cannot be told apart from new connections, outbound rule 110 also lets the subnet send any TCP traffic to destination ports 1024-65535 (including 8000) to any address, and inbound rule 140 accepts any TCP traffic from the app subnet on those ports. This follows from the required rules and is shown by packets E15, E16 and E20.
