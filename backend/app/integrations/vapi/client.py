from __future__ import annotations

from typing import Any

import httpx


class VapiProviderError(Exception):
    def __init__(self, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__("Vapi request failed")


class VapiClient:
    def __init__(self, api_key: str) -> None:
        self._client = httpx.Client(
            base_url="https://api.vapi.ai",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(20.0),
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, path, json=payload)
        except httpx.RequestError as error:
            raise VapiProviderError() from error
        if not response.is_success:
            raise VapiProviderError(response.status_code)
        if response.status_code == 204:
            return {}
        try:
            return response.json()
        except ValueError as error:
            raise VapiProviderError(response.status_code) from error

    def find_assistant(self, provisioning_id: str) -> dict[str, Any] | None:
        response = self._request("GET", "/assistant")
        if not isinstance(response, list):
            raise VapiProviderError()
        for assistant in response:
            if (
                isinstance(assistant, dict)
                and isinstance(assistant.get("metadata"), dict)
                and assistant["metadata"].get("provisioningId") == provisioning_id
            ):
                return assistant
        return None

    def create_assistant(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", "/assistant", payload=payload)
        if not isinstance(response, dict) or not isinstance(response.get("id"), str):
            raise VapiProviderError()
        return response

    def update_assistant(self, assistant_id: str, payload: dict[str, Any]) -> None:
        self._request("PATCH", f"/assistant/{assistant_id}", payload=payload)

    def find_phone_number(self, name: str, phone_number: str) -> dict[str, Any] | None:
        response = self._request("GET", "/phone-number")
        if not isinstance(response, list):
            raise VapiProviderError()
        for phone in response:
            if (
                isinstance(phone, dict)
                and phone.get("name") == name
                and phone.get("number") == phone_number
                and isinstance(phone.get("id"), str)
            ):
                return phone
        return None

    def import_twilio_number(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", "/phone-number", payload=payload)
        if not isinstance(response, dict) or not isinstance(response.get("id"), str):
            raise VapiProviderError()
        return response

    def assign_assistant(self, phone_number_id: str, assistant_id: str) -> None:
        self._request(
            "PATCH",
            f"/phone-number/{phone_number_id}",
            payload={"assistantId": assistant_id},
        )

    def get_phone_number(self, phone_number_id: str) -> dict[str, Any]:
        response = self._request("GET", f"/phone-number/{phone_number_id}")
        if not isinstance(response, dict):
            raise VapiProviderError()
        return response

    def close(self) -> None:
        self._client.close()
