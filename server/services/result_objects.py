"""Typed service result wrappers for JSON-shaped service projections."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from pydantic import RootModel


P = ParamSpec("P")
T = TypeVar("T")


class ServiceObjectResult(RootModel[dict[str, Any]], Mapping[str, Any]):
    """Pydantic object wrapper that preserves a JSON object wire shape."""

    def __getitem__(self, key: str) -> Any:
        return self.root[key]

    def __contains__(self, key: object) -> bool:
        return key in self.root

    def __iter__(self) -> Iterator[str]:
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    def get(self, key: str, default: Any = None) -> Any:
        return self.root.get(key, default)

    def items(self):
        return self.root.items()

    def keys(self):
        return self.root.keys()

    def values(self):
        return self.root.values()


class ServiceListResult(RootModel[list[Any]]):
    """Pydantic object wrapper that preserves a JSON array wire shape."""

    def __iter__(self) -> Iterator[Any]:
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    def __getitem__(self, index: int) -> Any:
        return self.root[index]


def as_service_object(
    value: ServiceObjectResult | dict[str, Any],
) -> ServiceObjectResult:
    if isinstance(value, ServiceObjectResult):
        return value
    return ServiceObjectResult(value)


def as_service_list(value: ServiceListResult | list[Any]) -> ServiceListResult:
    if isinstance(value, ServiceListResult):
        return value
    return ServiceListResult(value)


def dump_service_result(value: Any) -> Any:
    """Recursively convert service result wrappers at API boundaries."""

    if isinstance(value, (ServiceObjectResult, ServiceListResult)):
        return dump_service_result(value.model_dump())
    if isinstance(value, dict):
        return {key: dump_service_result(item) for key, item in value.items()}
    if isinstance(value, list):
        return [dump_service_result(item) for item in value]
    return value


def service_object_result(
    func: Callable[P, ServiceObjectResult | dict[str, Any]],
) -> Callable[P, ServiceObjectResult]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ServiceObjectResult:
        return as_service_object(func(*args, **kwargs))

    return wrapper


def service_list_result(
    func: Callable[P, ServiceListResult | list[Any]],
) -> Callable[P, ServiceListResult]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ServiceListResult:
        return as_service_list(func(*args, **kwargs))

    return wrapper
