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

# 导入必要的 Flask 相关模块
from flask import request
from flask_login import current_user, login_required

# 导入项目配置和数据库相关模块
from api import settings
from api.db import StatusEnum, UserTenantRole
from api.db.db_models import UserTenant
from api.db.services.user_service import UserService, UserTenantService
# 导入工具函数
from api.utils import delta_seconds, get_uuid
from api.utils.api_utils import (get_data_error_result, get_json_result,
                                 server_error_response, validate_request)


@manager.route("/<tenant_id>/user/list", methods=["GET"])  # noqa: F821
@login_required
def user_list(tenant_id):
    # 验证当前用户是否有权限访问该租户的信息
    if current_user.id != tenant_id:
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )

    try:
        # 获取该租户下的所有用户列表
        users = UserTenantService.get_by_tenant_id(tenant_id)
        # 计算每个用户记录的更新时间差
        for u in users:
            u["delta_seconds"] = delta_seconds(str(u["update_date"]))
        return get_json_result(data=users)
    except Exception as e:
        return server_error_response(e)


@manager.route("/<tenant_id>/user", methods=["POST"])  # noqa: F821
@login_required
@validate_request("email")
def create(tenant_id):
    # 验证当前用户是否有权限在该租户下创建用户
    if current_user.id != tenant_id:
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )

    req = request.json
    invite_user_email = req["email"]
    # 查找要邀请的用户是否存在
    invite_users = UserService.query(email=invite_user_email)
    if not invite_users:
        return get_data_error_result(message="User not found.")

    user_id_to_invite = invite_users[0].id
    # 检查用户是否已经在该租户中
    user_tenants = UserTenantService.query(
        user_id=user_id_to_invite, tenant_id=tenant_id
    )
    if user_tenants:
        # 处理各种已存在的用户角色情况
        user_tenant_role = user_tenants[0].role
        if user_tenant_role == UserTenantRole.NORMAL:
            return get_data_error_result(
                message=f"{invite_user_email} is already in the team."
            )
        if user_tenant_role == UserTenantRole.OWNER:
            return get_data_error_result(
                message=f"{invite_user_email} is the owner of the team."
            )
        return get_data_error_result(
            message=f"{invite_user_email} is in the team, but the role: {user_tenant_role} is invalid."
        )

    # 创建新的用户-租户关系记录
    UserTenantService.save(
        id=get_uuid(),
        user_id=user_id_to_invite,
        tenant_id=tenant_id,
        invited_by=current_user.id,
        role=UserTenantRole.INVITE,
        status=StatusEnum.VALID.value,
    )

    # 返回被邀请用户的基本信息
    usr = invite_users[0].to_dict()
    usr = {k: v for k, v in usr.items() if k in ["id", "avatar", "email", "nickname"]}

    return get_json_result(data=usr)


@manager.route("/<tenant_id>/user/<user_id>", methods=["DELETE"])  # noqa: F821
@login_required
def rm(tenant_id, user_id):
    # 验证当前用户是否有权限删除用户（租户所有者或用户自己）
    if current_user.id != tenant_id and current_user.id != user_id:
        return get_json_result(
            data=False,
            message="No authorization.",
            code=settings.RetCode.AUTHENTICATION_ERROR,
        )

    try:
        # 删除用户-租户关系记录
        UserTenantService.filter_delete(
            [UserTenant.tenant_id == tenant_id, UserTenant.user_id == user_id]
        )
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route("/list", methods=["GET"])  # noqa: F821
@login_required
def tenant_list():
    try:
        # 获取当前用户所属的所有租户列表
        users = UserTenantService.get_tenants_by_user_id(current_user.id)
        # 计算每个租户记录的更新时间差
        for u in users:
            u["delta_seconds"] = delta_seconds(str(u["update_date"]))
        return get_json_result(data=users)
    except Exception as e:
        return server_error_response(e)


@manager.route("/agree/<tenant_id>", methods=["PUT"])  # noqa: F821
@login_required
def agree(tenant_id):
    try:
        # 用户同意加入租户，更新用户角色为普通成员
        UserTenantService.filter_update(
            [UserTenant.tenant_id == tenant_id, UserTenant.user_id == current_user.id],
            {"role": UserTenantRole.NORMAL},
        )
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)
