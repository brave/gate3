from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    OK = "OK"
    KO = "KO"


class PingResponse(BaseModel):
    redis: HealthStatus


class CoinType(int, Enum):
    ADA = 1815
    BTC = 0
    ETH = 60
    FIL = 461
    SOL = 501
    ZEC = 133


class ChainId(str, Enum):
    ARBITRUM = "0xa4b1"
    AVALANCHE = "0xa86a"
    BASE = "0x2105"
    BNB_CHAIN = "0x38"
    ETHEREUM = "0x1"
    OPTIMISM = "0xa"
    POLYGON = "0x89"
    SOLANA = "0x65"
