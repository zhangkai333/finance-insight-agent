from __future__ import annotations
import argparse
from finance_insight.llm import build_llm_client

def main():
    parser=argparse.ArgumentParser(description="用环境变量 DEEPSEEK_API_KEY 做一次可选 DeepSeek API 冒烟测试")
    parser.add_argument("--message",default="请只回复OK")
    args=parser.parse_args()
    client=build_llm_client()
    result=client.chat([{"role":"user","content":args.message}])
    print({"model":result.model,"content":result.content,"usage":result.usage,"fallback_used":result.fallback_used})
if __name__=="__main__": main()
