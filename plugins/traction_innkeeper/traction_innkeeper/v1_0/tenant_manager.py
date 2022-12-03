import logging
import uuid
from datetime import datetime, timedelta

import bcrypt
from aries_cloudagent.core.error import BaseError
from aries_cloudagent.core.profile import Profile
from aries_cloudagent.messaging.models.base import BaseModelError
from aries_cloudagent.multitenant.base import BaseMultitenantManager
from aries_cloudagent.storage.error import StorageError
from aries_cloudagent.wallet.models.wallet_record import WalletRecord

from .config import TractionInnkeeperConfig
from .models import TenantRecord, ReservationRecord


class TenantManager:
    """Class for managing tenants."""

    def __init__(self, profile: Profile, config: TractionInnkeeperConfig):
        """
        Initialize a TenantManager.

        Args:
            profile: The profile for this tenant manager
        """
        self._profile = profile
        self._logger = logging.getLogger(__name__)
        self._config = config

    @property
    def profile(self) -> Profile:
        """
        Accessor for the current profile.

        Returns:
            The profile for this tenant manager

        """
        return self._profile

    async def create_wallet(
            self,
            wallet_name: str = None,
            wallet_key: str = None,
            extra_settings: dict = {},
            tenant_id: str = None,
    ):
        if not wallet_name:
            wallet_name = str(uuid.uuid4())  # can we generate random words?

        if not wallet_key:
            wallet_key = str(uuid.uuid4())

        try:
            key_management_mode = WalletRecord.MODE_MANAGED
            wallet_webhook_urls = []
            wallet_dispatch_type = "base"

            settings = {
                "wallet.type": self._profile.context.settings["wallet.type"],
                "wallet.name": wallet_name,
                "wallet.key": wallet_key,
                "wallet.webhook_urls": wallet_webhook_urls,
                "wallet.dispatch_type": wallet_dispatch_type,
            }
            settings.update(extra_settings)

            label = wallet_name
            settings["default_label"] = label

            multitenant_mgr = self._profile.inject(BaseMultitenantManager)

            wallet_record = await multitenant_mgr.create_wallet(
                settings, key_management_mode
            )
            token = await self.get_token(wallet_record)
        except BaseError as err:
            self._logger.error(f"Error creating wallet ('{wallet_name}').", err)
            raise err

        # ok, all is good, then create a tenant record
        tenant = await self.create_tenant(wallet_record.wallet_id, tenant_id)

        return tenant, wallet_record, token

    async def get_token(self, wallet_record: WalletRecord):
        try:
            multitenant_mgr = self._profile.inject(BaseMultitenantManager)
            token = await multitenant_mgr.create_auth_token(
                wallet_record, wallet_record.wallet_key
            )
        except BaseError as err:
            self._logger.error(
                f"Error getting token for wallet ('{wallet_record.wallet_name}').", err
            )
            raise err
        return token

    async def get_token_by_wallet_id(self, wallet_id: str):
        try:
            async with self._profile.session() as session:
                wallet_record = await WalletRecord.retrieve_by_id(session, wallet_id)
                token = await self.get_token(wallet_record)
        except (StorageError, BaseModelError):
            self._logger.info(f"Wallet not found with ID '{wallet_id}'")
        return token

    async def create_tenant(self, wallet_id: str, tenant_id: str = None):
        try:
            async with self._profile.session() as session:
                wallet_record = await WalletRecord.retrieve_by_id(session, wallet_id)
                tenant: TenantRecord = TenantRecord(
                    tenant_id=tenant_id,
                    tenant_name=wallet_record.wallet_name,
                    wallet_id=wallet_record.wallet_id,
                    new_with_id=tenant_id is not None,
                )
                await tenant.save(session, reason="New tenant")
                # self._logger.info(tenant)
        except Exception as err:
            self._logger.error(err)
            raise err

        return tenant

    async def create_innkeeper(self):
        config = self._config.innkeeper_wallet
        tenant_id = config.tenant_id
        wallet_name = config.wallet_name
        wallet_key = config.wallet_key

        # does innkeeper already exist?
        tenant_record = None
        wallet_record = None
        try:
            async with self._profile.session() as session:
                tenant_record = await TenantRecord.retrieve_by_id(session, tenant_id)
                wallet_record = await WalletRecord.retrieve_by_id(
                    session, tenant_record.wallet_id
                )
        except (StorageError, BaseModelError):
            self._logger.info(f"Tenant not found with ID '{tenant_id}'")

        if tenant_record and wallet_record:
            self._logger.info(f"'{wallet_name}' wallet exists.")
            token = await self.get_token(wallet_record)
        else:
            self._logger.info(f"creating '{wallet_name}' wallet...")
            tenant_record, wallet_record, token = await self.create_wallet(
                wallet_name, wallet_key, {"wallet.innkeeper": True}, tenant_id
            )
            self._logger.info(f"...created '{wallet_name}' tenant and wallet.")

        print(f"\ntenant.tenant_name = {tenant_record.tenant_name}")
        print(f"tenant.tenant_id = {tenant_record.tenant_id}")
        print(f"tenant.wallet_id = {tenant_record.wallet_id}")
        print(f"wallet.wallet_name = {wallet_record.wallet_name}")
        print(f"wallet.wallet_id = {wallet_record.wallet_id}")
        _key = wallet_record.wallet_key if config.print_key else "********"
        print(f"wallet.wallet_key = {_key}\n")
        if config.print_token:
            print(f"Bearer {token}\n")

    def generate_reservation_token_data(self):
        _pwd = str(uuid.uuid4())
        self._logger.info(f"_pwd = {_pwd}")

        _salt = bcrypt.gensalt()
        self._logger.info(f"_salt = {_salt}")

        _hash = bcrypt.hashpw(_pwd.encode("utf-8"), _salt)
        self._logger.info(f"_hash = {_hash}")

        minutes = self._config.reservation.expiry_minutes
        _expiry = datetime.utcnow() + timedelta(minutes=minutes)
        self._logger.info(f"_expiry = {_expiry}")

        return _pwd, _salt, _hash, _expiry

    def check_reservation_password(
            self, reservation_pwd: str, reservation: ReservationRecord
    ):
        # make a hash from passed in value with saved salt...
        reservation_token = bcrypt.hashpw(
            reservation_pwd.encode("utf-8"),
            reservation.reservation_token_salt.encode("utf-8"),
        )
        # check the passed in value/hash against the calculated hash.
        checkpw = bcrypt.checkpw(reservation_pwd.encode("utf-8"), reservation_token)
        self._logger.debug(
            f"bcrypt.checkpw(reservation_pwd.encode('utf-8'), reservation_token) = {checkpw}"
        )

        # check the passed in value against the saved hash
        checkpw2 = bcrypt.checkpw(
            reservation_pwd.encode("utf-8"),
            reservation.reservation_token_hash.encode("utf-8"),
        )
        self._logger.debug(
            f"bcrypt.checkpw(reservation_pwd.encode('utf-8'), reservation.reservation_token_hash.encode('utf-8')) = {checkpw2}"
        )

        if checkpw and checkpw2:
            # if password is correct, then return the string equivalent...
            return reservation_token.decode("utf-8")
        else:
            # else return None
            return None