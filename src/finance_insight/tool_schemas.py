TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "financial_query",
            "description": "按公司、年度、指标查询已入库财务事实",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_codes": {"type": "array", "items": {"type": "string"}},
                    "years": {"type": "array", "items": {"type": "integer"}},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["stock_codes", "years", "metrics"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "annual_report_search",
            "description": "检索年报原文并返回页码引用",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string"},
                    "year": {"type": "integer"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["stock_code", "year", "query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "financial_analysis",
            "description": "对查询结果计算同比、CAGR并检测异常",
            "parameters": {
                "type": "object",
                "properties": {"detect_anomalies": {"type": "boolean"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chart_generation",
            "description": "将财务时间序列生成趋势图",
            "parameters": {
                "type": "object",
                "properties": {"chart_type": {"type": "string", "enum": ["line"]}},
                "additionalProperties": False,
            },
        },
    },
]
