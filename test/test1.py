"""

仅提供角色定义和用户问题，不注入任何 Schema 信息。
无 Schema 信息时 LLM 生成 SQL 的准确性边界。

运行方式:
    uv run python test1.py
"""

import langchain
import os

from click import prompt
from dotenv import load_dotenv
import re

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()


def generate_sql(query: str) -> str:
    # call openai llm to generate sql
    llm = ChatOpenAI(
        api_key=os.environ.get("API_KEY"),
        base_url=os.environ.get("BASE_URL"),
        model=os.environ.get("LLM_MODEL"),
    )


    prompt = ChatPromptTemplate.from_messages([
        ("system","请根据用户提问的自然语言查询生成对应的 SQL 语句，要求：请使用标准的 SQL 语法，并直接输出SQL语句不做解释，并确保生成的 SQL 语句是正确的"),
        ("human","{query}")
    ])


    chain = prompt | llm | StrOutputParser()
    result = chain.invoke(input={"query": query})


    print("原始输出:")
    print(result)
    print("==================================")
    print("提取后的 SQL 语句:")
    # 提取 markdown 代码块中的 sql（如果有的话），并去除首尾空白
    # 注意：图片中此处有些模糊，修正为了匹配 ```sql 和 ``` 的正则
    sql = re.sub(r"```sql|```", "", result).strip()
    print(sql)
    return sql


if __name__ == "__main__":
    query = "欧洲市场最近三个月的销售额是多少？"
    print("用户问题:")
    print(query)
    print("==================================")
    print("生成的 SQL 语句:")
    print(generate_sql(query))