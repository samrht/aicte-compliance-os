"""Tamper-evident audit log.

Every state change is appended as a leaf of an RFC 6962 Merkle tree (the
Certificate Transparency construction). After each append the new root is
signed with Ed25519, so the log's history is fixed: editing any past row
changes its leaf hash, which no longer matches the stored hash nor rolls up
to the signed root. Inclusion proofs let anyone check one entry against a
published root without seeing the rest of the log.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlmodel import Session, select

from app import config
from app.models import AuditEntry, SignedRoot


# --- Merkle tree (RFC 6962 §2.1) -------------------------------------------

def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def root(leaves: list[bytes]) -> bytes:
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node_hash(root(leaves[:k]), root(leaves[k:]))


def inclusion_proof(index: int, leaves: list[bytes]) -> list[bytes]:
    n = len(leaves)
    if n <= 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_proof(index, leaves[:k]) + [root(leaves[k:])]
    return inclusion_proof(index - k, leaves[k:]) + [root(leaves[:k])]


def verify_inclusion(index: int, size: int, leaf: bytes, proof: list[bytes], expected: bytes) -> bool:
    """RFC 9162 §2.1.3.2 verification of an audit path."""
    if index >= size:
        return False
    fn, sn, r = index, size - 1, leaf
    for p in proof:
        if sn == 0:
            return False
        if fn % 2 == 1 or fn == sn:
            r = node_hash(p, r)
            while fn % 2 == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == expected


# --- Signing ----------------------------------------------------------------

_key: Ed25519PrivateKey | None = None


def signing_key() -> Ed25519PrivateKey:
    global _key
    if _key is None and config.AUDIT_SIGNING_KEY:
        _key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(config.AUDIT_SIGNING_KEY))
    if _key is None:
        path = config.AUDIT_KEY_PATH
        if path.exists():
            _key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        else:
            config.ensure_dirs()
            _key = Ed25519PrivateKey.generate()
            path.write_bytes(_key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()))
    return _key


def public_key_hex() -> str:
    raw = signing_key().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return raw.hex()


def checkpoint_message(size: int, root_hex: str) -> bytes:
    return f"acos-audit-log\n{size}\n{root_hex}\n".encode()


# --- Log ----------------------------------------------------------------------

def canonical(entry: AuditEntry) -> bytes:
    ts = entry.ts.isoformat() if isinstance(entry.ts, datetime) else str(entry.ts)
    body = {"id": entry.id, "ts": ts, "actor": entry.actor, "action": entry.action,
            "entity": entry.entity, "payload": entry.payload}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()


def append(s: Session, actor: str, action: str, entity: str, payload: dict | None = None,
           ts: datetime | None = None) -> AuditEntry:
    from app.db import serialize
    serialize(s)
    entry = AuditEntry(actor=actor, action=action, entity=entity, payload=payload or {})
    if ts is not None:
        entry.ts = ts
    s.add(entry)
    s.flush()                          # assigns the id, which is part of the leaf
    entry.leaf_hash = leaf_hash(canonical(entry)).hex()
    s.add(entry)
    leaves = [bytes.fromhex(h) for h in s.exec(select(AuditEntry.leaf_hash).order_by(AuditEntry.id)).all()]
    r = root(leaves).hex()
    sig = signing_key().sign(checkpoint_message(len(leaves), r)).hex()
    s.add(SignedRoot(tree_size=len(leaves), root=r, signature=sig))
    return entry


def latest_root(s: Session) -> SignedRoot | None:
    return s.exec(select(SignedRoot).order_by(SignedRoot.tree_size.desc())).first()


def verify_log(s: Session) -> dict:
    """Recompute every leaf from its row and the root from the leaves.

    A row edited in the database shows up twice: its recomputed hash differs
    from the hash stored at append time, and the root rebuilt from the
    recomputed hashes no longer equals the signed checkpoint.
    """
    entries = s.exec(select(AuditEntry).order_by(AuditEntry.id)).all()
    recomputed = [leaf_hash(canonical(e)) for e in entries]
    tampered = [e.id for e, h in zip(entries, recomputed) if h.hex() != e.leaf_hash]
    cp = latest_root(s)
    rebuilt = root(recomputed).hex()
    sig_ok = False
    if cp is not None:
        try:
            signing_key().public_key().verify(bytes.fromhex(cp.signature),
                                              checkpoint_message(cp.tree_size, cp.root))
            sig_ok = True
        except InvalidSignature:
            sig_ok = False
    root_ok = cp is not None and cp.tree_size == len(entries) and cp.root == rebuilt
    return {
        "ok": not tampered and root_ok and sig_ok,
        "size": len(entries),
        "signed_root": cp.root if cp else None,
        "recomputed_root": rebuilt,
        "signature_valid": sig_ok,
        "root_matches": root_ok,
        "tampered": tampered,
        "public_key": public_key_hex(),
    }


def proof_for(s: Session, entry_id: int) -> dict:
    entries = s.exec(select(AuditEntry).order_by(AuditEntry.id)).all()
    ids = [e.id for e in entries]
    if entry_id not in ids:
        raise KeyError(entry_id)
    index = ids.index(entry_id)
    stored = [bytes.fromhex(e.leaf_hash) for e in entries]
    cp = latest_root(s)
    leaf = leaf_hash(canonical(entries[index]))
    path = inclusion_proof(index, stored)
    ok = cp is not None and verify_inclusion(index, len(stored), leaf, path, bytes.fromhex(cp.root))
    return {"entry_id": entry_id, "index": index, "tree_size": len(stored),
            "leaf": leaf.hex(), "path": [p.hex() for p in path],
            "root": cp.root if cp else None, "verified": ok}
