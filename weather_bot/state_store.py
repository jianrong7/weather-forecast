from __future__ import annotations

import boto3
from decimal import Decimal
import math


class StateStore:
    def __init__(self, table_name: str, region: str | None = None):
        resource = boto3.resource("dynamodb", region_name=region)
        self._table = resource.Table(table_name)

    @staticmethod
    def _pk(user_id: str) -> str:
        return f"USER#{user_id}"

    @staticmethod
    def _to_ddb_value(value):
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (str, bytes, Decimal, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("DynamoDB does not support NaN/Infinity float values")
            return Decimal(str(value))
        if isinstance(value, dict):
            return {key: StateStore._to_ddb_value(inner) for key, inner in value.items()}
        if isinstance(value, list):
            return [StateStore._to_ddb_value(inner) for inner in value]
        if isinstance(value, tuple):
            return [StateStore._to_ddb_value(inner) for inner in value]
        if isinstance(value, set):
            return {StateStore._to_ddb_value(inner) for inner in value}
        return value

    def get_profile(self, user_id: str) -> dict | None:
        response = self._table.get_item(Key={"PK": self._pk(user_id), "SK": "PROFILE"})
        return response.get("Item")

    def put_profile(self, user_id: str, profile: dict) -> None:
        item = {"PK": self._pk(user_id), "SK": "PROFILE", "entityType": "PROFILE", **profile}
        self._table.put_item(Item=self._to_ddb_value(item))

    def get_alert_state(self, user_id: str) -> dict | None:
        response = self._table.get_item(Key={"PK": self._pk(user_id), "SK": "ALERT_STATE"})
        return response.get("Item")

    def put_alert_state(self, user_id: str, state: dict) -> None:
        item = {"PK": self._pk(user_id), "SK": "ALERT_STATE", "entityType": "ALERT_STATE", **state}
        self._table.put_item(Item=self._to_ddb_value(item))
