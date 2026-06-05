from __future__ import annotations

import csv
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MEMPOOL_PATH = REPO_ROOT / "data" / "mempool.csv"
OUTPUT_PATH = REPO_ROOT / "solutions" / "exercise01.txt"
REQUIRED_TXID = "4c50e3dad7f98bceb6441f96b23748dea84fbdb7cedd603441e6ea4a574d04a6"
WEIGHT_LIMIT = 4_000_000


@dataclass(frozen=True)
class TxRecord:
    txid: str
    fee: int
    weight: int
    parents: tuple[str, ...]


def load_mempool(path: Path) -> tuple[dict[str, TxRecord], dict[str, list[str]]]:
    txs: dict[str, TxRecord] = {}
    children: dict[str, list[str]] = {}

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row_num, row in enumerate(reader, start=1):
            if len(row) < 3:
                raise ValueError(
                    f"Malformed CSV at line {row_num}: expected at least 3 columns."
                )

            txid = row[0].strip().lower()
            if not txid:
                raise ValueError(f"Empty txid at line {row_num}.")

            try:
                fee = int(row[1].strip())
                weight = int(row[2].strip())
            except ValueError as exc:
                raise ValueError(
                    f"Invalid fee/weight at line {row_num}: {row[1]!r}, {row[2]!r}"
                ) from exc

            parent_field = row[3].strip() if len(row) >= 4 else ""
            parents = tuple(
                parent.strip().lower()
                for parent in parent_field.split(";")
                if parent.strip()
            )

            if txid in txs:
                raise ValueError(f"Duplicate txid in mempool: {txid}")

            txs[txid] = TxRecord(txid=txid, fee=fee, weight=weight, parents=parents)
            children.setdefault(txid, [])

    for tx in txs.values():
        for parent in tx.parents:
            if parent not in txs:
                raise ValueError(f"Transaction {tx.txid} references missing parent {parent}")
            children.setdefault(parent, []).append(tx.txid)

    return txs, children


def get_all_ancestors(
    txid: str,
    txs: dict[str, TxRecord],
    cache: dict[str, set[str]],
    active: set[str] | None = None,
) -> set[str]:
    if txid in cache:
        return cache[txid]

    if active is None:
        active = set()
    if txid in active:
        raise ValueError(f"Cycle detected while resolving ancestors for {txid}")

    active.add(txid)
    ancestors: set[str] = set()
    for parent in txs[txid].parents:
        ancestors.add(parent)
        ancestors.update(get_all_ancestors(parent, txs, cache, active))
    active.remove(txid)
    cache[txid] = ancestors
    return ancestors


def build_package(
    txid: str,
    included: set[str],
    txs: dict[str, TxRecord],
    ancestors_cache: dict[str, set[str]],
) -> set[str]:
    package = {txid}
    package.update(get_all_ancestors(txid, txs, ancestors_cache))
    return {member for member in package if member not in included}


def topological_order(package_txids: set[str], txs: dict[str, TxRecord]) -> list[str]:
    indegree = {txid: 0 for txid in package_txids}
    adjacency = {txid: [] for txid in package_txids}

    for txid in package_txids:
        for parent in txs[txid].parents:
            if parent in package_txids:
                indegree[txid] += 1
                adjacency[parent].append(txid)

    ready = sorted(txid for txid, degree in indegree.items() if degree == 0)
    ordered: list[str] = []

    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(adjacency[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()

    if len(ordered) != len(package_txids):
        raise ValueError("Cycle detected while topologically ordering package")

    return ordered


def package_stats(package: set[str], txs: dict[str, TxRecord]) -> tuple[int, int]:
    fee = sum(txs[txid].fee for txid in package)
    weight = sum(txs[txid].weight for txid in package)
    return fee, weight


def select_block(txs: dict[str, TxRecord]) -> tuple[list[str], int, int]:
    ancestors_cache: dict[str, set[str]] = {}
    included: set[str] = set()
    ordered_block: list[str] = []
    total_fee = 0
    total_weight = 0

    required_package = build_package(REQUIRED_TXID, included, txs, ancestors_cache)
    required_order = topological_order(required_package, txs)
    required_fee, required_weight = package_stats(required_package, txs)

    if required_weight > WEIGHT_LIMIT:
        raise ValueError("Required transaction package exceeds the block weight limit")

    for txid in required_order:
        included.add(txid)
        ordered_block.append(txid)

    total_fee += required_fee
    total_weight += required_weight

    while True:
        best_choice: tuple[Fraction, int, int, str, set[str]] | None = None

        for txid in sorted(txs):
            if txid in included:
                continue

            package = build_package(txid, included, txs, ancestors_cache)
            if not package:
                continue

            package_fee, package_weight = package_stats(package, txs)
            if total_weight + package_weight > WEIGHT_LIMIT:
                continue

            candidate = (
                Fraction(package_fee, package_weight),
                package_fee,
                -package_weight,
                txid,
                package,
            )

            if best_choice is None or candidate > best_choice:
                best_choice = candidate

        if best_choice is None:
            break

        _, package_fee, neg_package_weight, _, package = best_choice
        ordered_package = topological_order(package, txs)
        for txid in ordered_package:
            if txid not in included:
                included.add(txid)
                ordered_block.append(txid)

        total_fee += package_fee
        total_weight += -neg_package_weight

    return ordered_block, total_fee, total_weight


def write_solution(path: Path, ordered_block: list[str]) -> None:
    path.write_text("\n".join(ordered_block) + "\n", encoding="utf-8")


def main() -> None:
    txs, _children = load_mempool(MEMPOOL_PATH)
    if REQUIRED_TXID not in txs:
        raise ValueError(f"Required txid not found in mempool: {REQUIRED_TXID}")

    ordered_block, total_fee, total_weight = select_block(txs)
    write_solution(OUTPUT_PATH, ordered_block)

    print(f"Selected {len(ordered_block)} transactions")
    print(f"Total fee: {total_fee}")
    print(f"Total weight: {total_weight}")
    print(f"Required txid included: {REQUIRED_TXID in ordered_block}")


if __name__ == "__main__":
    main()
