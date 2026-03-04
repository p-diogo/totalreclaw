"""
Pimlico paymaster integration for TotalReclaw Server.

Handles the full lifecycle of a gas-sponsored ERC-4337 UserOperation:

    1. sponsor_user_operation  — Get gas estimates and paymaster signature
    2. submit_user_operation   — Submit the signed UserOp to the bundler
    3. get_user_op_receipt     — Poll for the on-chain receipt

All communication with Pimlico uses raw JSON-RPC over httpx (no SDK).

Pimlico API endpoint format:
    https://api.pimlico.io/v2/{chainId}/rpc?apikey={apiKey}

JSON-RPC methods used:
    pm_getPaymasterStubData   — Gas estimation with paymaster stub
    pm_getPaymasterData       — Actual paymaster signature for the UserOp
    eth_sendUserOperation     — Submit to bundler
    eth_getUserOperationReceipt — Get receipt after inclusion
    eth_getUserOperationByHash  — Get UserOp details
"""
import logging
from typing import Any, Optional

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

# JSON-RPC request ID counter (module-level, no thread safety needed for async)
_rpc_id = 0


def _next_rpc_id() -> int:
    """Return a monotonically increasing JSON-RPC request ID."""
    global _rpc_id
    _rpc_id += 1
    return _rpc_id


class PaymasterServiceError(Exception):
    """Raised when a Pimlico JSON-RPC call fails."""

    def __init__(
        self,
        message: str,
        rpc_error: Optional[dict] = None,
        status_code: Optional[int] = None,
    ):
        self.message = message
        self.rpc_error = rpc_error
        self.status_code = status_code
        super().__init__(message)


class PaymasterService:
    """
    Stateless service that wraps Pimlico JSON-RPC calls for ERC-4337
    UserOperation sponsorship, submission, and receipt polling.

    All methods are async and use httpx.AsyncClient for HTTP transport.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        chain_id: Optional[int] = None,
        entry_point: Optional[str] = None,
        rpc_url: Optional[str] = None,
    ):
        """
        Initialize the PaymasterService.

        All parameters are optional and fall back to Settings if not provided.
        This allows overriding for tests without touching environment variables.

        Args:
            api_key: Pimlico API key. Falls back to settings.pimlico_api_key.
            chain_id: Chain ID (100 for Gnosis, 10200 for Chiado).
            entry_point: EntryPoint contract address (ERC-4337 v0.7).
            rpc_url: Full Pimlico RPC URL (overrides api_key + chain_id).
        """
        settings = get_settings()
        self.api_key = api_key or settings.pimlico_api_key
        self.chain_id = chain_id or settings.pimlico_chain_id
        self.entry_point = entry_point or settings.entry_point_address

        if rpc_url:
            self.rpc_url = rpc_url
        else:
            self.rpc_url = settings.pimlico_rpc_url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def sponsor_user_operation(
        self,
        user_op: dict,
        wallet_address: str,
        sponsorship_policy_id: Optional[str] = None,
    ) -> dict:
        """
        Send a UserOp to Pimlico for gas estimation and paymaster signature.

        This is a two-step process:
            1. pm_getPaymasterStubData — Estimate gas limits with a paymaster
               stub signature. The response contains gas estimates and a stub
               paymasterAndData field the client uses for signature generation.
            2. pm_getPaymasterData — After the client has signed the UserOp
               with the stub gas values, this returns the real paymaster
               signature (paymasterAndData) ready for submission.

        For simplicity, this method calls both in sequence. The caller
        provides the unsigned UserOp; this method returns the fully
        sponsored UserOp with gas estimates and paymaster data filled in.

        Args:
            user_op: The UserOperation dict (sender, nonce, callData, etc.).
                     Gas fields and paymasterAndData may be empty/stub.
            wallet_address: The sender's Smart Account address (for logging).
            sponsorship_policy_id: Optional Pimlico sponsorship policy ID.
                                   If set, included in the context parameter.

        Returns:
            The UserOperation dict with gas estimates and paymaster fields
            populated (callGasLimit, verificationGasLimit, preVerificationGas,
            paymasterAndData, etc.).

        Raises:
            PaymasterServiceError: If the Pimlico API returns an error or is
                                    unreachable.
        """
        if not self.api_key:
            raise PaymasterServiceError(
                "PIMLICO_API_KEY not configured. Cannot sponsor UserOperations."
            )

        # Build context with optional sponsorship policy
        context: dict[str, Any] = {}
        if sponsorship_policy_id:
            context["sponsorshipPolicyId"] = sponsorship_policy_id

        # Step 1: Get stub data (gas estimates + stub paymaster signature)
        stub_params: list[Any] = [
            user_op,
            self.entry_point,
            hex(self.chain_id),
        ]
        if context:
            stub_params.append(context)

        stub_result = await self._rpc_call(
            "pm_getPaymasterStubData", stub_params
        )

        # Merge stub gas estimates into the UserOp
        sponsored_op = {**user_op}
        if isinstance(stub_result, dict):
            # ERC-7677 response fields
            for field in (
                "paymasterAndData",
                "paymaster",
                "paymasterData",
                "paymasterVerificationGasLimit",
                "paymasterPostOpGasLimit",
                "callGasLimit",
                "verificationGasLimit",
                "preVerificationGas",
            ):
                if field in stub_result:
                    sponsored_op[field] = stub_result[field]

        logger.info(
            "Paymaster stub data obtained",
            extra={
                "wallet_address": wallet_address,
                "chain_id": self.chain_id,
            },
        )

        # Step 2: Get actual paymaster data (real signature)
        data_params: list[Any] = [
            sponsored_op,
            self.entry_point,
            hex(self.chain_id),
        ]
        if context:
            data_params.append(context)

        data_result = await self._rpc_call(
            "pm_getPaymasterData", data_params
        )

        # Merge real paymaster signature into the UserOp
        if isinstance(data_result, dict):
            for field in (
                "paymasterAndData",
                "paymaster",
                "paymasterData",
                "paymasterVerificationGasLimit",
                "paymasterPostOpGasLimit",
            ):
                if field in data_result:
                    sponsored_op[field] = data_result[field]

        logger.info(
            "UserOp sponsored successfully",
            extra={
                "wallet_address": wallet_address,
                "chain_id": self.chain_id,
                "sender": user_op.get("sender"),
            },
        )

        return sponsored_op

    async def submit_user_operation(self, signed_user_op: dict) -> str:
        """
        Submit a signed, sponsored UserOp to the Pimlico bundler.

        The UserOp must already have:
            - A valid user signature (from the client's seed-derived key)
            - Paymaster data (from sponsor_user_operation)
            - Gas estimates filled in

        Args:
            signed_user_op: The fully signed and sponsored UserOperation.

        Returns:
            The UserOperation hash (hex string). Use this to poll for receipt.

        Raises:
            PaymasterServiceError: If the bundler rejects the UserOp or is
                                    unreachable.
        """
        if not self.api_key:
            raise PaymasterServiceError(
                "PIMLICO_API_KEY not configured. Cannot submit UserOperations."
            )

        result = await self._rpc_call(
            "eth_sendUserOperation",
            [signed_user_op, self.entry_point],
        )

        if not isinstance(result, str):
            raise PaymasterServiceError(
                f"Bundler returned unexpected result type: {type(result)}",
                rpc_error={"result": result},
            )

        user_op_hash = result

        logger.info(
            "UserOp submitted to bundler",
            extra={
                "user_op_hash": user_op_hash,
                "sender": signed_user_op.get("sender"),
                "chain_id": self.chain_id,
            },
        )

        return user_op_hash

    async def get_user_op_receipt(
        self, user_op_hash: str
    ) -> Optional[dict]:
        """
        Get the receipt for a submitted UserOperation.

        The receipt is available after the bundler includes the UserOp in a
        bundle transaction and it is mined on-chain. Returns None if the
        UserOp is still pending.

        Args:
            user_op_hash: The UserOperation hash returned by submit_user_operation.

        Returns:
            The receipt dict containing transaction hash, block number, gas
            used, etc. Returns None if the UserOp is not yet mined.

        Raises:
            PaymasterServiceError: If the RPC call fails.
        """
        if not self.api_key:
            raise PaymasterServiceError(
                "PIMLICO_API_KEY not configured."
            )

        result = await self._rpc_call(
            "eth_getUserOperationReceipt",
            [user_op_hash],
        )

        # Result is null/None if UserOp is still pending
        if result is None:
            return None

        logger.info(
            "UserOp receipt retrieved",
            extra={
                "user_op_hash": user_op_hash,
                "success": result.get("success"),
                "tx_hash": result.get("receipt", {}).get("transactionHash"),
            },
        )

        return result

    async def get_user_op_by_hash(
        self, user_op_hash: str
    ) -> Optional[dict]:
        """
        Get UserOperation details by hash.

        Args:
            user_op_hash: The UserOperation hash.

        Returns:
            The UserOp details dict, or None if not found.

        Raises:
            PaymasterServiceError: If the RPC call fails.
        """
        if not self.api_key:
            raise PaymasterServiceError(
                "PIMLICO_API_KEY not configured."
            )

        return await self._rpc_call(
            "eth_getUserOperationByHash",
            [user_op_hash],
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _rpc_call(self, method: str, params: list) -> Any:
        """
        Make a JSON-RPC call to the Pimlico API.

        Args:
            method: The JSON-RPC method name.
            params: The method parameters.

        Returns:
            The "result" field from the JSON-RPC response.

        Raises:
            PaymasterServiceError: On HTTP errors, RPC errors, or timeouts.
        """
        request_id = _next_rpc_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.rpc_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

            if response.status_code != 200:
                logger.error(
                    "Pimlico RPC HTTP error",
                    extra={
                        "method": method,
                        "status_code": response.status_code,
                        "body": response.text[:500],
                    },
                )
                raise PaymasterServiceError(
                    f"Pimlico API returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )

            result = response.json()

            if "error" in result:
                error = result["error"]
                error_msg = error.get("message", str(error))
                error_code = error.get("code")
                logger.error(
                    "Pimlico RPC error",
                    extra={
                        "method": method,
                        "error_code": error_code,
                        "error_message": error_msg,
                    },
                )
                raise PaymasterServiceError(
                    f"Pimlico {method} failed: {error_msg}",
                    rpc_error=error,
                )

            return result.get("result")

        except httpx.TimeoutException as exc:
            logger.error(
                "Pimlico RPC timeout",
                extra={"method": method, "error": str(exc)},
            )
            raise PaymasterServiceError(
                f"Pimlico {method} timed out"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error(
                "Pimlico RPC connection error",
                extra={"method": method, "error": str(exc)},
            )
            raise PaymasterServiceError(
                f"Failed to connect to Pimlico: {exc}"
            ) from exc
