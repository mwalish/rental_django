"""
==========================================
M-Pesa Integration — Safaricom STK Push
==========================================
Handles Lipa Na M-Pesa Online (STK Push) for tenant rent payments.
Sends a payment request to the tenant's phone where they enter their PIN.
Uses sandbox credentials from settings.py — switch to live for production.
==========================================
"""
import base64
import logging
import requests
from datetime import datetime

from django.conf import settings

logger = logging.getLogger(__name__)


class MpesaService:
    """
    Handles M-Pesa STK Push (Lipa Na M-Pesa Online) for tenant rent payments.
    Tenant is prompted on their phone to enter M-Pesa PIN to pay.
    """

    # Environment-aware base URLs (override via settings for production/live).
    def __init__(self):
        """Initialize with credentials from Django settings."""
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.shortcode = settings.MPESA_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY
        self.callback_url = settings.MPESA_CALLBACK_URL
        self.timeout = getattr(settings, "MPESA_TIMEOUT_SECONDS", 30)

        base = getattr(settings, "MPESA_API_BASE_URL", "https://sandbox.safaricom.co.ke")
        self.token_url = f"{base}/oauth/v1/generate?grant_type=client_credentials"
        self.stk_url = f"{base}/mpesa/stkpush/v1/processrequest"

    def _safe_json(self, response, context=""):
        """Parse a JSON response defensively; raise a clear error on failure."""
        try:
            return response.json()
        except ValueError:
            logger.error("M-Pesa %s returned non-JSON (HTTP %s): %s",
                         context, response.status_code, response.text[:500])
            raise RuntimeError(
                f"M-Pesa {context} returned an invalid response "
                f"(HTTP {response.status_code})."
            )

    def get_token(self):
        """Get OAuth access token from Safaricom API using consumer key/secret."""
        try:
            response = requests.get(
                self.token_url,
                auth=requests.auth.HTTPBasicAuth(self.consumer_key, self.consumer_secret),
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("M-Pesa token request failed: %s", e)
            raise RuntimeError("Could not reach M-Pesa to obtain an access token.") from e

        data = self._safe_json(response, context="token")
        token = data.get("access_token")
        if not token:
            logger.error("M-Pesa token response missing access_token: %s", data)
            raise RuntimeError("M-Pesa authentication failed (missing access_token).")
        return token

    def get_password(self, timestamp):
        """Generate base64-encoded password for STK Push request (shortcode + passkey + timestamp)."""
        raw = f"{self.shortcode}{self.passkey}{timestamp}"
        return base64.b64encode(raw.encode()).decode()

    def stk_push(self, phone, amount, account_ref, description="Rent Payment"):
        """
        Initiates STK Push to tenant's phone.
        phone: format 2547XXXXXXXX
        amount: integer (KSh)
        account_ref: e.g. lease ID or property name

        Returns the parsed Safaricom response dict on success.
        Raises RuntimeError on connectivity/protocol failures.
        """
        token = self.get_token()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = self.get_password(timestamp)

        # Normalize phone: strip leading + or 0
        phone = str(phone).strip()
        if phone.startswith("+"):
            phone = phone[1:]
        elif phone.startswith("0"):
            phone = "254" + phone[1:]

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self.shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.callback_url,
            "AccountReference": str(account_ref),
            "TransactionDesc": description,
        }

        try:
            response = requests.post(
                self.stk_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("M-Pesa STK push request failed: %s", e)
            raise RuntimeError("M-Pesa STK push request failed.") from e

        return self._safe_json(response, context="STK push")
