"""Repository 边界。

复杂查询逐步从 service 下沉至此；业务规则仍保留在 service。当前 V1.0
的事件聚合查询已封装为服务内私有函数，避免在 API 层直接操作 ORM。
"""
