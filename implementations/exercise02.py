from __future__ import annotations

import hashlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TXID_LIST_PATH = REPO_ROOT / "data" / "ex02_txid_list.txt"
OUTPUT_PATH = REPO_ROOT / "solutions" / "exercise02.txt"
REQUIRED_TXID = "49ff8cccf1ca12179e9ae7a4760f550b5a18401b27e1e057604e27c3e10c08fb"


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def load_txids(path: Path) -> list[bytes]:
    txids: list[bytes] = []
    for line_num, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip().lower()
        if not line:
            continue
        if len(line) != 64:
            raise ValueError(f"Invalid txid length at line {line_num}: {line}")
        try:
            txids.append(bytes.fromhex(line))
        except ValueError as exc:
            raise ValueError(f"Invalid hex txid at line {line_num}: {line}") from exc
    if not txids:
        raise ValueError("Transaction list is empty")
    return txids


def build_merkle_root_and_proof(txids: list[bytes], required_txid: bytes) -> tuple[bytes, list[bytes]]:
    try:
        target_index = txids.index(required_txid)
    except ValueError as exc:
        raise ValueError("Required txid not found in transaction list") from exc

    level = list(txids)
    proof: list[bytes] = []

    while len(level) > 1:
        if len(level) % 2 == 1:
            level = level + [level[-1]]

        sibling_index = target_index ^ 1
        proof.append(level[sibling_index])

        next_level: list[bytes] = []
        for i in range(0, len(level), 2):
            next_level.append(sha256(level[i] + level[i + 1]))

        target_index //= 2
        level = next_level

    return level[0], proof


def write_solution(path: Path, root: bytes, proof: list[bytes]) -> None:
    lines = [root.hex(), *(node.hex() for node in proof)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    txids = load_txids(TXID_LIST_PATH)
    required_txid = bytes.fromhex(REQUIRED_TXID)
    root, proof = build_merkle_root_and_proof(txids, required_txid)
    write_solution(OUTPUT_PATH, root, proof)

    print(f"Merkle root: {root.hex()}")
    print(f"Proof length: {len(proof)}")
    print(f"Required txid included: {required_txid in txids}")


if __name__ == "__main__":
    main()
