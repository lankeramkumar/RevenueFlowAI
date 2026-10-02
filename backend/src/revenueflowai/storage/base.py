"""Object-store adapter interface. Swap implementations without touching callers."""

from abc import ABC, abstractmethod


class ObjectStore(ABC):
    @abstractmethod
    async def put_object(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def get_object(self, bucket: str, key: str) -> bytes: ...

    @abstractmethod
    async def object_exists(self, bucket: str, key: str) -> bool: ...
