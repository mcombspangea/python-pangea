# Copyright 2022 Pangea Cyber Corporation
# Author: Pangea Cyber Corporation
import base64
import json
import logging
import os
from binascii import hexlify, unhexlify
from dataclasses import dataclass
from hashlib import sha256
from typing import Dict, List

import requests

Hash = bytes


JSON_TYPES = [int, float, str, bool]


logger = logging.getLogger("audit")


ARWEAVE_BASE_URL = "https://arweave.net"


@dataclass
class MembershipProofItem:
    side: str
    node_hash: Hash


MembershipProof = List[MembershipProofItem]


@dataclass
class ConsistencyProofItem:
    node_hash: Hash
    proof: MembershipProof


ConsistencyProof = List[ConsistencyProofItem]


@dataclass
class BufferRoot:
    tree_id: str
    cold_tree_size: int
    tree_size: int
    root_hash: Hash


def decode_buffer_root(enc_buffer_root: str) -> BufferRoot:
    parts = enc_buffer_root.split(",")
    return BufferRoot(
        tree_id=parts[0], cold_tree_size=int(parts[1]), tree_size=int(parts[2]), root_hash=decode_hash(parts[3])
    )

def encode_buffer_root(buffer_root: BufferRoot) -> str:
    return f"{buffer_root.tree_id},{buffer_root.cold_tree_size},{buffer_root.tree_size},{encode_hash(buffer_root.root_hash)}"
    
def decode_hash(hexhash) -> Hash:
    return unhexlify(hexhash.encode("utf8"))

def encode_hash(hash_: Hash) -> str:
    return hexlify(hash_).decode("utf8")

def hash_pair(hash1: Hash, hash2: Hash) -> Hash:
    return sha256(hash1 + hash2).digest()

def verify_hash(hash1: Hash, hash2: Hash) -> bool:
    return (hash1 == hash2)

def b64encode(data: bytes) -> bytes:
    ret = None
    if data is not None:    
        ret = base64.b64encode(data)
    return ret

def b64encode_ascii(data: bytes) -> str:
    ret = None
    if data is not None:    
        ret = base64.b64encode(data).decode("ascii")
    return ret

def b64decode(data) -> bytes:
    ret = None
    if data is not None:
        ret = base64.b64decode(data)
    return ret

def decode_membership_proof(data: str) -> MembershipProof:
    proof: MembershipProof = []

    if data:
        for item in data.split(","):
            parts = item.split(":")
            proof.append(
                MembershipProofItem(
                    side="left" if parts[0] == "l" else "right",
                    node_hash=decode_hash(parts[1]),
                )
            )
    return proof


def decode_consistency_proof(data: List[str]) -> ConsistencyProof:
    root_proof = []

    if data:
        for item in data:
            ndx = item.index(",")
            root_proof.append(
                ConsistencyProofItem(
                    node_hash=decode_hash(item[:ndx].split(":")[1]),
                    proof=decode_membership_proof(item[ndx + 1 :]),
                )
            )
    return root_proof


def verify_membership_proof(node_hash: Hash, root_hash: Hash, proof: MembershipProof) -> bool:
    for proof_item in proof:
        proof_hash = proof_item.node_hash
        node_hash = hash_pair(proof_hash, node_hash) if proof_item.side == "left" else hash_pair(node_hash, proof_hash)
    return root_hash == node_hash


def canonicalize_json(message: dict) -> bytes:
    """Convert log to valid JSON types and apply RFC-7159 (Canonical JSON)"""

    def _default(obj):
        if not any(isinstance(obj, typ) for typ in JSON_TYPES):
            return str(obj)
        else:
            return obj

    # stringify invalid JSON types before canonicalizing
    return json.dumps(
        message, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True, default=_default
    ).encode("utf-8")


def hash_bytes(data: bytes) -> bytes:
    return sha256(data).digest()


def hash_str(data: str) -> str:
    return sha256(bytes(data, "utf8")).hexdigest()


def hash_dict(data: dict) -> bytes:
    return sha256(canonicalize_json(data)).digest()


def base64url_decode(input_parameter):
    rem = len(input_parameter) % 4
    if rem > 0:
        input_parameter += "=" * (4 - rem)
    return base64.urlsafe_b64decode(input_parameter)


def arweave_transaction_url(trans_id: str):
    return f"{ARWEAVE_BASE_URL}/{trans_id}/"


def arweave_graphql_url():
    return f"{ARWEAVE_BASE_URL}/graphql"


def get_arweave_published_roots(tree_name: str, tree_sizes: List[int]) -> Dict[int, dict]:
    if len(tree_sizes) == 0:
        return {}

    logger.debug(f"Querying Arweave for published roots of sizes: {', '.join(map(str, tree_sizes))}")

    query = """
    {
        transactions(
          tags: [
                {
                    name: "tree_size"
                    values: [{tree_sizes}]
                },
                {
                    name: "tree_name"
                    values: ["{tree_name}"]
                }
            ]
        ) {
            edges {
                node {
                    id
                    tags {
                        name
                        value
                    }
                }
            }
        }
    }
    """.replace(
        "{tree_sizes}", ", ".join(f'"{tree_size}"' for tree_size in tree_sizes)
    ).replace(
        "{tree_name}", tree_name
    )

    resp = requests.post(arweave_graphql_url(), json={"query": query})
    if resp.status_code != 200:
        logger.error(f"Error querying Arweave: {resp.reason}")
        return {}

    ans: Dict[int, dict] = {}
    data = resp.json()
    tree_size = None

    for edge in data.get("data", {}).get("transactions", {}).get("edges", []):
        try:
            node_id = edge.get("node").get("id")
            tree_size = next(
                tag.get("value") for tag in edge.get("node").get("tags", []) if tag.get("name") == "tree_size"
            )

            url = arweave_transaction_url(node_id)

            # TODO: do all the requests concurrently
            resp2 = requests.get(url)
            if resp2.status_code != 200:
                logger.error(f"Error fetching published root for size {tree_size}: {resp2.reason}")
            elif resp2.text == "Pending":
                logger.warning(f"Published root for size {tree_size} is pending")
            else:
                ans[int(tree_size)] = json.loads(resp2.text)
        except Exception as e:
            logger.error(f"Error decoding published root for size {tree_size}: {str(e)}")

    return ans


def verify_consistency_proof(new_root: Hash, prev_root: Hash, proof: ConsistencyProof) -> bool:

    # check the prev_root
    logger.debug("Calculating the proof for the old root")
    root_hash = proof[0].node_hash
    for item in proof[1:]:
        root_hash = hash_pair(item.node_hash, root_hash)

    logger.debug("Comparing the old root with the hash generated from the proof")
    if root_hash != prev_root:
        return False

    logger.debug("Verifying the proofs for the new root")
    for item in proof:
        if not verify_membership_proof(item.node_hash, new_root, item.proof):
            return False

    return True

def get_root_filename():
    token = os.getenv("PANGEA_TOKEN", "")
    config_id = os.getenv("AUDIT_CONFIG_ID", "")

    root_id = token + "-" + config_id
    root_id_filename = hash_str(root_id)

    return root_id_filename     
