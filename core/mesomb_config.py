"""
MeSomb Payment Gateway Configuration

This module handles all MeSomb-related configuration settings,
including API credentials and operational modes.
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class MeSombSettings:
    """MeSomb configuration settings"""

    def __init__(self):
        # API Credentials - Get from environment variables
        self.MESOMB_APPLICATION_KEY: str = os.getenv("MESOMB_APPLICATION_KEY", "")
        self.MESOMB_ACCESS_KEY: str = os.getenv("MESOMB_ACCESS_KEY", "")
        self.MESOMB_SECRET_KEY: str = os.getenv("MESOMB_SECRET_KEY", "")

        # Operational Settings
        self.MESOMB_ENABLED: bool = os.getenv("MESOMB_ENABLED", "true").lower() == "true"
        self.MESOMB_TEST_MODE: bool = os.getenv("MESOMB_TEST_MODE", "false").lower() == "true"

        # Payment Configuration
        self.MESOMB_CURRENCY: str = "XAF"  # Central African Franc
        self.MESOMB_COUNTRY: str = "CM"    # Cameroon

        # Supported Services
        self.SUPPORTED_SERVICES = {
            'mtn_momo': 'MTN',
            'orange_money': 'Orange'
        }

    def is_configured(self) -> bool:
        """Check if MeSomb is properly configured with credentials"""
        return bool(
            self.MESOMB_APPLICATION_KEY and
            self.MESOMB_ACCESS_KEY and
            self.MESOMB_SECRET_KEY
        )

    def get_service_name(self, payment_method: str) -> Optional[str]:
        """Convert payment method to MeSomb service name"""
        return self.SUPPORTED_SERVICES.get(payment_method)

    def validate_payment_method(self, payment_method: str) -> bool:
        """Validate if payment method is supported"""
        return payment_method in self.SUPPORTED_SERVICES


# Global settings instance
mesomb_settings = MeSombSettings()
