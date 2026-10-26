"""Test doubles for the ingest tests (allowed only under tests/, SPEC 0.10)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from botocore.exceptions import ClientError


class FakeGridLogTable:
    """In-memory stand-in for the boto3 DynamoDB `Table` calls used by the ingest code.

    Supports exactly: get_item, put_item with the two condition expressions the writer uses, and query
    with the key condition string used by DynamoGridLog.
    """

    def __init__(self, conflict_once: bool = False):
        self.items: dict[tuple[str, int], dict[str, Any]] = {}
        self.conflict_once = conflict_once
        self.put_calls = 0

    def get_item(self, Key: dict[str, Any], ConsistentRead: bool = False) -> dict[str, Any]:
        it = self.items.get((Key["pk"], int(Key["t"])))
        return {"Item": copy.deepcopy(it)} if it is not None else {}

    def _fail(self) -> None:
        raise ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "x"}}, "PutItem")

    def put_item(self, Item: dict[str, Any], ConditionExpression: str | None = None,
                 ExpressionAttributeNames: dict[str, str] | None = None,
                 ExpressionAttributeValues: dict[str, Any] | None = None) -> dict[str, Any]:
        self.put_calls += 1
        k = (Item["pk"], int(Item["t"]))
        cur = self.items.get(k)
        if self.conflict_once:
            self.conflict_once = False
            self._fail()
        if ConditionExpression == "attribute_not_exists(pk)":
            if cur is not None:
                self._fail()
        elif ConditionExpression == "#v = :v":
            assert ExpressionAttributeNames == {"#v": "version"}
            if cur is None or cur["version"] != ExpressionAttributeValues[":v"]:
                self._fail()
        elif ConditionExpression is not None:
            raise NotImplementedError(ConditionExpression)
        self.items[k] = copy.deepcopy(Item)
        return {}

    def query(self, KeyConditionExpression: str, ExpressionAttributeNames: dict[str, str],
              ExpressionAttributeValues: dict[str, Any], ScanIndexForward: bool = True,
              Limit: int | None = None, ExclusiveStartKey: dict[str, Any] | None = None) -> dict[str, Any]:
        assert KeyConditionExpression == "#pk = :pk AND #t BETWEEN :a AND :b"
        v = ExpressionAttributeValues
        rows = sorted((it for (pk, t), it in self.items.items()
                       if pk == v[":pk"] and v[":a"] <= t <= v[":b"]),
                      key=lambda it: it["t"], reverse=not ScanIndexForward)
        if ExclusiveStartKey is not None:
            rows = [r for r in rows if (r["t"] > ExclusiveStartKey["t"]) == ScanIndexForward
                    and r["t"] != ExclusiveStartKey["t"]]
        page = 50 if Limit is None else Limit  # small pages exercise pagination
        out = {"Items": copy.deepcopy(rows[:page])}
        if len(rows) > page and Limit is None:
            out["LastEvaluatedKey"] = {"pk": v[":pk"], "t": rows[page - 1]["t"]}
        return out


@pytest.fixture
def fake_table() -> FakeGridLogTable:
    return FakeGridLogTable()


@pytest.fixture
def fake_table_cls() -> type[FakeGridLogTable]:
    return FakeGridLogTable
