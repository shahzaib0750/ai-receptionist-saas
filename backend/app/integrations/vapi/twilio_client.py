from __future__ import annotations

from typing import Any

import httpx


class TwilioProviderError(Exception):
    def __init__(self, status_code: int | None = None, *, no_number: bool = False) -> None:
        self.status_code = status_code
        self.no_number = no_number
        super().__init__("Twilio request failed")


class TwilioClient:
    def __init__(self, account_sid: str, auth_token: str) -> None:
        self._account_sid = account_sid
        self._client = httpx.Client(
            base_url="https://api.twilio.com/2010-04-01",
            auth=(account_sid, auth_token),
            timeout=httpx.Timeout(20.0),
        )
        self._account_path = f"/Accounts/{account_sid}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(
                method,
                path,
                params=params,
                data=data,
            )
        except httpx.RequestError as error:
            raise TwilioProviderError() from error
        if not response.is_success:
            raise TwilioProviderError(response.status_code)
        try:
            result = response.json()
        except ValueError as error:
            raise TwilioProviderError(response.status_code) from error
        if not isinstance(result, dict):
            raise TwilioProviderError(response.status_code)
        return result

    def find_owned_number(self, phone_number: str) -> dict[str, str] | None:
        result = self._request(
            "GET",
            f"{self._account_path}/IncomingPhoneNumbers.json",
            params={"PhoneNumber": phone_number, "PageSize": "1"},
        )
        numbers = result.get("incoming_phone_numbers")
        if not isinstance(numbers, list):
            raise TwilioProviderError()
        for item in numbers:
            if (
                isinstance(item, dict)
                and item.get("phone_number") == phone_number
                and isinstance(item.get("sid"), str)
            ):
                return {"sid": item["sid"], "phone_number": phone_number}
        return None

    def find_available_number(self, country_code: str) -> str:
        result = self._request(
            "GET",
            f"{self._account_path}/AvailablePhoneNumbers/{country_code}/Local.json",
            params={"VoiceEnabled": "true", "PageSize": "1"},
        )
        numbers = result.get("available_phone_numbers")
        if not isinstance(numbers, list):
            raise TwilioProviderError()
        for item in numbers:
            if isinstance(item, dict) and isinstance(item.get("phone_number"), str):
                return item["phone_number"]
        raise TwilioProviderError(no_number=True)

    def purchase_number(self, phone_number: str) -> dict[str, str]:
        result = self._request(
            "POST",
            f"{self._account_path}/IncomingPhoneNumbers.json",
            data={"PhoneNumber": phone_number},
        )
        sid = result.get("sid")
        purchased_number = result.get("phone_number")
        if not isinstance(sid, str) or purchased_number != phone_number:
            raise TwilioProviderError()
        return {"sid": sid, "phone_number": phone_number}

    def close(self) -> None:
        self._client.close()
