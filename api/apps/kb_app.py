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
import json
import os

from flask import request
from flask_login import current_user, login_required

from api import settings
from api.constants import DATASET_NAME_LIMIT
from api.db import FileSource, StatusEnum
from api.db.db_models import File
from api.db.services import duplicate_name
from api.db.services.document_service import DocumentService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.file_service import FileService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.user_service import TenantService, UserTenantService
from api.utils import get_uuid
from api.utils.api_utils import (
    get_data_error_result,
    get_json_result,
    not_allowed_parameters,
    server_error_response,
    validate_request,
)
from rag.nlp import search
from rag.settings import PAGERANK_FLD


# 知识库创建接口
@manager.route("/create", methods=["post"])
@login_required
@validate_request("name")
def create():
    """创建新的知识库

    请求参数:
    - name: 知识库名称

    返回:
    - kb_id: 新创建的知识库ID
    """
    req = request.json
    dataset_name = req["name"]
    # 验证知识库名称的合法性
    if not isinstance(dataset_name, str):
        return get_data_error_result(message="Dataset name must be string.")
    if dataset_name == "":
        return get_data_error_result(message="Dataset name can't be empty.")
    if len(dataset_name) >= DATASET_NAME_LIMIT:
        return get_data_error_result(
            message=f"Dataset name length is {len(dataset_name)} which is large than {DATASET_NAME_LIMIT}"
        )

    dataset_name = dataset_name.strip()
    dataset_name = duplicate_name(
        KnowledgebaseService.query,
        name=dataset_name,
        tenant_id=current_user.id,
        status=StatusEnum.VALID.value,
    )
    try:
        req["id"] = get_uuid()
        req["tenant_id"] = current_user.id
        req["created_by"] = current_user.id
        e, t = TenantService.get_by_id(current_user.id)
        if not e:
            return get_data_error_result(message="Tenant not found.")
        req["embd_id"] = t.embd_id
        if not KnowledgebaseService.save(**req):
            return get_data_error_result()
        return get_json_result(data={"kb_id": req["id"]})
    except Exception as e:
        return server_error_response(e)


# 知识库更新接口
@manager.route("/update", methods=["post"])
@login_required
@validate_request("kb_id", "name", "description", "permission", "parser_id")
@not_allowed_parameters(
    "id",
    "tenant_id",
    "created_by",
    "create_time",
    "update_time",
    "create_date",
    "update_date",
    "created_by",
)
def update():
    """更新知识库信息

    请求参数:
    - kb_id: 知识库ID
    - name: 新的知识库名称
    - description: 知识库描述
    - permission: 权限设置
    - parser_id: 解析器ID
    """
    req = request.json
    req["name"] = req["name"].strip()
    # 检查用户是否有权限修改该知识库
    if not KnowledgebaseService.accessible4deletion(req["kb_id"], current_user.id):
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )
    try:
        if not KnowledgebaseService.query(created_by=current_user.id, id=req["kb_id"]):
            return get_json_result(
                data=False,
                message="Only owner of knowledgebase authorized for this operation.",
                code=settings.RetCode.OPERATING_ERROR,
            )

        e, kb = KnowledgebaseService.get_by_id(req["kb_id"])
        if not e:
            return get_data_error_result(message="Can't find this knowledgebase!")

        if (
            req.get("parser_id", "") == "tag"
            and os.environ.get("DOC_ENGINE", "elasticsearch") == "infinity"
        ):
            return get_json_result(
                data=False,
                message="The chunk method Tag has not been supported by Infinity yet.",
                code=settings.RetCode.OPERATING_ERROR,
            )

        if (
            req["name"].lower() != kb.name.lower()
            and len(
                KnowledgebaseService.query(
                    name=req["name"],
                    tenant_id=current_user.id,
                    status=StatusEnum.VALID.value,
                )
            )
            > 1
        ):
            return get_data_error_result(message="Duplicated knowledgebase name.")

        del req["kb_id"]
        if not KnowledgebaseService.update_by_id(kb.id, req):
            return get_data_error_result()

        if kb.pagerank != req.get("pagerank", 0):
            if req.get("pagerank", 0) > 0:
                settings.docStoreConn.update(
                    {"kb_id": kb.id},
                    {PAGERANK_FLD: req["pagerank"]},
                    search.index_name(kb.tenant_id),
                    kb.id,
                )
            else:
                # Elasticsearch requires PAGERANK_FLD be non-zero!
                settings.docStoreConn.update(
                    {"exists": PAGERANK_FLD},
                    {"remove": PAGERANK_FLD},
                    search.index_name(kb.tenant_id),
                    kb.id,
                )

        e, kb = KnowledgebaseService.get_by_id(kb.id)
        if not e:
            return get_data_error_result(
                message="Database error (Knowledgebase rename)!"
            )
        kb = kb.to_dict()
        kb.update(req)

        return get_json_result(data=kb)
    except Exception as e:
        return server_error_response(e)


# 获取知识库详情接口
@manager.route("/detail", methods=["GET"])
@login_required
def detail():
    """获取知识库详细信息

    URL参数:
    - kb_id: 知识库ID
    """
    kb_id = request.args["kb_id"]
    try:
        # 验证用户是否有权限访问该知识库
        tenants = UserTenantService.query(user_id=current_user.id)
        for tenant in tenants:
            if KnowledgebaseService.query(tenant_id=tenant.tenant_id, id=kb_id):
                break
        else:
            return get_json_result(
                data=False,
                message="Only owner of knowledgebase authorized for this operation.",
                code=settings.RetCode.OPERATING_ERROR,
            )
        kb = KnowledgebaseService.get_detail(kb_id)
        if not kb:
            return get_data_error_result(message="Can't find this knowledgebase!")
        return get_json_result(data=kb)
    except Exception as e:
        return server_error_response(e)


# 知识库列表接口
@manager.route("/list", methods=["GET"])
@login_required
def list_kbs():
    """获取知识库列表

    URL参数:
    - keywords: 搜索关键词
    - page: 页码
    - page_size: 每页数量
    - parser_id: 解析器ID过滤
    - orderby: 排序字段
    - desc: 是否降序
    """
    keywords = request.args.get("keywords", "")
    page_number = int(request.args.get("page", 1))
    items_per_page = int(request.args.get("page_size", 150))
    parser_id = request.args.get("parser_id")
    orderby = request.args.get("orderby", "create_time")
    desc = request.args.get("desc", True)
    try:
        tenants = TenantService.get_joined_tenants_by_user_id(current_user.id)
        kbs, total = KnowledgebaseService.get_by_tenant_ids(
            [m["tenant_id"] for m in tenants],
            current_user.id,
            page_number,
            items_per_page,
            orderby,
            desc,
            keywords,
            parser_id,
        )
        return get_json_result(data={"kbs": kbs, "total": total})
    except Exception as e:
        return server_error_response(e)


# 删除知识库接口
@manager.route("/rm", methods=["post"])
@login_required
@validate_request("kb_id")
def rm():
    """删除指定知识库

    请求参数:
    - kb_id: 要删除的知识库ID

    说明: 会同时删除知识库下的所有文档和相关文件
    """
    req = request.json
    if not KnowledgebaseService.accessible4deletion(req["kb_id"], current_user.id):
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )
    try:
        kbs = KnowledgebaseService.query(created_by=current_user.id, id=req["kb_id"])
        if not kbs:
            return get_json_result(
                data=False,
                message="Only owner of knowledgebase authorized for this operation.",
                code=settings.RetCode.OPERATING_ERROR,
            )

        for doc in DocumentService.query(kb_id=req["kb_id"]):
            if not DocumentService.remove_document(doc, kbs[0].tenant_id):
                return get_data_error_result(
                    message="Database error (Document removal)!"
                )
            f2d = File2DocumentService.get_by_document_id(doc.id)
            if f2d:
                FileService.filter_delete(
                    [
                        File.source_type == FileSource.KNOWLEDGEBASE,
                        File.id == f2d[0].file_id,
                    ]
                )
            File2DocumentService.delete_by_document_id(doc.id)
        FileService.filter_delete(
            [
                File.source_type == FileSource.KNOWLEDGEBASE,
                File.type == "folder",
                File.name == kbs[0].name,
            ]
        )
        if not KnowledgebaseService.delete_by_id(req["kb_id"]):
            return get_data_error_result(
                message="Database error (Knowledgebase removal)!"
            )
        for kb in kbs:
            settings.docStoreConn.delete(
                {"kb_id": kb.id}, search.index_name(kb.tenant_id), kb.id
            )
            settings.docStoreConn.deleteIdx(search.index_name(kb.tenant_id), kb.id)
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


# 获取知识库标签列表接口
@manager.route("/<kb_id>/tags", methods=["GET"])
@login_required
def list_tags(kb_id):
    """获取指定知识库的所有标签

    URL参数:
    - kb_id: 知识库ID
    """
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )

    tags = settings.retrievaler.all_tags(current_user.id, [kb_id])
    return get_json_result(data=tags)


# 获取多个知识库的标签列表接口
@manager.route("/tags", methods=["GET"])
@login_required
def list_tags_from_kbs():
    """获取多个知识库的所有标签

    URL参数:
    - kb_ids: 知识库ID列表，以逗号分隔
    """
    kb_ids = request.args.get("kb_ids", "").split(",")
    for kb_id in kb_ids:
        if not KnowledgebaseService.accessible(kb_id, current_user.id):
            return get_json_result(
                data=False,
                message="No authorization.",
                code=settings.RetCode.AUTHENTICATION_ERROR,
            )

    tags = settings.retrievaler.all_tags(current_user.id, kb_ids)
    return get_json_result(data=tags)


# 删除知识库标签接口
@manager.route("/<kb_id>/rm_tags", methods=["POST"])
@login_required
def rm_tags(kb_id):
    """删除知识库中的指定标签

    请求参数:
    - tags: 要删除的标签列表
    """
    req = request.json
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )
    e, kb = KnowledgebaseService.get_by_id(kb_id)

    for t in req["tags"]:
        settings.docStoreConn.update(
            {"tag_kwd": t, "kb_id": [kb_id]},
            {"remove": {"tag_kwd": t}},
            search.index_name(kb.tenant_id),
            kb_id,
        )
    return get_json_result(data=True)


# 重命名知识库标签接口
@manager.route("/<kb_id>/rename_tag", methods=["POST"])
@login_required
def rename_tags(kb_id):
    """重命名知识库中的标签

    请求参数:
    - from_tag: 原标签名
    - to_tag: 新标签名
    """
    req = request.json
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )
    e, kb = KnowledgebaseService.get_by_id(kb_id)

    settings.docStoreConn.update(
        {"tag_kwd": req["from_tag"], "kb_id": [kb_id]},
        {
            "remove": {"tag_kwd": req["from_tag"].strip()},
            "add": {"tag_kwd": req["to_tag"]},
        },
        search.index_name(kb.tenant_id),
        kb_id,
    )
    return get_json_result(data=True)


# 获取知识图谱接口
@manager.route("/<kb_id>/knowledge_graph", methods=["GET"])
@login_required
def knowledge_graph(kb_id):
    """获取知识库的知识图谱数据

    返回:
    - graph: 图谱数据
    - mind_map: 思维导图数据

    说明:
    - 返回的节点按PageRank值排序，最多返回256个节点
    - 边按权重排序，最多返回128条边
    - 过滤掉自环边
    """
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )
    _, kb = KnowledgebaseService.get_by_id(kb_id)
    req = {"kb_id": [kb_id], "knowledge_graph_kwd": ["graph"]}

    obj = {"graph": {}, "mind_map": {}}
    if not settings.docStoreConn.indexExist(search.index_name(kb.tenant_id), kb_id):
        return get_json_result(data=obj)
    sres = settings.retrievaler.search(req, search.index_name(kb.tenant_id), [kb_id])
    if not len(sres.ids):
        return get_json_result(data=obj)

    for id in sres.ids[:1]:
        ty = sres.field[id]["knowledge_graph_kwd"]
        try:
            content_json = json.loads(sres.field[id]["content_with_weight"])
        except Exception:
            continue

        obj[ty] = content_json

    if "nodes" in obj["graph"]:
        obj["graph"]["nodes"] = sorted(
            obj["graph"]["nodes"], key=lambda x: x.get("pagerank", 0), reverse=True
        )[:256]
        if "edges" in obj["graph"]:
            node_id_set = {o["id"] for o in obj["graph"]["nodes"]}
            filtered_edges = [
                o
                for o in obj["graph"]["edges"]
                if o["source"] != o["target"]
                and o["source"] in node_id_set
                and o["target"] in node_id_set
            ]
            obj["graph"]["edges"] = sorted(
                filtered_edges, key=lambda x: x.get("weight", 0), reverse=True
            )[:128]
    return get_json_result(data=obj)
