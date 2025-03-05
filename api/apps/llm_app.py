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
import logging
import json
import os
from flask import request
from flask_login import login_required, current_user
from api.db.services.llm_service import (
    LLMFactoriesService,
    TenantLLMService,
    LLMService,
)
from api import settings
from api.utils.api_utils import (
    server_error_response,
    get_data_error_result,
    validate_request,
)
from api.db import StatusEnum, LLMType
from api.db.db_models import TenantLLM
from api.utils.api_utils import get_json_result
from api.utils.file_utils import get_project_base_directory
from rag.llm import EmbeddingModel, ChatModel, RerankModel, CvModel, TTSModel


@manager.route("/factories", methods=["GET"])  # noqa: F821
@login_required
def factories():
    """获取所有可用的LLM工厂配置

    返回:
        JSON响应，包含所有支持的LLM工厂及其支持的模型类型
        每个工厂包含基本信息和支持的模型类型列表(chat/embedding/rerank等)
    """
    try:
        # 获取所有工厂配置，排除Youdao、FastEmbed和BAAI
        fac = LLMFactoriesService.get_all()
        fac = [
            f.to_dict() for f in fac if f.name not in ["Youdao", "FastEmbed", "BAAI"]
        ]

        # 获取所有有效的LLM模型，并按工厂ID归类其支持的模型类型
        llms = LLMService.get_all()
        mdl_types = {}
        for m in llms:
            if m.status != StatusEnum.VALID.value:
                continue
            if m.fid not in mdl_types:
                mdl_types[m.fid] = set([])
            mdl_types[m.fid].add(m.model_type)

        # 为每个工厂添加支持的模型类型
        for f in fac:
            f["model_types"] = list(
                mdl_types.get(
                    f["name"],
                    [
                        LLMType.CHAT,
                        LLMType.EMBEDDING,
                        LLMType.RERANK,
                        LLMType.IMAGE2TEXT,
                        LLMType.SPEECH2TEXT,
                        LLMType.TTS,
                    ],
                )
            )
        return get_json_result(data=fac)
    except Exception as e:
        return server_error_response(e)


@manager.route("/set_api_key", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory", "api_key")
def set_api_key():
    """设置LLM工厂的API密钥

    请求体参数:
        llm_factory: LLM工厂名称
        api_key: API密钥
        base_url: 可选，API基础URL

    返回:
        成功返回True，失败返回错误信息
    """
    req = request.json
    # 测试API密钥是否有效
    chat_passed, embd_passed, rerank_passed = False, False, False
    factory = req["llm_factory"]
    msg = ""

    # 遍历工厂支持的所有模型类型，测试API密钥
    for llm in LLMService.query(fid=factory):
        # 测试Embedding模型
        if not embd_passed and llm.model_type == LLMType.EMBEDDING.value:
            mdl = EmbeddingModel[factory](
                req["api_key"], llm.llm_name, base_url=req.get("base_url")
            )
            try:
                arr, tc = mdl.encode(["Test if the api key is available"])
                if len(arr[0]) == 0:
                    raise Exception("Fail")
                embd_passed = True
            except Exception as e:
                msg += (
                    f"\nFail to access embedding model({llm.llm_name}) using this api key."
                    + str(e)
                )

        # 测试Chat模型
        elif not chat_passed and llm.model_type == LLMType.CHAT.value:
            mdl = ChatModel[factory](
                req["api_key"], llm.llm_name, base_url=req.get("base_url")
            )
            try:
                m, tc = mdl.chat(
                    None,
                    [{"role": "user", "content": "Hello! How are you doing!"}],
                    {"temperature": 0.9, "max_tokens": 50},
                )
                if m.find("**ERROR**") >= 0:
                    raise Exception(m)
                chat_passed = True
            except Exception as e:
                msg += (
                    f"\nFail to access model({llm.llm_name}) using this api key."
                    + str(e)
                )

        # 测试Rerank模型
        elif not rerank_passed and llm.model_type == LLMType.RERANK:
            mdl = RerankModel[factory](
                req["api_key"], llm.llm_name, base_url=req.get("base_url")
            )
            try:
                arr, tc = mdl.similarity("What's the weather?", ["Is it sunny today?"])
                if len(arr) == 0 or tc == 0:
                    raise Exception("Fail")
                rerank_passed = True
                logging.debug(f"passed model rerank {llm.llm_name}")
            except Exception as e:
                msg += (
                    f"\nFail to access model({llm.llm_name}) using this api key."
                    + str(e)
                )

        # 只要有一个模型测试通过就算成功
        if any([embd_passed, chat_passed, rerank_passed]):
            msg = ""
            break

    if msg:
        return get_data_error_result(message=msg)

    # 构建LLM配置
    llm_config = {"api_key": req["api_key"], "api_base": req.get("base_url", "")}
    for n in ["model_type", "llm_name"]:
        if n in req:
            llm_config[n] = req[n]

    # 更新或创建租户的LLM配置
    for llm in LLMService.query(fid=factory):
        llm_config["max_tokens"] = llm.max_tokens
        if not TenantLLMService.filter_update(
            [
                TenantLLM.tenant_id == current_user.id,
                TenantLLM.llm_factory == factory,
                TenantLLM.llm_name == llm.llm_name,
            ],
            llm_config,
        ):
            TenantLLMService.save(
                tenant_id=current_user.id,
                llm_factory=factory,
                llm_name=llm.llm_name,
                model_type=llm.model_type,
                api_key=llm_config["api_key"],
                api_base=llm_config["api_base"],
                max_tokens=llm_config["max_tokens"],
            )

    return get_json_result(data=True)


@manager.route("/add_llm", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory")
def add_llm():
    """添加新的LLM配置

    请求体参数:
        llm_factory: LLM工厂名称
        其他参数根据不同工厂类型有所不同

    返回:
        成功返回True，失败返回错误信息
    """
    req = request.json
    factory = req["llm_factory"]

    def apikey_json(keys):
        """将多个API密钥相关的参数组合成JSON字符串"""
        nonlocal req
        return json.dumps({k: req.get(k, "") for k in keys})

    # 根据不同的工厂类型处理API密钥
    if factory == "VolcEngine":
        # 火山引擎需要组合ark_api_key和endpoint_id
        llm_name = req["llm_name"]
        api_key = apikey_json(["ark_api_key", "endpoint_id"])

    elif factory == "Tencent Hunyuan":
        # 腾讯混元需要组合hunyuan_sid和hunyuan_sk
        req["api_key"] = apikey_json(["hunyuan_sid", "hunyuan_sk"])
        return set_api_key()

    elif factory == "Tencent Cloud":
        req["api_key"] = apikey_json(["tencent_cloud_sid", "tencent_cloud_sk"])
        return set_api_key()

    elif factory == "Bedrock":
        # For Bedrock, due to its special authentication method
        # Assemble bedrock_ak, bedrock_sk, bedrock_region
        llm_name = req["llm_name"]
        api_key = apikey_json(["bedrock_ak", "bedrock_sk", "bedrock_region"])

    elif factory == "LocalAI":
        llm_name = req["llm_name"] + "___LocalAI"
        api_key = "xxxxxxxxxxxxxxx"

    elif factory == "HuggingFace":
        llm_name = req["llm_name"] + "___HuggingFace"
        api_key = "xxxxxxxxxxxxxxx"

    elif factory == "OpenAI-API-Compatible":
        llm_name = req["llm_name"] + "___OpenAI-API"
        api_key = req.get("api_key", "xxxxxxxxxxxxxxx")

    elif factory == "VLLM":
        llm_name = req["llm_name"] + "___VLLM"
        api_key = req.get("api_key", "xxxxxxxxxxxxxxx")

    elif factory == "XunFei Spark":
        llm_name = req["llm_name"]
        if req["model_type"] == "chat":
            api_key = req.get("spark_api_password", "xxxxxxxxxxxxxxx")
        elif req["model_type"] == "tts":
            api_key = apikey_json(["spark_app_id", "spark_api_secret", "spark_api_key"])

    elif factory == "BaiduYiyan":
        llm_name = req["llm_name"]
        api_key = apikey_json(["yiyan_ak", "yiyan_sk"])

    elif factory == "Fish Audio":
        llm_name = req["llm_name"]
        api_key = apikey_json(["fish_audio_ak", "fish_audio_refid"])

    elif factory == "Google Cloud":
        llm_name = req["llm_name"]
        api_key = apikey_json(
            ["google_project_id", "google_region", "google_service_account_key"]
        )

    elif factory == "Azure-OpenAI":
        llm_name = req["llm_name"]
        api_key = apikey_json(["api_key", "api_version"])

    else:
        llm_name = req["llm_name"]
        api_key = req.get("api_key", "xxxxxxxxxxxxxxx")

    llm = {
        "tenant_id": current_user.id,
        "llm_factory": factory,
        "model_type": req["model_type"],
        "llm_name": llm_name,
        "api_base": req.get("api_base", ""),
        "api_key": api_key,
        "max_tokens": req.get("max_tokens"),
    }

    # 测试模型是否可用
    msg = ""
    mdl_nm = llm["llm_name"].split("___")[0]

    # 根据不同的模型类型进行测试
    if llm["model_type"] == LLMType.EMBEDDING.value:
        # 测试Embedding模型
        mdl = EmbeddingModel[factory](
            key=llm["api_key"], model_name=mdl_nm, base_url=llm["api_base"]
        )
        try:
            arr, tc = mdl.encode(["Test if the api key is available"])
            if len(arr[0]) == 0:
                raise Exception("Fail")
        except Exception as e:
            msg += f"\nFail to access embedding model({mdl_nm})." + str(e)
    elif llm["model_type"] == LLMType.CHAT.value:
        mdl = ChatModel[factory](
            key=llm["api_key"], model_name=mdl_nm, base_url=llm["api_base"]
        )
        try:
            m, tc = mdl.chat(
                None,
                [{"role": "user", "content": "Hello! How are you doing!"}],
                {"temperature": 0.9},
            )
            if not tc and m.find("**ERROR**:") >= 0:
                raise Exception(m)
        except Exception as e:
            msg += f"\nFail to access model({mdl_nm})." + str(e)
    elif llm["model_type"] == LLMType.RERANK:
        try:
            mdl = RerankModel[factory](
                key=llm["api_key"], model_name=mdl_nm, base_url=llm["api_base"]
            )
            arr, tc = mdl.similarity(
                "Hello~ Ragflower!", ["Hi, there!", "Ohh, my friend!"]
            )
            if len(arr) == 0:
                raise Exception("Not known.")
        except KeyError:
            msg += f"{factory} dose not support this model({mdl_nm})"
        except Exception as e:
            msg += f"\nFail to access model({mdl_nm})." + str(e)
    elif llm["model_type"] == LLMType.IMAGE2TEXT.value:
        mdl = CvModel[factory](
            key=llm["api_key"], model_name=mdl_nm, base_url=llm["api_base"]
        )
        try:
            with open(
                os.path.join(get_project_base_directory(), "web/src/assets/yay.jpg"),
                "rb",
            ) as f:
                m, tc = mdl.describe(f.read())
                if not m and not tc:
                    raise Exception(m)
        except Exception as e:
            msg += f"\nFail to access model({mdl_nm})." + str(e)
    elif llm["model_type"] == LLMType.TTS:
        mdl = TTSModel[factory](
            key=llm["api_key"], model_name=mdl_nm, base_url=llm["api_base"]
        )
        try:
            for resp in mdl.tts("Hello~ Ragflower!"):
                pass
        except RuntimeError as e:
            msg += f"\nFail to access model({mdl_nm})." + str(e)
    else:
        # TODO: check other type of models
        pass

    if msg:
        return get_data_error_result(message=msg)

    # 更新或创建租户的LLM配置
    if not TenantLLMService.filter_update(
        [
            TenantLLM.tenant_id == current_user.id,
            TenantLLM.llm_factory == factory,
            TenantLLM.llm_name == llm["llm_name"],
        ],
        llm,
    ):
        TenantLLMService.save(**llm)

    return get_json_result(data=True)


@manager.route("/delete_llm", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory", "llm_name")
def delete_llm():
    """删除指定的LLM配置

    请求体参数:
        llm_factory: LLM工厂名称
        llm_name: LLM模型名称

    返回:
        成功返回True
    """
    req = request.json
    TenantLLMService.filter_delete(
        [
            TenantLLM.tenant_id == current_user.id,
            TenantLLM.llm_factory == req["llm_factory"],
            TenantLLM.llm_name == req["llm_name"],
        ]
    )
    return get_json_result(data=True)


@manager.route("/delete_factory", methods=["POST"])  # noqa: F821
@login_required
@validate_request("llm_factory")
def delete_factory():
    """删除指定工厂的所有LLM配置

    请求体参数:
        llm_factory: LLM工厂名称

    返回:
        成功返回True
    """
    req = request.json
    TenantLLMService.filter_delete(
        [
            TenantLLM.tenant_id == current_user.id,
            TenantLLM.llm_factory == req["llm_factory"],
        ]
    )
    return get_json_result(data=True)


@manager.route("/my_llms", methods=["GET"])  # noqa: F821
@login_required
def my_llms():
    """获取当前用户的所有LLM配置

    返回:
        JSON响应，包含按工厂分组的LLM配置列表，
        每个LLM包含类型、名称和已使用的token数
    """
    try:
        res = {}
        for o in TenantLLMService.get_my_llms(current_user.id):
            if o["llm_factory"] not in res:
                res[o["llm_factory"]] = {"tags": o["tags"], "llm": []}
            res[o["llm_factory"]]["llm"].append(
                {
                    "type": o["model_type"],
                    "name": o["llm_name"],
                    "used_token": o["used_tokens"],
                }
            )
        return get_json_result(data=res)
    except Exception as e:
        return server_error_response(e)


@manager.route("/list", methods=["GET"])  # noqa: F821
@login_required
def list_app():
    """获取所有可用的LLM模型列表

    URL参数:
        model_type: 可选，筛选指定类型的模型

    返回:
        JSON响应，包含按工厂分组的模型列表，
        每个模型包含名称、类型和是否可用等信息
    """
    # 自部署的模型列表
    self_deployed = [
        "Youdao",
        "FastEmbed",
        "BAAI",
        "Ollama",
        "Xinference",
        "LocalAI",
        "LM-Studio",
        "GPUStack",
    ]
    # 轻量级模型列表
    weighted = ["Youdao", "FastEmbed", "BAAI"] if settings.LIGHTEN != 0 else []
    model_type = request.args.get("model_type")

    try:
        # 获取当前用户配置的所有LLM
        objs = TenantLLMService.query(tenant_id=current_user.id)
        facts = set([o.to_dict()["llm_factory"] for o in objs if o.api_key])

        # 获取所有有效的LLM模型
        llms = LLMService.get_all()
        llms = [
            m.to_dict()
            for m in llms
            if m.status == StatusEnum.VALID.value and m.fid not in weighted
        ]

        # 标记模型是否可用
        for m in llms:
            m["available"] = (
                m["fid"] in facts
                or m["llm_name"].lower() == "flag-embedding"
                or m["fid"] in self_deployed
            )

        llm_set = set([m["llm_name"] + "@" + m["fid"] for m in llms])
        for o in objs:
            if not o.api_key:
                continue
            if o.llm_name + "@" + o.llm_factory in llm_set:
                continue
            llms.append(
                {
                    "llm_name": o.llm_name,
                    "model_type": o.model_type,
                    "fid": o.llm_factory,
                    "available": True,
                }
            )

        res = {}
        for m in llms:
            if model_type and m["model_type"].find(model_type) < 0:
                continue
            if m["fid"] not in res:
                res[m["fid"]] = []
            res[m["fid"]].append(m)

        return get_json_result(data=res)
    except Exception as e:
        return server_error_response(e)
