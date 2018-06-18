import json as _json
import logging
from importlib import import_module

from django.utils import timezone

from api.indy.agent import Holder
from api.indy import eventloop

from von_agent.util import schema_key

from api_v2.models.Issuer import Issuer
from api_v2.models.Schema import Schema
from api_v2.models.Subject import Subject
from api_v2.models.CredentialType import CredentialType
from api_v2.models.Claim import Claim

from api_v2.models.Name import Name
from api_v2.models.Address import Address
from api_v2.models.Person import Person
from api_v2.models.Contact import Contact

logger = logging.getLogger(__name__)

PROCESSOR_FUNCTION_BASE_PATH = "api_v2.processor"

SUPPORTED_MODELS_MAPPING = {
    "name": Name,
    "address": Address,
    "person": Person,
    "contact": Contact,
}


class CredentialException(Exception):
    pass


class Credential(object):
    """A python-idiomatic representation of an indy credential
    
    Claim values are made available as class members.

    for example:

    ```json
    "postal_code": {
        "raw": "N2L 6P3",
        "encoded": "1062703188233012330691500488799027"
    }
    ```

    becomes:

    ```python
    self.postal_code = "N2L 6P3"
    ```

    on the class object.

    Arguments:
        credential_data {object} -- Valid credential data as sent by an issuer
    """

    def __init__(self, credential_data: object) -> None:
        self._raw = credential_data
        self._schema_id = credential_data["schema_id"]
        self._cred_def_id = credential_data["cred_def_id"]
        self._rev_reg_id = credential_data["rev_reg_id"]
        self._signature = credential_data["signature"]
        self._signature_correctness_proof = credential_data[
            "signature_correctness_proof"
        ]
        self._rev_reg = credential_data["rev_reg"]
        self._witness = credential_data["witness"]

        self._claim_attributes = []

        # Parse claim attributes into array
        # Values are available as class attributes
        claim_data = credential_data["values"]
        for claim_attribute in claim_data:
            self._claim_attributes.append(claim_attribute)

    def __getattr__(self, name: str):
        """Make claim values accessible on class instance"""
        try:
            claim_value = self.raw["values"][name]["raw"]
            return claim_value
        except KeyError:
            raise AttributeError(
                "'Credential' object has no attribute '{}'".format(name)
            )

    @property
    def raw(self) -> dict:
        """Accessor for raw credential data
        
        Returns:
            dict -- Python dict representation of raw credential data
        """
        return self._raw

    @property
    def json(self) -> str:
        """Accessor for json credential data
        
        Returns:
            str -- JSON representation of raw credential data
        """
        return _json.dumps(self._raw)

    @property
    def origin_did(self) -> str:
        """Accessor for schema origin did
        
        Returns:
            str -- origin did
        """
        return schema_key(self._schema_id).origin_did

    @property
    def schema_name(self) -> str:
        """Accessor for schema name
        
        Returns:
            str -- schema name
        """
        return schema_key(self._schema_id).name

    @property
    def schema_version(self) -> str:
        """Accessor for schema version
        
        Returns:
            str -- schema version
        """
        return schema_key(self._schema_id).version

    @property
    def claim_attributes(self) -> list:
        """Accessor for claim attributes
        
        Returns:
            list -- claim attributes
        """
        return self._claim_attributes


class CredentialManager(object):
    def __init__(
        self, credential: Credential, credential_definition_metadata: dict
    ) -> None:
        self.credential = credential
        self.credential_definition_metadata = credential_definition_metadata

    def process(self):
        # Get context for this credential if it exists
        try:
            issuer = Issuer.objects.get(did=self.credential.origin_did)
            schema = Schema.objects.get(
                origin_did=self.credential.origin_did,
                name=self.credential.schema_name,
                version=self.credential.schema_version,
            )
        except Issuer.DoesNotExist:
            raise CredentialException(
                "Issuer with did '{}' does not exist.".format(
                    self.credential.origin_did
                )
            )
        except Schema.DoesNotExist:
            raise CredentialException(
                "Schema with origin_did"
                + " '{}', name '{}', and version '{}' ".format(
                    self.credential.origin_did,
                    self.credential.schema_name,
                    self.credential.schema_version,
                )
                + " does not exist."
            )

        credential_type = CredentialType.objects.get(
            schema=schema, issuer=issuer
        )

        try:
            source_id = getattr(self.credential, credential_type.source_claim)
        except AttributeError as error:
            raise CredentialException(
                "Credential does not contain the configured source_claim "
                + "'{}'. Claims are: {}".format(
                    credential_type.source_claim,
                    ", ".join(self.credential.claim_attributes),
                )
            )

        credential = self.populate_application_database(
            credential_type, "source_id"
        )
        eventloop.do(self.store("source_id"))
        return credential

    def populate_application_database(self, credential_type, source_id):
        # Obtain required models from database

        # Create subject, credential, claim models
        subject, created = Subject.objects.get_or_create(source_id=source_id)

        credential = subject.credentials.create(
            subject=subject, credential_type=credential_type
        )

        # TODO: optimize into a single insert
        for claim_attribute in self.credential.claim_attributes:
            claim_value = getattr(self.credential, claim_attribute)
            Claim.objects.create(
                credential=credential, name=claim_attribute, value=claim_value
            )

        # Update optional models based on processor config
        processor_config = credential_type.processor_config
        if not processor_config:
            return credential.id

        # Iterate model types in processor mapping
        for i, model_mapper in enumerate(processor_config):
            model_name = model_mapper["model"]
            cardinality_fields = model_mapper.get("cardinality_fields") or []

            # We currently support 4 model types
            # see SUPPORTED_MODELS_MAPPING
            try:
                Model = SUPPORTED_MODELS_MAPPING[model_name]
            except KeyError as error:
                raise CredentialException(
                    "Unsupported model type '{}'".format(model_name)
                )

            # Iterate fields on model mapping config
            processed_values = {}
            for field in processor_config[i]["fields"]:
                field_data = processor_config[i]["fields"][field]

                # Get required values from config
                try:
                    _input = field_data["input"]
                    _from = field_data["from"]
                except KeyError as error:
                    raise CredentialException(
                        "Every field must specify 'input' and 'from' values."
                    )

                # Pocessor is optional
                try:
                    processor = field_data["processor"]
                except KeyError as error:
                    processor = None

                # Get model field value from string literal or claim value
                if _from == "value":
                    field_value = _input
                elif _from == "claim":
                    field_value = getattr(self.credential, _input)
                else:
                    raise CredentialException(
                        "Supported field from values are 'value' and 'claim'"
                        + " but received '{}'".format(_from)
                    )

                # If we have a processor config, build pipeline of functions
                # and run field value through pipeline
                if processor is not None:
                    pipeline = []
                    # Construct pipeline by dot notation. Last token is the function name
                    # and all preceeding dots denote path of module starting from
                    # `PROCESSOR_FUNCTION_BASE_PATH``
                    for function_path_with_name in processor:
                        function_path, function_name = function_path_with_name.rsplit(
                            ".", 1
                        )

                        # Does the file exist?
                        try:
                            function_module = import_module(
                                "{}.{}".format(
                                    PROCESSOR_FUNCTION_BASE_PATH, function_path
                                )
                            )
                        except ModuleNotFoundError as error:
                            raise CredentialException(
                                "No processor module named '{}'".format(
                                    function_path
                                )
                            )

                        # Does the function exist?
                        try:
                            function = getattr(function_module, function_name)
                        except AttributeError as error:
                            raise CredentialException(
                                "Module '{}' has no function '{}'.".format(
                                    function_path, function_name
                                )
                            )

                        # Build up a list of functions to call
                        pipeline.append(function)

                    # We want to run the pipeline in logical order
                    pipeline.reverse()

                    # Run pipeline
                    while len(pipeline) > 0:
                        function = pipeline.pop()
                        field_value = function(field_value)

                processed_values[field] = field_value

                # This is ugly. von-agent currently serializes null values
                # to the string 'None'
                if processed_values[field] == "None":
                    processed_values[field] = None

            model = None
            # Try to get an existing model based on cardinality_fields.
            # We always limit query by this subject and without an end_date.
            model_args = {
                "credentials__subject__id": subject.id,
                "end_date": None,
            }
            for cardinality_field in cardinality_fields:
                try:
                    model_args[cardinality_field] = processed_values[
                        cardinality_field
                    ]
                except KeyError as error:
                    raise CredentialException(
                        "Issuer configuration specifies field '{}' ".format(
                            cardinality_field
                        )
                        + "in cardinality_fields value does not exist in "
                        + "credential processor. Values are: {}".format(
                            ", ".join(list(processed_values.keys()))
                        )
                    )

            # If the issuer changes its `cardinality_fields` it's possible for
            # this query to return multiple records.
            #
            # To handle this, we always get the _last created_ record for this
            # subject, with no end_date, and with values in
            # `cardinality_fields` equal to their resulting values after
            # running through the function pipeline. We update the most
            # recently created record and we implicitly set the end_date
            # for `now` for all other returned records.
            try:
                query = (
                    Model.objects.filter(**model_args)
                    .order_by("-create_timestamp")
                    .distinct()
                )

                # We care about the most recent model if there
                # are more than one
                model = query[0]
                # If there are other records for this query, then the issuer
                # changed its `cardinality_fields` to something less specific
                # than it was previously.
                query.exclude(pk=model.id).update(end_date=timezone.now())
            except IndexError as error:
                logger.warn(error)

            # If it doesn't exist, we create a new one
            if not model:
                model = Model()

            # Either way, we update the fields based on results of
            # mapping and processor
            for value in processed_values:
                setattr(model, value, processed_values[value])

            # Save and associate with credential
            model.save()
            model.credentials.add(credential)

        return credential.id

    async def store(self, legal_entity_id):

        # Store credential in wallet
        async with Holder(legal_entity_id) as holder:
            await holder.store_cred(
                self.credential.json,
                _json.dumps(self.credential_definition_metadata),
            )
