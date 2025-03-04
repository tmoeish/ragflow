#
#  版权所有 2024 The InfiniFlow Authors. 保留所有权利。
#
#  根据Apache许可证2.0版（"许可证"）授权；除非遵循许可证，否则不得使用此文件。
#  您可以在以下网址获取许可证副本：
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  除非适用法律要求或书面同意，否则软件按"原样"分发，
#  无任何明示或暗示的担保或条件。
#  有关许可证下特定语言的权限和限制，请参阅许可证。
#

from api.db.services.file2document_service import File2DocumentService
from api.db.services.file_service import FileService

from flask import request
from flask_login import login_required, current_user
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.utils.api_utils import (
    server_error_response,
    get_data_error_result,
    validate_request,
)
from api.utils import get_uuid
from api.db import FileType
from api.db.services.document_service import DocumentService
from api import settings
from api.utils.api_utils import get_json_result


@manager.route("/convert", methods=["POST"])  # noqa: F821
@login_required
@validate_request("file_ids", "kb_ids")
def convert():
    """
    将文件转换为文档的API端点。
    需要用户登录并验证请求中包含file_ids和kb_ids。
    """
    req = request.json
    kb_ids = req["kb_ids"]
    file_ids = req["file_ids"]
    file2documents = []

    try:
        for file_id in file_ids:
            e, file = FileService.get_by_id(file_id)
            file_ids_list = [file_id]
            if file.type == FileType.FOLDER.value:
                # 如果文件是文件夹，获取所有最内层文件的ID
                file_ids_list = FileService.get_all_innermost_file_ids(file_id, [])
            for id in file_ids_list:
                informs = File2DocumentService.get_by_file_id(id)
                # 删除现有的文档信息
                for inform in informs:
                    doc_id = inform.document_id
                    e, doc = DocumentService.get_by_id(doc_id)
                    if not e:
                        return get_data_error_result(message="Document not found!")
                    tenant_id = DocumentService.get_tenant_id(doc_id)
                    if not tenant_id:
                        return get_data_error_result(message="Tenant not found!")
                    if not DocumentService.remove_document(doc, tenant_id):
                        return get_data_error_result(
                            message="Database error (Document removal)!"
                        )
                File2DocumentService.delete_by_file_id(id)

                # 插入新的文档信息
                for kb_id in kb_ids:
                    e, kb = KnowledgebaseService.get_by_id(kb_id)
                    if not e:
                        return get_data_error_result(
                            message="Can't find this knowledgebase!"
                        )
                    e, file = FileService.get_by_id(id)
                    if not e:
                        return get_data_error_result(message="Can't find this file!")

                    doc = DocumentService.insert(
                        {
                            "id": get_uuid(),
                            "kb_id": kb.id,
                            "parser_id": FileService.get_parser(
                                file.type, file.name, kb.parser_id
                            ),
                            "parser_config": kb.parser_config,
                            "created_by": current_user.id,
                            "type": file.type,
                            "name": file.name,
                            "location": file.location,
                            "size": file.size,
                        }
                    )
                    file2document = File2DocumentService.insert(
                        {
                            "id": get_uuid(),
                            "file_id": id,
                            "document_id": doc.id,
                        }
                    )
                    file2documents.append(file2document.to_json())
        return get_json_result(data=file2documents)
    except Exception as e:
        return server_error_response(e)


@manager.route("/rm", methods=["POST"])  # noqa: F821
@login_required
@validate_request("file_ids")
def rm():
    """
    删除文件与文档关联的API端点。
    需要用户登录并验证请求中包含file_ids。
    """
    req = request.json
    file_ids = req["file_ids"]
    if not file_ids:
        return get_json_result(
            data=False,
            message='Lack of "Files ID"',
            code=settings.RetCode.ARGUMENT_ERROR,
        )
    try:
        for file_id in file_ids:
            informs = File2DocumentService.get_by_file_id(file_id)
            if not informs:
                return get_data_error_result(message="Inform not found!")
            for inform in informs:
                if not inform:
                    return get_data_error_result(message="Inform not found!")
                File2DocumentService.delete_by_file_id(file_id)
                doc_id = inform.document_id
                e, doc = DocumentService.get_by_id(doc_id)
                if not e:
                    return get_data_error_result(message="Document not found!")
                tenant_id = DocumentService.get_tenant_id(doc_id)
                if not tenant_id:
                    return get_data_error_result(message="Tenant not found!")
                if not DocumentService.remove_document(doc, tenant_id):
                    return get_data_error_result(
                        message="Database error (Document removal)!"
                    )
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)
