#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
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

import importlib

from .akshare import AkShare, AkShareParam
from .answer import Answer, AnswerParam
from .arxiv import ArXiv, ArXivParam
from .baidu import Baidu, BaiduParam
from .baidufanyi import BaiduFanyi, BaiduFanyiParam
from .begin import Begin, BeginParam
from .bing import Bing, BingParam
from .categorize import Categorize, CategorizeParam
from .concentrator import Concentrator, ConcentratorParam
from .crawler import Crawler, CrawlerParam
from .deepl import DeepL, DeepLParam
from .duckduckgo import DuckDuckGo, DuckDuckGoParam
from .email import Email, EmailParam
from .exesql import ExeSQL, ExeSQLParam
from .generate import Generate, GenerateParam
from .github import GitHub, GitHubParam
from .google import Google, GoogleParam
from .googlescholar import GoogleScholar, GoogleScholarParam
from .invoke import Invoke, InvokeParam
from .iteration import Iteration, IterationParam
from .iterationitem import IterationItem, IterationItemParam
from .jin10 import Jin10, Jin10Param
from .keyword import KeywordExtract, KeywordExtractParam
from .message import Message, MessageParam
from .pubmed import PubMed, PubMedParam
from .qweather import QWeather, QWeatherParam
from .relevant import Relevant, RelevantParam
from .retrieval import Retrieval, RetrievalParam
from .rewrite import RewriteQuestion, RewriteQuestionParam
from .switch import Switch, SwitchParam
from .template import Template, TemplateParam
from .tushare import TuShare, TuShareParam
from .wencai import WenCai, WenCaiParam
from .wikipedia import Wikipedia, WikipediaParam
from .yahoofinance import YahooFinance, YahooFinanceParam


def component_class(class_name):
    m = importlib.import_module("agent.component")
    c = getattr(m, class_name)
    return c


__all__ = [
    "Begin",
    "BeginParam",
    "Generate",
    "GenerateParam",
    "Retrieval",
    "RetrievalParam",
    "Answer",
    "AnswerParam",
    "Categorize",
    "CategorizeParam",
    "Switch",
    "SwitchParam",
    "Relevant",
    "RelevantParam",
    "Message",
    "MessageParam",
    "RewriteQuestion",
    "RewriteQuestionParam",
    "KeywordExtract",
    "KeywordExtractParam",
    "Concentrator",
    "ConcentratorParam",
    "Baidu",
    "BaiduParam",
    "DuckDuckGo",
    "DuckDuckGoParam",
    "Wikipedia",
    "WikipediaParam",
    "PubMed",
    "PubMedParam",
    "ArXiv",
    "ArXivParam",
    "Google",
    "GoogleParam",
    "Bing",
    "BingParam",
    "GoogleScholar",
    "GoogleScholarParam",
    "DeepL",
    "DeepLParam",
    "GitHub",
    "GitHubParam",
    "BaiduFanyi",
    "BaiduFanyiParam",
    "QWeather",
    "QWeatherParam",
    "ExeSQL",
    "ExeSQLParam",
    "YahooFinance",
    "YahooFinanceParam",
    "WenCai",
    "WenCaiParam",
    "Jin10",
    "Jin10Param",
    "TuShare",
    "TuShareParam",
    "AkShare",
    "AkShareParam",
    "Crawler",
    "CrawlerParam",
    "Invoke",
    "InvokeParam",
    "Iteration",
    "IterationParam",
    "IterationItem",
    "IterationItemParam",
    "Template",
    "TemplateParam",
    "Email",
    "EmailParam",
    "component_class",
]
