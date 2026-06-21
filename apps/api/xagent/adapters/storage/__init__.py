"""文件/对象存储适配层：local FS（lite）+ S3（full）。

用于短剧素材、artifact、上传文件。按租户隔离路径前缀。
"""

from xagent.adapters.storage.base import ObjectStore, get_object_store, reset_object_store

__all__ = ["ObjectStore", "get_object_store", "reset_object_store"]
