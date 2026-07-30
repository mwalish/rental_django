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
import requests
from datetime import datetime
from django.conf import settings


class MpesaService:
    """
    Handles M-Pesa STK Push (Lipa Na M-Pesa Online) for tenant rent payments.
    Tenant is prompted on their phone to enter M-Pesa PIN to pay.
    """

    def __init__(self):
        """Initialize with credentials from Django settings."""
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.shortcode = settings.MPESA_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY
        self.callback_url = settings.MPESA_CALLBACK_URL
        self.token_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        self.stk_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

    def get_token(self):
        """Get OAuth access token from Safaricom API using consumer key/secret."""
        response = requests.get(
            self.token_url,
            auth=requests.auth.HTTPBasicAuth(self.consumer_key, self.consumer_secret)
        )
        return response.json()["access_token"]

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

        response = requests.post(
            self.stk_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )
        return response.json()
