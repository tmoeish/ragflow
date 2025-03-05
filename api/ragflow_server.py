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

# 日志系统
import logging

# 操作系统接口
import os

# 信号处理 - 用于优雅关闭应用
import signal

# 系统功能访问
import sys

# 多线程支持
import threading

# 时间处理
import time

# 异常跟踪
import traceback

# 线程池执行器 - 用于异步任务处理
from concurrent.futures import ThreadPoolExecutor

# Werkzeug服务器 - 用于开发环境中运行Flask应用
from werkzeug.serving import run_simple

# 应用设置 - 全局设置和配置
# 通用工具库
from api import settings, utils

# Flask应用实例 - 主要的Web应用对象
from api.apps import app

# 数据库模型 - 初始化数据库表结构
from api.db.db_models import init_database_tables as init_web_db

# 数据初始化 - 用于初始化Web应用的基础数据
from api.db.init_data import init_web_data

# 运行时配置 - 管理应用运行时的配置项
from api.db.runtime_config import RuntimeConfig

# 文档服务 - 处理文档的更新和进度追踪
from api.db.services.document_service import DocumentService

# 工具函数 - 用于显示系统配置信息
from api.utils import show_configs

# 日志工具 - 初始化根日志器
from api.utils.log_utils import initRootLogger

# 版本控制 - 提供系统版本信息
from api.versions import get_ragflow_version

# RAG设置模块 - 用于加载和显示RAG相关配置
from rag.settings import print_rag_settings

# 初始化根日志器，设置日志文件名为'ragflow_server'
initRootLogger("ragflow_server")

# 停止事件 - 用于控制后台线程的生命周期
stop_event = threading.Event()


def update_progress():
    """后台线程函数：定期更新所有任务的进度

    该函数在后台线程中运行，每6秒调用一次DocumentService.update_progress()
    以更新所有正在进行的任务的进度状态。当收到停止信号时，线程会结束执行。
    """
    while not stop_event.is_set():  # 循环直到收到停止信号
        try:
            # 调用服务方法更新所有任务的进度
            DocumentService.update_progress()
            # 等待6秒或者直到收到停止信号
            stop_event.wait(6)
        except Exception:
            # 记录异常但不终止线程
            logging.exception("update_progress exception")


def signal_handler(sig, frame):
    """信号处理函数：处理中断信号，实现优雅关闭

    当接收到SIGINT或SIGTERM信号时，该函数会被调用，
    它会发出停止事件信号，等待后台线程完成当前工作，然后退出程序。

    Args:
        sig: 接收到的信号
        frame: 当前栈帧
    """
    logging.info("Received interrupt signal, shutting down...")
    # 设置停止事件，通知所有等待该事件的线程
    stop_event.set()
    # 等待1秒，给线程一些时间来完成工作
    time.sleep(1)
    # 正常退出程序
    sys.exit(0)


if __name__ == "__main__":
    # 打印RAGFlow的ASCII艺术标志
    logging.info(
        r"""
        ____   ___    ______ ______ __
       / __ \ /   |  / ____// ____// /____  _      __
      / /_/ // /| | / / __ / /_   / // __ \| | /| / /
     / _, _// ___ |/ /_/ // __/  / // /_/ /| |/ |/ /
    /_/ |_|/_/  |_|\____//_/    /_/ \____/ |__/|__/

    """
    )
    # 记录版本信息
    logging.info(f"RAGFlow version: {get_ragflow_version()}")
    # 记录项目根目录路径
    logging.info(f"project base: {utils.file_utils.get_project_base_directory()}")

    # 显示当前系统配置
    show_configs()
    # 初始化应用设置
    settings.init_settings()
    # 打印RAG系统相关设置
    print_rag_settings()

    # 初始化数据库 - 创建表结构
    init_web_db()
    # 初始化基础数据 - 填充必要的初始数据
    init_web_data()

    # 命令行参数解析
    import argparse

    parser = argparse.ArgumentParser()
    # 添加--version参数，用于显示版本信息
    parser.add_argument(
        "--version", default=False, help="RAGFlow version", action="store_true"
    )
    # 添加--debug参数，用于启用调试模式
    parser.add_argument(
        "--debug", default=False, help="debug mode", action="store_true"
    )
    args = parser.parse_args()

    # 如果指定了--version参数，显示版本后退出
    if args.version:
        print(get_ragflow_version())
        sys.exit(0)

    # 设置调试模式标志
    RuntimeConfig.DEBUG = args.debug
    if RuntimeConfig.DEBUG:
        logging.info("run on debug mode")

    # 初始化环境变量
    RuntimeConfig.init_env()
    # 初始化运行时配置
    RuntimeConfig.init_config(
        JOB_SERVER_HOST=settings.HOST_IP, HTTP_PORT=settings.HOST_PORT
    )

    # 注册信号处理函数 - 用于捕获Ctrl+C和终止信号
    signal.signal(signal.SIGINT, signal_handler)  # 处理SIGINT信号（Ctrl+C）
    signal.signal(signal.SIGTERM, signal_handler)  # 处理SIGTERM信号（终止）

    # 创建线程池，用于后台任务
    thread = ThreadPoolExecutor(max_workers=1)
    # 提交后台任务 - 定期更新任务进度
    thread.submit(update_progress)

    # 启动HTTP服务器
    try:
        logging.info("RAGFlow HTTP server start...")
        # 使用Werkzeug的run_simple启动开发服务器
        run_simple(
            hostname=settings.HOST_IP,  # 主机名/IP地址
            port=settings.HOST_PORT,  # 端口号
            application=app,  # Flask应用实例
            threaded=True,  # 启用多线程处理请求
            use_reloader=RuntimeConfig.DEBUG,  # 仅在调试模式下启用自动重载
            use_debugger=RuntimeConfig.DEBUG,  # 仅在调试模式下启用调试器
        )
    except Exception:
        # 发生异常时打印堆栈跟踪
        traceback.print_exc()
        # 设置停止事件，通知后台线程
        stop_event.set()
        # 等待1秒给线程完成工作的时间
        time.sleep(1)
        # 强制终止进程
        os.kill(os.getpid(), signal.SIGKILL)
