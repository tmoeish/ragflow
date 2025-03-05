#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import pathlib
import re

from .user_service import UserService as UserService


def duplicate_name(query_func, **kwargs):
    """生成不重复的文件名。

    当给定的文件名已存在时，通过添加或递增计数器来生成一个新的唯一文件名。
    例如：如果 'file.jpg' 已存在，将返回 'file(1).jpg'；
    如果 'file(1).jpg' 也存在，将返回 'file(2).jpg'，以此类推。

    Args:
        query_func: 查询函数，用于检查给定名称是否已存在
        **kwargs: 关键字参数，必须包含 'name' 键，表示要检查的文件名
                 其他参数将传递给 query_func

    Returns:
        str: 不重复的文件名
    """
    # 获取当前文件名
    fnm = kwargs["name"]
    # 使用查询函数检查文件名是否已存在
    objs = query_func(**kwargs)
    # 如果文件名不存在，直接返回原文件名
    if not objs:
        return fnm

    # 提取文件扩展名（如 .jpg）
    ext = pathlib.Path(fnm).suffix
    # 移除扩展名，获取基本文件名
    nm = re.sub(r"%s$" % ext, "", fnm)
    # 查找文件名中是否已有计数器，如 'file(1)'
    r = re.search(r"\(([0-9]+)\)$", nm)
    c = 0

    # 如果找到计数器，提取计数值并移除计数器部分
    if r:
        c = int(r.group(1))
        nm = re.sub(r"\([0-9]+\)$", "", nm)

    # 计数器加1
    c += 1
    # 组合新文件名：基本名称 + 计数器
    nm = f"{nm}({c})"
    # 如果有扩展名，添加回文件名
    if ext:
        nm += f"{ext}"

    # 更新关键字参数中的文件名
    kwargs["name"] = nm
    # 递归调用，继续检查新生成的文件名是否存在
    return duplicate_name(query_func, **kwargs)
