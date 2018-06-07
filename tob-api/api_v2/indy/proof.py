import json
import logging
from collections import namedtuple

from api.indy.agent import Holder
from api.indy import eventloop

from api_v2.indy.proof_request import ProofRequest

logger = logging.getLogger(__name__)


Filter = namedtuple("Filter", "claim_name claim_value")


class ProofManager(object):
    def __init__(self, proof_request: ProofRequest, source_id: str) -> None:
        self.source_id = source_id
        self.proof_request = proof_request
        self.filters = []

    def add_filter(self, claim_name: str, claim_value: str):
        self.filters.append(Filter(claim_name, claim_value))

    def construct_proof(self):
        return eventloop.do(self.construct_proof_async())

    async def construct_proof_async(self):
        async with Holder(self.source_id) as holder:
            logger.info(self.proof_request.json)
            referents, credentials_for_proof_request = await holder.get_creds(
                self.proof_request.json
            )

            credentials_for_proof_request = json.loads(
                credentials_for_proof_request
            )

            # Construct the required payload to create proof
            requested_credentials = {}
            requested_credentials["self_attested_attributes"] = {}
            requested_credentials["requested_predicates"] = {}
            requested_credentials["requested_attributes"] = {}

            for claim_name in credentials_for_proof_request["attrs"]:
                requested_credentials["requested_attributes"][claim_name] = {}
                requested_credentials["requested_attributes"][claim_name][
                    "revealed"
                ] = True
                requested_credentials["requested_attributes"][claim_name][
                    "cred_id"
                ] = credentials_for_proof_request["attrs"][claim_name][0][
                    "cred_info"
                ][
                    "referent"
                ]

            proof = await holder.create_proof(
                self.proof_request.dict,
                credentials_for_proof_request,
                requested_credentials,
            )

            return json.loads(proof)
