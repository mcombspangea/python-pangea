# Copyright 2022 Pangea Cyber Corporation
# Author: Pangea Cyber Corporation

import json
import typing as t

from pangea.response import JSONObject, PangeaResponse
from .base import ServiceBase

from .audit_util import (
    decode_consistency_proof,
    decode_hash,
    decode_membership_proof,
    get_arweave_published_roots,
    verify_consistency_proof,
    verify_membership_proof,
)

SupportedFields = [
    "actor",
    "action",
    "status",
    "source",
    "target",
]

SupportedJSONFields = [
    "message",
    "new",
    "old",
]


class AuditSearchResponse(object):
    """
    Wrap the base Response object to include search pagination support
    """

    def __init__(self, response, data):
        self.response = response
        self.data = data

    def __getattr__(self, attr):
        return getattr(self.response, attr)

    def next(self) -> t.Optional[t.Dict[str, t.Any]]:
        if self.count < self.total:
            return self.data | {"last": self.response.result.last}
        else:
            return None

    @property
    def total(self) -> int:
        if self.success:
            last = self.result["last"]
            total = last.split("|")[1]  # TODO: update once `last` returns an object
            return int(total)
        else:
            return 0

    @property
    def count(self) -> int:
        if self.success:
            last = self.result["last"]
            count = last.split("|")[0]  # TODO: update once `last` returns an object
            return int(count)
        else:
            return 0


class Audit(ServiceBase):
    """Audit service client.

    Provides methods to interact with Pangea Audit Service:
        https://docs.dev.pangea.cloud/docs/api/log-an-entry

    The following information is needed:
        PANGEA_TOKEN - service token which can be found on the Pangea User
            Console at https://console.dev.pangea.cloud/project/tokens
        AUDIT_CONFIG_ID - Configuration ID which can be found on the Pangea
            User Console at https://console.dev.pangea.cloud/service/audit

    Examples:
        import os

        # Pangea SDK
        from pangea.config import PangeaConfig
        from pangea.services import Audit

        PANGEA_TOKEN = os.getenv("PANGEA_TOKEN")
        AUDIT_CONFIG_ID = os.getenv("AUDIT_CONFIG_ID")

        audit_config = PangeaConfig(base_domain="dev.pangea.cloud", config_id=AUDIT_CONFIG_ID)

        # Setup Pangea Audit service
        audit = Audit(token=PANGEA_TOKEN, config=audit_config)
    """

    response_class = AuditSearchResponse
    service_name = "audit"
    version = "v1"
    config_id_header = "X-Pangea-Audit-Config-ID"

    # In case of Arweave failure, ask the server for the roots
    allow_server_roots = True

    def log(self, event: dict, verify: bool = False) -> PangeaResponse:
        """
        Log an entry

        Create a log entry in the Secure Audit Log.

        Args:
            input (dict): A structured dict describing an auditable activity.
            verify (bool):

        Returns:
            A PangeaResponse where the hash of event data and optional verbose
                results are returned in the response.result field.
                Available response fields can be found at:
                https://docs.dev.pangea.cloud/docs/api/audit#log-an-entry

        Examples:
            audit_data = {
                "action": "add_employee",
                "actor": "Mariah Carey",
                "target": "mariah@mariahcarey.com",
                "status": "success",
                "message": "Resume accepted",
                "new": { "status": "employed" },
                "source": "web",
            }

            response = audit.log(input=audit_data)

            response contains:
            {
                "request_id": "prq_ttd3wa7pm4fbut73tlc2r7gi5tcelfcq",
                "request_time": "2022-07-06T23:46:57.537Z",
                "response_time": "2022-07-06T23:46:57.556Z",
                "status_code": 200,
                "status": "success",
                "result": {
                    "hash": "eba9cd62d2f765a462b6a1c246e18dcb20411c5ee6f6ba4b6d315f455fdfb38a"
                },
                "summary": "Logged 1 record(s)"
            }
        """

        endpoint_name = "log"

        data: t.Dict[str, t.Any] = {"event": {}, "return_hash": True}

        for name in SupportedFields:
            if name in event:
                data["event"][name] = event[name]

        for name in SupportedJSONFields:
            if name in event:
                data["event"][name] = json.dumps(event[name])

        if "message" not in data["event"]:
            raise Exception(f"Error: missing required field, no `message` provided")

        resp = self.request.post(endpoint_name, data=data)
        return resp

    def search(
        self,
        query: str = "",
        sources: list = [],
        page_size: int = 20,
        start: str = "",
        end: str = "",
        last: str = "",
        verify: bool = False,
    ) -> AuditSearchResponse:
        """
        Search for events

        Search for events that match the provided search criteria.

        Args:
            query (str, optional): Natural search string; list of keywords with optional `<option>:<value>` qualifiers.
            The following optional qualifiers are supported:
            - action: - actor: - message: - new: - old: - status: - target:`
            sources (list, optional): A list of sources that the search can apply to.
            If empty or not provided, matches only the default source.
            page_size (int, optional): Maximum number of records to return per page. Default is 20.
            start (str, optional): The start of the time range to perform the search on.
            end (str, optional): The end of the time range to perform the search on.
            All records up to the latest if left out.
            last (str, optional): If set, the last value from the response to fetch the next page from.
            verify (bool, optional):

        Returns:
            An AuditSearchResponse where the list of matched events is returned in the
                response.result field.  Available response fields can be found at:
                https://docs.dev.pangea.cloud/docs/api/audit#search-for-events

        Examples:
            response = audit.search("Resume accepted", page_size=10)

            response contains:
            {
                "request_id": "prq_cdrlelm2xm66kyeughcyokpg6y5mcewv",
                "request_time": "2022-07-06T23:49:09.034Z",
                "response_time": "2022-07-06T23:49:09.044Z",
                "status_code": 200,
                "status": "success",
                "result": {
                    "events": [
                        {
                            "event": {
                                "action": "update_employee",
                                "actor": "manager@acme.co",
                                "message": "\"{updating employee}\"",
                                "received_at": "2022-06-29T15:25:00.547967+00:00",
                                "source": "web",
                                "status": "pending",
                                "target": "jane.smith@gmail.com"
                            },
                            "hash": "df91bf7cc7500160525dc0959ef1c5387a998d1f68851058f427f5ac7ac8d4fb",
                            "leaf_index": 5,
                            "membership_proof": "r:34d9eb62de1d039870abd4a62d7e08be2ed4065c66b435f19a973beea53fefef,r:12bb5ab67c4a8a44439bfddbd93edc656f6bdddf6d61754364ba4eb845125aa4,r:47ea9cb1c54c3357ba1680d48c1ad33d29af53dcef5077d4f6d48ed7705fc09c,r:317b823fa5ca93e3d67d537863c9abe133128e9d26b5112b72be2ff8dafa6ceb,l:89ec1a955393bf1b5eefe29415eec8738bb00b974279a5d96bcbe9b5826f1905,l:c7610ea9a181ab9263d9ec0c0bb307480eb2f6a28c3065d1a02ba89f2268a934"
                        }
                    ],
                    "last": "1|1|",
                    "root": {
                    "consistency_proof": [
                        "x:89ec1a955393bf1b5eefe29415eec8738bb00b974279a5d96bcbe9b5826f1905,r:730315ba3fe23d9724bab2375105934c9097f08e12567d33aaf3ba36ef7eb750,l:c7610ea9a181ab9263d9ec0c0bb307480eb2f6a28c3065d1a02ba89f2268a934",
                        "x:c7610ea9a181ab9263d9ec0c0bb307480eb2f6a28c3065d1a02ba89f2268a934,r:639b0b5694aaeb70aa75380956f88b10e3507a67b94fb58c96986cf34b705344"
                    ],
                    "published_at": "2022-06-29T16:25:11.110758Z",
                    "root_hash": "d2da009f4778cd29b5bfec823f0952ee63bd1585139c4c09ddafb330ee84c27f",
                    "size": 6,
                    "tree_name": "ffaba963b14d03a695714c39f2d324c1ed8c482fcdcd224c57f5040867567de4",
                    "url": "https://arweave.net/tx/vUe6aAH4761WIeC8FMMSd1_51X6KLlGzJjuWYAa0u5g/data/"
                    }
                },
                "summary": "Found 1 record(s)"
            }
        """

        endpoint_name = "search"

        params = {
            "query": query,
            "sources": sources,
            "page_size": page_size,
            "start": start,
            "end": end,
            "last": last,
            "verify": verify,
        }

        if not (isinstance(page_size, int) and page_size > 0):
            raise Exception("The 'page_size' argument must be a positive integer > 0")

        data = {
            "query": query,
            "include_membership_proof": True,
            "include_hash": True,
            "include_root": True,
            "page_size": page_size,
        }

        if start:
            data["start"] = start

        if end:
            data["end"] = end

        if last:
            data["last"] = last

        if sources:
            data["sources"] = sources

        response = self.request.post(endpoint_name, data=data)
        if not response.success:
            return AuditSearchResponse(response, data)

        root = response.result.root

        # if there is no root, we don't have any record migrated to cold. We cannot verify any proof
        if not root:
            response.result.root = {}
            response.result.published_roots = {}
            return AuditSearchResponse(response, data)

        if verify is True:
            for audit in response.result.events:
                # verify membership proofs
                if not self.verify_membership_proof(response.result.root, audit):
                    raise Exception(f"Error: Membership proof failed.")

                # verify consistency proofs
                if not self.verify_consistency_proof(response.result.root, audit):
                    raise Exception(f"Error: Consistency proof failed.")

        response_wrapper = AuditSearchResponse(response, params)
        return response_wrapper

    def search_next(self, response: AuditSearchResponse):
        params = response.next()
        if not params:
            return None
        else:
            return self.search(**params)

    def update_published_roots(
        self, pub_roots: t.Dict[int, t.Optional[JSONObject]], result: JSONObject
    ):
        tree_sizes = set()
        for audit in result.events:
            leaf_index = audit.get("leaf_index")
            if leaf_index is not None:
                tree_sizes.add(leaf_index + 1)
                if leaf_index > 0:
                    tree_sizes.add(leaf_index)
        tree_sizes.add(result.root.size)

        tree_sizes.difference_update(pub_roots.keys())
        if tree_sizes:
            arweave_roots = get_arweave_published_roots(
                result.root.tree_name, list(tree_sizes) + [result.root.size]
            )
        else:
            arweave_roots = {}

        # fill the missing roots from the server (if allowed)
        for tree_size in tree_sizes:
            pub_root = None
            if tree_size in arweave_roots:
                pub_root = JSONObject(arweave_roots[tree_size])
                pub_root.source = "arweave"
            elif self.allow_server_roots:
                resp = self.root(tree_size)
                if resp.success:
                    pub_root = resp.result
                    pub_root.source = "pangea"
            pub_roots[tree_size] = pub_root

    def can_verify_membership_proof(self, event: JSONObject) -> bool:
        return event.get("membership_proof") is not None

    def verify_membership_proof(self, root: JSONObject, event: JSONObject) -> bool:
        if not self.allow_server_roots and root.source != "arweave":
            return False

        # TODO: uncomment when audit created field bug is fixed
        # canon = canonicalize_log(event.event)
        # node_hash_enc = hash_data(canon)
        node_hash_enc = event.hash
        node_hash = decode_hash(node_hash_enc)
        root_hash = decode_hash(root.root_hash)
        proof = decode_membership_proof(event.membership_proof)
        return verify_membership_proof(node_hash, root_hash, proof)

    def can_verify_consistency_proof(self, event: JSONObject) -> bool:
        leaf_index = event.get("leaf_index")
        return leaf_index is not None and leaf_index > 0

    def verify_consistency_proof(
        self, pub_roots: t.Dict[int, t.Optional[JSONObject]], event: JSONObject
    ) -> bool:
        leaf_index = event["leaf_index"]
        curr_root = pub_roots.get(leaf_index + 1)
        prev_root = pub_roots.get(leaf_index)

        if not curr_root or not prev_root:
            return False

        if not self.allow_server_roots and (
            curr_root.source != "arweave" or prev_root.source != "arweave"
        ):
            return False

        curr_root_hash = decode_hash(curr_root.root_hash)
        prev_root_hash = decode_hash(prev_root.root_hash)
        proof = decode_consistency_proof(curr_root.consistency_proof)
        return verify_consistency_proof(curr_root_hash, prev_root_hash, proof)

    def root(self, tree_size: int = 0) -> AuditSearchResponse:
        """
        Retrieve tamperproof verification

        Returns current root hash and consistency proof.

        Args:
            tree_size (int): The size of the tree (the number of records)

        Returns:
            An AuditSearchResponse.

        Examples:
            response = audit.root(tree_size=7)
        """
        endpoint_name = "root"

        data = {}

        if tree_size > 0:
            data["tree_size"] = tree_size

        response = self.request.post(endpoint_name, data=data)
        return AuditSearchResponse(response, data)
