"""请求/响应模型。

原来散落在 main.py 顶部，和业务代码混在一起。
"""
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AnalyzeRequest(BaseModel):
    text: str
